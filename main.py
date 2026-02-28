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

import base64

def get_base64_of_bin_file(bin_file):
    """Yerel imaj dosyasını HTML içinde kullanabilmek için base64'e çevirir."""
    with open(bin_file, 'rb') as f:
        data = f.read()
    return base64.b64encode(data).decode()

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
    smart_fix_coordinates, get_nearest_grid_distance, process_coordinate_conversion
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

supabase = get_supabase()

# --------------------------------------------------------------------------
# 🎯 SD ENERJİ - MERKEZİ OTURUM YÖNETİMİ (KONSOLİDE EDİLDİ)
# --------------------------------------------------------------------------
import time

# 1. URL'den gelen anahtarı yakala (Mavi buton tıklandığında çalışır)
if "access_token" in st.query_params:
    token = st.query_params["access_token"]
    refresh = st.query_params.get("refresh_token", "")
    try:
        # Supabase'e oturumu zorla tanıt
        supabase.auth.set_session(token, refresh)

        # Kullanıcıyı doğrula
        user_resp = supabase.auth.get_user()
        if user_resp and user_resp.user:
            u = user_resp.user
            st.session_state.logged_in = True
            st.session_state.user_id = u.id
            st.session_state.user_email = u.email
            st.session_state.username = u.user_metadata.get('full_name', u.email.split('@')[0])

            # Rol bilgisini çek
            try:
                r_q = supabase.table("users").select("role").eq("id", u.id).execute()
                st.session_state.user_role = r_q.data[0].get("role", "Free") if r_q.data else "Free"
            except:
                st.session_state.user_role = "Free"

            # URL'yi temizle ve tertemiz sayfaya geç
            st.query_params.clear()
            st.success("✅ Giriş başarılı, yönlendiriliyorsunuz...")
            time.sleep(0.5)
            st.rerun()
    except Exception as e:
        st.error(f"❌ Giriş anahtarı işlenemedi: {e}")

# 2. Mevcut oturumu koru (Kullanıcıyı dışarı atma bug'ı çözüldü)
try:
    sess = supabase.auth.get_session()
    if sess and sess.user:
        u = sess.user
        st.session_state.logged_in = True
        st.session_state.user_id = u.id
        st.session_state.username = u.user_metadata.get('full_name', u.email.split('@')[0])
        # Rolü hafızada yoksa veritabanından çek
        if st.session_state.get('user_role', 'Free') == 'Free':
            r_data = supabase.table("users").select("role").eq("id", u.id).execute()
            st.session_state.user_role = r_data.data[0].get("role", "Free") if r_data.data else "Free"
    else:
        if 'logged_in' not in st.session_state: st.session_state.logged_in = False
