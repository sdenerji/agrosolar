import numpy as np
import geopandas as gpd
import pandas as pd
import plotly.graph_objects as go
from scipy.interpolate import RegularGridInterpolator, griddata
from shapely.geometry import Point, MultiPoint
import streamlit as st
from pyproj import Transformer
import json

# YETKİ KONTROLÜ
from user_config import has_permission
from gis_service import fetch_srtm_elevation_data


# --- 1. PROJEKSİYON ---
def get_turkey_utm_epsg(lon):
    if 24 <= lon < 30:
        return "EPSG:32635"
    elif 30 <= lon < 36:
        return "EPSG:32636"
    elif 36 <= lon < 42:
        return "EPSG:32637"
    elif 42 <= lon <= 48:
        return "EPSG:32638"
    return "EPSG:32635"


# --- 2. AKILLI BİRLEŞİK DOSYA OKUYUCU ---
def process_unified_file(uploaded_file):
    """Hem GeoJSON hem de nokta dosyalarını (NCN, CSV, TXT) okur, Z verisi varsa tespit eder."""
    filename = uploaded_file.name.lower()

    # DURUM 1: GeoJSON / JSON
    if filename.endswith(('json', 'geojson')):
        gdf = gpd.read_file(uploaded_file)
        wgs84_center = gdf.to_crs("EPSG:4326").geometry.centroid.iloc[0]
        target_epsg = get_turkey_utm_epsg(wgs84_center.x)
        return gdf.to_crs(target_epsg), target_epsg, None

    # DURUM 2: NCN, CSV, TXT (Ölçüm Dosyaları)
    points_3d = []
    has_z = False

    if filename.endswith('ncn'):
        for line in uploaded_file.getvalue().decode('utf-8').splitlines():
            parts = line.split()
            if len(parts) >= 3:
                y, x = float(parts[1]), float(parts[2])
                z = float(parts[3]) if len(parts) >= 4 else None
                if z is not None: has_z = True
                points_3d.append([y, x, z])
    elif filename.endswith(('csv', 'txt')):
        df = pd.read_csv(uploaded_file, header=None)
        for row in df.values:
            y, x = float(row[0]), float(row[1])
            z = float(row[2]) if len(row) > 2 and not pd.isna(row[2]) else None
            if z is not None: has_z = True
            points_3d.append([y, x, z])

    if not points_3d:
        raise ValueError("Dosyadan geçerli koordinat okunamadı.")

    # Otomatik Dönüşüm ve Poligon Oluşturma
    y0, x0 = points_3d[0][0], points_3d[0][1]
    is_wgs84 = abs(y0) < 100 and abs(x0) < 100
    transformed_points = []

    if is_wgs84:
        lon_val = y0 if y0 > x0 else x0
        target_epsg = get_turkey_utm_epsg(lon_val)
        transformer = Transformer.from_crs("EPSG:4326", target_epsg, always_xy=True)
        for p in points_3d:
            lon = p[0] if p[0] > p[1] else p[1]
            lat = p[1] if p[0] > p[1] else p[0]
            mx, my = transformer.transform(lon, lat)
            transformed_points.append([mx, my, p[2]])
    else:
        target_epsg = "EPSG:32636"  # Genel metrik varsayım
        for p in points_3d:
            v1, v2 = p[0], p[1]
            my = v1 if v1 < v2 else v2  # Sağa Değer (Y) daha küçüktür
            mx = v2 if v1 < v2 else v1  # Yukarı Değer (X) daha büyüktür
            transformed_points.append([my, mx, p[2]])

    # Noktalardan dış sınır (Convex Hull) poligonu oluştur
    multipoint = MultiPoint([(p[0], p[1]) for p in transformed_points])
    poly = multipoint.convex_hull
    if poly.geom_type in ['Point', 'LineString']:
        poly = poly.buffer(10)  # Çizgi ise kalınlık ver

    metric_gdf = gpd.GeoDataFrame(geometry=[poly], crs=target_epsg)
    return metric_gdf, target_epsg, transformed_points if has_z else None


