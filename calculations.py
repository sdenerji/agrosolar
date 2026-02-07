import requests
import pandas as pd
import json
import math
import urllib3
import matplotlib.pyplot as plt
import numpy as np
import streamlit as st
import zipfile
import os
import xml.etree.ElementTree as ET
import re

# --- YENİ: Veritabanı entegrasyonu için import ---
from gis_service import get_substation_data

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
    return None


def get_shading_metrics(df):
    """Ufuk analizinden max engel ve tahmini kayıp katsayısını hesaplar."""
    if df is None or df.empty:
        return "0°", 1.00

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


# --- 2. ARAZİ ANALİZİ (ÖN BELLEKLİ) ---
@st.cache_data(ttl=3600, show_spinner="Arazi yapısı inceleniyor...")
def calculate_slope_aspect(lat, lon):
    delta = 0.0008
    locations = [
        {"latitude": lat, "longitude": lon},
        {"latitude": lat + delta, "longitude": lon},
        {"latitude": lat - delta, "longitude": lon},
        {"latitude": lat, "longitude": lon + delta},
        {"latitude": lat, "longitude": lon - delta}
    ]
    try:
        response = requests.post(
            "https://api.open-elevation.com/api/v1/lookup",
            json={"locations": locations},
            timeout=15,
            verify=False
        )
        if response.status_code == 200:
            res = response.json()["results"]
            z = [r["elevation"] for r in res]
            dist = delta * 111139
            dz_dx = (z[3] - z[4]) / (2 * dist)
            dz_dy = (z[1] - z[2]) / (2 * dist)
            slope_val = math.sqrt(dz_dx ** 2 + dz_dy ** 2)
            egim = round(slope_val * 100, 1)

            if slope_val < 0.001:
                baki = "Duz"
            else:
                aspect_rad = math.atan2(dz_dy, -dz_dx)
                aspect_deg = (math.degrees(aspect_rad) + 360) % 360
                directions = ["Kuzey", "Kuzeydogu", "Dogu", "Guneydogu", "Guney", "Guneybati", "Bati", "Kuzeybati"]
                baki = directions[int(((aspect_deg + 22.5) % 360) / 45)]

            return int(z[0]), egim, baki
    except Exception as e:
        print(f"Arazi Hatası: {e}")
    return 0, 0.0, "Bilinmiyor"


# --- 3. ŞEBEKE VERİ İŞLEME (DİNAMİK DB ENTEGRASYONLU) ---
# GÖRSEL KOMUTLAR YOK, SADECE SAF VERİ İŞLEME
@st.cache_data(show_spinner="Ulusal Şebeke Verileri Yükleniyor...")
def parse_grid_data(file_path):
    parsed_elements = []
    if not os.path.exists(file_path):
        return parsed_elements

    # --- 1. HIZLI MOD: GEOJSON OKUMA ---
    if file_path.endswith('.geojson'):
        try:
            with open(file_path, 'r', encoding='utf-8') as f:
                data = json.load(f)

            for feature in data.get('features', []):
                props = feature.get('properties', {})
                geom = feature.get('geometry', {})

                if geom['type'] == 'Point':
                    # GeoJSON [lon, lat] -> Folium [lat, lon]
                    lon, lat = geom['coordinates']
                    parsed_elements.append({
                        'type': 'Point',
                        'name': props.get('name', 'İsimsiz'),
                        'coords': [lat, lon],
                        'mw': props.get('mw', 0),  # Kapasite verisi
                        'total': props.get('total', 100)  # Toplam kapasite
                    })
                elif geom['type'] == 'LineString':
                    path = [[c[1], c[0]] for c in geom['coordinates']]
                    parsed_elements.append({
                        'type': 'Line',
                        'name': props.get('name', 'İsimsiz'),
                        'path': path
                    })
            return parsed_elements
        except Exception as e:
            print(f"GeoJSON Okuma Hatası: {e}")
            return []