except:
    if 'logged_in' not in st.session_state: st.session_state.logged_in = False

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
st.set_page_config(page_title="SD Enerji Analiz App", layout="wide")
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
    logo_path = "assets/logo.png"
    if os.path.exists(logo_path):
        # Logoyu tıklanabilir yapmak için HTML kullan
        binary_logo = get_base64_of_bin_file(logo_path)
        st.markdown(
            f"""
                <a href="https://www.sdenerji.com/" target="_blank">
                    <img src="data:image/png;base64,{binary_logo}" style="width: 100%; cursor: pointer; border-radius: 5px;">
                </a>
                """,
            unsafe_allow_html=True
        )
    else:
        st.markdown("<h2 style='text-align: center;'>SD Enerji</h2>", unsafe_allow_html=True)

    st.markdown("<h2 style='text-align: center; margin-top: -15px;'>SD Enerji Analiz App</h2>", unsafe_allow_html=True)
    st.divider()

    if st.session_state.logged_in:
        r_data = supabase.table("users").select("role").eq("id", st.session_state.user_id).execute()
        current_role = r_data.data[0].get("role", "Free") if r_data.data else "Free"
        st.session_state.user_role = current_role  # Rolü anlık güncelle

        role_label = ROLE_PERMISSIONS.get(current_role, {}).get("label", current_role)
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
        import streamlit.components.v1 as components

        components.html("""
                    <div id="finish-login" style="display:none; text-align:center; padding: 5px;">
                        <div style="color:#155724; background-color:#d4edda; border:1px solid #c3e6cb; padding:8px; border-radius:5px; margin-bottom:10px; font-family:sans-serif; font-size:13px; font-weight:bold;">
                            ✅ Google Doğrulandı
                        </div>
                        <p style="font-family:sans-serif; font-size:11px; color:#666; margin-bottom:10px;">
                            * Giriş yapmak için aşağıdaki Platforma Geç butonuna tıklayın.
                        </p>
                        <a id="login-link" href="#" target="_blank" style="display:inline-block; background-color:#1a73e8; color:white; padding:10px; border:none; border-radius:5px; font-weight:bold; cursor:pointer; width:100%; font-family:sans-serif; text-decoration:none; box-sizing:border-box; box-shadow: 0 2px 4px rgba(0,0,0,0.1);">
                            🚀 Platforma Geç
                        </a>
                    </div>

                    <script>
                        var win = window.top || window.parent || window;
                        var currentHash = win.location.hash;

                        // URL'de token varsa bu menüyü göster ve Linki ayarla
                        if (currentHash && currentHash.includes("access_token=")) {
                            document.getElementById('finish-login').style.display = 'block';

                            // # işaretini ? yap ve bu adresi linkin içine (href) yerleştir
                            var cleanUrl = win.location.origin + win.location.pathname + currentHash.replace('#', '?');
                            document.getElementById('login-link').href = cleanUrl;
                        }
                    </script>
                """, height=150)

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