# --- 3. HİBRİT YÜKSEKLİK MODELİ ---
def get_elevation_data(polygon, epsg_code, resolution=1.0, custom_points=None):
    minx, miny, maxx, maxy = polygon.bounds
    x_fine = np.arange(minx, maxx, resolution)
    y_fine = np.arange(miny, maxy, resolution)
    X_target, Y_target = np.meshgrid(x_fine, y_fine)
    Z = np.full(X_target.shape, np.nan)

    # EĞER DOSYADA KOT VARSA -> MİLİMETRİK HESAP (Griddata Interpolasyonu)
    if custom_points is not None:
        st.toast("📌 Dosyadaki Z (Kot) verileri kullanılıyor.", icon="💎")
        pts_xy = np.array([(p[0], p[1]) for p in custom_points])
        pts_z = np.array([p[2] if p[2] is not None else 0 for p in custom_points])

        Z_flat = griddata(pts_xy, pts_z, (X_target, Y_target), method='linear')
        Z = Z_flat

        # Sınır dışı boşlukları doldur
        if np.isnan(Z).any():
            Z_nearest = griddata(pts_xy, pts_z, (X_target, Y_target), method='nearest')
            Z[np.isnan(Z)] = Z_nearest[np.isnan(Z)]

    # EĞER KOT YOKSA -> UYDU VERİSİ (SRTM)
    else:
        st.toast("🛰️ Dosyada Z verisi yok, SRTM uydusuna bağlanılıyor.", icon="🌍")
        transformer_to_wgs84 = Transformer.from_crs(epsg_code, "EPSG:4326", always_xy=True)
        min_lon, min_lat = transformer_to_wgs84.transform(minx, miny)
        max_lon, max_lat = transformer_to_wgs84.transform(maxx, maxy)

        api_data = fetch_srtm_elevation_data([min_lon, min_lat, max_lon, max_lat])

        if api_data and api_data.get('success'):
            z_srtm, x_srtm, y_srtm = api_data['z'], api_data['x'], api_data['y']
            if y_srtm[0] > y_srtm[-1]:
                y_srtm, z_srtm = y_srtm[::-1], z_srtm[::-1, :]

            interp_func = RegularGridInterpolator((y_srtm, x_srtm), z_srtm, method='linear', bounds_error=False,
                                                  fill_value=None)
            X_target_flat, Y_target_flat = X_target.ravel(), Y_target.ravel()
            lon_target, lat_target = transformer_to_wgs84.transform(X_target_flat, Y_target_flat)
            Z_flat = interp_func(np.array([lat_target, lon_target]).T)
            Z = Z_flat.reshape(X_target.shape)
        else:
            st.warning("⚠️ Arazi verisi çekilemedi, düz zemin varsayılıyor.")
            Z = np.full(X_target.shape, 100.0)

    # Poligon dışındaki kareleri sil (Sadece parsel içi kalsın)
    for i in range(len(y_fine)):
        for j in range(len(x_fine)):
            if not polygon.contains(Point(x_fine[j], y_fine[i])):
                Z[i, j] = np.nan

    return X_target, Y_target, Z


# --- 4. KAZI-DOLGU VE GÖRSELLEŞTİRME (AYNEN KORUNDU) ---
def run_3d_analysis(X, Y, Z, unit_prices, target_z=None):
    ideal_z = target_z if target_z is not None else np.nanmean(Z)
    mode = "Manuel Kot" if target_z is not None else "Otomatik Denge"
    diff = Z - ideal_z
    v_cut = np.nansum(np.where(diff > 0, diff, 0)) * 1.0
    v_fill = np.nansum(np.where(diff < 0, np.abs(diff), 0)) * 1.0
    return ideal_z, v_cut, v_fill, (v_cut * unit_prices['kazi']) + (v_fill * unit_prices['dolgu']), mode


def plot_3d(X, Y, Z, ideal_z, mode_label):
    fig = go.Figure()

    # 🎯 colorscale='Earth' yerine 'Jet' yazıldı.
    fig.add_trace(go.Surface(z=Z, x=X, y=Y, colorscale='Jet', name='Mevcut Arazi',
                             lighting=dict(ambient=0.4, diffuse=0.9, roughness=0.1, specular=0.05),
                             contours_z=dict(show=True, usecolormap=True, highlightcolor="limegreen", project_z=True)))

    fig.add_trace(go.Surface(z=np.full_like(Z, ideal_z), x=X, y=Y, opacity=0.4, colorscale='Greys', showscale=False,
                             name=f'Hedef Kot: {ideal_z:.2f}m'))

    fig.update_layout(title=f'3D Topografik Model - {mode_label}', autosize=True, height=700,
                      scene=dict(xaxis_title='BATI ⟷ DOĞU (m)', yaxis_title='GÜNEY ⟷ KUZEY (m)',
                                 zaxis_title='Yükseklik (m)', aspectmode='data',
                                 camera=dict(eye=dict(x=0.1, y=-2.2, z=0.8))))
    return fig


