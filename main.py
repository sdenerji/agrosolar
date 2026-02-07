import os
import streamlit as st
from streamlit_folium import st_folium
import folium
from folium.plugins import MarkerCluster
import matplotlib.pyplot as plt
import matplotlib
from datetime import datetime
import time
import json  # GeoJSON okumak için eklendi

# --- MODÜL IMPORTLARI ---
from db_base import get_supabase
from ui_utils import (hide_header_footer, render_google_login, render_analysis_box,
                      create_substation_popup, get_grid_color)
from auth_ui import show_auth_pages
from calculations import (calculate_slope_aspect, get_solar_potential, analyze_suitability,
                          get_projection_data, generate_earnings_graph, generate_horizon_plot,
                          get_horizon_analysis, get_shading_metrics, evaluate_shading_suitability,
                          parse_grid_data)
from reports import generate_full_report
from profile_page import show_profile_page
from user_config import ROLE_PERMISSIONS, has_permission
from session_manager import handle_session_limit
from user_service import check_and_update_subscription

# Çizim kararlılığı için
matplotlib.use('Agg')

# --------------------------------------------------------------------------
# 1. AYARLAR VE OTURUM
# --------------------------------------------------------------------------
st.set_page_config(page_title="AgroSolar Platform", layout="wide", page_icon="⚡", initial_sidebar_state="expanded")
hide_header_footer()

# Default Değerler
if 'page' not in st.session_state: st.session_state.page = 'analiz'
if 'lat' not in st.session_state: st.session_state.lat = 40.5850
if 'lon' not in st.session_state: st.session_state.lon = 36.9450
if 'logged_in' not in st.session_state: st.session_state.logged_in = False
if 'user_role' not in st.session_state: st.session_state.user_role = "Free"
if 'username' not in st.session_state: st.session_state.username = "Misafir"
if 'user_id' not in st.session_state: st.session_state.user_id = None
if 'user_email' not in st.session_state: st.session_state.user_email = None


# --- Oturum Başlatma ---
def init_app_session():
    supabase = get_supabase()
    try:
        session = supabase.auth.get_session()
        if session:
            user = session.user
            st.session_state.logged_in = True
            st.session_state.user_id = user.id
            st.session_state.user_email = user.email

            # Abonelik Kontrolü
            try:
                updated, new_role = check_and_update_subscription(user.id)
                if updated:
                    st.session_state.user_role = new_role
                    st.toast(f"ℹ️ Abonelik süreniz dolduğu için paketiniz {new_role} olarak güncellendi.", icon="🔄")
                    time.sleep(2)
                    st.rerun()
            except Exception as e:
                print(f"Main Abonelik Hatası: {e}")

            # Rolü veritabanından çek
            try:
                res = supabase.table("users").select("role, username").eq("id", user.id).execute()
                if res.data:
                    st.session_state.user_role = res.data[0].get("role", "Free")
                    st.session_state.username = res.data[0].get("username", "Kullanıcı")
            except:
                pass
        else:
            st.session_state.logged_in = False
    except:
        pass


init_app_session()
handle_session_limit()


# --------------------------------------------------------------------------
# 3. YARDIMCI FONKSİYONLAR
# --------------------------------------------------------------------------
def logout():
    supabase = get_supabase()
    supabase.auth.sign_out()
    st.session_state.logged_in = False
    st.session_state.username = "Misafir"
    st.session_state.user_role = "Free"
    st.session_state.user_id = None
    st.session_state.page = 'analiz'
    st.rerun()


def update_from_input():
    st.session_state.lat = st.session_state.input_lat
    st.session_state.lon = st.session_state.input_lon


def update_from_map(clicked_lat, clicked_lon):
    st.session_state.lat = clicked_lat
    st.session_state.lon = clicked_lon
    st.session_state.map_updater = True


def go_home(): st.session_state.page = 'analiz'


def go_profile(): st.session_state.page = 'profil'


