import pdfplumber
import json
import os
import difflib
import re
from datetime import datetime

# --- DOSYA YOLLARI ---
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
DATA_DIR = os.path.join(BASE_DIR, "data")
PDF_PATH = os.path.join(DATA_DIR, "guncel_kapasite.pdf")
GEOJSON_PATH = os.path.join(DATA_DIR, "sebeke_verisi.geojson")
OUTPUT_JSON_PATH = os.path.join(DATA_DIR, "teias_kapasite.json")


def normalize_name(name):
    """
    İsimleri temizler ancak ana karakteristiği bozmaz.
    Örn: 'ÇAN-2 TM' -> 'CAN-2' (Tire kalır, TM gider)
    """
    if not name: return ""

    # 1. Temizlik ve Büyük Harf
    name = str(name).replace('\n', ' ').strip().upper()

    # 2. Türkçe Karakter Dönüşümü (Standartlaştırma için şart)
    tr_map = str.maketrans("ĞÜŞİÖÇIİ", "GUSIOCII")
    name = name.translate(tr_map)

    # 3. SİLİNECEK KELİMELER (Sadece teknik terimler)
    # Kelimenin tam eşleşmesi için boşluklu versiyonları silinir.
    remove_words = [
        " TRAFO MERKEZI", " MERKEZI", " MERKEZ", " SUBSTATION",
        " TRAFO", " TM", " GIS", " KOK", " DM", " INDIRICI",
        " HES", " RES", " GES", " JES", " TES",
        " DGKCS", " DGKÇS", " DOGALGAZ", " SANTRALI", " ENERJI"
    ]

    for word in remove_words:
        # Kelimeyi normalize et (listenin kendisini de çevirerek ara)
        clean_word = word.translate(tr_map)
        name = name.replace(clean_word, "").replace(word, "")

    # 4. Fazla boşlukları temizle ama harf/rakam/tire silme
    return name.strip()


def detect_voltage(tm_name):
    """TM isminden gerilim seviyesini tahmin eder."""
    if "380" in tm_name:
        return "380 kV"
    return "154 kV"  # Varsayılan dağıtım gerilimi


