import streamlit as st
import streamlit.components.v1 as components  # iFrame için gerekli
import time

# --- MODÜL IMPORTLARI (Hata Yakalamalı ve Güvenli) ---
try:
    from auth_service import change_password
    from user_service import schedule_role_change, cancel_pending_change
    from paytr_utils import get_paytr_iframe_token
except ImportError:
    # Modüller hazır değilse dummy fonksiyonlar
    def change_password(u, c, n):
        return False, "Modül Bulunamadı"


    def schedule_role_change(u, r):
        return False, "Modül Bulunamadı"


    def cancel_pending_change(u):
        pass


    def get_paytr_iframe_token(i, e, a, r):
        return {"status": "error", "reason": "Modül Pasif"}


# --- ONAY PENCERESİ ---
@st.dialog("⚠️ Paket Değişikliği Onayı")
def confirm_downgrade(target_role, end_date_str):
    st.write(f"Mevcut paketinizden **{target_role}** paketine geçmek üzeresiniz.")
    if end_date_str:
        st.warning(
            f"ℹ️ Bu değişiklik, mevcut abonelik sürenizin dolacağı **{end_date_str}** tarihinde gerçekleşecektir.")

    st.write("Onaylıyor musunuz?")
    col1, col2 = st.columns(2)

    with col1:
        if st.button("Evet, Onaylıyorum", key="btn_confirm_down", type="primary"):
            # DEĞİŞİKLİK: Artık user_id gönderiyoruz
            user_id = st.session_state.get("user_id")
            success, msg = schedule_role_change(user_id, target_role)

            if success:
                st.success(msg)
                time.sleep(1)
                st.rerun()
            else:
                st.error(msg)
    with col2:
        if st.button("Vazgeç", key="btn_cancel_down"):
            st.rerun()


