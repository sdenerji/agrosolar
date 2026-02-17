import numpy as np
import pandas as pd
import matplotlib.pyplot as plt
from shapely.geometry import shape, Polygon, MultiPolygon
import math
from gis_service import fetch_srtm_elevation_data
from pyproj import Transformer


# --- 🌐 KOORDİNAT DÖNÜŞÜM MOTORU ---
def transform_points(points, from_epsg, to_epsg):
    """
    Kullanıcının yüklediği koordinatları bir sistemden diğerine çevirir.

    """
    try:
        transformer = Transformer.from_crs(f"EPSG:{from_epsg}", f"EPSG:{to_epsg}", always_xy=True)
        # HATA DÜZELTİLDİ: 'transformed' yerine giriş parametresi olan 'points' üzerinden dönülüyor.
        transformed_data = [transformer.transform(p[0], p[1]) for p in points]
        return transformed_data
    except Exception as e:
        return None


def get_utm_zone_epsg(lon, datum="ITRF"):
    """
    Türkiye için lon değerine göre UTM (6 derece) EPSG kodunu bulur.
    ITRF (WGS84) -> 32635-32638
    ED50 -> 23035-23038

    """
    utm_zone = int(lon / 6) + 31
    if datum == "ITRF":
        return f"326{utm_zone}"
    return f"230{utm_zone}"


def smart_fix_coordinates(points):
    """
    Gelen noktaların Enlem/Boylam mı yoksa Metrik mi olduğunu anlar
    ve Türkiye sınırlarına göre (Y, X) sırasını otomatik düzeltir.

    """
    if not points: return []
    fixed_points = []

    for p in points:
        try:
            v1, v2 = float(p[0]), float(p[1])

            # 🎯 DURUM 1: Coğrafi Koordinat (WGS84) Tespiti
            if abs(v1) < 100 and abs(v2) < 100:
                # Türkiye: Lat (35-43), Lon (25-45)
                # Eğer ilk değer 35-43 arasındaysa bu Enlem'dir, (Lon, Lat) sırasına çevir.
                if 35 < v1 < 43:
                    fixed_points.append((v2, v1))
                else:
                    fixed_points.append((v1, v2))

            # 🎯 DURUM 2: Metrik Koordinat (ITRF/ED50) Tespiti
            else:
                # Türkiye'de Yukarı(X) ~4 milyon, Sağa(Y) ~500 bindir.
                # Eğer ilk değer 1 milyondan büyükse (v1 > v2), yer değiştir.
                if v1 > v2:
                    fixed_points.append((v2, v1))
                else:
                    fixed_points.append((v1, v2))
        except:
            continue
    return fixed_points


# --- 1. COĞRAFİ VE ALAN ANALİZİ ---
def calculate_slope_aspect(lat, lon):
    try:
        snap_lat, snap_lon = round(lat, 2), round(lon, 2)
        pad = 0.005
        bbox = [snap_lon - pad, snap_lat - pad, snap_lon + pad, snap_lat + pad]
        data = fetch_srtm_elevation_data(bbox)

        if data and data['success']:
            Z, X, Y = data['z'], data['x'], data['y']
            if Z is not None and Z.size > 0:
                x_step, y_step = X[1] - X[0], Y[1] - Y[0]
                col_f = (lon - X[0]) / x_step
                row_f = (lat - Y[0]) / y_step
                c0, r0 = int(np.floor(col_f)), int(np.floor(row_f))

                if 0 <= r0 < Z.shape[0] - 1 and 0 <= c0 < Z.shape[1] - 1:
                    tx, ty = col_f - c0, row_f - r0
                    h00, h01 = Z[r0, c0], Z[r0, c0 + 1]
                    h10, h11 = Z[r0 + 1, c0], Z[r0 + 1, c0 + 1]
                    rakim = int(h00 * (1 - tx) * (1 - ty) + h01 * tx * (1 - ty) + h10 * (1 - tx) * ty + h11 * tx * ty)

                    r, c = int(round(row_f)), int(round(col_f))
                    if 0 < r < Z.shape[0] - 1 and 0 < c < Z.shape[1] - 1:
                        a, b, c_val = Z[r - 1, c - 1], Z[r - 1, c], Z[r - 1, c + 1]
                        d, e, f = Z[r, c - 1], Z[r, c], Z[r, c + 1]
                        g, h, i = Z[r + 1, c - 1], Z[r + 1, c], Z[r + 1, c + 1]
                        cell = 30.0
                        dz_dx = ((c_val + 2 * f + i) - (a + 2 * d + g)) / (8.0 * cell)
                        dz_dy = ((a + 2 * b + c_val) - (g + 2 * h + i)) / (8.0 * cell)
                        slope_deg = math.degrees(math.atan(math.sqrt(dz_dx ** 2 + dz_dy ** 2)))
                        aspect_rad = math.atan2(-dz_dy, -dz_dx)
                        aspect_deg = math.degrees(aspect_rad)
                        compass_deg = (90.0 - aspect_deg) % 360.0
                        dirs = ["Kuzey", "Kuzeydoğu", "Doğu", "Güneydoğu", "Güney", "Güneybatı", "Batı", "Kuzeybatı"]
                        baki_text = dirs[int((compass_deg + 22.5) / 45.0) % 8]
                        return rakim, round(slope_deg, 1), baki_text
                return int(Z[r0, c0]), 5.0, "Kuzey"
        return 800, 5.0, "Güney"
    except:
        return 1000, 3.0, "Güney"