def run_import():
    print("🚀 TEİAŞ Veri Aktarım Aracı (Düzeltilmiş Versiyon)...")

    # 1. GEOJSON İNDEKSLEME
    if not os.path.exists(GEOJSON_PATH):
        print("❌ GeoJSON dosyası bulunamadı.")
        return

    with open(GEOJSON_PATH, "r", encoding="utf-8") as f:
        geo_data = json.load(f)

    # GeoJSON lookup sözlüğü: { "NORMALIZE_ISIM": "Gerçek Harita İsmi" }
    geo_lookup = {}
    for feature in geo_data.get("features", []):
        if feature["geometry"]["type"] == "Point":
            raw_name = feature["properties"].get("name", "")
            if raw_name:
                # GeoJSON'daki ismi de aynı kurallarla normalize et
                norm = normalize_name(raw_name)
                # İsim çakışması varsa ilkini tut
                if norm and norm not in geo_lookup:
                    geo_lookup[norm] = raw_name
                # Alternatif: Boşluksuz halini de ekle (CAN 2 -> CAN2)
                norm_nospace = norm.replace(" ", "").replace("-", "")
                if norm_nospace and norm_nospace not in geo_lookup:
                    geo_lookup[norm_nospace] = raw_name

    print(f"🗺️ Harita İndeksi: {len(geo_lookup)} nokta tarandı.")

    # 2. PDF İŞLEME
    if not os.path.exists(PDF_PATH):
        print("❌ PDF dosyası bulunamadı.")
        return

    print("⏳ PDF okunuyor...")
    matched_data = []
    total_mw = 0
    match_count = 0

    with pdfplumber.open(PDF_PATH) as pdf:
        for page in pdf.pages:
            table = page.extract_table()
            if not table: continue

            for row in table:
                # Satır kontrolü: En az 5 sütun olmalı (İl, TM, Bara, Edaş, Kapasite)
                if not row or len(row) < 5: continue

                # --- SÜTUN SEÇİMİ (DÜZELTİLDİ) ---
                # row[0]: İL (Örn: ADANA)
                # row[1]: TM ADI (Örn: ALADAĞ TM)
                # row[4]: KAPASİTE (Örn: 0,00)

                tm_name_pdf = row[1]
                capacity_str = row[4]

                # Başlık veya boş satır kontrolü
                if not tm_name_pdf or "TRANSFORMATÖR" in str(tm_name_pdf): continue

                # Kapasite Dönüşümü (TR Formatı: 1.234,56 -> 1234.56)
                try:
                    if isinstance(capacity_str, str):
                        clean_cap = capacity_str.replace(".", "").replace(",", ".")
                        capacity_val = float(clean_cap)
                    else:
                        capacity_val = float(capacity_str) if capacity_str else 0.0
                except:
                    capacity_val = 0.0

                # --- EŞLEŞTİRME ---
                norm_pdf = normalize_name(tm_name_pdf)  # Örn: "ALADAG"
                norm_pdf_nospace = norm_pdf.replace(" ", "").replace("-", "")  # Örn: "ALADAG"

                real_name = None

                # 1. Tam Eşleşme
                if norm_pdf in geo_lookup:
                    real_name = geo_lookup[norm_pdf]
                # 2. Boşluksuz/Tiresiz Eşleşme (CAN-2 vs CAN 2)
                elif norm_pdf_nospace in geo_lookup:
                    real_name = geo_lookup[norm_pdf_nospace]

                # 3. İsim İçerme (Kısmi Eşleşme)
                if not real_name:
                    for g_key, g_val in geo_lookup.items():
                        # Sadece yeterince uzun isimlerde ara (Hatalı eşleşmeyi önle)
                        if len(g_key) > 3 and len(norm_pdf) > 3:
                            if norm_pdf in g_key or g_key in norm_pdf:
                                real_name = g_val
                                break

                # Eşleşme varsa veya yoksa da PDF verisini kaydet
                # (Haritada olmasa bile listede görünmesi iyidir, haritada gösteremeyiz sadece)

                # Durum Belirle
                if capacity_val <= 0:
                    status = "KAPASİTE YOK"
                elif capacity_val < 10:
                    status = "KISITLI"
                else:
                    status = "UYGUN"

                # Gerilim Seviyesi
                voltage = detect_voltage(tm_name_pdf)

                entry = {
                    "name": real_name if real_name else norm_pdf,  # Harita ismi (yoksa normalize isim)
                    "teias_name": tm_name_pdf,  # Orijinal PDF ismi
                    "free_mw": capacity_val,
                    "total_mw": 100,  # Tahmini toplam
                    "status": status,
                    "voltage": voltage,
                    "matched": True if real_name else False
                }

                matched_data.append(entry)
                total_mw += capacity_val
                if real_name: match_count += 1

    # 3. KAYDET
    now_str = datetime.now().strftime("%Y-%m-%d %H:%M")

    output = {
        "updated_at": now_str,
        "source": "TEİAŞ PDF",
        "total_free": f"{total_mw:,.2f} MW",
        "substations": matched_data
    }

    os.makedirs(DATA_DIR, exist_ok=True)
    with open(OUTPUT_JSON_PATH, "w", encoding="utf-8") as f:
        json.dump(output, f, indent=4, ensure_ascii=False)

    print("-" * 40)
    print(f"✅ İŞLEM TAMAMLANDI")
    print(f"📅 Güncelleme Zamanı: {now_str}")
    print(f"📄 PDF'ten Okunan: {len(matched_data)} Merkez")
    print(f"🔗 Harita ile Eşleşen: {match_count} Merkez")
    print(f"💾 Dosya: {OUTPUT_JSON_PATH}")


if __name__ == "__main__":
    run_import()