# --- ANA PROFİL FONKSİYONU ---
def show_profile_page():
    """Kullanıcı profilini, ödeme ve abonelik işlemlerini yönetir."""

    # 1. Güvenlik Kontrolü
    user_id = st.session_state.get("user_id")
    username = st.session_state.get("username", "Misafir")
    email = st.session_state.get("user_email", "E-posta Yok")
    user_role = st.session_state.get("user_role", "Free")
    logged_in = st.session_state.get("logged_in", False)

    if logged_in and user_id is None:
        st.warning("⚠️ Kullanıcı verileri yüklenemedi. Lütfen tekrar giriş yapınız.")
        st.stop()

    st.title("👤 Hesap ve Abonelik Yönetimi")

    # --- KULLANICI BİLGİSİ ---
    if logged_in:
        u_id_str = str(user_id) if user_id else "0"
        display_id = f"{u_id_str[:8]}..." if len(u_id_str) > 8 else u_id_str
        st.markdown(f"### Hoş Geldiniz, **{username}**")
        st.info(f"📧 **E-Posta:** {email}  |  🆔 **Müşteri No:** #{display_id}")
    else:
        st.markdown(f"### Hoş Geldiniz, **Misafir Kullanıcı**")
        return

    st.divider()

    # --- ÖDEME SONUCU MESAJLARI ---
    query_params = st.query_params
    if "payment_status" in query_params:
        status = query_params["payment_status"]
        if status == "success":
            st.success("✅ Ödeme Başarılı! Aboneliğiniz güncellendi.")
        elif status == "fail":
            st.error("❌ Ödeme işlemi başarısız oldu veya iptal edildi.")

    # --- PAKET DURUMU ÇEKME ---
    # Bu veriyi session'da tutmak yerine user_service'den taze çekmek daha iyidir,
    # ama şimdilik session'dan veya main.py'deki veriden gelene bakıyoruz.
    # user_service güncellemesi yaptığımız için burada bir sonraki yenilemede veri düzelir.

    # next_role kontrolü için basit bir sözlük sorgusu (Veri main.py'den dolmalı)
    # Eğer çok kritikse burada user_service.get_user_data(user_id) çağrılabilir.

    # Şimdilik UI akışını bozmuyoruz.

    col1, col2, col3 = st.columns(3)

    # --- 1. FREE PAKET ---
    with col1:
        st.markdown("""
        <div style="border: 1px solid #ddd; padding: 20px; border-radius: 10px; text-align: center; height: 420px;">
            <h4>TIER 1: STANDART</h4>
            <h2>0 ₺ <small>/ Ay</small></h2>
            <hr>
            <ul style="text-align: left; list-style-type: '✅ '; font-size:14px;">
                <li>Temel Eğim ve Bakı Analizi</li>
                <li>OpenStreetMap Altlığı</li>
                <li>Günlük 10 Analiz Hakkı</li>
            </ul>
        </div>
        """, unsafe_allow_html=True)

        if user_role == "Free":
            st.button("Mevcut Paketiniz", disabled=True, key="p1", use_container_width=True)
        else:
            if st.button("Standart'a Dön", key="p1_back", use_container_width=True):
                # Downgrade için tarih bilgisi lazım, veritabanından çekmek en doğrusu
                from user_service import get_user_data
                u_data = get_user_data(user_id)
                sub_end = u_data.get("subscription_end_date") if u_data else None
                confirm_downgrade("Free", sub_end)

    # --- 2. PRO PAKET ---
    with col2:
        st.markdown("""
        <div style="border: 2px solid #28a745; padding: 20px; border-radius: 10px; text-align: center; background-color: #f8fff9; height: 420px;">
            <h4 style="color: #28a745;">TIER 2: PROFESSIONAL</h4>
            <h2>49 ₺ <small>/ Ay</small></h2>
            <hr>
            <ul style="text-align: left; list-style-type: '✅ '; font-size:14px;">
                <li><b>Kapsamlı PDF Raporlama</b></li>
                <li><b>Ufuk Gölge Analizi</b></li>
                <li>Analiz Geçmişi Kaydı</li>
                <li>Uydu Görüntüsü Katmanı</li>
                <li>Günlük 50 Analiz Hakkı</li>
            </ul>
        </div>
        """, unsafe_allow_html=True)

        if user_role == "Pro":
            st.button("Mevcut Paketiniz", disabled=True, key="p2", use_container_width=True)
        else:
            if st.button("🚀 Hemen Yükselt (49₺)", key="p2_up", type="primary", use_container_width=True):
                with st.spinner("Güvenli Ödeme Sayfası Hazırlanıyor..."):
                    token_res = get_paytr_iframe_token(user_id, email, 49, "Pro")
                    if token_res["status"] == "success":
                        st.session_state.paytr_iframe_token = token_res["token"]
                        st.session_state.show_payment_frame = True
                        st.rerun()
                    else:
                        st.error(f"Ödeme Hatası: {token_res.get('reason', 'Bilinmeyen Hata')}")

    # --- 3. ULTRA PAKET ---
    with col3:
        st.markdown("""
        <div style="border: 1px solid #31333F; padding: 20px; border-radius: 10px; text-align: center; background-color: #31333F; color: white; height: 420px;">
            <h4 style="color: #ffd700;">TIER 3: ULTRA</h4>
            <h2>149 ₺ <small>/ Ay</small></h2>
            <hr>
            <ul style="text-align: left; list-style-type: '⭐ '; font-size:14px;">
                <li><b>Ulusal İletim Şebekesi (TEİAŞ)</b></li>
                <li><b>Kapasite Sorgulama</b></li>
                <li>25 Yıllık Finansal Projeksiyon</li>
                <li>KMZ / GeoJSON Veri Çıktısı</li>
                <li>Sınırsız Analiz Hakkı</li>
            </ul>
        </div>
        """, unsafe_allow_html=True)

        if user_role == "Ultra":
            st.button("Mevcut Paketiniz", disabled=True, key="p3", use_container_width=True)
        else:
            if st.button("💎 Ultra'ya Geç (149₺)", key="p3_up", use_container_width=True):
                with st.spinner("Güvenli Ödeme Sayfası Hazırlanıyor..."):
                    token_res = get_paytr_iframe_token(user_id, email, 149, "Ultra")
                    if token_res["status"] == "success":
                        st.session_state.paytr_iframe_token = token_res["token"]
                        st.session_state.show_payment_frame = True
                        st.rerun()
                    else:
                        st.error(f"Ödeme Hatası: {token_res.get('reason', 'Bilinmeyen Hata')}")

    # --- ÖDEME EKRANI (IFRAME) ---
    if st.session_state.get("show_payment_frame", False) and "paytr_iframe_token" in st.session_state:
        st.divider()
        st.markdown("### 💳 Güvenli Ödeme Ekranı")
        if st.button("❌ Ödeme Ekranını Kapat", type="secondary"):
            st.session_state.show_payment_frame = False
            if "paytr_iframe_token" in st.session_state: del st.session_state.paytr_iframe_token
            st.rerun()

        iframe_url = f"https://www.paytr.com/odeme/guvenli/{st.session_state.paytr_iframe_token}"
        components.iframe(iframe_url, height=700, scrolling=True)

    st.divider()

    # --- KONTROL BUTONLARI ---
    c1, c2 = st.columns([1, 2])
    with c1:
        if st.button("← Analiz Ekranına Dön", use_container_width=True):
            st.session_state.page = 'analiz'
            st.rerun()
    with c2:
        with st.expander("🔐 Şifre Değiştir"):
            with st.form("password_change_form"):
                current_pass = st.text_input("Mevcut Şifre", type="password")
                new_pass = st.text_input("Yeni Şifre", type="password")
                confirm_pass = st.text_input("Yeni Şifre (Tekrar)", type="password")

                submit_btn = st.form_submit_button("Güncelle", type="primary")
                if submit_btn:
                    if new_pass != confirm_pass:
                        st.error("Yeni şifreler birbiriyle uyuşmuyor!")
                    elif len(new_pass) < 6:
                        st.error("Yeni şifre en az 6 karakter olmalıdır.")
                    else:
                        # Şifre değiştirme hala username ile çalışıyor (auth servisi öyle)
                        # Eğer auth_service.py'yi ID'ye çevirmediysek bu kalabilir.
                        success, msg = change_password(username, current_pass, new_pass)
                        if success:
                            st.success(msg)
                        else:
                            st.error(msg)