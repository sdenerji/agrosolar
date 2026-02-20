import os
import streamlit as st
import pandas as pd
import json
import time
from datetime import datetime
from streamlit_folium import st_folium
import folium
import matplotlib.pyplot as plt
import matplotlib
from shapely.geometry import shape

# --- MODÜL IMPORTLARI ---
from db_base import get_supabase
from ui_utils import (hide_header_footer, render_google_login,
                      render_announcement_banner, render_admin_announcement_editor)
from auth_ui import show_auth_pages
from ai_service import generate_smart_report_summary
from gis_service import process_parsel_geojson, get_basemaps, fetch_pvgis_horizon, get_pvgis_production
from map_manager import create_base_map, add_teias_layer, add_parsel_layer, add_panel_layer
from calculations import (
    calculate_slope_aspect, get_solar_potential, transform_points, get_utm_zone_epsg,
    calculate_geodesic_area, calculate_bankability_metrics, generate_horizon_plot,
    generate_earnings_graph, generate_parsel_plot, get_shading_metrics,
    evaluate_shading_suitability, interpret_shading, get_suitability_badge,
    smart_fix_coordinates
)
from equipment_db import PANEL_LIBRARY, INVERTER_LIBRARY
from ges_engine import perform_string_analysis
from layout_engine import SolarLayoutEngine
from reports import generate_full_report
from profile_page import show_profile_page
from user_config import ROLE_PERMISSIONS, has_permission
from session_manager import handle_session_limit
from supabase import create_client
from user_service import check_and_update_subscription

try:
    from cut_fill_3d import show_3d_page
except ImportError:
    def show_3d_page():
        st.error("⚠️ 'cut_fill_3d.py' modülü yüklenemedi.")

matplotlib.use('Agg')

# --------------------------------------------------------------------------
# 🎯 SUPABASE & GOOGLE OTURUM YAKALAYICI
# --------------------------------------------------------------------------
supabase = get_supabase()

# --------------------------------------------------------------------------
# 🎯 SUPABASE & GOOGLE OTURUM YAKALAYICI (PYTHON KISMI)
# --------------------------------------------------------------------------
import time

# OTURUMU AÇMA (Sadece bu kalacak)
query_params = st.query_params
if "access_token" in query_params:
    try:
        supabase.auth.set_session(query_params["access_token"], query_params.get("refresh_token", ""))
        st.query_params.clear()
        time.sleep(0.5)
        st.rerun()
    except Exception as e:
        print(f"Oturum doğrulama hatası: {e}")

# 3. MEVCUT OTURUM KONTROLÜ
def check_active_session():
    try:
        session = supabase.auth.get_session()
        if session and session.user:
            return session.user
    except:
        return None


current_user = check_active_session()

if current_user:
    st.session_state.logged_in = True
    st.session_state.user_id = current_user.id
    st.session_state.user_email = current_user.email
    if 'full_name' in current_user.user_metadata:
        st.session_state.username = current_user.user_metadata['full_name']

    try:
        user_data = supabase.table("users").select("role").eq("id", current_user.id).execute()
        st.session_state.user_role = user_data.data[0].get("role", "Free") if user_data.data else "Free"
    except:
        st.session_state.user_role = "Free"

# --------------------------------------------------------------------------
# 🎯 KRİTİK: HATA ÖNLEYİCİ BAŞLATMA (INITIALIZATION)
# --------------------------------------------------------------------------
if 'initialized' not in st.session_state:
    st.session_state.initialized = True
    defaults = {
        'page': 'analiz', 'lat': 40.5850, 'lon': 36.9450, 'input_lat': 40.5850, 'input_lon': 36.9450,
        'elec_price': 0.130, 'unit_capex': 700.0, 'logged_in': False, 'user_role': "Free",
        'username': "Misafir", 'parsel_geojson': None, 'parsel_location': None,
        'layout_data': None, 'report_package': None, 'analysis_results': {}, 'string_results': None,
        'map_initialized': False, 'horizon_data': None, 'pvgis_yield_data': None, 'panel_tilt': 30,
        'last_processed_file': None, 'map_updater': False
    }
    for k, v in defaults.items():
        if k not in st.session_state: st.session_state[k] = v