# --------------------------------------------------------------------------
# 🎯 SAYFA AKIŞI (ROUTING)
# --------------------------------------------------------------------------
if st.session_state.page == 'profil':
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
        # 🎯 YENİ: 3° TM (Türkiye Haritacı Standardı) seçenekleri eklendi
        sys_options = [
            "WGS84 (GPS/Coğrafi)",
            "ITRF (3° TM / Kadastro)",
            "ED50 (3° TM / Eski Harita)",
            "ITRF (6° UTM / Global)",
            "ED50 (6° UTM / Global)"
        ]
        input_sys = st.selectbox("Giriş Sistemi:", sys_options,
                                 index=0 if detected_sys == "WGS84 (GPS/Coğrafi)" else 2,
                                 disabled=is_detected)
    with col_set2:
        # WGS84 hariç tüm sistemleri hedef sistem olarak seçebilme
        target_sys_options = ["WGS84 (GPS/Coğrafi)"] + [opt for opt in sys_options if "WGS84" not in opt]
        target_sys = st.selectbox("Hedef Sistem:", target_sys_options)

    if st.button("🚀 Dönüşümü Başlat ve Listele", use_container_width=True):
        if not points_to_convert:
            st.error("⚠️ Lütfen önce bir dosya yükleyin!")
        else:
            # 🎯 SİHİRLİ SATIR: Tüm hesaplama ve isimlendirme calculations.py'ye devredildi
            df_res, dynamic_filename = process_coordinate_conversion(
                points_to_convert, input_sys, target_sys, st.session_state.lon
            )

            # Ekranda sadece gösterme ve indirme kaldı
            st.subheader(f"📍 Dönüşüm Sonuçları")
            st.table(df_res.head(15).style.format("{:.8f}"))

            st.download_button("📥 Tam Listeyi CSV İndir",
                               df_res.to_csv(index=False),
                               dynamic_filename,  # calculations'tan gelen taze isim
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
    st.title("SD Enerji Analiz App")

    st.markdown("""
        ### Profesyonel GES Tasarım ve Analiz Platformu
        **SD Enerji Analiz App**; mühendislik ve enerji yatırım süreçlerini dijitalleştirmek amacıyla geliştirilmiş kapsamlı bir platformdur. 
        Platformumuz kullanıcılara şu temel mühendislik çözümlerini sunar:
        * **Profesyonel GES Tasarımı:** Güneş panellerinin araziye en verimli şekilde yerleştirilmesi ve kapasite analizi.
        * **3D Arazi Modelleme:** SRTM verileri ile arazinin dijital ikizinin oluşturulması, eğim ve bakı analizleri.
        * **Gölge ve Ufuk Analizi:** Çevresel faktörlerin üretim verimliliğine etkisinin simüle edilmesi.
        * **Teknik Raporlama:** Yapay zeka destekli, banka onaylı detaylı fizibilite ve verimlilik raporlarının oluşturulması.
        """ )
    st.markdown("---")


    render_announcement_banner()
    #st.divider()

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

        has_grid_perm = has_permission(st.session_state.user_role, "tm_proximity")
        toggle_label = "⚡ Şebekeyi Göster" if has_grid_perm else "⚡ Şebekeyi Göster (🔒 Ultra Paket)"

        if st.toggle(toggle_label, disabled=not has_grid_perm):
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

        grid_dist, grid_name = get_nearest_grid_distance(st.session_state.lat, st.session_state.lon)
        if grid_dist is not None:
            has_grid_perm = has_permission(st.session_state.user_role, "tm_proximity")

            # Yetkisi varsa gerçek verileri göster
            if has_grid_perm:
                dist_str = f"{grid_dist / 1000:.2f} km" if grid_dist > 1000 else f"{int(grid_dist)} m"
                name_str = f"📍 {grid_name}"
                val_color = "#052c65"  # Lacivert
            # Yetkisi yoksa gizle ve paketi işaret et
            else:
                dist_str = "🔒 Ultra Pakete Özel"
                name_str = "📍 Harita ve İsim Bilgisi Gizli"
                val_color = "#6c757d"  # Hissiyatı güçlendiren gri renk

            st.markdown(f"""
                    <div style="background-color: #e2f0fb; padding: 10px; border-radius: 5px; border: 1px solid #b6d4fe; margin-bottom: 10px; text-align: center; box-shadow: 0 2px 4px rgba(0,0,0,0.05);">
                        <div style="font-size: 1rem; color: #084298; font-weight: bold;">⚡ Şebekeye En Kısa Mesafe</div>
                        <div style="font-weight: bold; font-size: 1.2rem; color: {val_color}; margin: 5px 0;">{dist_str}</div>
                        <div style="font-size: 0.8rem; color: #444;">{name_str}</div>
                    </div>
                    """, unsafe_allow_html=True)

        with st.expander("🔌 Tasarım & Yerleşim", expanded=True):
            # 1. FİNANSAL PARAMETRELER
            f_col1, f_col2 = st.columns(2)
            st.session_state.elec_price = f_col1.number_input("Satış ($/kWh)", value=st.session_state.elec_price,
                                                              format="%.3f")
            # 🎯 EKLENDİ: Yatırım Maliyeti (CAPEX) girdisi geri getirildi
            st.session_state.unit_capex = f_col2.number_input("Maliyet ($/kWp)", value=st.session_state.unit_capex,
                                                              step=50.0, format="%.1f")

            st.markdown("---")

            # 2. DONANIM SEÇİMİ
            p_brand = st.selectbox("Panel:", list(PANEL_LIBRARY.keys()))
            st.session_state.selected_panel_brand = p_brand
            p_model = st.selectbox("Model:", list(PANEL_LIBRARY[p_brand].keys()))
            st.session_state.selected_panel_model = p_model

            i_col1, i_col2 = st.columns(2)
            i_brand = i_col1.selectbox("İnverter:", list(INVERTER_LIBRARY.keys()))
            sel_i_model = i_col2.selectbox("Model:", list(INVERTER_LIBRARY[i_brand].keys()))
            st.session_state.selected_inverter_model = sel_i_model

            st.markdown("---")

            # 3. GEOMETRİK YERLEŞİM VE TASARIM
            t_col1, t_col2 = st.columns(2)
            tt = t_col1.selectbox("Sehpa", ["2x20 (40 Panel)", "2x10 (20 Panel)", "2x5 (10 Panel)", "1x5 (5 Panel)"],
                                  index=2)
            t_r, t_c = int(tt.split(' ')[0].split('x')[0]), int(tt.split(' ')[0].split('x')[1])

            # 🎯 EKLENDİ: Panel eğim açısı manuel kontrole açıldı
            st.session_state.panel_tilt = t_col2.number_input("Panel Eğimi (°)", value=st.session_state.panel_tilt,
                                                              min_value=0, max_value=90, step=1)

            s_col1, s_col2 = st.columns(2)
            # 🎯 EKLENDİ: Dizi aralığı ve çekme mesafesi (setback) kullanıcıya açıldı
            row_spacing_val = s_col1.number_input("Dizi Mesafesi (m)", value=3.5, step=0.1, format="%.1f")
            setback_val = s_col2.number_input("Çekme Mesafesi (m)", value=1.0, step=0.5, format="%.1f")

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
                            panel_height=PANEL_LIBRARY[p_brand][p_model].get("height", 2.279),
                            setback=setback_val,  # Sabit 1.0 yerine dinamik değer
                            row_spacing=row_spacing_val,  # Sabit 3.5 yerine dinamik değer
                            col_spacing=0.5,
                            table_rows=t_r,
                            table_cols=t_c)
                        st.session_state.layout_data = l_res
                        st.rerun()

        if has_permission(st.session_state.user_role, "financials") and res_prod > 0:
            st.markdown("### 💰 Finansal Özet")
            st.metric("Üretim", f"{int(res_prod):,} kWh");
            st.metric("ROI", f"{res_roi} Yıl")
            if st.button("📊 Rapor Oluştur", use_container_width=True):
                if st.session_state.parsel_geojson:
                    generate_parsel_plot(st.session_state.parsel_geojson, st.session_state.layout_data)
                bankability = calculate_bankability_metrics(res_prod, res_cost, st.session_state.elec_price)
                rep_d = {
                    "kwp": st.session_state.layout_data['capacity_kw'],
                    "kwh": res_prod,
                    "username": st.session_state.username,
                    "gelir": res_pot[1] if res_pot else 0,
                    "cost": res_cost,
                    "capex": res_cost,
                    "roi": res_roi,
                    "irr": bankability["irr"],
                    "npv": bankability["npv"],
                    "co2": bankability["co2"],
                    "trees": bankability["trees"],
                    "cash_flow": bankability["cash_flow"],  # 🎯 EKLENDİ (Nakit Akışı Tablosu İçin)

                    "panel_brand": st.session_state.get('selected_panel_brand', 'Bilinmeyen Marka'),
                    "panel_model": st.session_state.get('selected_panel_model', 'Bilinmeyen Model'),
                    "inv_model": st.session_state.get('selected_inverter_model', 'Bilinmeyen Inverter'),
                    # 🎯 İSİM DÜZELTİLDİ

                    "slope": egim,  # 🎯 EKLENDİ (Arazi Eğimi)
                    "aspect": baki,  # 🎯 EKLENDİ (Arazi Bakısı)
                    "layout_data": st.session_state.layout_data  # 🎯 EKLENDİ (Panel Adedini Bulması İçin)
                }
                if has_permission(st.session_state.user_role, "ai_report"):
                    rep_d["ai_summary"] = generate_smart_report_summary(rep_d)
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

st.markdown("""
    <div style="margin-top: 50px; padding: 20px; border-top: 1px solid #eee; text-align: center; font-size: 0.75rem; color: #888; line-height: 1.6;">
        <p><b>SD ENERJİ</b> | sd@sdenerji.com | Bağlar Mah. Atatürk Bulv. 156/2 Niksar/Tokat</p>
        <p>
            <a href="https://www.sdenerji.com/mesafeli-satis-sozlesmesi/" target="_blank" style="color: #888; text-decoration: none;">Mesafeli Satış Sözleşmesi</a> • 
            <a href="https://www.sdenerji.com/iptal-ve-iade-kosullari/" target="_blank" style="color: #888; text-decoration: none;">İptal ve İade Koşulları</a> • 
            <a href="https://www.sdenerji.com/gizlilik-politikasi/" target="_blank" style="color: #888; text-decoration: none;">Gizlilik Politikası</a>
        </p>
        <p style="font-size: 0.65rem; color: #bbb; margin-top: 10px;">© 2026 SD Enerji Analiz Platformu. Tüm Hakları Saklıdır.</p>
    </div>
""", unsafe_allow_html=True)