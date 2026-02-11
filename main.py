import os
import streamlit as st
from streamlit_folium import st_folium
import folium
from folium.plugins import MarkerCluster
import matplotlib.pyplot as plt
import matplotlib
from datetime import datetime
import time
import json

# --- MODÜL IMPORTLARI ---
from db_base import get_supabase
from ui_utils import (hide_header_footer, render_google_login, render_analysis_box,
                      create_substation_popup, get_grid_color,
                      render_announcement_banner, render_admin_announcement_editor)
from auth_ui import show_auth_pages
# GÜNCELLEME: get_substation_data EKLENDİ
from gis_service import process_parsel_geojson, get_substation_data

from calculations import (calculate_slope_aspect, get_solar_potential, analyze_suitability,
                          get_projection_data, generate_earnings_graph, generate_horizon_plot,
                          get_horizon_analysis, get_shading_metrics, evaluate_shading_suitability,
                          parse_grid_data, get_suitability_badge)

# MÜHENDİSLİK & EKİPMAN IMPORTLARI
from equipment_db import PANEL_LIBRARY, INVERTER_LIBRARY
from ges_engine import perform_string_analysis
from layout_engine import SolarLayoutEngine

# --- ULTRA MODÜL IMPORTU (STANDART) ---
try:
    from cut_fill_3d import show_3d_page
except ImportError:
    def show_3d_page():
        st.error("⚠️ 'cut_fill_3d.py' modülü yüklenemedi. Dosya adını kontrol edin.")

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
st.set_page_config(page_title="SD Enerji Analiz Platformu", layout="wide", page_icon="⚡",
                   initial_sidebar_state="expanded")
hide_header_footer()

# --- DEFAULT DEĞERLER ---
if 'page' not in st.session_state: st.session_state.page = 'analiz'
if 'lat' not in st.session_state: st.session_state.lat = 40.5850
if 'lon' not in st.session_state: st.session_state.lon = 36.9450
if 'input_lat' not in st.session_state: st.session_state.input_lat = 40.5850
if 'input_lon' not in st.session_state: st.session_state.input_lon = 36.9450

if 'logged_in' not in st.session_state: st.session_state.logged_in = False
if 'user_role' not in st.session_state: st.session_state.user_role = "Free"
if 'username' not in st.session_state: st.session_state.username = "Misafir"
if 'user_id' not in st.session_state: st.session_state.user_id = None
if 'parsel_geojson' not in st.session_state: st.session_state.parsel_geojson = None
if 'layout_data' not in st.session_state: st.session_state.layout_data = None

# PANEL VE INVERTER SEÇİMİ İÇİN STATE TAKİBİ
if 'selected_panel_brand' not in st.session_state: st.session_state.selected_panel_brand = list(PANEL_LIBRARY.keys())[0]
if 'selected_inverter_brand' not in st.session_state: st.session_state.selected_inverter_brand = \
list(INVERTER_LIBRARY.keys())[0]


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
            try:
                updated, new_role = check_and_update_subscription(user.id)
                if updated:
                    st.session_state.user_role = new_role
                    st.toast(f"ℹ️ Abonelik süreniz doldu, paket: {new_role}", icon="🔄")
                    st.rerun()
            except:
                pass
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


# --- YARDIMCI FONKSİYONLAR ---
def logout():
    supabase = get_supabase()
    supabase.auth.sign_out()
    st.session_state.logged_in = False
    st.session_state.page = 'analiz'
    st.rerun()


def update_from_input():
    if 'input_lat' in st.session_state:
        st.session_state.lat = st.session_state.input_lat
    if 'input_lon' in st.session_state:
        st.session_state.lon = st.session_state.input_lon


def update_from_map(clicked_lat, clicked_lon):
    st.session_state.lat = clicked_lat
    st.session_state.lon = clicked_lon
    st.session_state.map_updater = True


# --------------------------------------------------------------------------
# 4. SAYFA AKIŞI
# --------------------------------------------------------------------------
if st.session_state.page == 'profil':
    show_profile_page()

# --- 3D ANALİZ SAYFASI ---
elif st.session_state.page == '3d_analiz':
    show_3d_page()

