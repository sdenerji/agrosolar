import streamlit as st
import time

# --- MODÜL IMPORTLARI ---
try:
    from auth_service import sign_up_user
except ImportError:
    def sign_up_user(u, e, p):
        return False, "Veritabanı modülü bulunamadı."

# --- SESSION MANAGER IMPORT ---
# IP adresini kaydetmek için gerekli
try:
    from session_manager import register_new_session_login
except ImportError:
    def register_new_session_login(uid):
        pass


# ---------------------------

def show_auth_pages(supabase):
    # --- 1. ADIM: Yönlendirme Bayrağı Kontrolü ---
    if st.session_state.get("signup_success_redirect"):
        st.session_state.auth_mode = "Giriş Yap"
        st.session_state.signup_success_redirect = False

    if "auth_mode" not in st.session_state:
        st.session_state.auth_mode = "Giriş Yap"

    # Radyo butonu widget'ı
    secim = st.radio("İşlem", ["Giriş Yap", "Kayıt Ol"], horizontal=True, label_visibility="collapsed", key="auth_mode")
    st.divider()

    # --- GİRİŞ YAP EKRANI ---
    if secim == "Giriş Yap":
        st.subheader("🔐 Üye Girişi")
        with st.form("login_form"):
            email_input = st.text_input("E-posta Adresi")
            p_input = st.text_input("Şifre", type="password")
            submit_btn = st.form_submit_button("Giriş Yap", type="primary")

            if submit_btn:
                try:
                    # 1. Supabase Auth ile Giriş Dene
                    auth_response = supabase.auth.sign_in_with_password({"email": email_input, "password": p_input})

                    if auth_response.user:
                        user_id = auth_response.user.id

                        # 2. KRİTİK: IP Adresini 'active_sessions' tablosuna kaydet
                        register_new_session_login(user_id)

                        # 3. KULLANICI DETAYLARINI ÇEK (Rol, Kullanıcı Adı)
                        # Bunu yapmazsak main.py yenilenene kadar rol "Free" kalabilir.
                        try:
                            user_data = supabase.table("users").select("role, username").eq("id", user_id).execute()
                            if user_data.data:
                                st.session_state.user_role = user_data.data[0].get("role", "Free")
                                st.session_state.username = user_data.data[0].get("username", "Kullanıcı")
                        except Exception as e:
                            print(f"Rol Çekme Hatası: {e}")
                            st.session_state.user_role = "Free"

                        # 4. Session State'i Güncelle
                        st.session_state.logged_in = True
                        st.session_state.user_id = user_id
                        st.session_state.user_email = auth_response.user.email

                        st.success(f"Hoşgeldiniz, {st.session_state.get('username', '')}!")
                        time.sleep(0.5)
                        st.rerun()

                except Exception as e:
                    err_msg = str(e)
                    if "Email not confirmed" in err_msg:
                        st.warning("⚠️ Lütfen önce e-posta adresinize gelen linke tıklayarak hesabınızı doğrulayın.")
                    elif "Invalid login credentials" in err_msg:
                        st.error("Hatalı E-posta veya Şifre!")
                    else:
                        st.error(f"Giriş Hatası: {err_msg}")

    # --- KAYIT OL EKRANI ---
    elif secim == "Kayıt Ol":
        st.subheader("🚀 Yeni Hesap")
        n_email = st.text_input("E-posta Adresi", key="reg_email")
        n_pass = st.text_input("Şifre Belirleyin", type="password", key="reg_pass")

        if st.button("Ücretsiz Üyeliği Başlat", type="primary", use_container_width=True):
            if not n_email or not n_pass:
                st.warning("Lütfen tüm alanları doldurun.")
            else:
                new_username = n_email.split("@")[0]
                basari, mesaj = sign_up_user(new_username, n_email, n_pass)

                if basari:
                    st.success(f"🎉 {mesaj}")
                    st.balloons()
                    st.info("📨 Doğrulama e-postası gönderildi. Lütfen kutunuzu kontrol edin.")

                    time.sleep(4)
                    st.session_state.signup_success_redirect = True
                    st.rerun()
                else:
                    if "rate limit" in mesaj.lower():
                        st.error("⚠️ Çok fazla deneme yapıldı. Lütfen 1 saat sonra tekrar deneyin.")
                    else:
                        st.error(f"Kayıt Başarısız: {mesaj}")