import numpy as np
import geopandas as gpd
import pandas as pd
import plotly.graph_objects as go
from scipy.interpolate import RegularGridInterpolator
from shapely.geometry import Point
import streamlit as st
from pyproj import Transformer

# YETKİ KONTROLÜ
from user_config import has_permission
# GERÇEK VERİ İÇİN IMPORT
from gis_service import fetch_srtm_elevation_data


# 1. PROJEKSİYON (AYNEN KORUNDU)
def get_turkey_utm_epsg(lon):
    if 24 <= lon < 30:
        return "EPSG:32635"
    elif 30 <= lon < 36:
        return "EPSG:32636"
    elif 36 <= lon < 42:
        return "EPSG:32637"
    elif 42 <= lon <= 48:
        return "EPSG:32638"
    else:
        return "EPSG:32635"


def process_geojson(uploaded_file):
    gdf = gpd.read_file(uploaded_file)
    wgs84_center = gdf.to_crs("EPSG:4326").geometry.centroid.iloc[0]
    target_epsg = get_turkey_utm_epsg(wgs84_center.x)
    metric_gdf = gdf.to_crs(target_epsg)
    return metric_gdf, target_epsg


# 2. GERÇEK VERİYE DAYALI YÜKSEKLİK MODELİ
def get_elevation_data(polygon, epsg_code, resolution=1.0):
    minx, miny, maxx, maxy = polygon.bounds

    # UTM -> WGS84 Dönüşümü (API için)
    transformer_to_wgs84 = Transformer.from_crs(epsg_code, "EPSG:4326", always_xy=True)
    min_lon, min_lat = transformer_to_wgs84.transform(minx, miny)
    max_lon, max_lat = transformer_to_wgs84.transform(maxx, maxy)

    # API Çağrısı
    api_data = fetch_srtm_elevation_data([min_lon, min_lat, max_lon, max_lat])

    # Hedef Grid (Metrik)
    x_fine = np.arange(minx, maxx, resolution)
    y_fine = np.arange(miny, maxy, resolution)
    X_target, Y_target = np.meshgrid(x_fine, y_fine)

    if api_data and api_data.get('success'):
        z_srtm = api_data['z']
        x_srtm = api_data['x']
        y_srtm = api_data['y']

        # Lat sırasını kontrol et (Artan sıra gerekli)
        if y_srtm[0] > y_srtm[-1]:
            y_srtm = y_srtm[::-1]
            z_srtm = z_srtm[::-1, :]

        interp_func = RegularGridInterpolator((y_srtm, x_srtm), z_srtm, method='linear', bounds_error=False,
                                              fill_value=None)

        # Grid Dönüşümü ve İnterpolasyon
        X_target_flat = X_target.ravel()
        Y_target_flat = Y_target.ravel()
        lon_target, lat_target = transformer_to_wgs84.transform(X_target_flat, Y_target_flat)

        Z_flat = interp_func(np.array([lat_target, lon_target]).T)
        Z = Z_flat.reshape(X_target.shape)

    else:
        st.warning("⚠️ Arazi verisi çekilemedi, düz zemin varsayılıyor.")
        Z = np.full(X_target.shape, 100.0)

    # Poligon dışını temizle
    for i in range(len(y_fine)):
        for j in range(len(x_fine)):
            if not polygon.contains(Point(x_fine[j], y_fine[i])):
                Z[i, j] = np.nan

    return X_target, Y_target, Z


# 3. KAZI-DOLGU (AYNEN KORUNDU)
def run_3d_analysis(X, Y, Z, unit_prices, target_z=None):
    if target_z is not None:
        ideal_z = target_z
        mode = "Manuel Kot"
    else:
        ideal_z = np.nanmean(Z)
        mode = "Otomatik Denge"

    cell_area = 1.0
    diff = Z - ideal_z
    v_cut = np.nansum(np.where(diff > 0, diff, 0)) * cell_area
    v_fill = np.nansum(np.where(diff < 0, np.abs(diff), 0)) * cell_area
    total_cost = (v_cut * unit_prices['kazi']) + (v_fill * unit_prices['dolgu'])
    return ideal_z, v_cut, v_fill, total_cost, mode


