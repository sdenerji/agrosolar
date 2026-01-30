import streamlit as st
from supabase import create_client, Client
from datetime import datetime
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
def get_user_data(username):
    """Kullanıcı adından tüm bilgileri (session_id, role, id, password vb.) çeker."""
    supabase = get_supabase()
    try:
        # Tek sorguda her şeyi alalım
        res = supabase.table("users").select("*").eq("username", username).execute()
        if res.data and len(res.data) > 0:
            return res.data[0]
    except Exception as e:
        print(f"Kullanıcı Verisi Hatası: {e}")
    return None


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