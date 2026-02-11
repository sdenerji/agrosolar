import pdfplumber
import json
import os
import difflib
import re

# --- DOSYA YOLLARI ---
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
DATA_DIR = os.path.join(BASE_DIR, "data")
PDF_PATH = os.path.join(DATA_DIR, "guncel_kapasite.pdf")
GEOJSON_PATH = os.path.join(DATA_DIR, "sebeke_verisi.geojson")
OUTPUT_JSON_PATH = os.path.join(DATA_DIR, "teias_kapasite.json")


# --- GELİŞMİŞ NORMALİZASYON FONKSİYONU ---
def normalize_name(name):
    """
    İsimleri kök haline getirir.
    Örn: 'ALMUS HES' -> 'ALMUS'
    Örn: 'NİKSAR TM' -> 'NIKSAR'
    """
    if not name: return ""

    # 1. Büyük harf ve Türkçe karakter düzeltme
    name = str(name).replace('İ', 'I').replace('ı', 'i').upper()
    replacements = {"Ş": "S", "Ğ": "G", "Ü": "U", "Ö": "O", "Ç": "C"}
    for old, new in replacements.items():
        name = name.replace(old, new)

    # 2. SİLİNECEK KELİMELER LİSTESİ (Genişletildi)
    # Buradaki kelimeleri isimden tamamen atıyoruz.
    remove_words = [
        " TM", " TRAFO MERKEZI", " GIS", " MERKEZI", " SUBSTATION",
        " HES", " RES", " GES", " KOK", " DM", " DGKCS", " SANTRALI"
    ]

    for word in remove_words:
        name = name.replace(word, "")

    # 3. Sadece harf ve rakamları bırak (Noktalama işaretlerini sil)
    name = re.sub(r'[^A-Z0-9]', '', name)

    return name.strip()


def run_import():
    print("🚀 TEİAŞ Veri Aktarım Aracı (Gelişmiş Eşleştirme)...")

    # 1. GEOJSON'I OKU VE HARİTALAMA YAP
    if not os.path.exists(GEOJSON_PATH):
        print("❌ GeoJSON bulunamadı.")
        return

    with open(GEOJSON_PATH, "r", encoding="utf-8") as f:
        geo_data = json.load(f)

    # GeoJSON'daki her ismin hem kendisini hem de normalize halini sakla
    # Key: Normalize İsim (ALMUS), Value: Gerçek İsim (ALMUS HES)
    geo_lookup = {}

    for feature in geo_data.get("features", []):
        if feature["geometry"]["type"] == "Point":
            raw_name = feature["properties"].get("name", "")
            if raw_name:
                norm = normalize_name(raw_name)
                # Eğer birden fazla aynı isim varsa (örn: ALMUS ve ALMUS TM), ilkini al
                if norm not in geo_lookup:
                    geo_lookup[norm] = raw_name

    print(f"🗺️ Harita İndeksi: {len(geo_lookup)} nokta tarandı.")

    # 2. PDF'İ OKU
    if not os.path.exists(PDF_PATH):
        print("❌ PDF bulunamadı.")
        return

    print("📄 PDF İşleniyor...")
    matched_data = []
    total_mw = 0
    match_count = 0

    with pdfplumber.open(PDF_PATH) as pdf:
        for page in pdf.pages:
            table = page.extract_table()
            if not table: continue
            for row in table:
                if not row or len(row) < 3: continue

                tm_name_pdf = row[1]  # PDF'teki İsim (Örn: ALMUS)
                capacity_str = row[-1]

                if not tm_name_pdf or "TRANSFORMATÖR" in str(tm_name_pdf): continue

                # Kapasite Dönüşümü
                try:
                    if isinstance(capacity_str, str):
                        clean_cap = capacity_str.replace(".", "").replace(",", ".")
                        capacity_val = float(clean_cap)
                    else:
                        capacity_val = float(capacity_str)
                except:
                    capacity_val = 0.0

                # --- EŞLEŞTİRME MANTIĞI ---
                norm_pdf = normalize_name(tm_name_pdf)  # ALMUS -> ALMUS

                # 1. Doğrudan Kök İsim Eşleşmesi
                real_name = geo_lookup.get(norm_pdf)  # geo_lookup["ALMUS"] -> "ALMUS HES" döner mi?
                match_type = "TAM"

                # 2. Eğer bulamazsa, "İçerme" kontrolü yap
                if not real_name:
                    for g_norm, g_raw in geo_lookup.items():
                        # PDF'teki isim haritadakinin içindeyse veya tam tersi
                        if (norm_pdf in g_norm) or (g_norm in norm_pdf):
                            real_name = g_raw
                            match_type = "KISMI"
                            break

                # 3. Hala yoksa Bulanık Arama
                if not real_name:
                    matches = difflib.get_close_matches(norm_pdf, geo_lookup.keys(), n=1, cutoff=0.85)
                    if matches:
                        real_name = geo_lookup[matches[0]]
                        match_type = "BULANIK"

                if real_name:
                    # Durum Rengi
                    if capacity_val < 5:
                        status = "KAPASİTE YOK"
                    elif capacity_val < 20:
                        status = "KISITLI"
                    else:
                        status = "UYGUN"

                    matched_data.append({
                        "name": real_name,  # Haritadaki ismi kaydet (Popup için şart)
                        "teias_name": tm_name_pdf,
                        "free_mw": capacity_val,
                        "total_mw": 100,  # Varsayılan
                        "status": status,
                        "voltage": "154 kV"
                    })
                    total_mw += capacity_val
                    match_count += 1
                    # Log bas (Hata ayıklama için)
                    # print(f"✅ Eşleşti: PDF[{tm_name_pdf}] -> HARİTA[{real_name}] ({match_type})")

    # 3. KAYDET
    output = {
        "updated_at": "2026-02-12",
        "source": "TEİAŞ PDF",
        "total_free": f"{total_mw:,.2f} MW",
        "substations": matched_data
    }

    os.makedirs(DATA_DIR, exist_ok=True)
    with open(OUTPUT_JSON_PATH, "w", encoding="utf-8") as f:
        json.dump(output, f, indent=4, ensure_ascii=False)

    print(f"\n✅ Veritabanı Güncellendi!")
    print(f"🔗 {match_count} trafo eşleştirildi.")


if __name__ == "__main__":
    run_import()