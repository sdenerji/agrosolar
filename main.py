import os
import streamlit as st
from streamlit_folium import st_folium
import folium
import matplotlib.pyplot as plt
import matplotlib
from datetime import datetime
import requests

# --- ÖZEL MODÜLLER ---
from database import get_supabase
# ui_utils'den görsel şablonları çağırıyoruz
from ui_utils import (hide_header_footer, render_google_login, render_analysis_box,
                      create_substation_popup, get_grid_color)
from auth_ui import show_auth_pages
# calculations'dan veri işleme mantığını çağırıyoruz
from calculations import (calculate_slope_aspect, get_solar_potential, analyze_suitability,
                          get_projection_data, generate_earnings_graph, generate_horizon_plot,
                          get_horizon_analysis, get_shading_metrics, evaluate_shading_suitability,
                          parse_grid_data)
from reports import generate_full_report
from profile_page import show_profile_page
from user_config import ROLE_PERMISSIONS, has_permission

# Session kontrolü
from session_manager import handle_session_limit

# Sunucuda çizim kararlılığı için Agg modu
matplotlib.use('Agg')

# --- 1. AYARLAR VE SESSION STATE ---
st.set_page_config(page_title="AgroSolar Platform", layout="wide", page_icon="⚡", initial_sidebar_state="expanded")
hide_header_footer()

# --- GÜVENLİK KONTROLÜ ---
handle_session_limit()
# -------------------------

if 'page' not in st.session_state: st.session_state.page = 'analiz'
if 'lat' not in st.session_state: st.session_state.lat = 40.5850
if 'lon' not in st.session_state: st.session_state.lon = 36.9450
if 'logged_in' not in st.session_state: st.session_state.logged_in = False
if 'username' not in st.session_state: st.session_state.username = "Misafir"
if 'user_role' not in st.session_state: st.session_state.user_role = "Free"


# --- 2. YARDIMCI FONKSİYONLAR ---
def logout():
    st.session_state.logged_in = False
    st.session_state.username = "Misafir"
    st.session_state.user_role = "Free"
    st.session_state.page = 'analiz'
    st.rerun()


def update_from_input():
    st.session_state.lat = st.session_state.input_lat
    st.session_state.lon = st.session_state.input_lon


def update_from_map(clicked_lat, clicked_lon):
    st.session_state.lat = clicked_lat
    st.session_state.lon = clicked_lon


def go_home(): st.session_state.page = 'analiz'


def go_profile(): st.session_state.page = 'profil'


# --- 3. SAYFA YÖNETİMİ ---
if st.session_state.page == 'profil' and st.session_state.logged_in:
    show_profile_page()