def get_suitability_badge(slope, aspect):
    s_col, s_msg, s_icon = "green", "Uygun", "✅"
    a_col, a_msg, a_icon = "green", "Uygun", "☀️"
    if slope > 25:
        s_col, s_msg, s_icon = "red", "Çok Dik (>25°)", "⚠️"
    elif slope > 15:
        s_col, s_msg, s_icon = "orange", "Orta Eğim", "⚠️"
    if "Kuzey" in aspect:
        a_col, a_msg, a_icon = "red", "Kuzey Cephe", "☁️"
    elif "Doğu" in aspect or "Batı" in aspect:
        a_col, a_msg, a_icon = "orange", "Yan Cephe", "⛅"
    return s_col, s_msg, s_icon, a_col, a_msg, a_icon


def calculate_geodesic_area(geojson_data):
    if not geojson_data: return 0
    try:
        geom_shapely = shape(geojson_data['features'][0]['geometry'])
        centroid_lat = geom_shapely.centroid.y
        m_lat = 111132.95
        m_lon = 111132.95 * math.cos(math.radians(centroid_lat))
        return geom_shapely.area * (m_lat * m_lon)
    except:
        return 0


# --- FİNANSAL ---
def get_solar_potential(lat, lon, aspect, kwp, slope, altitude, elec_price=0.13, fetched_yield=None, unit_capex=700):
    yield_val = fetched_yield if fetched_yield else 1450
    if not fetched_yield:
        if "Kuzey" in aspect:
            yield_val *= 0.85
        elif "Doğu" in aspect or "Batı" in aspect:
            yield_val *= 0.92
    annual_production = kwp * yield_val
    rev = annual_production * elec_price
    cost = kwp * unit_capex
    roi = round(cost / rev, 1) if rev > 0 else 99
    return annual_production, rev, cost, roi


def calculate_bankability_metrics(annual_production, capex, elec_price):
    years, degradation, opex_rate = 25, 0.005, 0.015
    cash_flow, cumulative, total_prod = [], -capex, 0
    for y in range(1, years + 1):
        prod = annual_production * ((1 - degradation) ** (y - 1))
        rev, opex = prod * elec_price, capex * opex_rate
        net = rev - opex
        cumulative += net
        total_prod += prod
        cash_flow.append({"yil": y, "uretim": int(prod), "gelir": int(rev), "gider": int(opex), "net": int(net),
                          "kumulatif": int(cumulative)})

    irr = round((((cumulative + capex) / years) / capex) * 100, 1) if capex > 0 else 0
    npv = sum([r['net'] / ((1.1) ** r['yil']) for r in cash_flow]) - capex
    co2 = total_prod * 0.0006
    return {"irr": irr, "npv": int(npv), "cash_flow": cash_flow, "co2": int(co2 / 25), "trees": int(co2 * 45 / 25)}


# --- GRAFİKLER ---
def generate_horizon_plot(df_horizon):
    if df_horizon is None or df_horizon.empty: return None
    plt.figure(figsize=(10, 3))
    df_sorted = df_horizon.sort_values('azimuth')
    plt.fill_between(df_sorted['azimuth'], 0, df_sorted['height'], color='gray', alpha=0.6, label='Engel')
    plt.plot(df_sorted['azimuth'], df_sorted['height'], color='black', linewidth=1)
    x_sun = np.linspace(-120, 120, 100)
    y_sun = 70 * np.cos(np.radians(x_sun * 0.75))
    plt.plot(x_sun, y_sun, color='orange', linestyle='--', linewidth=2, label='Yaz Güneşi')
    plt.xlim(120, -120);
    plt.ylim(0, 90)
    plt.ylabel("Açı (°)")
    plt.xticks([90, 45, 0, -45, -90], ['BATI', 'G.Batı', 'GÜNEY', 'G.Doğu', 'DOĞU'], fontweight='bold', fontsize=9)
    plt.grid(True, alpha=0.3, linestyle='--');
    plt.legend(loc='upper right', fontsize=8)
    path = "temp_horizon_plot.png"
    plt.savefig(path, bbox_inches='tight', dpi=100);
    plt.close()
    return path