# --- 5. ARAYÜZ (TEK UPLOADER) ---
def show_3d_page():
    if st.button("⬅️ Analiz Sayfasına Dön", type="secondary"):
        st.session_state.page = 'analiz';
        st.rerun()

    st.divider()
    st.title("🏔️ 3D Arazi ve Hafriyat Analizi")

    st.info("""
    💡 **Nasıl Çalışır?**
    Parsel dosyanızı veya nokta listenizi yükleyin. Sistem, dosyada yükseklik (Z) verisi bulursa o veriyi kullanır; bulamazsa otomatik olarak uzaydan (NASA SRTM) yükseklik verisi çeker.
    """)

    # YETKİYE GÖRE UZANTI DESTEĞİ
    allowed_types = ['geojson', 'json']
    if has_permission(st.session_state.user_role, "3d_precision_data"):
        allowed_types.extend(['ncn', 'csv', 'txt'])

    # 🎯 TEK VE TEMİZ UPLOADER
    uploaded_file = st.file_uploader("Dosya Yükle (GeoJSON, JSON, NCN, CSV, TXT)", type=allowed_types,
                                     key="3d_main_uploader")

    if uploaded_file:
        try:
            metric_gdf, epsg_code, custom_pts = process_unified_file(uploaded_file)
            st.success(f"✅ Dosya başarıyla işlendi. (Projeksiyon: {epsg_code})")

            c1, c2 = st.columns(2)
            u_kazi = c1.number_input("Kazı Birim Fiyatı (TL/m³)", value=150.0)
            u_dolgu = c2.number_input("Dolgu Birim Fiyatı (TL/m³)", value=120.0)

            st.subheader("🛠️ Tesviye Ayarları")
            method = st.radio("Hesaplama Yöntemi",
                              ["Otomatik (Kazı-Dolgu Dengele)", "Manuel Kot Gir (Sabit Yükseklik)"], horizontal=True)
            manual_z_val = st.number_input("Hedef Tesviye Kotu (m)", value=100.0,
                                           step=0.5) if "Manuel" in method else None

            if st.button("🚀 3D Analizi Başlat", type="primary"):
                if has_permission(st.session_state.user_role, "3d_srtm"):
                    with st.spinner("Arazi yüzeyi modelleniyor..."):
                        poly = metric_gdf.geometry.iloc[0]
                        X, Y, Z = get_elevation_data(poly, epsg_code, custom_points=custom_pts)
                        ideal_z, cut, fill, cost, mode = run_3d_analysis(X, Y, Z, {'kazi': u_kazi, 'dolgu': u_dolgu},
                                                                         target_z=manual_z_val)

                    st.divider()
                    k1, k2, k3, k4 = st.columns(4)
                    k1.metric("⚖️ Hedef Kot", f"{ideal_z:.2f} m")
                    k2.metric("📉 Toplam Kazı", f"{cut:,.0f} m³", delta_color="inverse")
                    k3.metric("📈 Toplam Dolgu", f"{fill:,.0f} m³", delta_color="normal")
                    k4.metric("💰 Toplam Maliyet", f"{cost:,.0f} TL")

                    st.plotly_chart(plot_3d(X, Y, Z, ideal_z, mode), use_container_width=True)
                    data_source = "Ölçüm Dosyası (Z Verisi)" if custom_pts else "NASA SRTM GL3 (30m) - OpenTopography"
                    st.caption(f"ℹ️ Veri Kaynağı: {data_source}")
                else:
                    st.error("🔒 Özellik Kilitli: Professional veya Ultra pakete geçiniz.")
        except Exception as e:
            st.error(f"❌ Analiz Hatası: İşlem yapılamadı. ({str(e)})")