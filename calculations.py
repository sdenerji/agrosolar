import requests
import pandas as pd
import json
import math
import urllib3
import matplotlib.pyplot as plt
import numpy as np
import streamlit as st
import os

# SSL uyarılarını kapatmak için
urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)


# --- 1. UFUK ANALİZİ (ÖN BELLEKLİ) ---
@st.cache_data(ttl=3600, show_spinner="Ufuk verileri alınıyor...")
def get_horizon_analysis(lat, lon):
    url = "https://re.jrc.ec.europa.eu/api/v5_3/printhorizon"
    params = {'lat': lat, 'lon': lon, 'outputformat': 'json'}
    try:
        response = requests.get(url, params=params, timeout=15, verify=False)
        if response.status_code == 200:
            data = response.json()
            if 'outputs' in data and 'horizon_profile' in data['outputs']:
                df = pd.DataFrame(data['outputs']['horizon_profile'])
                return df.rename(columns={'A': 'Azimut', 'H_hor': 'Ufuk_Yuksekligi'})
        else:
            print(f"PVGIS Hatası: {response.status_code}")
    except Exception as e:
        print(f"Bağlantı Hatası: {e}")
    return None


def get_shading_metrics(df):
    if df is None or df.empty: return "0°", 1.00
    max_idx = df['Ufuk_Yuksekligi'].idxmax()
    max_angle = df.loc[max_idx, 'Ufuk_Yuksekligi']
    max_azimut = df.loc[max_idx, 'Azimut']
    yon = "Guney" if abs(max_azimut) < 45 else ("Dogu" if max_azimut < -45 else "Bati")
    max_engeli_str = f"{max_angle:.1f}° ({yon})"
    south_shading = df[(df['Azimut'] > -90) & (df['Azimut'] < 90)]['Ufuk_Yuksekligi'].mean()
    loss_factor = max(0.85, 1.0 - (south_shading * 0.005))
    return max_engeli_str, round(loss_factor, 2)


def evaluate_shading_suitability(max_angle):
    if max_angle < 10:
        return "UYGUN", "green", "Cevresel engel az, uretim verimli."
    elif 10 <= max_angle < 25:
        return "ORTA / DIKKAT", "orange", "Kis aylarinda golge kaybi olusabilir."
    else:
        return "UYGUN DEGIL", "red", "Yuksek engel! Proje riskli."


# --- 2. ARAZİ ANALİZİ ---
@st.cache_data(ttl=3600, show_spinner="Arazi yapısı inceleniyor...")
def calculate_slope_aspect(lat, lon):
    url = "https://api.open-meteo.com/v1/elevation"
    delta = 0.001
    lats = [lat, lat + delta, lat - delta, lat, lat]
    lons = [lon, lon, lon, lon + delta, lon - delta]

    try:
        params = {"latitude": lats, "longitude": lons}
        response = requests.get(url, params=params, timeout=10)

        if response.status_code == 200:
            elevations = response.json().get("elevation", [])
            if not elevations or len(elevations) < 5:
                return 0, 0.0, "Bilinmiyor"

            z_c = elevations[0]
            z_n = elevations[1]
            z_s = elevations[2]
            z_e = elevations[3]
            z_w = elevations[4]

            dist_y = 2 * delta * 111132
            lat_rad = math.radians(lat)
            dist_x = 2 * delta * 111132 * math.cos(lat_rad)

            dz_dx = (z_e - z_w) / dist_x
            dz_dy = (z_n - z_s) / dist_y

            slope_rad = math.atan(math.sqrt(dz_dx ** 2 + dz_dy ** 2))
            slope_pct = math.tan(slope_rad) * 100

            if slope_pct < 3.0:
                return int(z_c), 0.0, "Düz"

            aspect_rad = math.atan2(-dz_dy, -dz_dx)
            aspect_deg = math.degrees(aspect_rad)
            compass_aspect = (90 - aspect_deg + 360) % 360

            directions = ["Kuzey", "Kuzeydoğu", "Doğu", "Güneydoğu", "Güney", "Güneybatı", "Batı", "Kuzeybatı"]
            index = int((compass_aspect + 22.5) / 45.0) % 8
            aspect_label = directions[index]

            return int(z_c), round(slope_pct, 1), aspect_label

    except Exception as e:
        print(f"Arazi API Hatası: {e}")

    return 0, 0.0, "Bilinmiyor"


# --- 3. ŞEBEKE VERİ İŞLEME ---
@st.cache_data(show_spinner="Ulusal Şebeke Verileri Yükleniyor...")
def parse_grid_data(file_path):
    parsed_elements = []
    if not os.path.exists(file_path): return parsed_elements
    if file_path.endswith('.geojson'):
        try:
            with open(file_path, 'r', encoding='utf-8') as f:
                data = json.load(f)
            for feature in data.get('features', []):
                props = feature.get('properties', {})
                geom = feature.get('geometry', {})
                if geom['type'] == 'Point':
                    lon, lat = geom['coordinates']
                    parsed_elements.append({'type': 'Point', 'name': props.get('name', 'İsimsiz'), 'coords': [lat, lon],
                                            'mw': props.get('mw', 0), 'total': props.get('total', 100)})
                elif geom['type'] == 'LineString':
                    path = [[c[1], c[0]] for c in geom['coordinates']]
                    parsed_elements.append({'type': 'Line', 'name': props.get('name', 'İsimsiz'), 'path': path})
            return parsed_elements
        except:
            return []
    return []


