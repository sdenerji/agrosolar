import streamlit as st
import streamlit.components.v1 as components  # iFrame için gerekli
import time

# --- MODÜL IMPORTLARI ---
try:
    from auth_service import change_password
    from user_service import schedule_role_change, cancel_pending_change
    from paytr_utils import get_paytr_iframe_token
except ImportError:
    # Modüller henüz yüklenmediyse hata vermesin
    def change_password(u, c, n):
        return False, "Modül Bulunamadı"


    def schedule_role_change(u, r):
        return False, "Modül Bulunamadı"


    def cancel_pending_change(u):
        pass


    def get_paytr_iframe_token(i, e, a, r):
        return {"status": "error", "reason": "Modül Pasif"}

# --- 🚀 SUPABASE IMPORT VE BAĞLANTI (YENİ EKLEME) ---
try:
    from supabase import create_client

    # Secrets içindeki [supabase] başlığına ve altındaki küçük harflere (url, key) bakıyoruz
    url = st.secrets["supabase"]["url"]
    key = st.secrets["supabase"]["key"]

    supabase = create_client(url, key)
except Exception as e:
    st.error(f"❌ Supabase bağlantı hatası: {e}")


# ---------------------------------------------------

# --- ONAY PENCERESİ (PAKET DÜŞÜRME) ---
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

    # 1. Verileri Al
    user_id = st.session_state.get("user_id")
    username = st.session_state.get("username", "Misafir")
    email = st.session_state.get("user_email", "E-posta Yok")
    user_role = st.session_state.get("user_role", "Free")
    logged_in = st.session_state.get("logged_in", False)

    st.title("👤 Hesap ve Abonelik Yönetimi")
    # --- 🛠️ DİNAMİK FİYAT ÇEKME (YENİ EKLEME) ---
    try:
        # Supabase'deki 'paket_fiyat' tablonuzdan verileri çekiyoruz
        fiyat_verisi = supabase.table("paket_fiyat").select("*").execute()
        fiyatlar = {item['package_name']: float(item['price']) for item in fiyat_verisi.data}
    except Exception as e:
        # Veritabanı bağlantısı koparsa sistem çökmesin diye yedek fiyatlar
        fiyatlar = {"Pro": 499.0, "Ultra": 1299.0}
        st.sidebar.error(f"Fiyatlar yüklenirken hata oluştu: {e}")

    # Tablodaki isimlerinize göre değişkenleri atıyoruz
    PRO_PRICE = fiyatlar.get("Pro", 499.0)
    ULTRA_PRICE = fiyatlar.get("Ultra", 1299.0)
    # --------------------------------------------
    # --- KRİTİK EKLENTİ: ÖDEME MESAJINI EN BAŞTA GÖSTER ---
    # Kullanıcı giriş yapmamış olsa bile (session düşse bile) parayı ödediyse mesajı görsün.
    query_params = st.query_params
    if "payment_status" in query_params:
        status = query_params["payment_status"]
        if status == "success":
            st.balloons()
            st.success("✅ Ödeme Başarıyla Alındı! İşleminiz tamamlandı.")
            st.info("ℹ️ Güvenlik gereği lütfen sisteme tekrar giriş yapınız.")
            if st.button("🔑 Şimdi Giriş Yap", use_container_width=True):
                st.session_state.page = "login"
                st.rerun()
        elif status == "fail":
            st.error("❌ Ödeme işlemi başarısız oldu veya iptal edildi.")

    # --- UX DÜZELTMESİ: MİSAFİR KULLANICIYI KURTARMA ---
    if not logged_in:
        st.warning("⚠️ Abonelik paketlerini yönetmek için giriş yapmalısınız.")

        # Geri Dön Butonu
        col1, col2 = st.columns([1, 2])
        with col1:
            if st.button("← Analiz Ekranına Dön", key="guest_back_btn", type="primary", use_container_width=True):
                st.session_state.page = 'analiz'
                st.rerun()

        # Fonksiyonu burada bitiriyoruz ki aşağıya geçip hata vermesin
        return

        # --- LOGGED IN KONTROLÜ (Giriş Yapmışsa Buradan Devam Eder) ---
    if user_id is None:
        st.error("⚠️ Kullanıcı verileri yüklenemedi. Lütfen tekrar giriş yapınız.")
        if st.button("Ana Ekrana Dön"):
            st.session_state.page = 'analiz'
            st.rerun()
        st.stop()

    # --- KULLANICI BİLGİ KARTI ---
    u_id_str = str(user_id) if user_id else "0"
    display_id = f"{u_id_str[:8]}..." if len(u_id_str) > 8 else u_id_str

    st.markdown(f"### Hoş Geldiniz, **{username}**")
    st.info(f"📧 **E-Posta:** {email}  |  🆔 **Müşteri No:** #{display_id}")

    st.divider()

    # --- ÖDEME SONUCU MESAJLARI (CALLBACK) ---
    query_params = st.query_params
    if "payment_status" in query_params:
        status = query_params["payment_status"]
        if status == "success":
            st.balloons()
            st.success("✅ Ödeme Başarıyla Alındı! Aboneliğiniz kısa süre içinde güncellenecektir.")
        elif status == "fail":
            st.error("❌ Ödeme işlemi tamamlanamadı veya iptal edildi.")

    st.markdown("### 📦 Abonelik Paketleri")

    # 3 KOLONLU FİYATLANDIRMA
    col1, col2, col3 = st.columns(3)

    # --- 1. TIER 1: FREE ---
    with col1:
        st.markdown("""
        <div style="border: 1px solid #e0e0e0; padding: 20px; border-radius: 10px; text-align: center; height: 500px; display: flex; flex-direction: column; justify-content: space-between; background-color: #ffffff;">
            <div>
                <h4 style="color: #555; margin-bottom:0;">STANDART</h4>
                <div style="font-size: 12px; color: #999; margin-bottom: 10px;">Meraklılar İçin</div>
                <h2 style="font-size: 2.2rem; color: #333;">0 ₺ <small style="font-size: 1rem;">/ Ay</small></h2>
                <hr style="border-top: 1px solid #eee;">
                <ul style="text-align: left; list-style-type: '⚪ '; font-size:13px; padding-left: 20px; color: #666; margin-top: 15px;">
                    <li style="margin-bottom: 8px;">Temel Eğim ve Bakı Analizi</li>
                    <li style="margin-bottom: 8px;">OpenStreetMap Haritası</li>
                    <li style="margin-bottom: 8px;">Sınırlı Panel Yerleşimi</li>
                    <li style="margin-bottom: 8px;">Günlük 3 Analiz Hakkı</li>
                    <li style="margin-bottom: 8px; text-decoration: line-through; color: #ccc;">PDF Raporlama</li>
                </ul>
            </div>
        </div>
        """, unsafe_allow_html=True)

        st.write("")  # Boşluk
        if user_role == "Free":
            st.button("Mevcut Paketiniz", disabled=True, key="p1_current", use_container_width=True)
        else:
            if st.button("Standart'a Dön", key="p1_downgrade", use_container_width=True):
                # Tarih bilgisi için DB'ye bakılabilir, şimdilik mockup
                confirm_downgrade("Free", "Dönem Sonu")

    # --- 2. TIER 2: PRO (499 TL) ---
    with col2:
        st.markdown(f"""
        <div style="border: 2px solid #28a745; padding: 20px; border-radius: 10px; text-align: center; height: 500px; display: flex; flex-direction: column; justify-content: space-between; background-color: #f0fff4;">
            <div>
                <h4 style="color: #28a745; margin-bottom:0;">PROFESSIONAL</h4>
                <div style="font-size: 12px; color: #28a745; margin-bottom: 10px;">Bireysel Yatırımcı & Emlakçı</div>
                <h2 style="font-size: 2.2rem; color: #1e7e34;">{PRO_PRICE} ₺ <small style="font-size: 1rem;">/ Ay</small></h2>
                <hr style="border-top: 1px solid #c3e6cb;">
                <ul style="text-align: left; list-style-type: '✅ '; font-size:13px; padding-left: 20px; color: #155724; margin-top: 15px;">
                    <li style="margin-bottom: 8px;"><b>Profesyonel PDF Rapor</b></li>
                    <li style="margin-bottom: 8px;">Ufuk Çizgisi ve Gölge Analizi</li>
                    <li style="margin-bottom: 8px;">Yatırım Geri Dönüş (ROI) Hesabı</li>
                    <li style="margin-bottom: 8px;">Uydu Görüntüsü Katmanı</li>
                    <li style="margin-bottom: 8px;">Günlük 20 Analiz Hakkı</li>
                </ul>
            </div>
        </div>
        """, unsafe_allow_html=True)

        st.write("")
        if user_role == "Pro":
            st.button("Mevcut Paketiniz", disabled=True, key="p2_current", use_container_width=True)
        else:
            if st.button(f"🚀 Yükselt ({PRO_PRICE}₺)", key="p2_upgrade", type="primary", use_container_width=True):
                with st.spinner("💳 Güvenli Ödeme Sayfası Hazırlanıyor..."):
                    token_res = get_paytr_iframe_token(user_id, email, PRO_PRICE, "Pro")
                    if token_res["status"] == "success":
                        st.session_state.paytr_iframe_token = token_res["token"]
                        st.session_state.show_payment_frame = True
                        st.rerun()
                    else:
                        st.error(f"Ödeme Başlatılamadı: {token_res.get('reason')}")

    # --- 3. TIER 3: ULTRA (1.299 TL) ---
    with col3:
        st.markdown(f"""
        <div style="border: 2px solid #ffd700; padding: 20px; border-radius: 10px; text-align: center; height: 500px; display: flex; flex-direction: column; justify-content: space-between; background-color: #2b2d42; color: white;">
            <div>
                <h4 style="color: #ffd700; margin-bottom:0;">ULTRA (KURUMSAL)</h4>
                <div style="font-size: 12px; color: #aaa; margin-bottom: 10px;">Mühendislik & EPC Firmaları</div>
                <h2 style="font-size: 2.2rem; color: #ffd700;">{ULTRA_PRICE} ₺ <small style="font-size: 1rem;">/ Ay</small></h2>
                <hr style="border-top: 1px solid #444;">
                <ul style="text-align: left; list-style-type: '💎 '; font-size:13px; padding-left: 20px; margin-top: 15px;">
                    <li style="margin-bottom: 8px;"><b>Yapay Zeka (Gemini) Yorumu</b></li>
                    <li style="margin-bottom: 8px;"><b>TEİAŞ Kapasite Haritası</b></li>
                    <li style="margin-bottom: 8px;">25 Yıllık Finansal Projeksiyon</li>
                    <li style="margin-bottom: 8px;">KMZ / CAD Veri Çıktısı</li>
                    <li style="margin-bottom: 8px;"><b>Sınırsız Analiz Hakkı</b></li>
                </ul>
            </div>
        </div>
        """, unsafe_allow_html=True)

        st.write("")
        if user_role == "Ultra":
            st.button("Mevcut Paketiniz", disabled=True, key="p3_current", use_container_width=True)
        else:
            if st.button(f"💎 Ultra'ya Geç ({ULTRA_PRICE}₺)", key="p3_upgrade", type="primary",
                         use_container_width=True):
                with st.spinner("💳 Güvenli Ödeme Sayfası Hazırlanıyor..."):
                    token_res = get_paytr_iframe_token(user_id, email, ULTRA_PRICE, "Ultra")
                    if token_res["status"] == "success":
                        st.session_state.paytr_iframe_token = token_res["token"]
                        st.session_state.show_payment_frame = True
                        st.rerun()
                    else:
                        st.error(f"Ödeme Başlatılamadı: {token_res.get('reason')}")

        # --- ÖDEME ALANI (GÜNCELLENDİ: iFrame Yerine Yönlendirme) ---
        if st.session_state.get("show_payment_frame", False) and "paytr_iframe_token" in st.session_state:
            st.markdown("---")
            st.markdown("### 💳 Ödeme İşlemini Tamamlayın")

            st.info("👇 Aşağıdaki butona tıkladığınızda güvenli ödeme sayfasına yönlendirileceksiniz.")

            # PayTR Linki
            iframe_url = f"https://www.paytr.com/odeme/guvenli/{st.session_state.paytr_iframe_token}"

            # target="_self" diyerek aynı sekmede açılmasını sağlıyoruz (En temiz yöntem)
            st.markdown(f'''
                <a href="{iframe_url}" target="_self" style="text-decoration: none;">
                    <button style="
                        background-color: #FF4B4B; 
                        color: white; 
                        padding: 15px 32px; 
                        text-align: center; 
                        text-decoration: none; 
                        display: inline-block; 
                        font-size: 16px; 
                        margin: 4px 2px; 
                        cursor: pointer; 
                        border-radius: 8px; 
                        border: none; 
                        width: 100%;
                        font-weight: bold;">
                        🚀 Güvenli Ödeme Sayfasına Git
                    </button>
                </a>
            ''', unsafe_allow_html=True)

            st.write("")  # Boşluk

            if st.button("❌ Vazgeç / Kapat", type="secondary", use_container_width=True):
                st.session_state.show_payment_frame = False
                if "paytr_iframe_token" in st.session_state: del st.session_state.paytr_iframe_token
                st.rerun()