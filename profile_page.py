import streamlit as st
import streamlit.components.v1 as components
import time

# --- MODÜL IMPORTLARI ---
try:
    from auth_service import change_password
    from user_service import schedule_role_change, cancel_pending_change
    from paytr_utils import get_paytr_iframe_token
except ImportError:
    def change_password(u, c, n): return False, "Modül Bulunamadı"
    def schedule_role_change(u, r): return False, "Modül Bulunamadı"
    def cancel_pending_change(u): pass
    def get_paytr_iframe_token(i, e, a, r): return {"status": "error", "reason": "Modül Pasif"}

# --- SUPABASE BAĞLANTI ---
try:
    from supabase import create_client
    url = st.secrets["supabase"]["url"]
    key = st.secrets["supabase"]["key"]
    supabase = create_client(url, key)
except Exception as e:
    st.error(f"❌ Supabase bağlantı hatası: {e}")

# --- ONAY PENCERESİ ---
@st.dialog("⚠️ Paket Değişikliği Onayı")
def confirm_downgrade(target_role, end_date_str):
    st.write(f"Mevcut paketinizden **{target_role}** paketine geçmek üzeresiniz.")
    if end_date_str:
        st.warning(f"ℹ️ Bu değişiklik, abonelik sürenizin dolacağı **{end_date_str}** tarihinde gerçekleşecektir.")
    st.write("Onaylıyor musunuz?")
    col1, col2 = st.columns(2)
    with col1:
        if st.button("Evet, Onaylıyorum", key="btn_confirm_down", type="primary"):
            user_id = st.session_state.get("user_id")
            success, msg = schedule_role_change(user_id, target_role)
            if success:
                st.success(msg); time.sleep(1); st.rerun()
            else: st.error(msg)
    with col2:
        if st.button("Vazgeç", key="btn_cancel_down"): st.rerun()

