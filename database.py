import streamlit as st
from supabase import create_client, Client
from datetime import datetime, date, timedelta
import hashlib  # --- YENİ: Şifreleme için gerekli kütüphane


# --- 1. BAĞLANTI YÖNETİMİ ---
@st.cache_resource
def get_supabase() -> Client:
    """Supabase bağlantısını kurar ve önbelleğe alır."""
    try:
        if "supabase" not in st.secrets:
            st.error("❌ secrets.toml içinde [supabase] ayarları bulunamadı!")
            st.stop()

        url = st.secrets["supabase"]["url"]
        key = st.secrets["supabase"]["key"]
        return create_client(url, key)
    except Exception as e:
        st.error(f"⚠️ Veritabanı Bağlantı Hatası: {e}")
        st.stop()
    return None


# --- 2. GÜVENLİK VE HASH İŞLEMLERİ (YENİ EKLENDİ) ---
def make_hashes(password):
    """Şifreyi SHA-256 ile geri döndürülemez bir koda (hash) çevirir."""
    return hashlib.sha256(str.encode(password)).hexdigest()


def check_hashes(password, hashed_text):
    """Girilmiş şifreyi hashleyip veritabanındaki kodla karşılaştırır."""
    if make_hashes(password) == hashed_text:
        return True
    return False


def verify_user_login(username, password):
    """
    Kullanıcı adı ve şifreyi doğrular.
    Başarılıysa kullanıcı verisini döner, başarısızsa None döner.
    """
    user = get_user_data(username)

    if user:
        stored_password_hash = user.get("password")

        # Eğer veritabanında şifre sütunu boşsa (sadece Google ile girenler için)
        if not stored_password_hash:
            return None

        # Şifre kontrolü
        if check_hashes(password, stored_password_hash):
            return user

    return None


# --- 3. KULLANICI & SESSION İŞLEMLERİ ---
# --- 1. FONKSİYON: GİRİŞ SIRASINDAKİ OTOMATİK KONTROL (Lazy Check) ---
def get_user_data(username):
    """
    Kullanıcı verisini çekerken, abonelik süresi dolmuş mu kontrol eder
    ve yeni paketin tarihini (Boş veya +1 Ay) ayarlar.
    """
    supabase = get_supabase()
    try:
        res = supabase.table("users").select("*").eq("username", username).execute()
        if res.data and len(res.data) > 0:
            user = res.data[0]

            # --- AKILLI KONTROL MEKANİZMASI ---
            # Eğer planlanmış bir değişiklik varsa VE (bugün >= bitiş tarihi) ise:
            if user.get("next_role") and user.get("subscription_end_date"):
                end_date_str = user["subscription_end_date"]
                # String tarihi objeye çevir
                end_date = datetime.strptime(end_date_str, "%Y-%m-%d").date()

                if date.today() >= end_date:
                    target_role = user["next_role"]
                    new_end_date = None  # Varsayılan: Free ise tarih yok (NULL)

                    # EĞER YENİ GEÇİLEN PAKET ÜCRETLİ İSE:
                    # Yeni bir 30 günlük dönem başlat (Oto-Yenileme Mantığı)
                    if target_role in ["Pro", "Ultra"]:
                        new_end_date = (date.today() + timedelta(days=30)).isoformat()

                    # Veritabanını Güncelle
                    supabase.table("users").update({
                        "role": target_role,
                        "next_role": None,  # Talebi temizle
                        "subscription_end_date": new_end_date  # Yeni tarihi (veya NULL) yaz
                    }).eq("username", username).execute()

                    # Kullanıcıya döneceğimiz veriyi de canlı güncelle
                    user["role"] = target_role
                    user["next_role"] = None
                    user["subscription_end_date"] = new_end_date
            # ----------------------------------------

            return user
    except Exception as e:
        print(f"Kullanıcı Verisi Hatası: {e}")
    return None


