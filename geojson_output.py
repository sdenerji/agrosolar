import os
import zipfile
import re
import json


def parse_grid_data_to_geojson(kmz_path):
    features = []
    if not os.path.exists(kmz_path):
        print(f"Hata: Dosya bulunamadı -> {kmz_path}")
        return None

    try:
        raw_content = ""
        with zipfile.ZipFile(kmz_path, 'r') as z:
            kml_files = [f for f in z.namelist() if f.lower().endswith('.kml')]
            if not kml_files: return None
            with z.open(kml_files[0]) as f:
                raw_content = f.read().decode('utf-8', errors='ignore')

        pm_pattern = re.compile(r'<[\w:]*Placemark.*?>(.*?)</[\w:]*Placemark>', re.DOTALL)
        placemarks = pm_pattern.findall(raw_content)

        for pm_text in placemarks:
            name = "İsimsiz"
            # REGEX ile İsim bulma
            trafo_match = re.search(r'name="TRAFO_ADI">([^<]+)<', pm_text)
            if trafo_match:
                name = trafo_match.group(1).strip()
            else:
                name_match = re.search(r'<[\w:]*name>(.*?)</[\w:]*name>', pm_text)
                if name_match: name = name_match.group(1).strip()

            # REGEX ile Koordinat bulma
            coord_match = re.search(r'<[\w:]*coordinates>(.*?)</[\w:]*coordinates>', pm_text, re.DOTALL)
            if coord_match:
                c_data = coord_match.group(1).strip().split()

                # NOKTA (Trafo)
                if len(c_data) == 1:
                    parts = c_data[0].split(',')
                    if len(parts) >= 2:
                        lon, lat = float(parts[0]), float(parts[1])
                        features.append({
                            "type": "Feature",
                            "geometry": {"type": "Point", "coordinates": [lon, lat]},
                            "properties": {"name": name, "type": "Point", "mw": 0, "total": 100}
                        })

                # HAT (LineString)
                elif len(c_data) > 1:
                    path = [[float(p.split(',')[0]), float(p.split(',')[1])] for p in c_data if len(p.split(',')) >= 2]
                    features.append({
                        "type": "Feature",
                        "geometry": {"type": "LineString", "coordinates": path},
                        "properties": {"name": name, "type": "Line", "kv": "154 kV"}
                    })

        return {"type": "FeatureCollection", "features": features}

    except Exception as e:
        print(f"Dönüşüm Hatası: {e}")
        return None


if __name__ == "__main__":
    kmz_yolu = "data/trafo_merkez.kmz"
    cikti_yolu = "data/sebeke_verisi.geojson"

    geojson_data = parse_grid_data_to_geojson(kmz_yolu)
    if geojson_data:
        with open(cikti_yolu, "w", encoding="utf-8") as f:
            json.dump(geojson_data, f, ensure_ascii=False, indent=4)
        print(f"✅ İşlem Tamam! {len(geojson_data['features'])} adet veri aktarıldı.")