# Kütüphane Seçimleri (Hata Önleyici)
if 'selected_panel_brand' not in st.session_state:
    st.session_state.selected_panel_brand = list(PANEL_LIBRARY.keys())[0]
if 'selected_panel_model' not in st.session_state:
    st.session_state.selected_panel_model = list(PANEL_LIBRARY[st.session_state.selected_panel_brand].keys())[0]
if 'selected_inverter_brand' not in st.session_state:
    st.session_state.selected_inverter_brand = list(INVERTER_LIBRARY.keys())[0]

# --------------------------------------------------------------------------
# AYARLAR VE OTURUM
# --------------------------------------------------------------------------
st.set_page_config(page_title="SD Enerji", layout="wide")
hide_header_footer()
if st.session_state.logged_in:
    handle_session_limit()


def update_from_input():
    st.session_state.lat, st.session_state.lon = st.session_state.input_lat, st.session_state.input_lon


def update_from_map(clicked_lat, clicked_lon):
    st.session_state.lat, st.session_state.lon = clicked_lat, clicked_lon
    st.session_state.map_updater = True


# --------------------------------------------------------------------------
# GLOBAL SIDEBAR
# --------------------------------------------------------------------------
with st.sidebar:
    if os.path.exists("assets/logo.png"): st.image("assets/logo.png", width="stretch")
    st.markdown("<h2 style='text-align: center; margin-top: -15px;'>SD ENERJİ</h2>", unsafe_allow_html=True)
    st.divider()

    if st.session_state.logged_in:
        role_label = ROLE_PERMISSIONS.get(st.session_state.user_role, {}).get("label", st.session_state.user_role)
        st.success(f"👤 {st.session_state.username}")
        st.info(f"🛡️ Paket: **{role_label}**")
        c1, c2 = st.columns(2)
        if c1.button("🏠 Analiz", use_container_width=True): st.session_state.page = 'analiz'; st.rerun()
        if c2.button("👤 Profil", use_container_width=True): st.session_state.page = 'profil'; st.rerun()
        if st.button("Çıkış Yap", type="primary", use_container_width=True):
            supabase.auth.sign_out()
            st.session_state.logged_in = False
            st.rerun()
    else:
        # Eğer giriş yapılmamışsa sadece Login Formunu Göster
        show_auth_pages(supabase)

        render_google_login()

    st.divider()

    # Menünün Geri Kalanı (Değişiklik Yok)
    st.markdown("### 📍 Konum & Parsel")
    t_m, t_p = st.tabs(["📌 Manuel", "🗺️ Parsel"])

    with t_m:
        st.number_input("Enlem", key='input_lat', format="%.6f", on_change=update_from_input)
        st.number_input("Boylam", key='input_lon', format="%.6f", on_change=update_from_input)

    with t_p:
        with st.expander("❓ GeoJSON Nasıl İndirilir?", expanded=False):
            st.markdown("""
            1. **[TKGM Parsel Sorgu](https://parselsorgu.tkgm.gov.tr/)** sitesine gidin.
            2. Parselinizi bulun ve seçin.
            3. Sağ üstteki **Üç Nokta (...)** ikonuna tıklayın.
            4. **GeoJSON** formatını seçip indirin.
            5. Dosyayı aşağıdaki alana yükleyin.
            """)
        uploaded_file = st.file_uploader("Dosyayı Buraya Sürükleyin", type=["geojson", "json"])
        if uploaded_file and has_permission(st.session_state.user_role, "panel_placement"):
            if st.session_state.get('last_processed_file') != uploaded_file.name:
                geojson_data = json.load(uploaded_file)
                p_lat, p_lon, loc_data, success, msg = process_parsel_geojson(geojson_data)
                if success:
                    st.session_state.lat, st.session_state.lon = p_lat, p_lon
                    st.session_state.parsel_geojson, st.session_state.parsel_location = geojson_data, loc_data
                    st.session_state.last_processed_file = uploaded_file.name
                    st.session_state.map_initialized = False;
                    st.rerun()
                else:
                    st.error(msg)
        elif uploaded_file:
            st.error("🔒 Dosya işleme Professional/Ultra pakete özeldir.")

    st.divider()
    st.markdown("### 🛠️ Mühendislik Araçları")
    if st.button("🌐 Koordinat Dönüşümü", use_container_width=True):
        if has_permission(st.session_state.user_role, "coord_transform"):
            st.session_state.page = 'coord_tool';
            st.rerun()
        else:
            st.warning("🔒 Ultra paket gereklidir.")

    if st.button("🚀 3D Arazi Analizi", use_container_width=True):
        if has_permission(st.session_state.user_role, "3d_srtm"):
            st.session_state.page = '3d_analiz';
            st.rerun()
        else:
            st.warning("🔒 Pro paket gereklidir.")

    st.divider()
    st.caption("Mühendislik ve Veri Güvenliği")
    st.sidebar.page_link("https://www.sdenerji.com/gizlilik-politikasi/", label="⚖️ Gizlilik Politikası", icon="📜")
    st.sidebar.page_link("https://www.sdenerji.com/kullanim-sartlari/", label="🛡️ Kullanım Şartları", icon="📑")