# --- 2. FONKSİYON: TALEP OLUŞTURMA VEYA HEMEN GEÇİŞ ---
def schedule_role_change(username, target_role):
    """
    Kullanıcı Free ise -> HEMEN geçir ve 30 gün ver.
    Kullanıcı Ücretli ise -> Gelecek planı (next_role) olarak kaydet.
    """
    supabase = get_supabase()
    user = get_user_data(username)  # Mevcut durumu öğren

    if not user: return False, "Kullanıcı bulunamadı."

    current_role = user.get("role", "Free")
    current_end_date = user.get("subscription_end_date")

    try:
        # SENARYO 1: Şu an Free ise veya süresi zaten bitmişse -> HEMEN YÜKSELT
        if current_role == "Free" or not current_end_date:

            new_end_date = None
            # Ücretli bir pakete geçiyorsa 30 gün ekle
            if target_role in ["Pro", "Ultra"]:
                new_end_date = (date.today() + timedelta(days=30)).isoformat()

            supabase.table("users").update({
                "role": target_role,
                "subscription_end_date": new_end_date,
                "next_role": None  # Varsa eski planı sil
            }).eq("username", username).execute()

            return True, f"Tebrikler! Aboneliğiniz anında **{target_role}** olarak başlatıldı."

        # SENARYO 2: Zaten ücretli bir paketteyse -> SIRAYA AL (Dönem Sonu)
        else:
            supabase.table("users").update({
                "next_role": target_role
            }).eq("username", username).execute()

            end_date_fmt = user["subscription_end_date"]
            return True, f"Talep alındı. **{end_date_fmt}** tarihinde paketiniz **{target_role}** olarak güncellenecek."

    except Exception as e:
        return False, f"İşlem Hatası: {e}"

def cancel_pending_change(username):
    """Bekleyen paket değişikliği talebini iptal eder."""
    supabase = get_supabase()
    try:
        supabase.table("users").update({"next_role": None}).eq("username", username).execute()
        return True
    except:
        return False


def update_user_session_id(username, new_session_id):
    """Kullanıcının aktif session ID'sini günceller."""
    supabase = get_supabase()
    try:
        supabase.table("users").update({"current_session_id": new_session_id}).eq("username", username).execute()
        return True
    except Exception as e:
        print(f"Session Güncelleme Hatası: {e}")
        return False


# --- 4. ANALİZ KAYIT İŞLEMLERİ ---
def save_analysis_to_history(user_id, lat, lon, rakim, egim, baki, kw, kwh, roi):
    supabase = get_supabase()
    data = {
        "user_id": user_id,
        "latitude": float(lat),
        "longitude": float(lon),
        "rakim": int(rakim),
        "egim": float(egim),
        "baki": str(baki),
        "kw_power": float(kw),
        "annual_kwh": float(kwh),
        "roi": float(roi),
        "created_at": datetime.now().isoformat()
    }
    try:
        supabase.table("analysis_history").insert(data).execute()
        return True
    except Exception as e:
        print(f"🔴 DB Kayıt Hatası: {e}")
        return False


# --- 5. ŞEBEKE VERİLERİ ---
def get_substation_data(substation_name):
    supabase = get_supabase()
    try:
        res = supabase.table("substation_capacities") \
            .select("available_capacity_mw, total_capacity_mw") \
            .eq("substation_name", substation_name) \
            .execute()
        if res.data:
            return {
                "mw": res.data[0]["available_capacity_mw"],
                "total": res.data[0]["total_capacity_mw"]
            }
    except Exception as e:
        pass  # Hata olursa varsayılan döner
    return {"mw": 0, "total": 0.01}


def change_password(username, old_plain_password, new_plain_password):
    """
    Kullanıcının eski şifresini doğrular ve yenisiyle değiştirir.
    Dönüş: (Başarılı_mı?, Mesaj)
    """
    # 1. Kullanıcıyı bul
    user = get_user_data(username)
    if not user:
        return False, "Kullanıcı bulunamadı."

    stored_hash = user.get("password")

    # 2. Eski şifre doğru mu kontrol et
    # (Not: check_hashes fonksiyonunu daha önce eklemiştik)
    if not check_hashes(old_plain_password, stored_hash):
        return False, "Mevcut şifrenizi yanlış girdiniz."

    # 3. Yeni şifreyi hashle
    new_hash = make_hashes(new_plain_password)

    # 4. Veritabanını güncelle
    supabase = get_supabase()
    try:
        supabase.table("users").update({"password": new_hash}).eq("username", username).execute()
        return True, "Şifreniz başarıyla güncellendi! Lütfen yeni şifrenizle tekrar giriş yapın."
    except Exception as e:
        return False, f"Güncelleme Hatası: {e}"