# --- ANA PROFİL FONKSİYONU ---
def show_profile_page():
    user_id = st.session_state.get("user_id")
    username = st.session_state.get("username", "Misafir")
    email = st.session_state.get("user_email", "E-posta Yok")
    user_role = st.session_state.get("user_role", "Free")
    logged_in = st.session_state.get("logged_in", False)

    st.title("👤 Hesap ve Abonelik Yönetimi")

    # --- FİYAT ÇEKME ---
    try:
        fiyat_verisi = supabase.table("paket_fiyat").select("*").execute()
        fiyatlar = {item['package_name']: float(item['price']) for item in fiyat_verisi.data}
    except Exception as e:
        fiyatlar = {"Pro": 499.0, "Ultra": 1299.0}
        st.sidebar.error(f"Fiyatlar yüklenirken hata oluştu: {e}")

    PRO_PRICE = fiyatlar.get("Pro", 499.0)
    ULTRA_PRICE = fiyatlar.get("Ultra", 1299.0)

    # --- ÖDEME DURUM KONTROLÜ ---
    query_params = st.query_params
    if "payment_status" in query_params:
        status = query_params["payment_status"]
        if status == "success":
            st.balloons()
            st.success("✅ Ödeme Başarıyla Alındı! İşleminiz tamamlandı.")
            if st.button("🔑 Şimdi Giriş Yap", use_container_width=True):
                st.query_params.clear()
                st.session_state.page = "login"
                st.rerun()
        elif status == "fail":
            st.error("❌ Ödeme işlemi başarısız oldu.")
            if st.button("Tekrar Dene"):
                st.query_params.clear(); st.rerun()

    if not logged_in:
        st.warning("⚠️ Abonelik paketlerini yönetmek için giriş yapmalısınız.")
        return

    u_id_str = str(user_id) if user_id else "0"
    display_id = f"{u_id_str[:8]}..."
    st.info(f"👤 **Kullanıcı:** {username} | 📧 **E-Posta:** {email} | 🆔 **Müşteri No:** #{display_id}")

    st.markdown("### 📦 Abonelik Paketleri")
    col1, col2, col3 = st.columns(3)

    # --- 1. STANDART (FREE) ---
    with col1:
        st.markdown(f"""
        <div style="border: 1px solid #ddd; padding: 20px; border-radius: 10px; text-align: center; height: 570px; background-color: white;">
            <h4>STANDART</h4>
            <p style="color: gray; font-size: 0.8rem;">Giriş Seviyesi</p>
            <h2 style="margin: 20px 0;">0 ₺ <small style="font-size: 0.8rem;">/ Ay</small></h2>
            <hr>
            <ul style="text-align: left; list-style-type: none; padding-left: 0; font-size: 0.85rem; line-height: 1.8;">
                <li>✅ Temel Harita Analizi</li>
                <li>✅ Bakı ve Eğim Sorgulama</li>
                <li>❌ Panel Yerleşimi ve Tasarım</li>
                <li>❌ Finansal Analiz & Raporlama</li>
                <li>❌ 3D Arazi Analizi</li>
            </ul>
        </div>
        """, unsafe_allow_html=True)
        st.write("")
        if user_role == "Free":
            st.button("Mevcut Paketiniz", disabled=True, key="p1_curr", use_container_width=True)
        else:
            if st.button("Standart'a Dön", key="p1_down", use_container_width=True):
                confirm_downgrade("Free", "Dönem Sonu")

    # --- 2. PROFESSIONAL (PRO) ---
    with col2:
        st.markdown(f"""
        <div style="border: 2px solid #28a745; padding: 20px; border-radius: 10px; text-align: center; height: 570px; background-color: #f8fff9;">
            <h4 style="color: #28a745;">PROFESSIONAL</h4>
            <p style="color: gray; font-size: 0.8rem;">Tasarımcı & Yatırımcı</p>
            <h2 style="margin: 20px 0; color: #28a745;">{PRO_PRICE} ₺ <small style="font-size: 0.8rem;">/ Ay</small></h2>
            <hr>
            <ul style="text-align: left; list-style-type: none; padding-left: 0; font-size: 0.85rem; line-height: 1.8;">
                <li>✅ <b>Tüm Standart Özellikler Dahil</b></li>
                <li>✅ <b>Panel Yerleşimi ve Tasarım</b></li>
                <li>✅ Finansal Geri Dönüş (ROI) Hesabı</li>
                <li>✅ 3D Arazi Analizi (SRTM)</li>
                <li>✅ Profesyonel PDF Raporlama</li>
                <li>❌ DXF / CAD Çıktısı</li>
            </ul>
        </div>
        """, unsafe_allow_html=True)
        st.write("")
        if user_role == "Pro":
            st.button("Mevcut Paketiniz", disabled=True, key="p2_curr", use_container_width=True)
        else:
            if st.button(f"🚀 Yükselt ({PRO_PRICE}₺)", type="primary", key="p2_up", use_container_width=True):
                with st.spinner("💳 Hazırlanıyor..."):
                    token_res = get_paytr_iframe_token(user_id, email, PRO_PRICE, "Pro")
                    if token_res["status"] == "success":
                        st.session_state.paytr_iframe_token = token_res["token"]
                        st.session_state.show_payment_frame = True; st.rerun()
                    else: st.error(f"Hata: {token_res.get('reason')}")

    # --- 3. ULTRA (KURUMSAL) ---
    with col3:
        st.markdown(f"""
        <div style="border: 2px solid #ffc107; padding: 20px; border-radius: 10px; text-align: center; height: 570px; background-color: #2b2d42; color: white;">
            <h4 style="color: #ffc107;">ULTRA (KURUMSAL)</h4>
            <p style="color: #aaa; font-size: 0.8rem;">Mühendislik & EPC Firmaları</p>
            <h2 style="margin: 20px 0; color: #ffc107;">{ULTRA_PRICE} ₺ <small style="font-size: 0.8rem;">/ Ay</small></h2>
            <hr style="border: 0; border-top: 1px solid #555;">
            <ul style="text-align: left; list-style-type: none; padding-left: 0; font-size: 0.82rem; line-height: 1.7;">
                <li>✅ <b>Tüm Professional Özellikler Dahil</b></li>
                <li>✅ <b>Yapay Zeka (AI) Rapor Özeti</b></li>
                <li>✅ <b>DXF / CAD Veri Çıktısı</b></li>
                <li>✅ 3D Hassas Nokta Bulutu Analizi</li>
                <li>✅ EPSG Koordinat Dönüşümü</li>
                <li>✅ Trafo (TM) Mesafe Analizi</li>
            </ul>
        </div>
        """, unsafe_allow_html=True)
        st.write("")
        if user_role == "Ultra":
            st.button("Mevcut Paketiniz", disabled=True, key="p3_curr", use_container_width=True)
        else:
            if st.button(f"💎 Ultra'ya Geç ({ULTRA_PRICE}₺)", type="primary", key="p3_up", use_container_width=True):
                with st.spinner("💳 Hazırlanıyor..."):
                    token_res = get_paytr_iframe_token(user_id, email, ULTRA_PRICE, "Ultra")
                    if token_res["status"] == "success":
                        st.session_state.paytr_iframe_token = token_res["token"]
                        st.session_state.show_payment_frame = True; st.rerun()
                    else: st.error(f"Hata: {token_res.get('reason')}")

    if st.session_state.get("show_payment_frame", False) and "paytr_iframe_token" in st.session_state:
        st.divider()
        st.info("👇 Güvenli ödeme sayfasına gitmek için butona tıklayın.")
        iframe_url = f"https://www.paytr.com/odeme/guvenli/{st.session_state.paytr_iframe_token}"
        st.markdown(f'''<a href="{iframe_url}" target="_self"><button style="background-color: #FF4B4B; color: white; padding: 15px; border-radius: 8px; border: none; width: 100%; font-weight: bold; cursor: pointer;">🚀 Güvenli Ödemeye Git</button></a>''', unsafe_allow_html=True)
        if st.button("❌ Vazgeç", use_container_width=True):
            st.session_state.show_payment_frame = False; st.rerun()