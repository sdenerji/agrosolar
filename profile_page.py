import streamlit as st
import streamlit.components.v1 as components  # iFrame için gerekli
from database import change_password, schedule_role_change, cancel_pending_change
from paytr_utils import get_paytr_iframe_token  # <--- YENİ MODÜLÜ ÇAĞIRIYORUZ


# --- ONAY PENCERESİ (SADECE FREE'YE DÖNÜŞ İÇİN) ---
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
            success, msg = schedule_role_change(st.session_state.username, target_role)
            if success:
                st.success(msg)
                st.rerun()
            else:
                st.error(msg)
    with col2:
        if st.button("Vazgeç", key="btn_cancel_down"):
            st.rerun()


# --- ANA PROFİL FONKSİYONU ---
def show_profile_page():
    """Kullanıcı profilini, ödeme ve abonelik işlemlerini yönetir."""
    st.title("👤 Hesap ve Abonelik Yönetimi")

    # --- 1. KULLANICI BİLGİSİ ---
    if st.session_state.get("logged_in", False):
        email = st.session_state.get("user_email", "E-posta Yok")
        user_id = st.session_state.get("user_id", "0")

        # ID Gösterimi
        u_id_str = str(user_id)
        display_id = f"{u_id_str[:8]}..." if len(u_id_str) > 8 else u_id_str

        st.markdown(f"### Hoş Geldiniz, **{st.session_state.username}**")
        st.info(f"📧 **E-Posta:** {email}  |  🆔 **Müşteri No:** #{display_id}")
    else:
        st.markdown(f"### Hoş Geldiniz, **Misafir Kullanıcı**")
        st.caption("Lütfen işlem yapmak için giriş yapınız.")
        return  # Giriş yoksa aşağıyı gösterme

    st.divider()

    # --- ÖDEME SONUCU MESAJLARI (URL'den gelen) ---
    query_params = st.query_params
    if "payment_status" in query_params:
        status = query_params["payment_status"]
        if status == "success":
            st.success("✅ Ödeme Başarılı! Aboneliğiniz kısa süre içinde güncellenecektir.")
        elif status == "fail":
            st.error("❌ Ödeme işlemi başarısız oldu veya iptal edildi.")
        # Parametreyi temizle ki sürekli çıkmasın (Opsiyonel)

    # --- PAKET SEÇİM EKRANI ---
    st.markdown("### 🚀 AgroSolar Paketleri")

    # Mevcut Durum Kontrolü
    user_data = st.session_state.get("user_data_raw", {})
    sub_end = user_data.get("subscription_end_date", "Belirsiz")
    pending_role = user_data.get("next_role")

    if pending_role:
        st.warning(
            f"🕒 **Bilgi:** {sub_end} tarihinde hesabınız otomatik olarak **{pending_role}** paketine geçecektir.")
        if st.button("Bu Değişikliği İptal Et"):
            cancel_pending_change(st.session_state.username)
            st.success("Talebiniz iptal edildi.")
            st.rerun()
        st.divider()

    # Sütunlar
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

        if st.session_state.user_role == "Free":
            st.button("Mevcut Paketiniz", disabled=True, key="p1", use_container_width=True)
        else:
            # Downgrade işlemi -> Onay Penceresi (Dialog)
            if st.button("Standart'a Dön", key="p1_back", use_container_width=True):
                confirm_downgrade("Free", sub_end)

    # --- 2. PRO PAKET (PAYTR ENTEGRE) ---
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

        if st.session_state.user_role == "Pro":
            st.button("Mevcut Paketiniz", disabled=True, key="p2", use_container_width=True)
        else:
            # UPGRADE işlemi -> PayTR iFrame
            if st.button("🚀 Hemen Yükselt (49₺)", key="p2_up", type="primary", use_container_width=True):
                with st.spinner("Güvenli Ödeme Sayfası Hazırlanıyor..."):
                    token_res = get_paytr_iframe_token(
                        st.session_state.user_id,
                        st.session_state.get("user_email"),
                        49,
                        "Pro"
                    )

                    if token_res["status"] == "success":
                        st.session_state.paytr_iframe_token = token_res["token"]
                        st.session_state.show_payment_frame = True
                        st.rerun()
                    else:
                        st.error(f"Ödeme Hatası: {token_res['reason']}")

    # --- 3. ULTRA PAKET (PAYTR ENTEGRE) ---
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

        if st.session_state.user_role == "Ultra":
            st.button("Mevcut Paketiniz", disabled=True, key="p3", use_container_width=True)
        else:
            # UPGRADE işlemi -> PayTR iFrame
            if st.button("💎 Ultra'ya Geç (149₺)", key="p3_up", use_container_width=True):
                with st.spinner("Güvenli Ödeme Sayfası Hazırlanıyor..."):
                    token_res = get_paytr_iframe_token(
                        st.session_state.user_id,
                        st.session_state.get("user_email"),
                        149,
                        "Ultra"
                    )

                    if token_res["status"] == "success":
                        st.session_state.paytr_iframe_token = token_res["token"]
                        st.session_state.show_payment_frame = True
                        st.rerun()
                    else:
                        st.error(f"Ödeme Hatası: {token_res['reason']}")

    # --- ÖDEME EKRANI (IFRAME) GÖSTERİMİ ---
    if st.session_state.get("show_payment_frame", False) and "paytr_iframe_token" in st.session_state:
        st.divider()
        st.markdown("### 💳 Güvenli Ödeme Ekranı")

        # Kapatma Butonu
        if st.button("❌ Ödeme Ekranını Kapat", type="secondary"):
            st.session_state.show_payment_frame = False
            del st.session_state.paytr_iframe_token
            st.rerun()

        # PayTR iFrame Render
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
                        success, msg = change_password(st.session_state.username, current_pass, new_pass)
                        if success:
                            st.success(msg)
                        else:
                            st.error(msg)