else:
    # --- SIDEBAR ---
    with st.sidebar:
        logo_path = "assets/logo.png"
        if os.path.exists(logo_path):
            st.image(logo_path, width="stretch")
        st.markdown("<h2 style='text-align: center; margin-top: -15px; color: #31333F;'>SD ENERJİ</h2>",
                    unsafe_allow_html=True)
        st.divider()

        if not st.session_state.logged_in:
            show_auth_pages(get_supabase())
            render_google_login()
        else:
            role_label = ROLE_PERMISSIONS.get(st.session_state.user_role, {}).get("label", "Misafir")
            st.success(f"👤 {st.session_state.username}")
            st.caption(f"🛡️ {role_label}")
            c1, c2 = st.columns(2)
            if c1.button("🏠 Analiz", width="stretch"): go_home(); st.rerun()
            if c2.button("👤 Profil", width="stretch"): go_profile(); st.rerun()
            if st.button("Çıkış Yap", type="primary", width="stretch"): logout()

        st.divider()
        st.markdown("### 📍 Konum Kontrolü")
        st.number_input("Enlem", key='input_lat', value=st.session_state.lat, format="%.6f",
                        on_change=update_from_input)
        st.number_input("Boylam", key='input_lon', value=st.session_state.lon, format="%.6f",
                        on_change=update_from_input)
        kw_power = st.number_input("Kurulu Güç (kWp)", value=100, step=10)

        elec_price = st.number_input("Elektrik Satış Fiyatı (USD/kWh)", min_value=0.001, max_value=1.0, value=0.130,
                                     format="%.3f") if has_permission(st.session_state.user_role,
                                                                      "financials") else 0.130

    # --- ANA EKRAN ---
    st.title("⚡ AgroSolar Platform")
    col1, col2 = st.columns([2, 1])

    with col1:
        # 1. Katman Seçimi (Altlıklar)
        map_options = ROLE_PERMISSIONS[st.session_state.user_role]["map_layers"]
        secim = st.radio("Görünüm", map_options, horizontal=True, label_visibility="collapsed")

        # 2. Şebeke Katmanı Anahtarı (TOGGLE) - Sadece Yetkisi Olanlara
        show_grid = False
        if has_permission(st.session_state.user_role, "grid_network_view"):
            show_grid = st.toggle("⚡ Ulusal İletim Şebekesini Göster", value=False)

        # 3. Harita Altlık Yapısı
        tiles = 'OpenStreetMap'
        attr = None
        if "Uydu" in secim:
            tiles = 'https://server.arcgisonline.com/ArcGIS/rest/services/World_Imagery/MapServer/tile/{z}/{y}/{x}'
            attr = 'Esri World Imagery'
        elif "Topoğrafik" in secim:
            tiles = 'https://server.arcgisonline.com/ArcGIS/rest/services/World_Topo_Map/MapServer/tile/{z}/{y}/{x}'
            attr = 'Esri World Topo Map'

        # Haritayı Başlat
        m = folium.Map(location=[st.session_state.lat, st.session_state.lon], zoom_start=16, tiles=tiles, attr=attr)

        # --- MODÜLER ŞEBEKE KATMANI ENTEGRASYONU ---
        if show_grid:
            # Dosya yolunu hatasız bul
            base_dir = os.path.dirname(os.path.abspath(__file__))
            kmz_file_path = os.path.join(base_dir, "data", "trafo_merkez.kmz")

            # Veriyi sessizce çek
            grid_data = parse_grid_data(kmz_file_path)

            # Bilgilendirme
            if grid_data:
                st.toast(f"✅ {len(grid_data)} şebeke noktası yüklendi!", icon="⚡")
            else:
                st.error(f"⚠️ Veri okunamadı. Yol: {kmz_file_path}")
                if not os.path.exists(kmz_file_path):
                    st.caption("🔍 İPUCU: 'data' klasörünün main.py ile aynı yerde olduğundan emin olun.")

            # Haritaya Çiz
            for item in grid_data:
                if item['type'] == 'Point':
                    popup_html = create_substation_popup(item['name'], item['mw'], item['total'])
                    color = get_grid_color(item['mw'])
                    folium.CircleMarker(
                        location=item['coords'],
                        radius=6, color=color, fill=True, fill_opacity=0.8,
                        popup=folium.Popup(popup_html, max_width=250)
                    ).add_to(m)
                elif item['type'] == 'Line':
                    folium.PolyLine(
                        item['path'], color="blue", weight=2, opacity=0.6,
                        tooltip=f"ENH: {item['name']}"
                    ).add_to(m)

        # Kullanıcı Konum İşaretçisi
        folium.Marker([st.session_state.lat, st.session_state.lon],
                      icon=folium.Icon(color="red", icon="bolt", prefix="fa")).add_to(m)

        output = st_folium(m, height=500, width="100%", returned_objects=["last_clicked"])
        if output and output['last_clicked']:
            clat, clon = output['last_clicked']['lat'], output['last_clicked']['lng']
            if abs(clat - st.session_state.lat) > 0.0001:
                update_from_map(clat, clon)
                st.rerun()

        st.markdown("---")
        if has_permission(st.session_state.user_role, "horizon_shading"):
            horizon_graph = generate_horizon_plot(st.session_state.lat, st.session_state.lon)
            if horizon_graph and os.path.exists(horizon_graph):
                st.markdown("### 🏔️ Ufuk Gölge Analizi")
                st.image(horizon_graph, width="stretch")
        else:
            st.warning("🏔️ **Ufuk Gölge Analizi** sadece Tier 2 ve Tier 3 paketlerde mevcuttur.")

    with col2:
        st.subheader("📊 Fizibilite Analizi")
        with st.spinner('Veriler analiz ediliyor...'):
            rakim, egim, baki = calculate_slope_aspect(st.session_state.lat, st.session_state.lon)
            report = analyze_suitability(egim, baki)

            st.metric("Ortalama Rakım", f"{rakim} m")
            st.write(f"**Arazi Eğimi:** %{egim}")
            render_analysis_box("Eğim", report["slope"]["status"], report["slope"]["color"])
            st.write(f"**Bakı Yönü / Cephe:** {baki}")
            render_analysis_box("Cephe", report["aspect"]["status"], report["aspect"]["color"])

            if has_permission(st.session_state.user_role, "financials"):
                horizon_df = get_horizon_analysis(st.session_state.lat, st.session_state.lon)
                shading_metrics = get_shading_metrics(horizon_df)
                loss_factor = shading_metrics[1] if shading_metrics else 1.0

                res = get_solar_potential(st.session_state.lat, st.session_state.lon, baki, kw_power, egim, rakim,
                                          loss_factor=loss_factor, elec_price=elec_price)

                if res:
                    kwh, gelir, maliyet, roi, unit_cost = res
                    earnings_graph = generate_earnings_graph(kwh, elec_price, maliyet, roi)
                    projection_data = get_projection_data(kwh, elec_price, maliyet)

                    st.write(f"**Maksimum Engel:** {shading_metrics[0]}")
                    try:
                        max_angle_val = float(shading_metrics[0].split('°')[0])
                    except:
                        max_angle_val = 0.0

                    sh_status, sh_color, sh_note = evaluate_shading_suitability(max_angle_val)
                    render_analysis_box("Engel Durumu", sh_status, sh_color)
                    st.caption(f"ℹ️ {sh_note}")

                    st.divider()
                    st.metric("Tahmini Yıllık Üretim", f"{int(kwh):,} kWh".replace(",", "."))
                    st.metric("Yaklaşık Yatırım Maliyeti", f"$ {int(maliyet):,}".replace(",", "."))
                    st.metric("Geri Ödeme Süresi (ROI)", f"{roi} Yıl")

                    if has_permission(st.session_state.user_role, "report_access"):
                        if st.button("📊 Raporu Oluştur", width="stretch", key="btn_generate_full_report"):
                            with st.spinner("Rapor hazırlanıyor..."):
                                st.session_state.pdf_bytes = generate_full_report(
                                    st.session_state.lat, st.session_state.lon, rakim, egim, baki,
                                    kw_power, kwh, gelir, maliyet, roi, unit_cost,
                                    st.session_state.username, st.session_state.user_role,
                                    secim, earnings_graph, horizon_graph, projection_data,
                                    shading_metrics=shading_metrics
                                )
                    if "pdf_bytes" in st.session_state:
                        st.download_button(label="📥 PDF Olarak İndir", data=st.session_state.pdf_bytes,
                                           file_name=f"SD_Enerji_Rapor_{datetime.now().strftime('%Y%m%d')}.pdf",
                                           mime="application/pdf", width="stretch", key="btn_download_final")
            else:
                st.divider()
                st.info("📊 **Finansal Analiz ve ROI** verileri için Professional pakete geçin.")