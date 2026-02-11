# equipment_db.py

# --- GÜNEŞ PANELLERİ VERİTABANI ---
# Format: Marka -> Model -> Özellikler
# width/height: Metre cinsinden
# voc: Açık devre voltajı (V)
# isc: Kısa devre akımı (A)
# temp_coef_voc: Sıcaklık katsayısı (%/C) (Genelde negatiftir)
# p_max: Güç (W)

PANEL_LIBRARY = {
    "CW Enerji": {
        "CW-144-550-BiFacial": {
            "p_max": 550, "voc": 49.8, "isc": 13.9, "width": 1.134, "height": 2.279, "eff": 21.5, "temp_coef_voc": -0.27
        },
        "CW-108-450-Perc": {
            "p_max": 450, "voc": 41.5, "isc": 13.6, "width": 1.134, "height": 1.724, "eff": 20.8, "temp_coef_voc": -0.28
        }
    },
    "HT Solar": {
        "HT-570-BiFacial": {
            "p_max": 570, "voc": 50.6, "isc": 14.1, "width": 1.134, "height": 2.384, "eff": 22.1, "temp_coef_voc": -0.26
        }
    },
    "TommaTech": {
        "TT-550-72PM": {
            "p_max": 550, "voc": 49.9, "isc": 14.0, "width": 1.134, "height": 2.279, "eff": 21.3, "temp_coef_voc": -0.27
        }
    },
    "Phono Solar": {
        "Draco N-Type 585W (PS585M8GFH-24/TNH)": {
            "p_max": 585,          # Maksimum Güç (W)
            "voc": 52.68,          # Açık Devre Voltajı (V)
            "isc": 14.18,          # Kısa Devre Akımı (A)
            "width": 1.134,        # Genişlik (m)
            "height": 2.278,       # Yükseklik (m)
            "eff": 22.65,          # Verimlilik (%)
            "temp_coef_voc": -0.25 # Sıcaklık Katsayısı (%/°C)
        }
    }
}

# --- İNVERTER VERİTABANI ---
# v_max_dc: Maksimum DC Giriş Voltajı (String hesabı için kritik)
# mppt_range: Çalışma aralığı (Bilgi amaçlı)

INVERTER_LIBRARY = {
    "Huawei": {
        "SUN2000-100KTL-M1": {"v_max_dc": 1100, "mppt_min": 200, "mppt_max": 1000},
        "SUN2000-50KTL-M0": {"v_max_dc": 1100, "mppt_min": 200, "mppt_max": 1000},
        "SUN2000-330KTL-H1": {"v_max_dc": 1500, "mppt_min": 500, "mppt_max": 1500} # Yüksek voltajlı
    },
    "Sungrow": {
        "SG110CX": {"v_max_dc": 1100, "mppt_min": 200, "mppt_max": 1000},
        "SG350HX": {"v_max_dc": 1500, "mppt_min": 500, "mppt_max": 1500}
    },
    "SMA": {
        "Sunny Tripower CORE2": {"v_max_dc": 1100, "mppt_min": 200, "mppt_max": 1000},
        "Sunny Highpower PEAK3": {"v_max_dc": 1500, "mppt_min": 680, "mppt_max": 1500}
    },
    "Özel Tanımlı (Manuel)": {
        "Standart 1100V": {"v_max_dc": 1100, "mppt_min": 200, "mppt_max": 1000},
        "Standart 1500V": {"v_max_dc": 1500, "mppt_min": 500, "mppt_max": 1500}
    }
}