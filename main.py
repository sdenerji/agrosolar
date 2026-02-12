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
import math
from shapely.geometry import shape

# --- MODÜL IMPORTLARI ---
from db_base import get_supabase
from ui_utils import (hide_header_footer, render_google_login, render_analysis_box,
                      create_substation_popup, get_grid_color,
                      render_announcement_banner, render_admin_announcement_editor)
from auth_ui import show_auth_pages
from ai_service import generate_smart_report_summary

# Servisler
from gis_service import process_parsel_geojson, get_basemaps, fetch_pvgis_horizon, get_pvgis_production
from map_manager import create_base_map, add_teias_layer, add_parsel_layer, add_panel_layer

# Hesaplamalar (Tüm Fonksiyonlar Import Edildi)
from calculations import (
    calculate_slope_aspect,
    get_solar_potential,
    analyze_suitability,
    get_projection_data,
    generate_earnings_graph,
    generate_horizon_plot,
    generate_parsel_plot,
    get_shading_metrics,
    evaluate_shading_suitability,
    parse_grid_data,
    get_suitability_badge,
    calculate_bankability_metrics,
    calculate_geodesic_area,
    interpret_monthly_data,
    interpret_cash_flow,
    interpret_shading
)

from equipment_db import PANEL_LIBRARY, INVERTER_LIBRARY
from ges_engine import perform_string_analysis
from layout_engine import SolarLayoutEngine

from reports import generate_full_report
from profile_page import show_profile_page
from user_config import ROLE_PERMISSIONS, has_permission
from session_manager import handle_session_limit
from user_service import check_and_update_subscription

try:
    from cut_fill_3d import show_3d_page
except ImportError:
    def show_3d_page():
        st.error("⚠️ 'cut_fill_3d.py' modülü yüklenemedi.")

matplotlib.use('Agg')

# --------------------------------------------------------------------------
# AYARLAR VE OTURUM
# --------------------------------------------------------------------------
st.set_page_config(page_title="SD Enerji Analiz Platformu", layout="wide", page_icon="⚡",
                   initial_sidebar_state="expanded")
hide_header_footer()

# DEFAULT DEĞERLER
if 'page' not in st.session_state: st.session_state.page = 'analiz'
if 'lat' not in st.session_state or st.session_state.lat == 0: st.session_state.lat = 40.5850
if 'lon' not in st.session_state or st.session_state.lon == 0: st.session_state.lon = 36.9450
if 'input_lat' not in st.session_state or st.session_state.input_lat == 0: st.session_state.input_lat = 40.5850
if 'input_lon' not in st.session_state or st.session_state.input_lon == 0: st.session_state.input_lon = 36.9450

if 'elec_price' not in st.session_state: st.session_state.elec_price = 0.130
if 'unit_capex' not in st.session_state: st.session_state.unit_capex = 700.0

if 'logged_in' not in st.session_state: st.session_state.logged_in = False
if 'user_role' not in st.session_state: st.session_state.user_role = "Free"
if 'username' not in st.session_state: st.session_state.username = "Misafir"
if 'user_id' not in st.session_state: st.session_state.user_id = None
if 'parsel_geojson' not in st.session_state: st.session_state.parsel_geojson = None
if 'parsel_location' not in st.session_state: st.session_state.parsel_location = None
if 'layout_data' not in st.session_state: st.session_state.layout_data = None
if 'report_package' not in st.session_state: st.session_state.report_package = None
if 'analysis_results' not in st.session_state: st.session_state.analysis_results = {}
if 'string_results' not in st.session_state: st.session_state.string_results = None

# Harita, Veri ve PVGIS State'leri
if 'map_initialized' not in st.session_state: st.session_state.map_initialized = False
if 'horizon_data' not in st.session_state: st.session_state.horizon_data = None
if 'pvgis_yield_data' not in st.session_state: st.session_state.pvgis_yield_data = None
if 'panel_tilt' not in st.session_state: st.session_state.panel_tilt = 30

if 'selected_panel_brand' not in st.session_state: st.session_state.selected_panel_brand = list(PANEL_LIBRARY.keys())[0]
if 'selected_inverter_brand' not in st.session_state: st.session_state.selected_inverter_brand = \
    list(INVERTER_LIBRARY.keys())[0]


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
                if updated: st.rerun()
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