def generate_earnings_graph(prod, rev, cost, roi):
    plt.figure(figsize=(10, 4));
    years = np.arange(0, 16)
    cum = np.cumsum([-cost] + [rev] * 15)
    plt.plot(years, cum, marker='o', color='#2b8cbe', linewidth=2)
    plt.axhline(0, color='red', ls='--')
    plt.title(f"Nakit Akışı ({roi} Yıl)");
    plt.grid(True, alpha=0.5)
    path = "temp_earnings_graph.png"
    plt.savefig(path, bbox_inches='tight');
    plt.close();
    return path


# --- PARSEL VE PANEL ÇİZİMİ (FINAL: AKILLI FLIP TEKNOLOJİSİ) ---
def generate_parsel_plot(geojson_data, layout_data=None):
    if not geojson_data: return None
    try:
        # 1. Parsel Geometrisi ve Merkezi
        geom = shape(geojson_data['features'][0]['geometry'])
        parcel_center = geom.centroid  # (Boylam, Enlem) olması beklenir
        cx, cy = parcel_center.x, parcel_center.y

        plt.figure(figsize=(6, 4))
        ax = plt.gca()

        # Parseli Çiz (Zemin)
        if geom.geom_type == 'Polygon':
            gx, gy = geom.exterior.xy
            plt.fill(gx, gy, alpha=0.3, fc='orange', ec='black', linewidth=2, label='Parsel')
        elif geom.geom_type == 'MultiPolygon':
            for poly in geom.geoms:
                gx, gy = poly.exterior.xy
                plt.fill(gx, gy, alpha=0.3, fc='orange', ec='black', linewidth=2, label='Parsel')

        # 2. Panelleri Çiz (Varsa)
        if layout_data and 'panels' in layout_data and layout_data['panels']:
            panels_raw = layout_data['panels']
            # Veri Tipi Kontrolü (Liste ise Polygon'a çevir)
            panels_polys = []
            for p in panels_raw:
                if isinstance(p, (list, tuple)):  # [[Lat,Lon],...] listesi
                    panels_polys.append(Polygon(p))
                elif isinstance(p, dict):  # GeoJSON Dict
                    panels_polys.append(shape(p['geometry'] if 'geometry' in p else p))
                else:  # Zaten Shapely nesnesi
                    panels_polys.append(p)

            if len(panels_polys) > 0:
                # --- AKILLI HİZALAMA KONTROLÜ ---
                # İlk panelin merkezine bak
                p1 = panels_polys[0]
                px, py = p1.centroid.x, p1.centroid.y

                # Durum 1: Panel ve Parsel aynı yerde mi? (Fark < 0.1 derece)
                if abs(cx - px) < 0.1 and abs(cy - py) < 0.1:
                    needs_flip = False  # Her şey yolunda
                # Durum 2: Koordinatlar ters mi (Lat, Lon) vs (Lon, Lat)?
                # Parsel X (37) ile Panel Y (37) yakınsa -> TERS
                elif abs(cx - py) < 0.1 and abs(cy - px) < 0.1:
                    needs_flip = True
                else:
                    # Durum 3: Çok uzak (Muhtemelen UTM vs LatLon).
                    # Bu durumda çizim yapılamaz, pas geçiyoruz.
                    print("Koordinat sistemi çok farklı, çizim atlanıyor.")
                    needs_flip = False
                    panels_polys = []

                    # Çizim
                for i, panel in enumerate(panels_polys):
                    xp, yp = panel.exterior.xy
                    if needs_flip:
                        # Koordinatları (Y, X) olarak değiştirip çiziyoruz
                        plt.fill(yp, xp, fc='#2c3e50', ec='none', alpha=0.9, label='Panel' if i == 0 else "")
                    else:
                        plt.fill(xp, yp, fc='#2c3e50', ec='none', alpha=0.9, label='Panel' if i == 0 else "")

        plt.axis('equal')
        plt.axis('off')  # Eksenleri gizle (Temiz görünüm)
        path = "temp_report_map.png"
        plt.savefig(path, bbox_inches='tight', dpi=200)
        plt.close()
        return path
    except Exception as e:
        print(f"Çizim Hatası: {e}")
        return None


# --- YARDIMCILAR ---
def get_shading_metrics(df):
    if df is None or df.empty: return "Veri Yok", 1.0
    row = df.loc[df['height'].idxmax()]
    return f"{row['height']:.1f}°", 1.0 - (row['height'] * 0.005)


def evaluate_shading_suitability(val):
    if val < 10: return "UYGUN", "green", "Engeller az."
    return "ORTA", "orange", "Kısmi gölge olabilir."


def interpret_monthly_data(m):
    if not m: return ""
    mx = max(m, key=lambda x: x['production'])
    return f"Maksimum üretim {int(mx['production'])} kWh."


def interpret_cash_flow(roi, npv): return f"ROI: {roi} yıl, NPV: {int(npv):,} $"


def interpret_shading(sm): return f"Engel açısı: {sm[0]}"


def analyze_suitability(lat, lon): return True


def parse_grid_data(path): return []


def get_projection_data(): return None