# --------------------------------------------------------------------------
# 🎯 SAYFA AKIŞI (ROUTING)
# --------------------------------------------------------------------------
if not st.session_state.logged_in:
    # Kullanıcı giriş yapmamışsa sadece bir karşılama ekranı göster
    st.title("⚡ SD Enerji Analiz App")
    st.info("Sisteme erişmek için sol taraftaki menüden giriş yapınız.")
    st.markdown("---")
    st.markdown(
        "SD Enerji Analiz App; profesyonel GES tasarımı, 3D arazi modelleme ve teknik raporlama sunan bir mühendislik platformudur.")

    import streamlit.components.v1 as components

    components.html("""
        <script>
            var targetWindow = window.parent || window;
            var hash = targetWindow.location.hash;

            // Eğer URL'de başarılı giriş şifresi varsa bu butonu çiz
            if (hash && hash.includes("access_token=")) {
                var newUrl = targetWindow.location.origin + targetWindow.location.pathname + hash.replace('#', '?');
                document.write(`
                    <div style="display:flex; flex-direction:column; justify-content:center; align-items:center; padding:30px; font-family:sans-serif; background-color:#f8f9fa; border-radius:10px; border:2px dashed #1a73e8; margin-top:20px;">
                        <h2 style="color:#2c3e50; margin-bottom:10px;">✅ Google Onayı Başarılı</h2>
                        <p style="color:#7f8c8d; margin-bottom:20px;">Streamlit güvenlik duvarını aşmak için lütfen aşağıdaki butona tıklayın.</p>
                        <a href="${newUrl}" target="_top" style="background-color:#1a73e8; color:white; padding:12px 25px; text-decoration:none; border-radius:5px; font-weight:bold; font-size:16px; box-shadow: 0 4px 6px rgba(0,0,0,0.1);">
                            🚀 Platforma Giriş Yap
                        </a>
                    </div>
                `);
            }
        </script>
        """, height=250)

elif st.session_state.page == 'profil':
    show_profile_page()

