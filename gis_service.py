import json
import os
import re
import requests
import pandas as pd
import numpy as np
from shapely.geometry import Polygon, MultiPolygon
import streamlit as st

# --- API AYARLARI (GÜVENLİ YÖNTEM) ---
# Anahtarı secrets.toml dosyasından çekiyoruz.
try:
    OPENTOPOGRAPHY_API_KEY = st.secrets["general"]["opentopography_key"]
except Exception:
    # Eğer secrets dosyası yoksa veya key girilmemişse uyarı ver ama çökme
    OPENTOPOGRAPHY_API_KEY = None
    # Geliştirme aşamasında geçici fallback (Bunu canlıya alırken silmek iyidir)
    # OPENTOPOGRAPHY_API_KEY = "0b8dbda945ecf12300f2af69ac716015"


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


# --- 1. PARSEL İŞLEME (TAPU BİLGİSİ DAHİL) ---
import json
import os
import re
import requests
import pandas as pd
import numpy as np
from shapely.geometry import Polygon, MultiPolygon
import streamlit as st

# --- API AYARLARI (GÜVENLİ YÖNTEM) ---
try:
    OPENTOPOGRAPHY_API_KEY = st.secrets["general"]["opentopography_key"]
except Exception:
    OPENTOPOGRAPHY_API_KEY = None


# --- YARDIMCI: GELİŞMİŞ İSİM NORMALİZASYONU ---
def normalize_name_for_search(name):
    if not name: return ""
    name = str(name).upper()
    tr_map = str.maketrans("ĞÜŞİÖÇIİ", "GUSIOCII")
    name = name.translate(tr_map)
    remove_words = [" TRAFO MERKEZI", " MERKEZI", " MERKEZ", " TRAFO", " TM", " HES", " RES", " GES", " JES", " TES",
                    " DGKCS", " DGKÇS", " DOGALGAZ", " GIS", " KOK", " DM", " INDIRICI", " SANTRALI", " SANTRAL",
                    " ENERJI"]
    for word in remove_words:
        normalized_word = word.translate(tr_map)
        name = name.replace(normalized_word, "").replace(word, "")
    clean_name = re.sub(r'[^A-Z0-9]', '', name)
    return clean_name


