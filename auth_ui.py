import streamlit as st
import time
import sys
import hashlib

def make_hashes(password):
    """Şifreyi SHA-256 ile geri döndürülemez bir koda çevirir."""
    return hashlib.sha256(str.encode(password)).hexdigest()

def check_hashes(password, hashed_text):
    """Girilmiş şifre ile veritabanındaki kodu karşılaştırır."""
    if make_hashes(password) == hashed_text:
        return True
    return False

# --- GÜNCELLEME: Yeni Session Yöneticisi Entegrasyonu ---
try:
    # Yeni mimariye uygun fonksiyonu çağırıyoruz
    from session_manager import register_new_session_login
except ImportError:
    # Dosya henüz oluşmadıysa hata vermesin
    def register_new_session_login(username): pass


def show_auth_pages(supabase):
    if "auth_mode" not in st.session_state:
        st.session_state.auth_mode = "Giriş Yap"

    secim = st.radio("İşlem", ["Giriş Yap", "Kayıt Ol"], horizontal=True, label_visibility="collapsed", key="auth_mode")
    st.divider()

    if secim == "Giriş Yap":
        st.subheader("🔐 Üye Girişi")
        with st.form("login_form"):
            email_input = st.text_input("E-posta Adresi")
            p_input = st.text_input("Şifre", type="password")
            submit_btn = st.form_submit_button("Giriş Yap", type="primary")

            if submit_btn:
                try:
                    # 1. Supabase Auth ile Giriş (En Güvenli Yöntem)
                    auth_response = supabase.auth.sign_in_with_password({"email": email_input, "password": p_input})

                    if auth_response.user:
                        user = auth_response.user
                        st.success("Kimlik doğrulandı, yetkiler kontrol ediliyor...")

                        # 2. 'users' tablosundan rol ve ek bilgileri çek
                        db_res = supabase.table("users").select("*").eq("id", user.id).execute()

                        # --- DEBUG: Terminalden rolün ne geldiğini görmek için ---
                        print(f"DEBUG [Giriş]: Veritabanından gelen veri: {db_res.data}")
                        # -------------------------------------------------------

                        user_role = "Free"  # Varsayılan
                        username = email_input.split("@")[0]  # Varsayılan isim

                        if db_res.data and len(db_res.data) > 0:
                            user_data = db_res.data[0]
                            user_role = user_data.get("role", "Free")
                            username = user_data.get("username", username)

                        # --- KRİTİK ENTEGRASYON 1: Session State Kaydı ---
                        st.session_state.logged_in = True
                        st.session_state.user_role = user_role
                        st.session_state.username = username
                        st.session_state.user_email = user.email
                        st.session_state.user_id = user.id

                        # --- KRİTİK ENTEGRASYON 2: Tekil Oturum Kaydı (GÜNCELLENDİ) ---
                        # Yeni mimariye uygun, tek satırlık temiz kod.
                        # Supabase nesnesi göndermiyoruz, sadece username yeterli.
                        try:
                            register_new_session_login(username)
                            print(f"DEBUG: {username} için yeni oturum anahtarı oluşturuldu.")
                        except Exception as sess_err:
                            print(f"Oturum Kayıt Uyarısı: {sess_err}")
                        # -------------------------------------------------------------

                        st.toast(f"Hoş geldin, {username}! Yetki: {user_role}", icon="🎉")
                        time.sleep(1)
                        st.rerun()
                    else:
                        st.error("Giriş başarısız oldu. Lütfen bilgilerinizi kontrol edin.")

                except Exception as e:
                    # Hata yönetimi
                    err_msg = str(e)
                    if "Invalid login credentials" in err_msg:
                        st.error("Hatalı E-posta veya Şifre!")
                    elif "Email not confirmed" in err_msg:
                        st.warning("Lütfen önce e-posta adresinizi doğrulayın.")
                    else:
                        st.error(f"Giriş Hatası: {err_msg}")

    elif secim == "Kayıt Ol":
        st.subheader("🚀 Yeni Hesap")
        n_email = st.text_input("E-posta Adresi", key="reg_email")
        n_pass = st.text_input("Şifre Belirleyin", type="password", key="reg_pass")

        if st.button("Ücretsiz Üyeliği Başlat", type="primary", use_container_width=True):
            try:
                # 1. Auth Kullanıcısı Oluştur
                auth_res = supabase.auth.sign_up({"email": n_email, "password": n_pass})

                if auth_res.user:
                    user_id = auth_res.user.id

                    # 2. public.users Tablosuna Kayıt At
                    try:
                        supabase.table("users").insert({
                            "id": user_id,
                            "email": n_email,
                            "role": "Free",
                            "username": n_email.split("@")[0]
                        }).execute()
                    except Exception as db_err:
                        print(f"DB Kayıt Hatası: {db_err}")

                    st.success("Kayıt başarılı! Lütfen e-postanızı kontrol edip hesabınızı doğrulayın.")
                    st.info("Doğrulama sonrası 'Giriş Yap' sekmesinden sisteme girebilirsiniz.")

            except Exception as e:
                st.error(f"Kayıt İşlemi Başarısız: {e}")