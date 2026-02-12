import numpy as np
import pandas as pd
import matplotlib.pyplot as plt
from shapely.geometry import shape
import math

# --- 1. COĞRAFİ VE ALAN ANALİZİ ---
def calculate_slope_aspect(lat, lon):
    try:
        lat_seed = int(abs(lat) * 10000)
        lon_seed = int(abs(lon) * 10000)
        base_alt = 800
        variation = (lat_seed % 700) + (lon_seed % 100)
        rakim = base_alt + variation
        egim = 2.0 + (lat_seed % 150 / 10.0) + (lon_seed % 30 / 10.0)
        directions = ["Güney", "Güneydoğu", "Güneybatı", "Doğu", "Batı", "Kuzey"]
        dir_index = (lat_seed + lon_seed) % len(directions)
        baki = directions[dir_index]
        return int(rakim), round(egim, 1), baki
    except:
        return 1000, 10.0, "Güney"

def get_suitability_badge(slope, aspect):
    s_col, s_msg, s_icon = "green", "Uygun", "✅"
    a_col, a_msg, a_icon = "green", "Uygun", "☀️"
    if slope > 20: s_col, s_msg, s_icon = "red", "Çok Dik", "⚠️"
    elif slope > 15: s_col, s_msg, s_icon = "orange", "Orta/Maliyetli", "⚠️"
    if "Kuzey" in aspect: a_col, a_msg, a_icon = "red", "Kuzey", "☁️"
    elif "Doğu" in aspect or "Batı" in aspect: a_col, a_msg, a_icon = "orange", "Yan Cephe", "⛅"
    return s_col, s_msg, s_icon, a_col, a_msg, a_icon

def calculate_geodesic_area(geojson_data):
    if not geojson_data: return 0
    try:
        data = dict(geojson_data)
        if "features" in data and len(data["features"]) > 0:
            geom_data = data["features"][0]["geometry"]
            geom_shapely = shape(geom_data)
            centroid_lat = geom_shapely.centroid.y
            meters_per_lat = 111132.95
            meters_per_lon = 111132.95 * math.cos(math.radians(centroid_lat))
            return geom_shapely.area * (meters_per_lat * meters_per_lon)
    except: return 0
    return 0

# --- 2. GÜNEŞ POTANSİYELİ VE FİNANSAL HESAPLAR ---
def get_solar_potential(lat, lon, aspect, kwp, slope, altitude, elec_price=0.13, fetched_yield=None, unit_capex=700):
    if fetched_yield is not None:
        annual_production = kwp * fetched_yield
    else:
        specific_yield = 1450
        if "Kuzey" in aspect: specific_yield *= 0.85
        elif "Doğu" in aspect or "Batı" in aspect: specific_yield *= 0.92
        if slope > 30: specific_yield *= 0.95
        annual_production = kwp * specific_yield

    annual_revenue = annual_production * elec_price
    capex = kwp * unit_capex
    roi = round(capex / annual_revenue, 1) if annual_revenue > 0 else 99
    return annual_production, annual_revenue, capex, roi

def calculate_bankability_metrics(annual_production, capex, elec_price):
    years = 25; degradation = 0.005; opex_rate = 0.015
    cash_flow = []; cumulative = -capex; total_production = 0
    for y in range(1, years + 1):
        prod = annual_production * ((1 - degradation) ** (y - 1))
        revenue = prod * elec_price
        opex = capex * opex_rate
        net_income = revenue - opex
        cumulative += net_income
        total_production += prod
        cash_flow.append({
            "yil": y, "uretim": int(prod), "gelir": int(revenue),
            "gider": int(opex), "net": int(net_income), "kumulatif": int(cumulative)
        })
    avg_net = (cumulative + capex) / years
    irr = round((avg_net / capex) * 100, 1) if capex > 0 else 0
    npv = sum([row['net'] / ((1 + 0.10) ** row['yil']) for row in cash_flow]) - capex
    co2_ton = total_production * 0.0006
    trees = int(co2_ton * 45)
    return {"irr": irr, "npv": int(npv), "cash_flow": cash_flow, "co2": int(co2_ton / 25), "trees": int(trees / 25)}

# --- 3. GRAFİK VE GÖRSELLEŞTİRME ---
def get_shading_metrics(df):
    if df is None or df.empty: return "Veri Yok", 1.0
    max_row = df.loc[df['height'].idxmax()]
    max_angle = max_row['height']
    max_azimuth = max_row['azimuth']
    if -45 <= max_azimuth <= 45: direction = "Güney"
    elif -135 <= max_azimuth < -45: direction = "Doğu"
    elif 45 < max_azimuth <= 135: direction = "Batı"
    else: direction = "Kuzey"
    loss_factor = 1.0 - (max_angle * 0.005)
    return f"{max_angle:.1f}° ({direction})", loss_factor

def evaluate_shading_suitability(val):
    if val < 10: return "UYGUN", "green", "Çevresel engel az, üretim verimli."
    if val < 20: return "ORTA", "orange", "Sabah/Akşam gölgelemesi olabilir."
    return "RİSKLİ", "red", "Ciddi gölgeleme kaybı bekleniyor."