# --- 4. GÜNEŞ POTANSİYELİ ---
@st.cache_data(ttl=3600, show_spinner="Güneş potansiyeli ve maliyet hesaplanıyor...")
def get_solar_potential(lat, lon, baki_str, kw_power, egim, rakim, loss_factor=1.0, elec_price=0.13):
    url = "https://re.jrc.ec.europa.eu/api/v5_3/PVcalc"
    if baki_str == "Düz": baki_str = "Güney"
    aspect_map = {
        "Güney": 0, "Güneydoğu": -45, "Güneybatı": 45,
        "Doğu": -90, "Batı": 90,
        "Kuzeydoğu": -135, "Kuzeybatı": 135, "Kuzey": 180, "Düz": 0
    }
    clean_baki = baki_str.replace("ı", "i").replace("ğ", "g").replace("ü", "u").replace("ş", "s").replace("ö", "o")
    aspect_val = aspect_map.get(baki_str, 0)
    params = {
        'lat': lat, 'lon': lon, 'peakpower': kw_power,
        'loss': 14, 'outputformat': 'json',
        'angle': egim if egim > 5 else 30,
        'aspect': aspect_val
    }
    try:
        response = requests.get(url, params=params, timeout=20, verify=False)
        if response.status_code == 200:
            data = response.json()
            raw_kwh = data['outputs']['totals']['fixed']['E_y']
            initial_annual_kwh = raw_kwh * loss_factor
            slope_weight = 1.0 + (egim / 100) * 0.5
            aspect_weight = 1.0
            total_cost = kw_power * 850 * slope_weight
            degradation_rate = 0.01
            total_production_25y = initial_annual_kwh * sum((1 - degradation_rate) ** t for t in range(25))
            annual_revenue_y1 = initial_annual_kwh * elec_price
            roi = total_cost / annual_revenue_y1 if annual_revenue_y1 > 0 else 0
            lcoe = total_cost / total_production_25y
            return int(initial_annual_kwh), annual_revenue_y1, total_cost, round(roi, 1), lcoe
    except:
        pass
    return 0, 0, 0, 0, 0


def analyze_suitability(egim, baki):
    # Bu eski fonksiyon yerine get_suitability_badge kullanacağız
    return {}


# --- YENİ EKLENEN FONKSİYON ---
def get_suitability_badge(slope, aspect):
    """
    Eğim ve Bakı değerlerine göre UI için renk, ikon ve mesaj döndürür.
    Logic katmanında olması gereken bir karar mekanizmasıdır.
    """
    # 1. Eğim Analizi
    if slope < 7:
        s_color, s_msg, s_icon = "green", "Mükemmel (Düz)", "✅"
    elif slope < 15:
        s_color, s_msg, s_icon = "green", "Uygun", "✅"
    elif slope < 25:
        s_color, s_msg, s_icon = "orange", "Orta/Maliyetli", "⚠️"
    else:
        s_color, s_msg, s_icon = "red", "Riskli (Dik)", "⛔"

    # 2. Bakı (Cephe) Analizi
    if slope < 5.0 or aspect == "Düz":
        a_color = "green"
        a_msg = "Önemsiz (Düz Zemin)"
        a_icon = "🌍"
    else:
        good = ["Güney", "Güneydoğu", "Güneybatı"]
        medium = ["Doğu", "Batı"]

        if aspect in good:
            a_color, a_msg, a_icon = "green", "Çok İyi", "☀️"
        elif aspect in medium:
            a_color, a_msg, a_icon = "orange", "Orta Verim", "⛅"
        else:
            a_color, a_msg, a_icon = "red", "Düşük Verim", "☁️"

    return s_color, s_msg, s_icon, a_color, a_msg, a_icon


# --- GRAFİK FONKSİYONLARI ---
def generate_earnings_graph(initial_kwh, elec_price, total_cost, roi_years):
    years = np.arange(1, 26)
    cumulative_profit = []
    current_profit = -total_cost
    for year in years:
        yearly_revenue = initial_kwh * (0.99 ** (year - 1)) * elec_price
        current_profit += yearly_revenue
        cumulative_profit.append(current_profit)
    plt.figure(figsize=(10, 5))
    plt.plot(years, cumulative_profit, color='#28a745', linewidth=3)
    plt.axvline(x=roi_years, color='#E74C3C', linestyle='--')
    plt.axhline(0, color='black', linewidth=0.8)
    plt.fill_between(years, cumulative_profit, 0, where=(np.array(cumulative_profit) > 0), color='#d4edda', alpha=0.5)
    path = "temp_earnings_graph.png"
    plt.savefig(path, bbox_inches='tight', dpi=100);
    plt.close()
    return path


def get_projection_data(initial_kwh, elec_price, total_cost):
    years_to_show = [1, 5, 10, 15, 20, 25]
    projection = []
    cumulative_revenue = 0
    for year in range(1, 26):
        yearly_production = initial_kwh * (0.99 ** (year - 1))
        cumulative_revenue += (yearly_production * elec_price)
        if year in years_to_show:
            projection.append(
                {"yil": year, "uretim": int(yearly_production), "gelir": int(yearly_production * elec_price),
                 "net": int(cumulative_revenue - total_cost)})
    return projection


def generate_horizon_plot(lat, lon):
    df = get_horizon_analysis(lat, lon)
    if df is None: return None
    plt.figure(figsize=(10, 4))
    plt.fill_between(df['Azimut'], df['Ufuk_Yuksekligi'], 0, color='gray', alpha=0.3)
    plt.plot(df['Azimut'], df['Ufuk_Yuksekligi'], color='black', linewidth=1)
    path = "temp_horizon_graph.png"
    plt.savefig(path, bbox_inches='tight', dpi=100);
    plt.close()
    return path