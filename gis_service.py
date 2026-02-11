import json
import os
import streamlit as st


# --- PARSEL İŞLEME SERVİSİ (Aynen Korunuyor) ---
def process_parsel_geojson(geojson_data):
    """
    TKGM'den gelen GeoJSON verisini işler ve parselin merkez noktasını hesaplar.
    """
    try:
        if not geojson_data: return None, None, False, "Boş veri."
        features = geojson_data.get("features", [])
        if not features: return None, None, False, "GeoJSON içinde 'features' bulunamadı."
        geometry = features[0].get("geometry", {})
        coords = geometry.get("coordinates", [])
        if not coords: return None, None, False, "Koordinat verisi yok."

        # Polygon Merkez Hesabı
        if geometry["type"] == "Polygon":
            first_point = coords[0][0]  # [lon, lat]
            p_lon, p_lat = first_point[0], first_point[1]
        elif geometry["type"] == "MultiPolygon":
            first_point = coords[0][0][0]
            p_lon, p_lat = first_point[0], first_point[1]
        else:
            return None, None, False, "Sadece Polygon desteklenir."

        if not (35 < p_lat < 43): p_lat, p_lon = p_lon, p_lat
        return p_lat, p_lon, True, "Başarılı"
    except Exception as e:
        return None, None, False, f"İşleme hatası: {str(e)}"


# --- TEİAŞ GERÇEK VERİ SERVİSİ (GÜNCELLENDİ) ---
def get_substation_data(tm_name):
    """
    data/teias_kapasite.json dosyasından GERÇEK veriyi okur.
    Rastgele simülasyon yerine, PDF'ten aktarılan veriyi kullanır.
    """

    # 1. JSON Veritabanı Yolunu Bul
    base_dir = os.path.dirname(os.path.abspath(__file__))
    json_path = os.path.join(base_dir, "data", "teias_kapasite.json")

    found_data = None

    # 2. Veritabanını Ara
    if os.path.exists(json_path):
        try:
            with open(json_path, 'r', encoding='utf-8') as f:
                db = json.load(f)

            # İsim Normalizasyonu (Büyük/Küçük harf ve Türkçe karakter toleransı)
            def normalize(s):
                if not isinstance(s, str): return ""
                return s.replace("İ", "I").replace("ı", "i").upper().strip()

            search_name = normalize(tm_name)

            # Veritabanındaki listeyi tara
            for item in db.get("substations", []):
                db_name = normalize(item["name"])

                # Tam eşleşme veya içerme kontrolü
                # Örn: "NIKSAR" aranıyorsa "NIKSAR TM" kabul edilir.
                if search_name == db_name or search_name in db_name or db_name in search_name:
                    found_data = item
                    break
        except Exception as e:
            print(f"Veritabanı okuma hatası: {e}")

    # 3. Veri Bulunduysa Formatla ve Döndür
    if found_data:
        # PDF'ten gelen veriyi kullan
        free_val = found_data.get("free_mw", 0)
        # Eğer total_mw yoksa varsayılan 100 kabul et (Oran hesabı için)
        total_val = found_data.get("total_mw", 100)
        used_val = total_val - free_val

        if total_val > 0:
            rate = int((used_val / total_val) * 100)
        else:
            rate = 0

        # Renk Belirle (Kapasiteye göre)
        if free_val < 5:
            color = "#dc3545"  # Kırmızı (Kapasite Yok)
        elif free_val < 20:
            color = "#fd7e14"  # Turuncu (Kısıtlı)
        else:
            color = "#28a745"  # Yeşil (Uygun)

        return {
            "name": found_data.get("name", tm_name),
            "voltage": found_data.get("voltage", "154 kV"),
            "total_mw": total_val,
            "used_mw": round(used_val, 1),
            "free_mw": round(free_val, 2),  # Virgülden sonra 2 hane
            "usage_rate": rate,
            "status": found_data.get("status", "BİLİNMİYOR"),
            "color": color
        }

    # 4. Veri Bulunamazsa (Varsayılan - Gri Renk)
    # "Veri Yok" = İsim eşleşmedi demektir. Kapasite 0 demek değildir.
    return {
        "name": tm_name,
        "voltage": "-",
        "total_mw": 0,
        "used_mw": 0,
        "free_mw": 0,
        "usage_rate": 0,
        "status": "VERİ YOK",
        "color": "#6c757d"  # Gri
    }