elif st.session_state.page == 'coord_tool':
    # Koordinat Sayfası Kodları (Değişiklik Yok)
    st.title("🌐 Koordinat Dönüşüm İstasyonu (Ultra)")
    st.markdown("---")
    st.info(
        "💡 Nokta listesini (NCN, CSV, TXT) veya GeoJSON dosyasını yükleyin. Sistem koordinatlarınızı otomatik tanıyacaktır.")
    ext_file = st.file_uploader("Dosya Yükle", type=["json", "geojson", "ncn", "csv", "txt"])

    is_detected = False
    detected_sys = "WGS84 (GPS/Coğrafi)"
    points_to_convert = []

    if ext_file:
        try:
            file_name = ext_file.name.lower()
            if file_name.endswith(('json', 'geojson')):
                data = json.load(ext_file)
                points_to_convert = data['features'][0]['geometry']['coordinates'][0]
            elif file_name.endswith('ncn'):
                for line in ext_file.read().decode('utf-8').splitlines():
                    parts = line.split()
                    if len(parts) >= 3: points_to_convert.append((float(parts[1]), float(parts[2])))
            elif file_name.endswith(('csv', 'txt')):
                df_temp = pd.read_csv(ext_file, header=None)
                points_to_convert = df_temp.values.tolist()

            if points_to_convert:
                points_to_convert = smart_fix_coordinates(points_to_convert)
                st.success(f"📂 {len(points_to_convert)} adet nokta okundu.")
                first_val = points_to_convert[0][0]
                if abs(first_val) < 100:
                    detected_sys = "WGS84 (GPS/Coğrafi)"
                    st.success("✅ **WGS84 (Coğrafi)** koordinatlar algılandı. Giriş sistemi kilitlendi.")
                    is_detected = True
                else:
                    detected_sys = "ITRF (UTM)"
                    st.warning("📂 Metrik koordinatlar algılandı. Lütfen giriş sistemini (ITRF/ED50) teyit edin.")
        except Exception as e:
            st.error(f"❌ Okuma hatası: {str(e)}")

    col_set1, col_set2 = st.columns(2)
    with col_set1:
        input_sys = st.selectbox("Giriş Sistemi:", ["WGS84 (GPS/Coğrafi)", "ITRF (UTM)", "ED50 (UTM)"],
                                 index=0 if detected_sys == "WGS84 (GPS/Coğrafi)" else 1,
                                 disabled=is_detected)
    with col_set2:
        target_sys = st.selectbox("Hedef Sistem:", ["ITRF (Modern/UTM)", "ED50 (Klasik/UTM)", "WGS84 (Coğrafi)"])

    if st.button("🚀 Dönüşümü Başlat ve Listele", use_container_width=True):
        if not points_to_convert:
            st.error("⚠️ Lütfen önce bir dosya yükleyin!")
        else:
            in_epsg = 4326 if "WGS84" in input_sys else get_utm_zone_epsg(st.session_state.lon, input_sys.split(' ')[0])
            out_epsg = 4326 if "WGS84" in target_sys else get_utm_zone_epsg(st.session_state.lon,
                                                                            target_sys.split(' ')[0])
            res_points = transform_points(points_to_convert, in_epsg, out_epsg)
            if res_points:
                y_label = "Boylam" if out_epsg == 4326 else "Sağa (Y) Değeri"
                x_label = "Enlem" if out_epsg == 4326 else "Yukarı (X) Değeri"
                df_res = pd.DataFrame(res_points, columns=[y_label, x_label])
                st.subheader(f"📍 Dönüşüm Sonuçları (EPSG:{out_epsg})")
                st.table(df_res.head(15))
                st.download_button("📥 Tam Listeyi CSV İndir", df_res.to_csv(index=False), "sd_enerji_donusum.csv",
                                   use_container_width=True)

    st.divider()
    if st.button("⬅️ Analiz Sayfasına Dön", use_container_width=True):
        st.session_state.page = 'analiz';
        st.rerun()

elif st.session_state.page == '3d_analiz':
    if has_permission(st.session_state.user_role, "3d_precision_data"):
        show_3d_page()