# --------------------------------------------------------------------------
# 4. SAYFA AKIŞI
# --------------------------------------------------------------------------
if st.session_state.page == 'profil':
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
            role_info = ROLE_PERMISSIONS.get(st.session_state.user_role, {})
            role_label = role_info.get("label", st.session_state.user_role)
            st.success(f"👤 {st.session_state.username}")
            st.info(f"🛡️ Paket: **{role_label}**")

            c1, c2 = st.columns(2)
            if c1.button("🏠 Analiz", width="stretch"): go_home(); st.rerun()
            if c2.button("👤 Profil", width="stretch"): go_profile(); st.rerun()
            if st.button("Çıkış Yap", type="primary", width="stretch"): logout()

        st.divider()
        st.markdown("### 📍 Konum Kontrolü")

        if st.session_state.get("map_updater", False):
            st.session_state.input_lat = st.session_state.lat
            st.session_state.input_lon = st.session_state.lon
            st.session_state.map_updater = False

        st.number_input("Enlem", key='input_lat', format="%.6f", on_change=update_from_input)
        st.number_input("Boylam", key='input_lon', format="%.6f", on_change=update_from_input)
        kw_power = st.number_input("Kurulu Güç (kWp)", value=100, step=10)

        elec_price = 0.130
        if has_permission(st.session_state.user_role, "financials"):
            elec_price = st.number_input("Elektrik Satış Fiyatı (USD/kWh)", min_value=0.001, max_value=1.0, value=0.130,
                                         format="%.3f")

    # --- ANA EKRAN ---
    st.title("⚡ AgroSolar | Akıllı Arazi Enerji Analiz Platformu")

    col1, col2 = st.columns([2, 1])

    with col1:
        # 1. HARİTA (HERKESE AÇIK)
        user_layers = ROLE_PERMISSIONS.get(st.session_state.user_role, ROLE_PERMISSIONS["Free"])["map_layers"]
        secim = st.radio("Görünüm", user_layers, horizontal=True, label_visibility="collapsed")

        # 2. ŞEBEKE BUTONU (Free Görebilir ama Tıklayamaz)
        can_view_grid = has_permission(st.session_state.user_role, "grid_network_view")
        show_grid = st.toggle("⚡ Ulusal İletim Şebekesini Göster", value=False, disabled=not can_view_grid)

        if not can_view_grid:
            st.caption("🔒 **Şebeke verilerini görmek için Pro pakete geçin.**")

        tiles = 'OpenStreetMap'
        attr = None
        if "Uydu" in secim:
            tiles = 'https://server.arcgisonline.com/ArcGIS/rest/services/World_Imagery/MapServer/tile/{z}/{y}/{x}'
            attr = 'Esri World Imagery'
        elif "Topoğrafik" in secim:
            tiles = 'https://server.arcgisonline.com/ArcGIS/rest/services/World_Topo_Map/MapServer/tile/{z}/{y}/{x}'
            attr = 'Esri World Topo Map'

        m = folium.Map(location=[st.session_state.lat, st.session_state.lon], zoom_start=16, tiles=tiles, attr=attr)

        # --- GÜNCEL ŞEBEKE GÖSTERİM BLOĞU ---
        if show_grid and can_view_grid:
            geojson_path = "data/sebeke_verisi.geojson"
            if os.path.exists(geojson_path):
                with open(geojson_path, "r", encoding="utf-8") as f:
                    data = json.load(f)

                folium.GeoJson(
                    data,
                    marker=folium.CircleMarker(radius=5, color="blue", fill=True),
                    style_function=lambda x: {'color': 'blue', 'weight': 2},
                    tooltip=folium.GeoJsonTooltip(fields=["name"], aliases=["İsim:"])
                ).add_to(m)
                st.toast("⚡ Şebeke verisi GeoJSON üzerinden anında yüklendi!", icon="✅")
        # ------------------------------------

        folium.Marker([st.session_state.lat, st.session_state.lon],
                      icon=folium.Icon(color="red", icon="bolt", prefix="fa")).add_to(m)
        output = st_folium(m, height=500, width="100%", returned_objects=["last_clicked"], key="main_map")

        if output and output['last_clicked']:
            clat, clon = output['last_clicked']['lat'], output['last_clicked']['lng']
            if abs(clat - st.session_state.lat) > 0.00001:
                update_from_map(clat, clon)
                st.rerun()

        st.markdown("---")

        # 3. UFUK ANALİZİ (HERKESE AÇIK)
        horizon_graph = generate_horizon_plot(st.session_state.lat, st.session_state.lon)
        if horizon_graph and os.path.exists(horizon_graph):
            st.markdown("### 🏔️ Ufuk Gölge Analizi")
            st.image(horizon_graph, width="stretch")

            if not has_permission(st.session_state.user_role, "electrical_engine"):
                st.info("💡 Ultra pakette, bu gölge verisiyle 'String Voltajı' ve 'Panel Dizilimi' otomatik hesaplanır.")

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

            horizon_df = get_horizon_analysis(st.session_state.lat, st.session_state.lon)
            shading_metrics = get_shading_metrics(horizon_df)
            loss_factor = shading_metrics[1] if shading_metrics else 1.0

            st.write(f"**Maksimum Engel:** {shading_metrics[0]}")
            try:
                max_angle_val = float(shading_metrics[0].split('°')[0])
            except:
                max_angle_val = 0.0

            sh_status, sh_color, sh_note = evaluate_shading_suitability(max_angle_val)
            render_analysis_box("Engel Durumu", sh_status, sh_color)
            st.caption(f"ℹ️ {sh_note}")

            if has_permission(st.session_state.user_role, "financials"):
                res = get_solar_potential(st.session_state.lat, st.session_state.lon, baki, kw_power, egim, rakim,
                                          loss_factor=loss_factor, elec_price=elec_price)

                if res:
                    kwh, gelir, maliyet, roi, unit_cost = res
                    earnings_graph = generate_earnings_graph(kwh, elec_price, maliyet, roi)
                    projection_data = get_projection_data(kwh, elec_price, maliyet)

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
                st.info("🔒 **Finansal Veriler Kilitli**")
                st.markdown("""
                Aşağıdaki verilere erişmek için **Pro** pakete geçin:
                * 📈 Yıllık Üretim Tahmini (kWh)
                * 💰 Yatırım Maliyeti ve Getirisi (ROI)
                * 📄 PDF Fizibilite Raporu
                """)
                if st.button("🚀 Hemen Yükselt", key="upgrade_nudge", use_container_width=True):
                    go_profile()
                    st.rerun()