else:  # Varsayılan: Analiz Sayfası
    # --- SIDEBAR (SADELEŞTİRİLDİ) ---
    with st.sidebar:
        logo_path = "assets/logo.png"
        if os.path.exists(logo_path): st.image(logo_path, width="stretch")
        st.markdown("<h2 style='text-align: center; margin-top: -15px;'>SD ENERJİ</h2>", unsafe_allow_html=True)
        st.divider()

        # MENÜ ALANI
        if st.session_state.logged_in:
            role_label = ROLE_PERMISSIONS.get(st.session_state.user_role, {}).get("label", st.session_state.user_role)
            st.success(f"👤 {st.session_state.username}")
            st.info(f"🛡️ Paket: **{role_label}**")

            # --- 3D BUTONU KALDIRILDI, 2 SÜTUNA DÜŞÜRÜLDÜ ---
            c1, c2 = st.columns(2)
            if c1.button("🏠 Analiz"): st.session_state.page = 'analiz'; st.rerun()
            if c2.button("👤 Profil"): st.session_state.page = 'profil'; st.rerun()

            if st.button("Çıkış Yap", type="primary", use_container_width=True): logout()
        else:
            show_auth_pages(get_supabase())
            render_google_login()

        st.divider()
        st.markdown("### 📍 Konum & Parsel")
        tab_manuel, tab_parsel = st.tabs(["📌 Manuel", "🗺️ Parsel"])

        with tab_manuel:
            if st.session_state.get("map_updater", False):
                st.session_state.input_lat, st.session_state.input_lon = st.session_state.lat, st.session_state.lon
                st.session_state.map_updater = False

            st.number_input("Enlem", key='input_lat', format="%.6f", on_change=update_from_input)
            st.number_input("Boylam", key='input_lon', format="%.6f", on_change=update_from_input)

        with tab_parsel:
            st.info("""
            **ℹ️ GeoJSON Dosyası Nasıl Alınır?**
            1. [TKGM Parsel Sorgu](https://parselsorgu.tkgm.gov.tr) adresine gidin.
            2. Parselinizi haritadan bulup seçin.
            3. Açılan bilgi kartındaki **üç nokta (⋮)** menüsüne tıklayın.
            4. **İndir > GeoJSON** seçeneği ile dosyayı bilgisayarınıza kaydedin.
            5. İndirdiğiniz dosyayı aşağıdaki alana sürükleyin.
            """)
            uploaded_file = st.file_uploader("GeoJSON Yükle", type=["geojson", "json"])

            if uploaded_file and st.session_state.get('last_processed_file') != uploaded_file.name:
                if has_permission(st.session_state.user_role, "panel_placement"):
                    try:
                        geojson_data = json.load(uploaded_file)
                        p_lat, p_lon, success, msg = process_parsel_geojson(geojson_data)
                        if success:
                            st.session_state.lat, st.session_state.lon = p_lat, p_lon
                            st.session_state.parsel_geojson = geojson_data
                            st.session_state.layout_data = None
                            st.session_state.last_processed_file = uploaded_file.name
                            st.success("✅ Parsel işlendi!")
                            time.sleep(0.5);
                            st.rerun()
                        else:
                            st.error(msg)
                    except Exception as e:
                        st.error(f"Hata: {e}")
                else:
                    st.error("🔒 **Dosya İşleme Kısıtlı**")
                    st.warning("Parsel verilerini işlemek ve otomatik yerleşim yapmak **Ultra** pakete dahildir.")

        st.divider()
        st.markdown("### 🏔️ 3D Arazi Analizi")
        st.caption("Arazinizin eğim haritasını çıkarın, kazı/dolgu (hafriyat) maliyetlerini hesaplayın.")
        if st.button("🚀 3D Modülüne Git", use_container_width=True):
            st.session_state.page = '3d_analiz'
            st.rerun()

    try:
        admin_email = st.secrets["general"]["admin_email"]
    except:
        admin_email = None
    if st.session_state.get("logged_in") and st.session_state.get("user_email") == admin_email:
        st.divider()
        with st.expander("🛠️ Yönetici Paneli", expanded=False):
            render_admin_announcement_editor()

    st.title("⚡ SD Enerji Analiz Platformu")
    horizon_graph = None
    col1, col2 = st.columns([2, 1])

    with col1:
        # Harita Görünüm
        secim = st.radio("Görünüm", ["Sokak (OSM)", "Uydu (Esri)", "Topoğrafik (Esri)"], horizontal=True,
                         label_visibility="collapsed")

        show_grid_request = st.toggle("⚡ Şebekeyi Göster", value=False)
        show_grid = False

        if show_grid_request:
            if has_permission(st.session_state.user_role, "grid_network_view"):
                show_grid = True
            else:
                st.toast("🔒 Bu özellik **Pro** pakete dahildir!", icon="🚫")
                st.error("Şebeke altyapısını görüntülemek için **Pro** pakete geçmelisiniz.")

        tile_configs = {
            "Sokak (OSM)": {"tiles": "OpenStreetMap", "attr": None},
            "Uydu (Esri)": {
                "tiles": "https://server.arcgisonline.com/ArcGIS/rest/services/World_Imagery/MapServer/tile/{z}/{y}/{x}",
                "attr": "Esri World Imagery"},
            "Topoğrafik (Esri)": {
                "tiles": "https://server.arcgisonline.com/ArcGIS/rest/services/World_Topo_Map/MapServer/tile/{z}/{y}/{x}",
                "attr": "Esri World Topo Map"}
        }
        selected_config = tile_configs.get(secim, tile_configs["Sokak (OSM)"])

        m = folium.Map(location=[st.session_state.lat, st.session_state.lon], zoom_start=18,
                       tiles=selected_config["tiles"], attr=selected_config["attr"])

        folium.Marker([st.session_state.lat, st.session_state.lon], tooltip="Seçili Konum",
                      popup=f"{st.session_state.lat:.5f}, {st.session_state.lon:.5f}",
                      icon=folium.Icon(color="red", icon="map-pin", prefix="fa")).add_to(m)

        if show_grid:
            base_dir = os.path.dirname(os.path.abspath(__file__))
            geojson_path = os.path.join(base_dir, "data", "sebeke_verisi.geojson")
            if not os.path.exists(geojson_path):
                st.error(f"⚠️ Şebeke veri dosyası bulunamadı.")
            else:
                grid_data = parse_grid_data(geojson_path)
                if grid_data:
                    marker_cluster = MarkerCluster(name="Trafo Merkezleri").add_to(m)
                    for item in grid_data:
                        if item['type'] == 'Point':
                            # --- YENİ: TEİAŞ VERİSİ İLE ZENGİNLEŞTİRİLMİŞ POPUP ---
                            # gis_service'den simüle edilmiş veriyi çekiyoruz
                            teias_live_data = get_substation_data(item['name'])

                            popup_html = create_substation_popup(teias_live_data)
                            color = teias_live_data['color']

                            folium.CircleMarker(
                                location=item['coords'], radius=9, color=color, fill=True, fill_opacity=0.9,
                                popup=folium.Popup(popup_html, max_width=300),
                                tooltip=f"{item['name']} ({teias_live_data['status']})"
                            ).add_to(marker_cluster)
                            # -----------------------------------------------------
                        elif item['type'] == 'Line':
                            folium.PolyLine(item['path'], color="blue", weight=2, opacity=0.4,
                                            tooltip=f"ENH: {item['name']}").add_to(m)
                    st.toast("⚡ Şebeke verileri yüklendi!", icon="✅")
                else:
                    try:
                        folium.GeoJson(geojson_path, name="Şebeke (Standart)",
                                       style_function=lambda x: {'color': 'red', 'weight': 2, 'opacity': 0.5},
                                       tooltip="Enerji Nakil Hattı").add_to(m)
                        st.toast("⚡ Standart şebeke verisi yüklendi.", icon="ℹ️")
                    except Exception as e:
                        st.error(f"Veri hatası: {e}")

        if st.session_state.parsel_geojson:
            tooltip_text = "Proje Alanı"
            if st.session_state.layout_data:
                l_data = st.session_state.layout_data
                area_m2 = l_data.get('area_m2', 0)
                tooltip_text = f"TOPLAM PROJE:<br>Alan: {area_m2:,.0f} m²<br>Panel: {l_data['count']} Adet<br>Güç: {l_data['capacity_kw']} kWp"
            folium.GeoJson(st.session_state.parsel_geojson,
                           style_function=lambda x: {'fillColor': '#ffaf00', 'color': '#ff4500', 'weight': 3,
                                                     'fillOpacity': 0.1}, tooltip=tooltip_text).add_to(m)

        if st.session_state.layout_data:
            l_data = st.session_state.layout_data
            if "kiosk" in l_data:
                folium.Polygon(locations=l_data["kiosk"], color="#444444", fill=True, fill_color="#777777",
                               fill_opacity=0.9, popup="Trafo Köşkü").add_to(m)

            current_panel_data = PANEL_LIBRARY[st.session_state.selected_panel_brand][
                st.session_state.get('selected_panel_model',
                                     list(PANEL_LIBRARY[st.session_state.selected_panel_brand].keys())[0])]

            geojson_features = []
            for p_coords in l_data["panels"]:
                swapped = [[c[1], c[0]] for c in p_coords]
                geojson_features.append({
                    "type": "Feature", "geometry": {"type": "Polygon", "coordinates": [swapped]},
                    "properties": {
                        "model": f"{st.session_state.selected_panel_brand} {st.session_state.get('selected_panel_model', '')}",
                        "pmax": f"{current_panel_data['p_max']} Wp", "voc": f"{current_panel_data['voc']} V",
                        "isc": f"{current_panel_data['isc']} A", "eff": f"%{current_panel_data.get('eff', '21')}"
                    }
                })
            panel_tooltip = folium.GeoJsonTooltip(fields=["model", "pmax", "voc", "isc", "eff"],
                                                  aliases=["Model:", "Güç:", "Voc:", "Isc:", "Verim:"],
                                                  style="background-color: white; border: 1px solid black; border-radius: 3px; font-weight: bold;")
            folium.GeoJson({"type": "FeatureCollection", "features": geojson_features},
                           style_function=lambda x: {'fillColor': '#2b8cbe', 'color': '#1c5a7a', 'weight': 1,
                                                     'fillOpacity': 0.7}, tooltip=panel_tooltip).add_to(m)

        output = st_folium(m, height=550, width="100%", returned_objects=["last_clicked"], key="main_map")
        if output and output['last_clicked']:
            clat, clon = output['last_clicked']['lat'], output['last_clicked']['lng']
            if abs(clat - st.session_state.lat) > 0.0001: update_from_map(clat, clon); st.rerun()

    with col2:
        st.subheader("📊 Analiz Sonuçları")
        with st.spinner('Analiz ediliyor...'):
            rakim, egim, baki = calculate_slope_aspect(st.session_state.lat, st.session_state.lon)

            # --- CALCULATIONS MODÜLÜNDEN GELEN FONKSİYON ---
            s_col, s_msg, s_icon, a_col, a_msg, a_icon = get_suitability_badge(egim, baki)

            k1, k2 = st.columns(2)
            k1.metric("Rakım", f"{rakim} m")
            k2.metric("Eğim", f"%{egim}")

            st.markdown(f"""
            <div style="display: flex; gap: 10px; margin-bottom: 10px;">
                <div style="flex:1; padding: 10px; border-radius: 5px; background-color: {'#d4edda' if s_col == 'green' else '#fff3cd' if s_col == 'orange' else '#f8d7da'}; border: 1px solid {s_col}; text-align: center;">
                    <div style="font-size: 1.2rem;">{s_icon}</div>
                    <div style="font-weight: bold; font-size: 0.9rem; color: {s_col};">Eğim: {s_msg}</div>
                </div>
                <div style="flex:1; padding: 10px; border-radius: 5px; background-color: {'#d4edda' if a_col == 'green' else '#fff3cd' if a_col == 'orange' else '#f8d7da'}; border: 1px solid {a_col}; text-align: center;">
                    <div style="font-size: 1.2rem;">{a_icon}</div>
                    <div style="font-weight: bold; font-size: 0.9rem; color: {a_col};">Cephe: {baki}</div>
                    <div style="font-size: 0.8rem; color: #666;">({a_msg})</div>
                </div>
            </div>
            """, unsafe_allow_html=True)

            st.markdown("---")
            with st.expander("🔌 Tasarım & Yerleşim", expanded=True):

                elec_price = st.number_input("Birim Fiyat ($/kWh)", value=0.130, format="%.3f",
                                             help="Satış veya mahsuplaşma fiyatı.")

                p_brands = list(PANEL_LIBRARY.keys())
                sel_p_brand = st.selectbox("Panel Markası:", p_brands, index=p_brands.index(
                    st.session_state.selected_panel_brand) if st.session_state.selected_panel_brand in p_brands else 0)
                st.session_state.selected_panel_brand = sel_p_brand

                p_models = list(PANEL_LIBRARY[sel_p_brand].keys())
                default_model_index = 0
                if 'selected_panel_model' in st.session_state and st.session_state.selected_panel_model in p_models: default_model_index = p_models.index(
                    st.session_state.selected_panel_model)
                sel_p_model = st.selectbox("Panel Modeli:", p_models, index=default_model_index)
                st.session_state.selected_panel_model = sel_p_model

                current_panel_data = PANEL_LIBRARY[sel_p_brand][sel_p_model]

                i_brands = list(INVERTER_LIBRARY.keys())
                sel_i_brand = st.selectbox("İnverter Markası:", i_brands, index=i_brands.index(
                    st.session_state.selected_inverter_brand) if st.session_state.selected_inverter_brand in i_brands else 0)
                st.session_state.selected_inverter_brand = sel_i_brand

                i_models = list(INVERTER_LIBRARY[sel_i_brand].keys())
                sel_i_model = st.selectbox("İnverter Modeli:", i_models)
                current_inverter_data = INVERTER_LIBRARY[sel_i_brand][sel_i_model]

                with st.expander("⚙️ Konstrüksiyon & Saha Ayarları"):
                    c_s1, c_s2 = st.columns(2)
                    sb = c_s1.slider("Çekme Payı (m)", 0.0, 10.0, 5.0)
                    rs = c_s2.slider("Sıra Arası Gölge Boşluğu (m)", 1.0, 8.0, 3.5)
                    c_s3, c_s4 = st.columns(2)
                    table_options = ["2x20 (40 Panel) - Standart Düz Arazi", "2x15 (30 Panel) - Orta Ölçek",
                                     "2x10 (20 Panel) - Parçalı Arazi", "2x5  (10 Panel) - Çok Engebeli Arazi",
                                     "1x20 (20 Panel) - Tekli Sıra (1P)", "1x15 (15 Panel) - Tekli Sıra (1P)",
                                     "1x10 (10 Panel) - Tekli Sıra (1P)"]
                    tt = c_s3.selectbox("Sehpa Tipi (Konstrüksiyon)", table_options, index=0)
                    parts = tt.split(' ')[0].split('x');
                    t_rows = int(parts[0]);
                    t_cols = int(parts[1])
                    col_sp = c_s4.slider("Masa Arası Yan Boşluk (m)", 0.1, 5.0, 0.5, step=0.1)
                    kw, kh = st.number_input("Trafo Gen/Derinlik (m)", value=6.0), st.number_input("Trafo Derinlik (m)",
                                                                                                   value=3.0)

                c1, c2 = st.columns(2)

                if c1.button("⚡ String Hesabı"):
                    if has_permission(st.session_state.user_role, "electrical_engine"):
                        results = perform_string_analysis(st.session_state.lat, st.session_state.lon,
                                                          current_panel_data, current_inverter_data)
                        st.success(f"Max String: **{results['max_string_size']}** Panel")
                        st.markdown(f"❄️ Tasarım Sıcaklığı: **{results['design_temp']} °C**")
                        st.caption(
                            "ℹ️ *Bu değer, Open-Meteo veritabanından bölgenin **son 30 yıllık** en düşük sıcaklık verisi taranarak hesaplanmıştır.*")
                        st.markdown(f"⚡ Panel Voc Max: **{results['panel_voc_max']} V**")
                    else:
                        st.error("🔒 **Özellik Kilitli**")
                        st.warning("Mühendislik hesaplamaları **Ultra** pakete dahildir.")

                if c2.button("🏗️ Yerleşimi Gör"):
                    if has_permission(st.session_state.user_role, "panel_placement"):
                        if st.session_state.parsel_geojson:
                            p_w = current_panel_data.get("width", 1.134)
                            p_h = current_panel_data.get("height", 2.279)
                            res = SolarLayoutEngine(
                                st.session_state.parsel_geojson["features"][0]["geometry"]).generate_layout(
                                panel_width=p_w, panel_height=p_h, setback=sb, row_spacing=rs, col_spacing=col_sp,
                                table_rows=t_rows, table_cols=t_cols, kiosk_w=kw, kiosk_h=kh)
                            st.session_state.layout_data = res
                            st.rerun()
                        else:
                            st.error("Lütfen önce parsel yükleyin!")
                    else:
                        st.error("🔒 **Özellik Kilitli**")
                        st.warning("Otomatik yerleşim **Ultra** pakete dahildir. Paketinizi yükseltin.")

                if st.session_state.layout_data:
                    st.info(
                        f"Panel: {st.session_state.layout_data['count']} Adet | Güç: {st.session_state.layout_data['capacity_kw']} kWp")

            if has_permission(st.session_state.user_role, "financials"):
                if st.session_state.layout_data:
                    kw_power = st.session_state.layout_data['capacity_kw']
                else:
                    kw_power = 100

                pot = get_solar_potential(st.session_state.lat, st.session_state.lon, baki, kw_power, egim, rakim,
                                          elec_price=elec_price)
                if pot:
                    st.metric("Yıllık Üretim", f"{int(pot[0]):,} kWh", help=f"Hesaplanan Güç: {kw_power} kWp")
                    st.metric("ROI", f"{pot[3]} Yıl")

                    if not st.session_state.layout_data:
                        st.caption(
                            "⚠️ *Hesaplama varsayılan **100 kWp** üzerinden yapılmıştır. Gerçek değerler için 'Yerleşimi Gör' butonunu kullanın.*")

                    if st.button("📊 Raporu Oluştur"):
                        st.session_state.pdf_bytes = generate_full_report(st.session_state.lat, st.session_state.lon,
                                                                          rakim, egim, baki, kw_power, pot[0], pot[1],
                                                                          pot[2], pot[3], pot[4],
                                                                          st.session_state.username,
                                                                          st.session_state.user_role, secim,
                                                                          generate_earnings_graph(*pot[:4]),
                                                                          generate_horizon_plot(st.session_state.lat,
                                                                                                st.session_state.lon),
                                                                          get_projection_data(*pot[:3]))
                    if "pdf_bytes" in st.session_state: st.download_button("📥 PDF İndir", st.session_state.pdf_bytes,
                                                                           f"Rapor_{datetime.now().strftime('%Y%m%d')}.pdf",
                                                                           "application/pdf")
            else:
                st.warning("🔒 **Finansal Analiz Kısıtlı**")
                st.info("Yıllık üretim tahmini, ROI hesabı ve PDF raporlama için **Pro** pakete geçiniz.")

    with col1:
        st.markdown("---")
        horizon_graph = generate_horizon_plot(st.session_state.lat, st.session_state.lon)
        if horizon_graph:
            st.markdown("### 🏔️ Ufuk Analizi")
            st.image(horizon_graph, width="stretch")

            df_hor = get_horizon_analysis(st.session_state.lat, st.session_state.lon)
            if df_hor is not None:
                max_ang_str, loss_factor = get_shading_metrics(df_hor)
                try:
                    val = float(max_ang_str.split('°')[0])
                except:
                    val = 0
                stat, col, msg = evaluate_shading_suitability(val)
                loss_pct = round((1 - loss_factor) * 100, 1)

                st.markdown(f"""
                <div style="background-color: #f8f9fa; padding: 15px; border-radius: 8px; border-left: 5px solid {col}; box-shadow: 0 2px 4px rgba(0,0,0,0.1);">
                    <h5 style="margin-top:0; color: #333; font-size: 1rem;">📉 Gölge Risk Raporu</h5>
                    <div style="font-size: 0.9rem; color: #444; line-height: 1.6;">
                        • <b>En Yüksek Engel:</b> {max_ang_str}<br>
                        • <b>Tahmini Kayıp:</b> %{loss_pct}<br>
                        • <b>Sonuç:</b> <strong style="color: {col};">{stat}</strong> — <i>{msg}</i>
                    </div>
                </div>
                """, unsafe_allow_html=True)