def logout():
    get_supabase().auth.sign_out()
    st.session_state.logged_in = False
    st.session_state.page = 'analiz'
    st.rerun()


def update_from_input():
    st.session_state.lat = st.session_state.input_lat
    st.session_state.lon = st.session_state.input_lon


def update_from_map(clicked_lat, clicked_lon):
    st.session_state.lat = clicked_lat
    st.session_state.lon = clicked_lon
    st.session_state.map_updater = True


# --------------------------------------------------------------------------
# SAYFA AKIŞI
# --------------------------------------------------------------------------
if st.session_state.page == 'profil':
    show_profile_page()
elif st.session_state.page == '3d_analiz':
    show_3d_page()
else:
    # --- SIDEBAR ---
    with st.sidebar:
        if os.path.exists("assets/logo.png"): st.image("assets/logo.png", width="stretch")
        st.markdown("<h2 style='text-align: center; margin-top: -15px;'>SD ENERJİ</h2>", unsafe_allow_html=True)
        st.divider()

        if st.session_state.logged_in:
            role_label = ROLE_PERMISSIONS.get(st.session_state.user_role, {}).get("label", st.session_state.user_role)
            st.success(f"👤 {st.session_state.username}")
            st.info(f"🛡️ Paket: **{role_label}**")
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
            st.info("TKGM GeoJSON dosyasını yükleyin.")
            uploaded_file = st.file_uploader("GeoJSON Yükle", type=["geojson", "json"])
            if uploaded_file:
                if st.session_state.get('last_processed_file') != uploaded_file.name:
                    if has_permission(st.session_state.user_role, "panel_placement"):
                        try:
                            geojson_data = json.load(uploaded_file)
                            # process_parsel_geojson artık 5 değer döndürüyor, burası DOĞRU
                            p_lat, p_lon, loc_data, success, msg = process_parsel_geojson(geojson_data)

                            if success:
                                st.session_state.lat, st.session_state.lon = p_lat, p_lon
                                st.session_state.parsel_geojson = geojson_data
                                st.session_state.parsel_location = loc_data  # Tapu bilgisini kaydet
                                st.session_state.layout_data = None
                                st.session_state.string_results = None
                                st.session_state.horizon_data = None
                                st.session_state.pvgis_yield_data = None
                                st.session_state.last_processed_file = uploaded_file.name
                                st.session_state.map_initialized = False  # Haritayı yenile
                                st.success(
                                    f"✅ Parsel: {loc_data.get('ilce', '')} / {loc_data.get('ada', '')}-{loc_data.get('parsel', '')}")
                                time.sleep(0.5);
                                st.rerun()
                            else:
                                st.error(msg)
                        except Exception as e:
                            st.error(f"Hata: {e}")
                    else:
                        st.error("🔒 **Dosya İşleme Kısıtlı**");
                        st.warning("Ultra pakete geçiniz.")
            else:
                if st.session_state.parsel_geojson is not None:
                    st.session_state.parsel_geojson = None
                    st.session_state.parsel_location = None
                    st.session_state.layout_data = None
                    st.session_state.string_results = None
                    st.session_state.last_processed_file = None
                    st.rerun()

        st.divider()
        if st.button("🚀 3D Arazi Analizi", use_container_width=True):
            st.session_state.page = '3d_analiz';
            st.rerun()

        try:
            admin_email = st.secrets["general"]["admin_email"]
        except:
            admin_email = None
        if st.session_state.get("logged_in") and st.session_state.get("user_email") == admin_email:
            st.divider()
            with st.expander("🛠️ Yönetici Paneli", expanded=False): render_admin_announcement_editor()

    # --- ANA EKRAN ---
    render_announcement_banner()
    st.title("⚡ SD Enerji Analiz Platformu")
    col1, col2 = st.columns([2, 1])

    # --- HESAPLAMALAR ---
    # Bu fonksiyon artık gerçek veriyi çekecek (calculations.py içindeki değişiklikle)
    rakim, egim, baki = calculate_slope_aspect(st.session_state.lat, st.session_state.lon)
    real_area_m2 = calculate_geodesic_area(st.session_state.parsel_geojson)

    # --- PVGIS UFUK ÇEKME ---
    if st.session_state.horizon_data is None or st.session_state.get('last_lat') != st.session_state.lat:
        with st.spinner("🌍 PVGIS Ufuk verisi çekiliyor..."):
            st.session_state.horizon_data = fetch_pvgis_horizon(st.session_state.lat, st.session_state.lon)
            st.session_state.last_lat = st.session_state.lat

    # --- ÜRETİM HESAPLAMA MOTORU ---
    res_prod = 0;
    res_roi = 0;
    res_cost = 0;
    res_pot = None
    if st.session_state.layout_data:
        kw_power = st.session_state.layout_data['capacity_kw']

        # PVGIS Verisi
        pvgis_val = None
        if st.session_state.pvgis_yield_data:
            pvgis_val = st.session_state.pvgis_yield_data['specific_yield']

        res_pot = get_solar_potential(
            st.session_state.lat, st.session_state.lon,
            baki, kw_power, egim, rakim,
            elec_price=st.session_state.elec_price,
            fetched_yield=pvgis_val,
            unit_capex=st.session_state.unit_capex
        )
        if res_pot:
            res_prod = res_pot[0];
            res_cost = res_pot[2];
            res_roi = res_pot[3]
            st.session_state.analysis_results = {
                "production": res_prod, "roi": res_roi, "cost": res_cost,
                "area": real_area_m2, "pot_data": res_pot
            }

    with col1:
        basemaps = get_basemaps()
        secim = st.radio("Görünüm", list(basemaps.keys()), horizontal=True, label_visibility="collapsed")
        selected_config = basemaps.get(secim, basemaps["Sokak (OSM)"])

        show_grid = False
        if st.toggle("⚡ Şebekeyi Göster", value=False):
            if has_permission(st.session_state.user_role, "grid_network_view"):
                show_grid = True
            else:
                st.toast("🔒 Pro özellik!", icon="🚫")

        # --- DÜZELTİLEN AUTO LOCATE MANTIĞI ---
        # Parsel Yüklüyse (geojson var) -> GPS KAPALI (False) -> Parsele odaklan
        # Parsel Yoksa (geojson yok) ve harita yeni açılıyorsa -> GPS AÇIK (True) -> Konuma git
        should_use_gps = (not st.session_state.map_initialized) and (st.session_state.parsel_geojson is None)

        m = create_base_map(st.session_state.lat, st.session_state.lon, selected_config, auto_locate=should_use_gps)
        st.session_state.map_initialized = True

        if show_grid:
            if add_teias_layer(m): st.toast("⚡ Şebeke yüklendi!", icon="✅")

        add_parsel_layer(m, st.session_state.parsel_geojson, st.session_state.analysis_results,
                         st.session_state.layout_data)

        panels_drawn = add_panel_layer(
            m, st.session_state.layout_data,
            st.session_state.selected_panel_brand,
            st.session_state.get('selected_panel_model', 'Standart')
        )

        if st.session_state.layout_data and not panels_drawn and st.session_state.layout_data.get('count', 0) == 0:
            st.toast("⚠️ Bu ayarlarla parsele panel sığmadı.", icon="ℹ️")

        output = st_folium(m, height=550, width="100%", returned_objects=["last_clicked"], key="main_map")
        if output and output['last_clicked']:
            if abs(output['last_clicked']['lat'] - st.session_state.lat) > 0.0001:
                update_from_map(output['last_clicked']['lat'], output['last_clicked']['lng']);
                st.rerun()

    with col2:
        st.subheader("📊 Analiz Sonuçları")
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
            </div>
        </div>""", unsafe_allow_html=True)

        if st.session_state.parsel_geojson:
            if st.session_state.pvgis_yield_data is None:
                with st.spinner("☀️ Optimum açı ve üretim verisi hesaplanıyor..."):
                    pv_res = get_pvgis_production(st.session_state.lat, st.session_state.lon, tilt=None)
                    if pv_res['success']:
                        st.session_state.pvgis_yield_data = pv_res
                        st.session_state.panel_tilt = int(pv_res['optimum_tilt'])
                        st.toast(f"Optimum Açı Bulundu: {st.session_state.panel_tilt}°", icon="📐")

        st.markdown("---")
        with st.expander("🔌 Tasarım & Yerleşim", expanded=True):

            c_fin1, c_fin2 = st.columns(2)
            st.session_state.elec_price = c_fin1.number_input("Satış Birim Fiyatı ($/kWh)",
                                                              value=st.session_state.elec_price, format="%.3f",
                                                              step=0.01)

            st.session_state.unit_capex = c_fin2.number_input("Birim Yatırım Maliyeti ($/kWp)",
                                                              value=st.session_state.unit_capex, format="%.0f",
                                                              step=50.0)

            p_brands = list(PANEL_LIBRARY.keys())
            sel_p_brand = st.selectbox("Panel Markası:", p_brands, index=p_brands.index(
                st.session_state.selected_panel_brand) if st.session_state.selected_panel_brand in p_brands else 0)
            st.session_state.selected_panel_brand = sel_p_brand
            p_models = list(PANEL_LIBRARY[sel_p_brand].keys())
            sel_p_model = st.selectbox("Panel Modeli:", p_models, index=0)
            st.session_state.selected_panel_model = sel_p_model
            current_panel_data = PANEL_LIBRARY[sel_p_brand][sel_p_model]

            i_brands = list(INVERTER_LIBRARY.keys())
            sel_i_brand = st.selectbox("İnverter Markası:", i_brands, index=i_brands.index(
                st.session_state.selected_inverter_brand) if st.session_state.selected_inverter_brand in i_brands else 0)
            st.session_state.selected_inverter_brand = sel_i_brand
            i_models = list(INVERTER_LIBRARY[sel_i_brand].keys())
            sel_i_model = st.selectbox("İnverter Modeli:", i_models)
            current_inverter_data = INVERTER_LIBRARY[sel_i_brand][sel_i_model]

            with st.expander("⚙️ Konstrüksiyon Ayarları", expanded=True):
                c_s1, c_s2 = st.columns(2)
                user_tilt = c_s1.slider("Panel Eğimi (°)", 0, 60, st.session_state.panel_tilt)
                if user_tilt != st.session_state.panel_tilt:
                    st.session_state.panel_tilt = user_tilt

                sb = c_s2.slider("Çekme Payı (m)", 0.0, 10.0, 1.0)
                rs = st.slider("Gölge Boşluğu (m)", 1.0, 8.0, 3.5)

                c_s3, c_s4 = st.columns(2)
                table_options = ["2x20 (40 Panel)", "2x15 (30 Panel)", "2x10 (20 Panel)", "2x5 (10 Panel)",
                                 "1x20 (20 Panel)", "1x10 (10 Panel)", "1x5 (5 Panel)"]
                tt = c_s3.selectbox("Sehpa Tipi", table_options, index=2)
                parts = tt.split(' ')[0].split('x');
                t_rows = int(parts[0]);
                t_cols = int(parts[1])
                col_sp = c_s4.slider("Yan Boşluk (m)", 0.1, 5.0, 0.5)

            if st.button("🚀 Hesapla ve Yerleştir", type="primary", use_container_width=True):
                if has_permission(st.session_state.user_role, "panel_placement"):
                    if st.session_state.parsel_geojson:
                        with st.spinner("☀️ Güneş verileri güncelleniyor..."):
                            fresh_pvgis = get_pvgis_production(st.session_state.lat, st.session_state.lon,
                                                               tilt=st.session_state.panel_tilt)
                            if fresh_pvgis['success']:
                                st.session_state.pvgis_yield_data = fresh_pvgis

                        p_w = current_panel_data.get("width", 1.134);
                        p_h = current_panel_data.get("height", 2.279)
                        layout_res = SolarLayoutEngine(
                            st.session_state.parsel_geojson["features"][0]["geometry"]).generate_layout(
                            panel_width=p_w, panel_height=p_h, setback=sb, row_spacing=rs, col_spacing=col_sp,
                            table_rows=t_rows, table_cols=t_cols
                        )
                        st.session_state.layout_data = layout_res
                        if has_permission(st.session_state.user_role, "electrical_engine"):
                            string_res = perform_string_analysis(st.session_state.lat, st.session_state.lon,
                                                                 current_panel_data, current_inverter_data)
                            st.session_state.string_results = string_res
                        st.rerun()
                    else:
                        st.error("Önce parsel yükleyin!")
                else:
                    st.error("🔒 **Kısıtlı**")

            if st.session_state.layout_data:
                l_data = st.session_state.layout_data
                st.info(f"Panel: {l_data['count']} Adet | Güç: {l_data['capacity_kw']} kWp")
                skipped = l_data.get('skipped_rows', 0)
                eng_note_text = None  # Varsayılan boş
                if skipped > 0:
                    # Detaylı açıklama geri eklendi
                    eng_note_text = (
                        f"Geometrik sınırlar ve çekme payları (Setback) nedeniyle {skipped} adet panel sırası parsele sığmamıştır. "
                        f"Çekme paylarını düşürmeyi veya daha küçük sehpa tiplerini (örn: 2x10 yerine 2x5) kullanmayı deneyebilirsiniz.")
                    st.warning(f"⚠️ Mühendislik Notu: {eng_note_text}")

            if st.session_state.string_results:
                st.success(f"⚡ String: {st.session_state.string_results.get('max_string_size', '-')} panel (Max)")

        if has_permission(st.session_state.user_role, "financials"):
            if res_prod > 0:
                st.markdown("### 💰 Finansal Özet")
                st.metric(label="Yıllık Üretim", value=f"{int(res_prod):,} kWh", delta="Tahmini")
                st.metric(label="Yatırım Maliyeti", value=f"{int(res_cost):,} $", delta_color="inverse")
                st.metric(label="ROI (Geri Dönüş)", value=f"{res_roi} Yıl", delta="Amortisman Süresi")

                bank_data = calculate_bankability_metrics(res_prod, res_cost, st.session_state.elec_price)

                # --- YORUM MOTORU ENTEGRASYONU ---
                from calculations import interpret_monthly_data, interpret_cash_flow, interpret_shading

                monthly_comment = ""
                if st.session_state.pvgis_yield_data:
                    monthly_comment = interpret_monthly_data(st.session_state.pvgis_yield_data['monthly_data'])

                cash_comment = interpret_cash_flow(res_roi, bank_data['npv'])

                shading_comment = ""
                if st.session_state.horizon_data is not None:
                    s_metrics = get_shading_metrics(st.session_state.horizon_data)
                    shading_comment = interpret_shading(s_metrics)

                st.session_state.report_package = {
                    "lat": st.session_state.lat, "lon": st.session_state.lon,
                    "kwp": kw_power if st.session_state.layout_data else 0,
                    "kwh": res_prod, "roi": res_roi, "cost": int(res_cost),
                    "irr": bank_data['irr'], "npv": bank_data['npv'],
                    "co2": bank_data['co2'], "trees": bank_data['trees'],
                    "cash_flow": bank_data['cash_flow'],
                    "slope": egim, "aspect": baki,
                    "panel_model": st.session_state.selected_panel_model,
                    "inv_model": sel_i_model,
                    "graph_path": generate_earnings_graph(*res_pot[:4]) if res_pot else None,
                    "map_type": secim,
                    "parsel_data": st.session_state.parsel_geojson,
                    "location_data": st.session_state.parsel_location,
                    "layout_data": st.session_state.layout_data,
                    "monthly_data": st.session_state.pvgis_yield_data[
                        'monthly_data'] if st.session_state.pvgis_yield_data else None,
                    "username": st.session_state.username if st.session_state.username else "Misafir",
                    # --- YENİ EKLENEN YORUMLAR ---
                    "monthly_comment": monthly_comment,
                    "cash_comment": cash_comment,
                    "shading_comment": shading_comment,
                    "engineering_note": eng_note_text
                }

                st.markdown("---")
                # --- RAPOR OLUŞTURMA BUTONU ---
                if st.button("📊 Rapor Oluştur", use_container_width=True):
                    if st.session_state.parsel_geojson:
                        with st.spinner("Yapay Zeka ve Rapor Hazırlanıyor..."):
                            # 1. Önce Veri Paketini (report_data) Oluşturalım
                            # (Burada tanımladığımız için artık "Unresolved Reference" hatası vermez)
                            bank_data = calculate_bankability_metrics(res_prod, res_cost, st.session_state.elec_price)

                            report_data = {
                                "lat": st.session_state.lat,
                                "lon": st.session_state.lon,
                                "kwp": kw_power,
                                "kwh": res_prod,
                                "roi": res_roi,
                                "cost": int(res_cost),
                                "irr": bank_data['irr'],
                                "npv": bank_data['npv'],
                                "co2": bank_data['co2'],  # <--- BU EKSİK SATIRI EKLEYİN
                                "trees": bank_data['trees'],
                                "cash_flow": bank_data['cash_flow'],
                                "slope": egim,
                                "aspect": baki,
                                "location_data": st.session_state.parsel_location,
                                "shading_comment": shading_comment,
                                "username": st.session_state.username,
                                "panel_model": st.session_state.selected_panel_model,
                                "inv_model": sel_i_model,
                                "engineering_note": eng_note_text
                            }

                            # 2. Şimdi bu paketi AI Servisine Gönderelim
                            # ai_service içindeki 'data' buradaki 'report_data' olacak
                            try:
                                from ai_service import generate_smart_report_summary

                                # Fonksiyonu çağır
                                ai_comment = generate_smart_report_summary(report_data)
                                report_data["ai_summary"] = ai_comment

                            except Exception as e:
                                # HATA BURADA: Bunu ekrana yazdıralım ki ne olduğunu görelim!
                                st.error(f"⚠️ YAPAY ZEKA BAĞLANTI HATASI: {str(e)}")

                                # Rapor patlamasın diye yedek metni koyuyoruz
                                report_data[
                                    "ai_summary"] = "Teknik veriler ışığında projenin yüksek verimlilik potansiyeline sahip olduğu öngörülmektedir."

                                # 3. Görselleri Hazırla
                            generate_parsel_plot(st.session_state.parsel_geojson, st.session_state.layout_data)
                            report_data["graph_path"] = generate_earnings_graph(*res_pot[:4]) if res_pot else None
                            report_data["monthly_data"] = st.session_state.pvgis_yield_data[
                                'monthly_data'] if st.session_state.pvgis_yield_data else None

                            # 4. PDF Oluştur
                            st.session_state.pdf_bytes = generate_full_report(report_data)
                            st.success("🤖 Yapay Zeka Analizi ve Rapor Hazır!")
                    else:
                        st.error("Önce bir parsel yüklemelisiniz!")

                if "pdf_bytes" in st.session_state:
                    file_name = f"{st.session_state.username}_{datetime.now().strftime('%Y%m%d_%H%M')}.pdf"
                    st.download_button("📥 PDF İndir", st.session_state.pdf_bytes, file_name, "application/pdf",
                                       use_container_width=True)
        else:
            st.info("🔒 Finansal analiz Pro pakette.")

    with col1:
        st.markdown("---")
        if st.session_state.horizon_data is not None:
            horizon_graph_path = generate_horizon_plot(st.session_state.horizon_data)
            if horizon_graph_path:
                st.markdown("### 🏔️ Ufuk ve Gölge Analizi (PVGIS)")
                st.image(horizon_graph_path, width="stretch")
                max_ang_str, loss_factor = get_shading_metrics(st.session_state.horizon_data)
                try:
                    val = float(max_ang_str.split('°')[0])
                except:
                    val = 0
                stat, col, msg = evaluate_shading_suitability(val)
                loss_pct = round((1 - loss_factor) * 100, 1)
                st.markdown(f"""
                <div style="background-color: #f8f9fa; padding: 15px; border-radius: 8px; border-left: 5px solid {col};">
                    <h5 style="margin-top:0; color: #333;">📉 Gölge Risk Raporu</h5>
                    <div style="font-size: 0.9rem; color: #444;">
                    • <b>En Yüksek Engel:</b> {max_ang_str}<br>
                    • <b>Tahmini Kayıp:</b> %{loss_pct}<br>
                    • <b>Sonuç:</b> <strong style="color: {col};">{stat}</strong> — <i>{msg}</i><br>
                    <small><i>Veri Kaynağı: AB Bilim Merkezi (PVGIS API)</i></small>
                    </div>
                </div>""", unsafe_allow_html=True)
        else:
            st.info("ℹ️ Ufuk analizi için konum seçiniz.")