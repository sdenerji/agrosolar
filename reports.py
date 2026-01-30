from fpdf import FPDF
import requests
from PIL import Image, ImageDraw
import io
import os
from datetime import datetime

def tr_to_en(text):
    """Türkçe karakterleri ASCII muadillerine çevirir."""
    mapping = str.maketrans("ğĞüÜşŞİıöÖçÇ", "gGuUsSiioOcc")
    return str(text).translate(mapping)

# 1. Fonksiyon tanımına 'projection_data' ve 'earnings_graph' eklediğinizden emin olun
def generate_full_report(lat, lon, rakim, egim, baki, kw_power, kwh, gelir, maliyet, roi, unit_cost,
                         username, user_role, map_type, earnings_graph, horizon_graph_path,
                         projection_data, shading_metrics):
    """Harita görselini hazırlar ve tüm verileri PDF oluşturucuya aktarır."""
    map_path = "temp_map.png"
    offset = 0.004
    bbox = f"{lon - offset},{lat - offset},{lon + offset},{lat + offset}"

    # Harita Tipi Seçimi
    base_url = "https://server.arcgisonline.com/ArcGIS/rest/services/World_Imagery/MapServer/export" if "Uydu" in map_type else "https://server.arcgisonline.com/ArcGIS/rest/services/World_Street_Map/MapServer/export"

    try:
        # SSL hatasını aşmak için verify=False eklenmiştir
        r = requests.get(f"{base_url}?bbox={bbox}&bboxSR=4326&size=800,600&f=image", timeout=15, verify=False)
        if r.status_code == 200:
            img = Image.open(io.BytesIO(r.content)).convert("RGB")
            draw = ImageDraw.Draw(img)
            cx, cy = img.size[0] / 2, img.size[1] / 2
            draw.ellipse((cx - 15, cy - 35, cx + 15, cy - 5), fill="#E74C3C", outline="white", width=3)
            draw.polygon([(cx - 8, cy - 10), (cx + 8, cy - 10), (cx, cy + 10)], fill="#E74C3C")
            img.save(map_path)
        else:
            map_path = None
    except:
        map_path = None

    return create_pdf(
        lat, lon, rakim, egim, baki, kw_power, kwh, gelir, maliyet, roi, unit_cost,
        username, user_role, map_path,
        earnings_graph,
        horizon_graph_path,  # 16. parametre olarak eklendi
        projection_data, shading_metrics  # 17. parametre olarak eklendi
    )


def create_pdf(lat, lon, rakim, egim, baki, kw_power, kwh, gelir, maliyet, roi, unit_cost,
               username, user_role, map_path, earnings_graph, horizon_earnings_graph,
               projection_data, shading_metrics):
    pdf = FPDF()
    pdf.set_auto_page_break(auto=False)

    # --- SAYFA 1: ANALİZ ÖZETİ ---
    pdf.add_page()
    pdf.set_font("Arial", 'B', 18)
    pdf.set_text_color(231, 76, 60)
    pdf.cell(0, 15, "SD ENERJI - AGROSOLAR ANALIZ RAPORU", ln=True, align='C')

    # Harita (Sadece 1 adet ve sabit konum)
    if map_path and os.path.exists(map_path):
        pdf.image(map_path, x=15, y=35, w=180, h=85)

    # Teknik Tablo (Haritanın hemen altına sabitlendi - Bölünmez)
    pdf.set_y(125)
    pdf.set_font("Arial", 'B', 12)
    pdf.set_text_color(0, 0, 0)
    pdf.cell(180, 10, " TEKNIK VE FINANSAL ANALIZ SONUCLARI", border=1, ln=1, align='C')

    pdf.set_font("Arial", '', 10)
    rows = [
        ["Konum", f"{lat:.5f}/{lon:.5f}", "Kurulu Guc", f"{kw_power} kWp"],
        ["Rakim", f"{rakim} m", "Uretim (1. Yil)", f"{int(kwh):,} kWh".replace(",", ".")],
        ["Egim", f"%{egim}", "Amortisman", f"{roi} Yil"],
        ["Baki", f"{baki}", "Birim Maliyet", f"{unit_cost:.3f} $/kWh"],
        ["Maks. Engel", shading_metrics[0], "Golge Kayip Kat.", f"{shading_metrics[1]}"]  # Yeni Satır
    ]
    for r in rows:
        pdf.cell(45, 10, r[0], border=1);
        pdf.cell(45, 10, r[1], border=1)
        pdf.cell(45, 10, r[2], border=1);
        pdf.cell(45, 10, r[3], border=1, ln=1)

    # --- SAYFA 2: MÜHENDİSLİK GRAFİKLERİ ---
    pdf.add_page()
    # 1. Ufuk Gölge Grafiği (Yeni eklendi)
    if horizon_earnings_graph and os.path.exists(horizon_earnings_graph):
        pdf.set_font("Arial", 'B', 14)
        pdf.cell(0, 10, "UFUK VE GOLGE ANALIZI", ln=True, align='C')
        pdf.image(horizon_earnings_graph, x=15, y=25, w=180)

    # 2. Yatırım Getiri Grafiği
    if earnings_graph and os.path.exists(earnings_graph):
        pdf.set_y(120)
        pdf.set_font("Arial", 'B', 14)
        pdf.cell(0, 10, "25 YILLIK FINANSAL PROJEKSIYON", ln=True, align='C')
        pdf.image(earnings_graph, x=15, y=135, w=180)

    # --- SAYFA 3: DETAYLI TABLO ---
    if projection_data:
        pdf.add_page()
        pdf.set_font("Arial", 'B', 14)
        pdf.set_text_color(255,255,255)
        pdf.cell(0, 10, "YILLARA GORE KAZANC TABLOSU", ln=True, align='C')
        pdf.ln(5)
        headers = ["YIL", "URETIM (kWh)", "YILLIK GELIR ($)", "KUMULATIF KAR ($)"]
        w = [25, 50, 50, 55]
        for i, h in enumerate(headers):
            pdf.cell(w[i], 10, h, border=1, align='C', fill=True)
        pdf.ln()

        pdf.set_text_color(0, 0, 0)
        pdf.set_font("Arial", '', 10)
        for r in projection_data:
            pdf.cell(w[0], 9, f"{r['yil']}. Yil", border=1, align='C')
            pdf.cell(w[1], 9, f"{r['uretim']:,}".replace(",", "."), border=1, align='C')
            pdf.cell(w[2], 9, f"$ {r['gelir']:,}".replace(",", "."), border=1, align='C')
            pdf.cell(w[3], 9, f"$ {r['net']:,}".replace(",", "."), border=1, align='C')
            pdf.ln()

    return pdf.output(dest='S').encode('latin-1')