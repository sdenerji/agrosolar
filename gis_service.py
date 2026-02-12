import json
import os
import re
import requests
import pandas as pd
from shapely.geometry import Polygon, MultiPolygon


# --- YARDIMCI: GELİŞMİŞ İSİM NORMALİZASYONU ---
def normalize_name_for_search(name):
    if not name: return ""
    name = str(name).upper()
    tr_map = str.maketrans("ĞÜŞİÖÇIİ", "GUSIOCII")
    name = name.translate(tr_map)
    remove_words = [
        " TRAFO MERKEZI", " MERKEZI", " MERKEZ", " TRAFO", " TM",
        " HES", " RES", " GES", " JES", " TES",
        " DGKCS", " DGKÇS", " DOGALGAZ",
        " GIS", " KOK", " DM", " INDIRICI",
        " SANTRALI", " SANTRAL", " ENERJI"
    ]
    for word in remove_words:
        normalized_word = word.translate(tr_map)
        name = name.replace(normalized_word, "")
        name = name.replace(word, "")
    clean_name = re.sub(r'[^A-Z0-9]', '', name)
    return clean_name


# --- 1. PARSEL İŞLEME (GÜNCELLENDİ: TAPU BİLGİSİ) ---
def process_parsel_geojson(geojson_data):
    """
    GeoJSON'dan koordinat ve tapu bilgilerini (İl, İlçe, Ada, Parsel) çıkarır.
    """
    try:
        if not geojson_data: return None, None, None, False, "Boş veri."
        features = geojson_data.get("features", [])
        if not features: return None, None, None, False, "GeoJSON features yok."

        # Tapu Bilgilerini Çek (Properties)
        props = features[0].get("properties", {})
        location_data = {
            "il": props.get("ilAd") or props.get("IL") or "-",
            "ilce": props.get("ilceAd") or props.get("ILCE") or "-",
            "mahalle": props.get("mahalleAd") or props.get("MAHALLE") or "-",
            "ada": props.get("adaNo") or props.get("ADA") or "-",
            "parsel": props.get("parselNo") or props.get("PARSEL") or "-"
        }

        geometry = features[0].get("geometry", {})
        coords = geometry.get("coordinates", [])
        if not coords: return None, None, None, False, "Koordinat yok."

        centroid = None
        if geometry["type"] == "Polygon":
            poly = Polygon(coords[0])
            centroid = poly.centroid
        elif geometry["type"] == "MultiPolygon":
            polys = [Polygon(p[0]) for p in coords]
            largest_poly = max(polys, key=lambda a: a.area)
            centroid = largest_poly.centroid

        if centroid:
            p_lon, p_lat = centroid.x, centroid.y
        else:
            return None, None, None, False, "Geometri işlenemedi."

        if not (35 < p_lat < 43):
            p_lat, p_lon = p_lon, p_lat

        # DÖNÜŞ: Lat, Lon, LocationData, Success, Msg
        return p_lat, p_lon, location_data, True, "Başarılı"

    except Exception as e:
        return None, None, None, False, str(e)


# --- 2. TEİAŞ TRAFO VERİSİ EŞLEŞTİRME ---
def get_substation_data(tm_name):
    base_dir = os.path.dirname(os.path.abspath(__file__))
    json_path = os.path.join(base_dir, "data", "teias_kapasite.json")
    found_data = None
    search_key = normalize_name_for_search(tm_name)

    if os.path.exists(json_path) and search_key:
        try:
            with open(json_path, 'r', encoding='utf-8') as f:
                db = json.load(f)
            for item in db.get("substations", []):
                db_name_raw = item.get("name", "")
                db_key = normalize_name_for_search(db_name_raw)
                if search_key == db_key:
                    found_data = item
                    break
                if len(search_key) > 3 and len(db_key) > 3:
                    if search_key in db_key or db_key in search_key:
                        found_data = item
                        break
        except Exception as e:
            print(f"DB Error: {e}")

    if found_data:
        free_val = float(found_data.get("free_mw", 0))
        total_val = float(found_data.get("total_mw", 100))
        if free_val > total_val: total_val = free_val + 10
        used_val = max(0, total_val - free_val)
        rate = int((used_val / total_val) * 100) if total_val > 0 else 0

        if free_val <= 0:
            color = "#dc3545"
        elif free_val < 10:
            color = "#fd7e14"
        else:
            color = "#28a745"

        status_text = "UYGUN" if free_val >= 5 else ("KISITLI" if free_val > 0 else "DOLU")

        return {
            "name": found_data.get("name", tm_name),
            "voltage": found_data.get("voltage", "154 kV"),
            "total_mw": total_val, "used_mw": round(used_val, 1),
            "free_mw": round(free_val, 2), "usage_rate": rate,
            "status": status_text, "color": color
        }

    return {
        "name": tm_name, "voltage": "-", "total_mw": 0, "used_mw": 0, "free_mw": 0,
        "usage_rate": 0, "status": "VERİ YOK", "color": "#6c757d"
    }


