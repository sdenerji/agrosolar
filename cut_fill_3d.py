import numpy as np
import geopandas as gpd
import pandas as pd
import plotly.graph_objects as go
from scipy.interpolate import RegularGridInterpolator
from scipy.ndimage import gaussian_filter
from shapely.geometry import Point
import streamlit as st
import math

# YETKİ KONTROLÜ İÇİN IMPORT
from user_config import has_permission


# ... (Tüm fonksiyonlar aynı kalacak: get_turkey_utm_epsg, process_geojson, get_elevation_data, run_3d_analysis, plot_3d) ...
# YUKARIDAKİ MATEMATİK FONKSİYONLARINI AYNEN KORUYUN (Kısalık için tekrar yazmıyorum, sadece show_3d_page'i değiştiriyoruz)

# 1. PROJEKSİYON VE UTM DÖNÜŞÜMÜ
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


# 2. SRTM30 VERİ SİMÜLASYONU (YUMUŞATILMIŞ)
def get_elevation_data(polygon, resolution=1.0):
    minx, miny, maxx, maxy = polygon.bounds
    pad = 50
    x_srtm = np.arange(minx - pad, maxx + pad, 30.0)
    y_srtm = np.arange(miny - pad, maxy + pad, 30.0)
    raw_noise = np.random.uniform(100, 110, (len(y_srtm), len(x_srtm)))
    z_srtm = gaussian_filter(raw_noise, sigma=3.0)
    xx, yy = np.meshgrid(np.arange(len(x_srtm)), np.arange(len(y_srtm)))
    slope = (xx * 0.05) + (yy * 0.02)
    z_srtm += slope
    interp_func = RegularGridInterpolator((y_srtm, x_srtm), z_srtm, method='cubic')
    x_fine = np.arange(minx, maxx, resolution)
    y_fine = np.arange(miny, maxy, resolution)
    X, Y = np.meshgrid(x_fine, y_fine)
    Z = interp_func(np.array([Y.ravel(), X.ravel()]).T).reshape(X.shape)
    for i in range(len(y_fine)):
        for j in range(len(x_fine)):
            if not polygon.contains(Point(x_fine[j], y_fine[i])):
                Z[i, j] = np.nan
    return X, Y, Z


# 3. KAZI-DOLGU HESABI
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


# 4. GÖRSELLEŞTİRME
def plot_3d(X, Y, Z, ideal_z, mode_label):
    fig = go.Figure()
    fig.add_trace(go.Surface(
        z=Z, x=X, y=Y, colorscale='Earth', name='Mevcut Arazi',
        lighting=dict(ambient=0.4, diffuse=0.9, roughness=0.1, specular=0.05),
        contours_z=dict(show=True, usecolormap=True, highlightcolor="limegreen", project_z=True)
    ))
    Z_plane = np.full_like(Z, ideal_z)
    fig.add_trace(go.Surface(z=Z_plane, x=X, y=Y, opacity=0.5, colorscale='Greys', showscale=False,
                             name=f'Hedef Kot: {ideal_z:.2f}m'))
    fig.update_layout(
        title=f'3D Topografik Model - {mode_label}',
        autosize=True, height=700,
        scene=dict(xaxis_title='Doğu-Batı (m)', yaxis_title='Kuzey-Güney (m)', zaxis_title='Yükseklik (m)',
                   aspectmode='data', camera=dict(eye=dict(x=1.2, y=1.2, z=0.8)))
    )
    return fig


# --- GÜNCELLENMİŞ 3D SAYFA GÖSTERİMİ ---
def show_3d_page():
    if st.button("⬅️ Analiz Sayfasına Dön", type="secondary"):
        st.session_state.page = 'analiz'
        st.rerun()

    st.divider()
    st.title("🏔️ 3D Arazi ve Hafriyat Analizi")  # "Ultra" ibaresini kaldırdım, herkes görsün.

    st.markdown("""
    Bu modül, arazinin topografik yapısını simüle ederek **kazı/dolgu (hafriyat)** miktarlarını hesaplar.
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

            # --- BUTONDA YETKİ KONTROLÜ ---
            if st.button("🚀 3D Analizi Başlat", type="primary"):
                if has_permission(st.session_state.user_role, "3d_analysis"):
                    with st.spinner("Arazi modelleniyor ve kübaj hesaplanıyor..."):
                        poly = metric_gdf.geometry.iloc[0]
                        X, Y, Z = get_elevation_data(poly)
                        ideal_z, cut, fill, cost, mode = run_3d_analysis(X, Y, Z, {'kazi': u_kazi, 'dolgu': u_dolgu},
                                                                         target_z=manual_z_val)

                    st.divider()
                    k1, k2, k3, k4 = st.columns(4)
                    k1.metric("⚖️ Hedef Kot", f"{ideal_z:.2f} m")
                    k2.metric("📉 Toplam Kazı", f"{cut:,.0f} m³", delta_color="inverse")
                    k3.metric("📈 Toplam Dolgu", f"{fill:,.0f} m³", delta_color="normal")
                    k4.metric("💰 Toplam Maliyet", f"{cost:,.0f} TL")

                    st.plotly_chart(plot_3d(X, Y, Z, ideal_z, mode), use_container_width=True)
                    st.info("ℹ️ Not: Görünüm 'Gerçek Ölçek' (1:1) modundadır.")

                else:
                    # YETKİ YOKSA
                    st.error("🔒 **Bu Özellik Kilitli**")
                    st.warning(
                        "Hafriyat maliyet analizi ve 3D modelleme **Ultra (Enterprise)** pakete dahildir. Devam etmek için lütfen paketinizi yükseltin.")

        except Exception as e:
            st.error(f"Analiz Hatası: {e}")