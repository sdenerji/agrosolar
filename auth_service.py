# Kayıt, giriş, şifreleme ve şifre değiştirme işlemleri.
import hashlib
from datetime import datetime
import traceback
from db_base import get_supabase


# --- YARDIMCI: HASH ---
def make_hashes(password):
    """Şifreyi SHA-256 ile hashler."""
    return hashlib.sha256(str.encode(password)).hexdigest()


def check_hashes(password, hashed_text):
    """Girilmiş şifreyi doğrular."""
    if make_hashes(password) == hashed_text:
        return True
    return False


# --- KAYIT İŞLEMLERİ ---
def sign_up_user(username, email, password):
    supabase = get_supabase()

    # 1. Kullanıcı adı kontrolü
    existing = supabase.table("users").select("username").eq("username", username).execute()
    if existing.data:
        return False, "Bu kullanıcı adı zaten kullanımda."

    try:
        # 2. Auth Kaydı (Supabase Auth)
        auth_response = supabase.auth.sign_up({
            "email": email,
            "password": password,
            "options": {"data": {"username": username}}
        })

        if auth_response.user and auth_response.user.id:
            user_uid = auth_response.user.id
            hashed_pw = make_hashes(password)

            data = {
                "id": user_uid,
                "username": username,
                "email": email,
                "password": hashed_pw,
                "role": "Free",
                "created_at": datetime.now().isoformat()
            }

            # 3. Tabloya Kayıt (Public Users Tablosu)
            supabase.table("users").insert(data).execute()
            return True, "Kayıt başarıyla oluşturuldu! Giriş yapabilirsiniz."
        else:
            return False, "Kimlik doğrulama servisi yanıt vermedi."

    except Exception as e:
        print("\n" + "=" * 50)
        print("🔴 KAYIT HATASI DETAYI:")
        print(traceback.format_exc())
        print("=" * 50 + "\n")

        err_msg = str(e)
        if "User already registered" in err_msg:
            return False, "Bu e-posta adresiyle zaten bir kayıt mevcut."
        return False, f"Sistemsel Hata: {err_msg}"


# --- GİRİŞ DOĞRULAMA (DÜZELTİLDİ) ---
def verify_user_login(username, password):
    """
    Kullanıcı adı ve şifreyi doğrular.
    Başarılı ise user objesini döndürür.
    """
    supabase = get_supabase()
    # Users tablosundan kullanıcıyı bul
    res = supabase.table("users").select("*").eq("username", username).execute()

    if res.data:
        user = res.data[0]
        stored_hash = user.get("password")  # DB'deki şifre

        # HATA DÜZELTİLDİ: 'stored_password_hash' yerine 'stored_hash' kullanıldı.
        if not stored_hash:
            return None

        if check_hashes(password, stored_hash):
            return user  # Şifre doğru, kullanıcıyı döndür

    return None


# --- ŞİFRE DEĞİŞTİRME ---
def change_password(username, old_plain_password, new_plain_password):
    supabase = get_supabase()
    # Kullanıcıyı doğrula
    res = supabase.table("users").select("password").eq("username", username).execute()
    if not res.data:
        return False, "Kullanıcı bulunamadı."

    stored_hash = res.data[0]["password"]
    if not check_hashes(old_plain_password, stored_hash):
        return False, "Mevcut şifrenizi yanlış girdiniz."

    new_hash = make_hashes(new_plain_password)
    try:
        supabase.table("users").update({"password": new_hash}).eq("username", username).execute()
        return True, "Şifreniz başarıyla güncellendi!"
    except Exception as e:
        return False, f"Güncelleme Hatası: {e}"