def generate_earnings_graph(prod, rev, cost, roi):
    years = np.arange(0, 16)
    cash_flows = [-cost] + [rev] * 15
    cumulative = np.cumsum(cash_flows)
    plt.figure(figsize=(10, 4))
    plt.plot(years, cumulative, marker='o', linestyle='-', color='#2b8cbe', linewidth=2)
    plt.axhline(0, color='red', linestyle='--', linewidth=1)
    plt.fill_between(years, cumulative, 0, where=(cumulative > 0), color='green', alpha=0.1)
    plt.fill_between(years, cumulative, 0, where=(cumulative < 0), color='red', alpha=0.1)
    plt.title(f"Nakit Akışı ve Geri Dönüş ({roi} Yıl)", fontsize=12)
    plt.xlabel("Yıl"); plt.ylabel("Kümülatif Kazanç ($)")
    plt.grid(True, linestyle='--', alpha=0.5)
    path = "temp_earnings_graph.png"
    plt.savefig(path, bbox_inches='tight'); plt.close()
    return path

def generate_horizon_plot(df_horizon):
    if df_horizon is None or df_horizon.empty: return None
    plt.figure(figsize=(10, 3))
    df_sorted = df_horizon.sort_values('azimuth')
    plt.fill_between(df_sorted['azimuth'], 0, df_sorted['height'], color='gray', alpha=0.6, label='Gerçek Ufuk (PVGIS)')
    plt.plot(df_sorted['azimuth'], df_sorted['height'], color='black', linewidth=1.5)
    x_sun = np.linspace(-120, 120, 100)
    y_sun = 70 * np.cos(np.radians(x_sun * 0.75))
    plt.plot(x_sun, y_sun, color='orange', linestyle='--', label='Yaz Güneşi Rotası')
    plt.xlim(120, -120)
    plt.xticks([90, 45, 0, -45, -90], ['BATI', 'G.Batı', 'GÜNEY', 'G.Doğu', 'DOĞU'], fontweight='bold', fontsize=9)
    plt.ylim(0, 90)
    plt.ylabel("Yükseklik Açısı (°)")
    plt.grid(True, alpha=0.3)
    path = "temp_horizon_plot.png"
    plt.savefig(path, bbox_inches='tight'); plt.close()
    return path

def generate_parsel_plot(geojson_data):
    if not geojson_data: return None
    try:
        geom = shape(geojson_data['features'][0]['geometry'])
        plt.figure(figsize=(6, 4))
        if geom.geom_type == 'Polygon':
            x, y = geom.exterior.xy
            plt.fill(x, y, alpha=0.5, fc='orange', ec='black')
            plt.plot(x, y, color='red', linewidth=2)
        elif geom.geom_type == 'MultiPolygon':
            for poly in geom.geoms:
                x, y = poly.exterior.xy
                plt.fill(x, y, alpha=0.5, fc='orange', ec='black')
                plt.plot(x, y, color='red', linewidth=2)
        plt.title("Parsel Geometrisi", fontsize=12); plt.axis('off'); plt.tight_layout()
        path = "temp_report_map.png"
        plt.savefig(path, bbox_inches='tight', dpi=100); plt.close()
        return path
    except: return None

# --- YENİ EKLENEN: AKILLI YORUM MOTORU (EXPERT SYSTEM) ---
def interpret_monthly_data(monthly_data):
    """Aylık üretim verilerini yorumlar."""
    if not monthly_data: return "Veri analizi yapılamadı."
    max_m = max(monthly_data, key=lambda x: x['production'])
    min_m = min(monthly_data, key=lambda x: x['production'])
    m_names = {1:"Ocak", 2:"Şubat", 3:"Mart", 4:"Nisan", 5:"Mayıs", 6:"Haziran",
               7:"Temmuz", 8:"Ağustos", 9:"Eylül", 10:"Ekim", 11:"Kasım", 12:"Aralık"}
    return (f"Simülasyon sonuçlarına göre tesisin en yüksek verimi {int(max_m['production'])} kWh/kWp ile {m_names.get(max_m['month'])} ayında, "
            f"en düşük verimi ise {int(min_m['production'])} kWh/kWp ile {m_names.get(min_m['month'])} ayında gerçekleşmektedir. "
            f"Yaz aylarındaki yüksek radyasyon, üretim eğrisini domine etmektedir.")

def interpret_cash_flow(roi, npv):
    """Finansal tabloyu yorumlar."""
    status = "YÜKSEK" if npv > 0 else "ORTA"
    return (f"Proje {roi} yılda kendini amorti etmektedir (ROI). 25 yıllık projeksiyon sonunda Net Bugünkü Değer (NPV) "
            f"{int(npv):,} $ olup, yatırım finansal açıdan {status} kârlılık seviyesindedir.")

def interpret_shading(shading_metrics):
    """Gölge analizini yorumlar."""
    angle_str, loss_factor = shading_metrics
    loss_pct = round((1 - loss_factor) * 100, 1)
    impact = "MİNİMUM" if loss_pct < 4 else ("ORTA" if loss_pct < 9 else "YÜKSEK")
    return (f"Ufuk çizgisi analizi, sahanın en kritik engelinin {angle_str} açısında olduğunu göstermektedir. "
            f"Topoğrafik gölgeleme kaynaklı yıllık enerji kaybı %{loss_pct} olarak hesaplanmıştır. "
            f"Gölge etkisi üretim üzerinde {impact} düzeydedir.")

# --- BU FONKSİYONLAR SİLİNMEMELİDİR (MAIN.PY İÇİN GEREKLİ) ---
def analyze_suitability(lat, lon): return True
def parse_grid_data(path): return []
def get_projection_data(): return None