else:
    # --- ANA ANALİZ EKRANI (DASHBOARD) ---
    st.title("⚡ SD Enerji Analiz App")
    st.info(
        "SD Enerji Analiz App; profesyonel GES tasarımı, 3D arazi modelleme ve teknik raporlama sunan bir mühendislik platformudur.")
    render_announcement_banner()
    st.divider()

    col1, col2 = st.columns([2, 1])

    rakim, egim, baki = calculate_slope_aspect(st.session_state.lat, st.session_state.lon)
    real_area_m2 = calculate_geodesic_area(st.session_state.parsel_geojson)

    if st.session_state.horizon_data is None or st.session_state.get('last_lat') != st.session_state.lat:
        st.session_state.horizon_data, st.session_state.last_lat = fetch_pvgis_horizon(st.session_state.lat,
                                                                                       st.session_state.lon), st.session_state.lat

    res_prod, res_roi, res_cost, res_pot = 0, 0, 0, None
    if st.session_state.layout_data:
        kw_p = st.session_state.layout_data['capacity_kw']
        pvgis_val = st.session_state.pvgis_yield_data['specific_yield'] if st.session_state.pvgis_yield_data else None
        res_pot = get_solar_potential(st.session_state.lat, st.session_state.lon, baki, kw_p, egim, rakim,
                                      elec_price=st.session_state.elec_price, fetched_yield=pvgis_val,
                                      unit_capex=st.session_state.unit_capex)
        if res_pot:
            res_prod, res_cost, res_roi = res_pot[0], res_pot[2], res_pot[3]
            st.session_state.analysis_results = {"production": res_prod, "roi": res_roi, "cost": res_cost,
                                                 "area": real_area_m2, "pot_data": res_pot}

    with col1:
        basemaps = get_basemaps();
        secim = st.radio("Görünüm", list(basemaps.keys()), horizontal=True, label_visibility="collapsed")
        m = create_base_map(st.session_state.lat, st.session_state.lon, basemaps[secim],
                            auto_locate=(not st.session_state.map_initialized) and (
                                        st.session_state.parsel_geojson is None))
        st.session_state.map_initialized = True
        if st.toggle("⚡ Şebekeyi Göster") and has_permission(st.session_state.user_role, "tm_proximity"):
            add_teias_layer(m)

        add_parsel_layer(m, st.session_state.parsel_geojson, st.session_state.analysis_results,
                         st.session_state.layout_data)
        add_panel_layer(m, st.session_state.layout_data, st.session_state.selected_panel_brand,
                        st.session_state.selected_panel_model)

        out = st_folium(m, height=550, width="100%", returned_objects=["last_clicked"], key="main_map")
        if out and out['last_clicked']:
            if abs(out['last_clicked']['lat'] - st.session_state.lat) > 0.0001:
                update_from_map(out['last_clicked']['lat'], out['last_clicked']['lng']);
                st.rerun()

    with col2:
        st.subheader("📊 Analiz Sonuçları")
        s_col, s_msg, s_icon, a_col, a_msg, a_icon = get_suitability_badge(egim, baki)
        k1, k2 = st.columns(2);
        k1.metric("Rakım", f"{rakim} m");
        k2.metric("Eğim", f"%{egim}")
        st.markdown(
            f"""<div style="display: flex; gap: 10px; margin-bottom: 10px;"><div style="flex:1; padding: 10px; border-radius: 5px; background-color: {'#d4edda' if s_col == 'green' else '#fff3cd' if s_col == 'orange' else '#f8d7da'}; border: 1px solid {s_col}; text-align: center;"><div style="font-size: 1.2rem;">{s_icon}</div><div style="font-weight: bold; font-size: 0.9rem; color: {s_col};">Eğim: {s_msg}</div></div><div style="flex:1; padding: 10px; border-radius: 5px; background-color: {'#d4edda' if a_col == 'green' else '#fff3cd' if a_col == 'orange' else '#f8d7da'}; border: 1px solid {a_col}; text-align: center;"><div style="font-size: 1.2rem;">{a_icon}</div><div style="font-weight: bold; font-size: 0.9rem; color: {a_col};">Cephe: {baki}</div></div></div>""",
            unsafe_allow_html=True)

        with st.expander("🔌 Tasarım & Yerleşim", expanded=True):
            st.session_state.elec_price = st.number_input("Satış ($/kWh)", value=st.session_state.elec_price,
                                                          format="%.3f")
            p_brand = st.selectbox("Panel:", list(PANEL_LIBRARY.keys()));
            st.session_state.selected_panel_brand = p_brand
            p_model = st.selectbox("Model:", list(PANEL_LIBRARY[p_brand].keys()));
            st.session_state.selected_panel_model = p_model
            i_brand = st.selectbox("İnverter:", list(INVERTER_LIBRARY.keys()));
            sel_i_model = st.selectbox("Model:", list(INVERTER_LIBRARY[i_brand].keys()))
            st.session_state.selected_inverter_model = sel_i_model

            tt = st.selectbox("Sehpa", ["2x20 (40 Panel)", "2x10 (20 Panel)", "2x5 (10 Panel)", "1x5 (5 Panel)"],
                              index=2)
            t_r, t_c = int(tt.split(' ')[0].split('x')[0]), int(tt.split(' ')[0].split('x')[1])

            if st.button("🚀 Hesapla ve Yerleştir", type="primary", use_container_width=True):
                if not st.session_state.parsel_geojson:
                    st.error("⚠️ Önce bir parsel yüklemelisiniz! Sol menüdeki '🗺️ Parsel' sekmesini kullanın.")
                elif not has_permission(st.session_state.user_role, "panel_placement"):
                    st.warning("🔒 Bu özellik Professional pakete dahildir.")
                else:
                    with st.spinner("Hesaplanıyor..."):
                        l_res = SolarLayoutEngine(
                            st.session_state.parsel_geojson["features"][0]["geometry"]).generate_layout(
                            panel_width=PANEL_LIBRARY[p_brand][p_model].get("width", 1.134),
                            panel_height=PANEL_LIBRARY[p_brand][p_model].get("height", 2.279), setback=1.0,
                            row_spacing=3.5, col_spacing=0.5, table_rows=t_r, table_cols=t_c)
                        st.session_state.layout_data = l_res;
                        st.rerun()

        if has_permission(st.session_state.user_role, "financials") and res_prod > 0:
            st.markdown("### 💰 Finansal Özet")
            st.metric("Üretim", f"{int(res_prod):,} kWh");
            st.metric("ROI", f"{res_roi} Yıl")
            if st.button("📊 Rapor Oluştur", use_container_width=True):
                rep_d = {"kwp": st.session_state.layout_data['capacity_kw'], "kwh": res_prod,
                         "username": st.session_state.username}
                if has_permission(st.session_state.user_role, "ai_report"): rep_d[
                    "ai_summary"] = generate_smart_report_summary(rep_d)
                st.session_state.pdf_bytes = generate_full_report(rep_d);
                st.success("🤖 Rapor Hazır!")
            if "pdf_bytes" in st.session_state:
                st.download_button("📥 PDF İndir", st.session_state.pdf_bytes, "rapor.pdf", "application/pdf",
                                   use_container_width=True)

    # 🏔️ Ufuk ve Gölge Analizi Grafiği
    with col1:
        st.markdown("---")
        if st.session_state.horizon_data is not None:
            horizon_graph_path = generate_horizon_plot(st.session_state.horizon_data)
            if horizon_graph_path:
                st.markdown("### 🏔️ Ufuk ve Gölge Analizi")
                st.image(horizon_graph_path, width="stretch")
                m_a, l_f = get_shading_metrics(st.session_state.horizon_data)
                stat, col, msg = evaluate_shading_suitability(float(m_a.split('°')[0]) if '°' in m_a else 0)
                st.markdown(
                    f'<div style="background-color: #f8f9fa; padding: 15px; border-left: 5px solid {col};"><b>📉 Gölge Risk Raporu</b><br>Engel: {m_a} | Kayıp: %{round((1 - l_f) * 100, 1)} | <strong style="color: {col};">{stat}</strong></div>',
                    unsafe_allow_html=True)