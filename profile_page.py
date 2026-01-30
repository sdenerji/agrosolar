import streamlit as st


def show_profile_page():
    """Kullanıcı profilini ve paket karşılaştırma arayüzünü yönetir."""
    st.title("👤 Hesap ve Abonelik Yönetimi")

    # --- 1. DİNAMİK KULLANICI BİLGİSİ ---
    if st.session_state.get("logged_in", False):
        # Supabase'den gelen verileri session_state'den okuyoruz
        email = st.session_state.get("user_email", "E-posta Yok")

        # Kullanıcı ID'si genelde uzun bir UUID olur, sadece başını gösterip şıklaştıralım
        user_id_raw = str(st.session_state.get("user_id", "-"))
        display_id = f"{user_id_raw[:8]}..." if len(user_id_raw) > 8 else user_id_raw

        st.markdown(f"### Hoş Geldiniz, **{st.session_state.username}**")
        # Şık bir bilgi satırı
        st.info(f"📧 **E-Posta:** {email}  |  🆔 **Müşteri No:** #{display_id}")
    else:
        # Giriş yapmamışsa (Test amaçlı)
        st.markdown(f"### Hoş Geldiniz, **Misafir Kullanıcı**")
        st.caption("Lütfen analizlerinizi kaydetmek için giriş yapınız.")

    st.divider()

    # --- PAKET KARŞILAŞTIRMA LANDING PAGE ---
    st.markdown("### 🚀 AgroSolar Paketleri")
    st.write("İhtiyacınıza en uygun mühendislik çözümünü seçin.")

    # Üçlü Sütun Yapısı
    col1, col2, col3 = st.columns(3)

    # 1. TIER: STANDART (FREE)
    with col1:
        st.markdown("""
        <div style="border: 1px solid #ddd; padding: 20px; border-radius: 10px; text-align: center; height: 400px;">
            <h4>TIER 1: STANDART</h4>
            <h2>$0 <small>/ Ay</small></h2>
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
            st.button("Standart'a Dön", key="p1_back", use_container_width=True)

    # 2. TIER: PROFESSIONAL (PRO)
    with col2:
        st.markdown("""
        <div style="border: 2px solid #28a745; padding: 20px; border-radius: 10px; text-align: center; background-color: #f8fff9; height: 400px;">
            <h4 style="color: #28a745;">TIER 2: PROFESSIONAL</h4>
            <h2>$49 <small>/ Ay</small></h2>
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
        elif st.session_state.user_role == "Free":
            if st.button("🚀 Hemen Yükselt", key="p2_up", type="primary", use_container_width=True):
                st.info("Ödeme sayfasına yönlendiriliyorsunuz...")
        else:
            st.button("Pro Paket Detayları", key="p2_inf", use_container_width=True)

    # 3. TIER: ENTERPRISE (ULTRA) - GÜNCELLENDİ
    with col3:
        # Ultra kutusuna 'Ulusal Şebeke' maddesini ekledik
        st.markdown("""
        <div style="border: 1px solid #31333F; padding: 20px; border-radius: 10px; text-align: center; background-color: #31333F; color: white; height: 400px;">
            <h4 style="color: #ffd700;">TIER 3: ULTRA</h4>
            <h2>$149 <small>/ Ay</small></h2>
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
            if st.button("💎 Ultra'ya Geç", key="p3_up", use_container_width=True):
                st.info("Kurumsal ödeme sayfasına yönlendiriliyorsunuz...")

    st.divider()

    # Kontrol Butonları
    c1, c2 = st.columns(2)
    with c1:
        if st.button("← Analiz Ekranına Dön", use_container_width=True):
            st.session_state.page = 'analiz'
            st.rerun()
    with c2:
        if st.button("🔐 Şifre Değiştir", use_container_width=True):
            st.warning("Bu özellik yakında aktif edilecektir.")