import requests
import datetime
import math
from equipment_db import PANEL_LIBRARY

# --- SICAKLIK API AYARLARI ---
API_URL = "https://archive-api.open-meteo.com/v1/archive"


def get_design_temperature(lat, lon):
    """
    Verilen koordinat için son 30 yılın EN DÜŞÜK hava sıcaklığını API'den çeker.
    Mühendislikte 'Worst Case' analizi için 30 yıllık veri (Climate Normal) esastır.
    """
    try:
        end_date = datetime.date.today()
        # GÜNCELLEME: 30 Yıl (yaklaşık 10950 gün) geriye gidiyoruz
        start_date = end_date - datetime.timedelta(days=10950)

        params = {
            "latitude": lat,
            "longitude": lon,
            "start_date": start_date.strftime("%Y-%m-%d"),
            "end_date": end_date.strftime("%Y-%m-%d"),
            "daily": "temperature_2m_min",
            "timezone": "auto"
        }

        # Veri boyutu arttığı için timeout süresini güvenlik payıyla 10 saniye yapalım
        response = requests.get(API_URL, params=params, timeout=10)

        if response.status_code == 200:
            data = response.json()
            if "daily" in data and "temperature_2m_min" in data["daily"]:
                min_temps = data["daily"]["temperature_2m_min"]
                valid_temps = [t for t in min_temps if t is not None]

                if valid_temps:
                    absolute_min = min(valid_temps)
                    # Güvenlik Marjı: Ekstra -2°C (Hissedilen/mikroklima farkı için)
                    return round(absolute_min - 2, 1)

        print("API verisi alınamadı, varsayılan değer (-15) kullanılıyor.")
        return -15

    except Exception as e:
        print(f"Sıcaklık API Hatası: {e}")
        return -15


# --- İÇ HESAPLAMA FONKSİYONLARI ---

def _calculate_voc_max(panel_data, t_min):
    """
    Panelin Voc değerini en düşük sıcaklığa göre revize eder.
    """
    if panel_data["voc"] <= 0: return 0
    delta_t = t_min - 25
    coef_decimal = panel_data["temp_coef_voc"] / 100.0
    voc_max = panel_data["voc"] * (1 + (coef_decimal * delta_t))
    return round(voc_max, 2)


def _calculate_max_string_size(inverter_max_v, voc_max_per_panel):
    """
    İnverter giriş voltajına göre max panel sayısını bulur.
    """
    if voc_max_per_panel <= 0: return 0
    return math.floor(inverter_max_v / voc_max_per_panel)


# --- ANA HESAPLAMA ORKESTRASYONU ---

def perform_string_analysis(lat, lon, panel_data, inverter_data):
    """
    Tüm string hesaplama sürecini yöneten ana fonksiyon.
    """
    # 1. Tasarım Sıcaklığını Bul (30 Yıllık Veri ile)
    t_min = get_design_temperature(lat, lon)

    # 2. İnverter Limitini Al
    inv_vmax = inverter_data.get("v_max_dc", 1100)

    # 3. Kış Voltajını Hesapla
    voc_max_winter = _calculate_voc_max(panel_data, t_min)

    # 4. String Kapasitesini Hesapla
    max_panels = _calculate_max_string_size(inv_vmax, voc_max_winter)

    return {
        "design_temp": t_min,
        "panel_voc_max": voc_max_winter,
        "inverter_vmax": inv_vmax,
        "max_string_size": max_panels
    }