# 4. GÖRSELLEŞTİRME (KAMERA VE EKSENLER GÜNCELLENDİ)
def plot_3d(X, Y, Z, ideal_z, mode_label):
    fig = go.Figure()

    # Arazi Yüzeyi
    fig.add_trace(go.Surface(
        z=Z, x=X, y=Y, colorscale='Earth', name='Mevcut Arazi',
        lighting=dict(ambient=0.4, diffuse=0.9, roughness=0.1, specular=0.05),
        contours_z=dict(show=True, usecolormap=True, highlightcolor="limegreen", project_z=True)
    ))

    # Düzlem (Hedef Kot)
    Z_plane = np.full_like(Z, ideal_z)
    fig.add_trace(go.Surface(z=Z_plane, x=X, y=Y, opacity=0.4, colorscale='Greys', showscale=False,
                             name=f'Hedef Kot: {ideal_z:.2f}m'))

    # --- KAMERA VE EKSEN AYARLARI (GÜNCELLEME BURADA) ---
    fig.update_layout(
        title=f'3D Topografik Model - {mode_label}',
        autosize=True, height=700,
        scene=dict(
            # Eksen İsimlerine Yön Bilgisi Eklendi
            xaxis_title='BATI ⟷ DOĞU (m)',
            yaxis_title='GÜNEY ⟷ KUZEY (m)',
            zaxis_title='Yükseklik (m)',
            aspectmode='data',

            # KAMERA AYARI: GÜNEYDEN BAKIŞ
            # x=0 (Ortada), y=-2.0 (Güneyden uzağa), z=0.8 (Hafif yukarıdan)
            camera=dict(eye=dict(x=0.1, y=-2.2, z=0.8))
        )
    )
    return fig


# --- 3D SAYFA GÖSTERİMİ ---
def show_3d_page():
    if st.button("⬅️ Analiz Sayfasına Dön", type="secondary"):
        st.session_state.page = 'analiz'
        st.rerun()

    st.divider()
    st.title("🏔️ 3D Arazi ve Hafriyat Analizi")

    st.markdown("""
    Bu modül, **OpenTopography NASA SRTM** verilerini kullanarak arazinin gerçek 3D modelini oluşturur.
    """)

    uploaded_file = st.file_uploader("Analiz için GeoJSON Yükleyin", type=['geojson', 'json'], key="3d_uploader")

    if uploaded_file:
        try:
            metric_gdf, epsg_code = process_geojson(uploaded_file)
            st.success(f"Projeksiyon: {epsg_code}")

            c1, c2 = st.columns(2)
            u_kazi = c1.number_input("Kazı Birim Fiyatı (TL/m³)", value=150.0)
            u_dolgu = c2.number_input("Dolgu Birim Fiyatı (TL/m³)", value=120.0)

            st.divider()
            st.subheader("🛠️ Tesviye Ayarları")
            method = st.radio("Hesaplama Yöntemi",
                              ["Otomatik (Kazı-Dolgu Dengele)", "Manuel Kot Gir (Sabit Yükseklik)"], horizontal=True)

            manual_z_val = None
            if "Manuel" in method:
                col_m1, col_m2 = st.columns([1, 2])
                manual_z_val = col_m1.number_input("Hedef Tesviye Kotu (m)", value=100.0, step=0.5, format="%.2f")

            if st.button("🚀 3D Analizi Başlat", type="primary"):
                if has_permission(st.session_state.user_role, "3d_analysis"):
                    with st.spinner("Gerçek arazi verisi çekiliyor ve modelleniyor..."):
                        poly = metric_gdf.geometry.iloc[0]
                        X, Y, Z = get_elevation_data(poly, epsg_code)
                        ideal_z, cut, fill, cost, mode = run_3d_analysis(X, Y, Z, {'kazi': u_kazi, 'dolgu': u_dolgu},
                                                                         target_z=manual_z_val)

                    st.divider()
                    k1, k2, k3, k4 = st.columns(4)
                    k1.metric("⚖️ Hedef Kot", f"{ideal_z:.2f} m")
                    k2.metric("📉 Toplam Kazı", f"{cut:,.0f} m³", delta_color="inverse")
                    k3.metric("📈 Toplam Dolgu", f"{fill:,.0f} m³", delta_color="normal")
                    k4.metric("💰 Toplam Maliyet", f"{cost:,.0f} TL")

                    st.plotly_chart(plot_3d(X, Y, Z, ideal_z, mode), use_container_width=True)
                    st.info("ℹ️ Veri Kaynağı: NASA SRTM GL3 (30m) - OpenTopography")

                else:
                    st.error("🔒 **Bu Özellik Kilitli**")
                    st.warning("Hafriyat maliyet analizi ve 3D modelleme **Ultra (Enterprise)** pakete dahildir.")

        except Exception as e:
            st.error(f"Analiz Hatası: {e}")