# --- 4. GÜNEŞ POTANSİYELİ (ÖN BELLEKLİ VE AĞIRLIKLI) ---
@st.cache_data(ttl=3600, show_spinner="Güneş potansiyeli ve maliyet hesaplanıyor...")
def get_solar_potential(lat, lon, baki_str, kw_power, egim, rakim, loss_factor=1.0, elec_price=0.13):
    url = "https://re.jrc.ec.europa.eu/api/v5_3/PVcalc"
    aspect_map = {
        "Guney": 0, "Guneydogu": -45, "Guneybati": 45,
        "Dogu": -90, "Bati": 90,
        "Kuzeydogu": -135, "Kuzeybati": 135, "Kuzey": 180, "Duz": 0
    }
    params = {
        'lat': lat, 'lon': lon, 'peakpower': kw_power,
        'loss': 14, 'outputformat': 'json',
        'angle': egim if egim > 2 else 35,
        'aspect': aspect_map.get(baki_str, 0)
    }
    try:
        response = requests.get(url, params=params, timeout=20, verify=False)
        if response.status_code == 200:
            data = response.json()
            raw_kwh = data['outputs']['totals']['fixed']['E_y']
            initial_annual_kwh = raw_kwh * loss_factor

            slope_weight = 1.0 + (egim / 100) * 1.2
            aspect_weight = 1.10 if "Kuzey" in baki_str else 1.0
            total_cost = kw_power * 850 * slope_weight * aspect_weight

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
    is_slope_ok = egim <= 20
    uygun_yonler = ["Guney", "Guneydogu", "Guneybati", "Duz", "Guney", "Guneydogu", "Guneybati"]
    is_baki_ok = baki in uygun_yonler
    return {
        "slope": {"status": "UYGUN" if is_slope_ok else "UYGUN DEGIL", "color": "#28a745" if is_slope_ok else "#dc3545",
                  "is_ok": is_slope_ok},
        "aspect": {"status": "UYGUN" if is_baki_ok else "UYGUN DEGIL", "color": "#28a745" if is_baki_ok else "#dc3545",
                   "is_ok": is_baki_ok}
    }


def generate_earnings_graph(initial_kwh, elec_price, total_cost, roi_years):
    years = np.arange(1, 26)
    cumulative_profit = []
    current_profit = -total_cost
    for year in years:
        yearly_revenue = initial_kwh * (0.99 ** (year - 1)) * elec_price
        current_profit += yearly_revenue
        cumulative_profit.append(current_profit)

    plt.figure(figsize=(10, 5))
    plt.plot(years, cumulative_profit, color='#28a745', linewidth=3, label="Kumulatif Kar (USD)")
    plt.axvline(x=roi_years, color='#E74C3C', linestyle='--', linewidth=2, label=f"Amortisman: {roi_years} Yıl")
    plt.axhline(0, color='black', linewidth=0.8)
    plt.fill_between(years, cumulative_profit, 0, where=(np.array(cumulative_profit) > 0), color='#d4edda', alpha=0.5)
    plt.title("25 Yıllık Yatırım ve Kârlılık Projeksiyonu", fontsize=14, fontweight='bold')
    plt.xlabel("Yıl"), plt.ylabel("Net Nakit Akışı (USD)")
    plt.grid(True, alpha=0.3), plt.legend()
    path = "temp_earnings_graph.png"
    plt.savefig(path, bbox_inches='tight', dpi=100), plt.close()
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
    plt.fill_between(df['Azimut'], df['Ufuk_Yuksekligi'], 0, color='gray', alpha=0.3, label="Ufuk Engeli")
    plt.plot(df['Azimut'], df['Ufuk_Yuksekligi'], color='black', linewidth=1)
    plt.title(f"Ufuk ve Gölge Analizi ({lat}, {lon})", fontsize=10)
    plt.xlabel("Azimut (°)"), plt.ylabel("Yükseklik Açısı (°)")
    plt.xlim(-180, 180), plt.ylim(0, 90), plt.grid(True, linestyle=':', alpha=0.6), plt.legend(loc='upper right')
    path = "temp_horizon_graph.png"
    plt.savefig(path, bbox_inches='tight', dpi=100), plt.close()
    return path