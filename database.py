import streamlit as st
from supabase import create_client, Client
from datetime import datetime, date, timedelta
import hashlib


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


# --- 2. GÜVENLİK VE HASH İŞLEMLERİ ---
def make_hashes(password):
    """Şifreyi SHA-256 ile geri döndürülemez bir koda (hash) çevirir."""
    return hashlib.sha256(str.encode(password)).hexdigest()


def check_hashes(password, hashed_text):
    """Girilmiş şifreyi hashleyip veritabanındaki kodla karşılaştırır."""
    if make_hashes(password) == hashed_text:
        return True
    return False


# --- [YENİ] KAYIT FONKSİYONU (UUID HATASINI ÇÖZEN KISIM) ---
def sign_up_user(username, email, password):
    """
    Kullanıcıyı hem Auth servisine hem de Public tabloya kaydeder.
    """
    supabase = get_supabase()

    # 1. Önce Kullanıcı Adı Kontrolü (Public tabloda var mı?)
    existing = supabase.table("users").select("username").eq("username", username).execute()
    if existing.data:
        return False, "Bu kullanıcı adı zaten kullanımda."

    try:
        # 2. Supabase Auth ile Kullanıcı Oluştur (UUID Almak İçin)
        auth_response = supabase.auth.sign_up({
            "email": email,
            "password": password,
            "options": {"data": {"username": username}}  # İsterseniz ekstra veri de ekleyebilirsiniz
        })

        # 3. Auth başarılıysa, dönen ID ile Tabloya yaz
        if auth_response.user and auth_response.user.id:
            user_uid = auth_response.user.id  # <--- KRİTİK ID BURADA ALINIYOR

            # Şifreyi hashleyip saklayalım (Manuel giriş desteği için)
            hashed_pw = make_hashes(password)

            data = {
                "id": user_uid,  # ARTIK NULL DEĞİL!
                "username": username,
                "email": email,
                "password": hashed_pw,
                "role": "Free",  # Varsayılan Paket
                "created_at": datetime.now().isoformat()
            }

            # Tabloya ekle
            supabase.table("users").insert(data).execute()
            return True, "Kayıt başarıyla oluşturuldu! Giriş yapabilirsiniz."

        else:
            return False, "Kimlik doğrulama servisi yanıt vermedi."

    except Exception as e:
        # Hata mesajını sadeleştir
        err_msg = str(e)
        if "User already registered" in err_msg:
            return False, "Bu e-posta adresiyle zaten bir kayıt mevcut."
        return False, f"Kayıt Hatası: {err_msg}"


def verify_user_login(username, password):
    """
    Kullanıcı adı ve şifreyi doğrular.
    """
    user = get_user_data(username)

    if user:
        stored_password_hash = user.get("password")
        if not stored_password_hash:
            return None  # Şifre yoksa (Google login vb.) manuel giremez

        if check_hashes(password, stored_password_hash):
            return user
    return None


# --- 3. KULLANICI & SESSION İŞLEMLERİ ---
def get_user_data(username):
    """
    Kullanıcı verisini çekerken, abonelik süresi dolmuş mu kontrol eder.
    """
    supabase = get_supabase()
    try:
        res = supabase.table("users").select("*").eq("username", username).execute()
        if res.data and len(res.data) > 0:
            user = res.data[0]

            # --- AKILLI ABONELİK KONTROLÜ ---
            if user.get("next_role") and user.get("subscription_end_date"):
                end_date_str = user["subscription_end_date"]
                try:
                    # Tarih formatı bazen tam ISO gelir, sadece tarihi alalım
                    end_date = datetime.fromisoformat(end_date_str.replace('Z', '')).date()
                except:
                    # Format hatası olursa düzeltmeye çalış veya geç
                    end_date = datetime.strptime(end_date_str[:10], "%Y-%m-%d").date()

                if date.today() >= end_date:
                    target_role = user["next_role"]
                    new_end_date = None

                    if target_role in ["Pro", "Ultra"]:
                        new_end_date = (date.today() + timedelta(days=30)).isoformat()

                    supabase.table("users").update({
                        "role": target_role,
                        "next_role": None,
                        "subscription_end_date": new_end_date
                    }).eq("username", username).execute()

                    user["role"] = target_role
                    user["next_role"] = None
                    user["subscription_end_date"] = new_end_date
            # ----------------------------------------
            return user
    except Exception as e:
        print(f"Kullanıcı Verisi Hatası: {e}")
    return None


def schedule_role_change(username, target_role):
    """Paket değişikliği veya talep oluşturma."""
    supabase = get_supabase()
    user = get_user_data(username)

    if not user: return False, "Kullanıcı bulunamadı."

    current_role = user.get("role", "Free")
    current_end_date = user.get("subscription_end_date")

    try:
        # SENARYO 1: Free -> Hemen Yükselt
        if current_role == "Free" or not current_end_date:
            new_end_date = None
            if target_role in ["Pro", "Ultra"]:
                new_end_date = (date.today() + timedelta(days=30)).isoformat()

            supabase.table("users").update({
                "role": target_role,
                "subscription_end_date": new_end_date,
                "next_role": None
            }).eq("username", username).execute()

            return True, f"Tebrikler! Aboneliğiniz anında **{target_role}** olarak başlatıldı."

        # SENARYO 2: Zaten paralı -> Sıraya al
        else:
            supabase.table("users").update({
                "next_role": target_role
            }).eq("username", username).execute()

            # Tarihi kullanıcıya göstermek için al
            end_date_display = current_end_date[:10] if current_end_date else "Dönem Sonu"
            return True, f"Talep alındı. **{end_date_display}** tarihinde paketiniz **{target_role}** olacak."

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
    """Kullanıcının aktif session ID'sini günceller (Tek cihaz kontrolü için)."""
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
        pass
    return {"mw": 0, "total": 0.01}


def change_password(username, old_plain_password, new_plain_password):
    """Kullanıcının eski şifresini doğrular ve yenisiyle değiştirir."""
    user = get_user_data(username)
    if not user:
        return False, "Kullanıcı bulunamadı."

    stored_hash = user.get("password")
    if not check_hashes(old_plain_password, stored_hash):
        return False, "Mevcut şifrenizi yanlış girdiniz."

    new_hash = make_hashes(new_plain_password)
    supabase = get_supabase()
    try:
        supabase.table("users").update({"password": new_hash}).eq("username", username).execute()
        return True, "Şifreniz başarıyla güncellendi!"
    except Exception as e:
        return False, f"Güncelleme Hatası: {e}"