# --- 1. PARSEL İŞLEME (DÜZELTİLDİ: TÜM FORMATLARI DESTEKLER) ---
def process_parsel_geojson(geojson_data):
    """
    GeoJSON'dan koordinat ve tapu bilgilerini (İl, İlçe, Ada, Parsel) çıkarır.
    TKGM (ParselNo, Il) ve Diğer (parselNo, IL) formatlarının hepsini destekler.
    """
    try:
        if not geojson_data: return None, None, None, False, "Boş veri."
        features = geojson_data.get("features", [])
        if not features: return None, None, None, False, "GeoJSON features yok."

        # Tapu Bilgilerini Çek (Properties)
        props = features[0].get("properties", {})

        # --- KRİTİK DÜZELTME BURADA ---
        # .get("Il") -> TKGM formatı için eklendi.
        # .get("ParselNo") -> TKGM formatı için eklendi.
        location_data = {
            "il": props.get("ilAd") or props.get("IL") or props.get("Il") or "-",
            "ilce": props.get("ilceAd") or props.get("ILCE") or props.get("Ilce") or "-",
            "mahalle": props.get("mahalleAd") or props.get("MAHALLE") or props.get("Mahalle") or "-",
            "ada": props.get("adaNo") or props.get("ADA") or props.get("Ada") or "-",
            "parsel": props.get("parselNo") or props.get("PARSEL") or props.get("ParselNo") or "-"
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

        # Koordinat sırası kontrolü
        if not (35 < p_lat < 43):
            p_lat, p_lon = p_lon, p_lat

        return p_lat, p_lon, location_data, True, "Başarılı"

    except Exception as e:
        return None, None, None, False, str(e)


# --- 2. GERÇEK SRTM VERİ ÇEKME (OPENTOPOGRAPHY & CACHING) ---
@st.cache_data(ttl=86400, show_spinner=False)  # 24 Saat Önbellek
def fetch_srtm_elevation_data(bbox):
    """
    OpenTopography API üzerinden gerçek SRTM GL3 (30m) verisini çeker.
    Secrets'tan API Key okur.
    """
    if not OPENTOPOGRAPHY_API_KEY:
        print("UYARI: OpenTopography API Key bulunamadı (secrets.toml).")
        return None

    # BBOX'ı biraz genişletelim
    pad = 0.002  # Yaklaşık 200m
    south, north = bbox[1] - pad, bbox[3] + pad
    west, east = bbox[0] - pad, bbox[2] + pad

    url = "https://portal.opentopography.org/API/globaldem"
    params = {
        "demtype": "SRTMGL3",  # 30m Çözünürlük
        "south": south,
        "north": north,
        "west": west,
        "east": east,
        "outputFormat": "AAIGrid",
        "API_Key": OPENTOPOGRAPHY_API_KEY
    }

    try:
        response = requests.get(url, params=params, timeout=15)

        if response.status_code == 200:
            content = response.text.splitlines()
            header = {}
            data_rows = []

            for line in content:
                parts = line.split()
                if len(parts) == 2 and parts[0].lower() in ['ncols', 'nrows', 'xllcorner', 'yllcorner', 'cellsize',
                                                            'nodata_value']:
                    header[parts[0].lower()] = float(parts[1])
                elif len(parts) > 2:
                    data_rows.append([float(x) for x in parts])

            Z = np.array(data_rows)
            nodata = header.get('nodata_value', -9999)
            Z[Z == nodata] = np.nan

            ncols = int(header['ncols'])
            nrows = int(header['nrows'])
            xll = header['xllcorner']
            yll = header['yllcorner']
            cellsize = header['cellsize']

            x_coords = np.linspace(xll, xll + (ncols * cellsize), ncols)
            y_coords = np.linspace(yll + (nrows * cellsize), yll, nrows)

            return {"x": x_coords, "y": y_coords, "z": Z, "success": True}

        else:
            print(f"API Error: {response.status_code} - {response.text}")
            return None

    except Exception as e:
        print(f"SRTM Fetch Error: {e}")
        return None


def get_real_elevation_at_point(lat, lon):
    """
    Belirli bir nokta için yaklaşık rakım çeker.
    """
    bbox = [lon - 0.0001, lat - 0.0001, lon + 0.0001, lat + 0.0001]
    data = fetch_srtm_elevation_data(bbox)

    if data and data.get('success'):
        return np.nanmean(data['z'])

    return 800.0  # Fallback


# --- 3. TEİAŞ TRAFO VERİSİ EŞLEŞTİRME ---
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

        color = "#dc3545" if free_val <= 0 else ("#fd7e14" if free_val < 10 else "#28a745")
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


# --- 4. PVGIS API ---
def fetch_pvgis_horizon(lat, lon):
    try:
        url = f"https://re.jrc.ec.europa.eu/api/v5_2/printhorizon?lat={lat}&lon={lon}&outputformat=json"
        response = requests.get(url, timeout=10)
        if response.status_code == 200:
            data = response.json()
            if 'outputs' in data and 'horizon_profile' in data['outputs']:
                df = pd.DataFrame(data['outputs']['horizon_profile']).rename(
                    columns={'A': 'azimuth', 'H_hor': 'height'})
                return df
        return None
    except:
        return None


# --- 5. PVGIS ÜRETİM ---
def get_pvgis_production(lat, lon, kwp=1, tilt=None, azimuth=0):
    url = "https://re.jrc.ec.europa.eu/api/v5_2/PVcalc"
    params = {'lat': lat, 'lon': lon, 'peakpower': 1, 'loss': 14, 'mountingplace': 'free', 'aspect': azimuth,
              'outputformat': 'json'}
    if tilt is None:
        params['optimalinclination'] = 1
    else:
        params['angle'] = tilt

    try:
        response = requests.get(url, params=params, timeout=10)
        if response.status_code == 200:
            data = response.json()
            out = data.get('outputs', {});
            inp = data.get('inputs', {})
            opt_tilt = inp.get('mounting_system', {}).get('fixed', {}).get('slope', {}).get('value')
            if tilt is not None: opt_tilt = tilt
            yearly_yield = out.get('totals', {}).get('fixed', {}).get('E_y', 0)
            monthly = [{"month": m['month'], "production": m['E_m']} for m in out.get('monthly', {}).get('fixed', [])]
            return {"success": True, "optimum_tilt": opt_tilt, "specific_yield": yearly_yield, "monthly_data": monthly}
        else:
            return {"success": False, "msg": "API Hatası"}
    except Exception as e:
        return {"success": False, "msg": str(e)}


# --- 6. ŞEBEKE PARSE ---
def parse_grid_data(geojson_path):
    grid_data = []
    try:
        with open(geojson_path, 'r', encoding='utf-8') as f:
            data = json.load(f)
        for feature in data.get('features', []):
            geom = feature.get('geometry', {});
            props = feature.get('properties', {})
            if geom.get('type') == 'Point':
                c = geom['coordinates']
                grid_data.append({"type": "Point", "name": props.get("name", "Trafo"), "coords": [c[1], c[0]]})
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