# --- 3. PVGIS API ---
def fetch_pvgis_horizon(lat, lon):
    try:
        url = f"https://re.jrc.ec.europa.eu/api/v5_2/printhorizon?lat={lat}&lon={lon}&outputformat=json"
        response = requests.get(url, timeout=10)
        if response.status_code == 200:
            data = response.json()
            if 'outputs' in data and 'horizon_profile' in data['outputs']:
                profile = data['outputs']['horizon_profile']
                df = pd.DataFrame(profile)
                df = df.rename(columns={'A': 'azimuth', 'H_hor': 'height'})
                return df
        return None
    except:
        return None


# --- 4. PVGIS ÜRETİM VE OPTİMİZASYON ---
def get_pvgis_production(lat, lon, kwp=1, tilt=None, azimuth=0):
    url = "https://re.jrc.ec.europa.eu/api/v5_2/PVcalc"
    params = {
        'lat': lat, 'lon': lon, 'peakpower': 1, 'loss': 14,
        'mountingplace': 'free', 'aspect': azimuth, 'outputformat': 'json'
    }
    if tilt is None:
        params['optimalinclination'] = 1
    else:
        params['angle'] = tilt

    try:
        response = requests.get(url, params=params, timeout=10)
        if response.status_code == 200:
            data = response.json()
            inputs = data.get('inputs', {})
            outputs = data.get('outputs', {})

            opt_slope = inputs.get('mounting_system', {}).get('fixed', {}).get('slope', {}).get('value')
            if tilt is not None: opt_slope = tilt

            yearly_yield = outputs.get('totals', {}).get('fixed', {}).get('E_y', 0)

            monthly_data = []
            m_vals = outputs.get('monthly', {}).get('fixed', [])
            for m in m_vals:
                monthly_data.append({"month": m['month'], "production": m['E_m']})

            return {
                "success": True, "optimum_tilt": opt_slope,
                "specific_yield": yearly_yield, "monthly_data": monthly_data
            }
        else:
            return {"success": False, "msg": "API Hatası"}
    except Exception as e:
        return {"success": False, "msg": str(e)}


# --- 5. ŞEBEKE VE HARİTA ---
def parse_grid_data(geojson_path):
    grid_data = []
    try:
        with open(geojson_path, 'r', encoding='utf-8') as f:
            data = json.load(f)
        for feature in data.get('features', []):
            geom = feature.get('geometry', {})
            props = feature.get('properties', {})
            if geom.get('type') == 'Point':
                coords = geom['coordinates']
                grid_data.append(
                    {"type": "Point", "name": props.get("name", "Trafo"), "coords": [coords[1], coords[0]]})
            elif geom.get('type') == 'LineString':
                path = [[p[1], p[0]] for p in geom['coordinates']]
                grid_data.append({"type": "Line", "name": props.get("name", "Hat"), "path": path})
    except:
        return []
    return grid_data


def get_basemaps():
    return {
        "Sokak (OSM)": {"tiles": "OpenStreetMap", "attr": "OpenStreetMap"},
        "Uydu (Esri)": {
            "tiles": "https://server.arcgisonline.com/ArcGIS/rest/services/World_Imagery/MapServer/tile/{z}/{y}/{x}",
            "attr": "Esri"},
        "Topoğrafik (Esri)": {
            "tiles": "https://server.arcgisonline.com/ArcGIS/rest/services/World_Topo_Map/MapServer/tile/{z}/{y}/{x}",
            "attr": "Esri"}
    }