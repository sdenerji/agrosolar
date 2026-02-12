from fpdf import FPDF
import os
import requests
from datetime import datetime
from PIL import Image, ImageDraw
import matplotlib.pyplot as plt
import matplotlib
import numpy as np

# Sunucu taraflı render için 'Agg' backend kullanımı
matplotlib.use('Agg')


def clean_text(text):
    """
    PDF uyumluluğu için Türkçe karakterleri ve AI'dan gelen
    Unicode özel karakterleri (akıllı tırnaklar vb.) temizler.
    """
    if text is None: return "-"

    # Unicode Karakter Temizliği (Hata veren süslü karakterler)
    replacements = {
        '\u2013': '-',  # en dash
        '\u2014': '-',  # em dash
        '\u2018': "'",  # left single quote
        '\u2019': "'",  # right single quote (Hatanın sebebi buydu)
        '\u201c': '"',  # left double quote
        '\u201d': '"',  # right double quote
        '\u2022': '*',  # bullet point
        '\u2026': '...',  # ellipsis
    }

    for key, val in replacements.items():
        text = text.replace(key, val)

    # Türkçe Karakter Map'leme
    map_tr = str.maketrans("ğĞüÜşŞİıöÖçÇ", "gGuUsSiioOcc")
    return str(text).translate(map_tr).encode('latin-1', 'ignore').decode('latin-1')


def generate_monthly_plot(monthly_data):
    """Aylık üretim verisinden Bar Chart oluşturur."""
    if not monthly_data: return None

    months = [d['month'] for d in monthly_data]
    production = [d['production'] for d in monthly_data]

    plt.figure(figsize=(10, 3.5))
    bars = plt.bar(months, production, color='#f39c12', edgecolor='#d35400', width=0.6)

    plt.title("Aylik Ortalama Uretim Dagilimi (kWh/kWp)", fontsize=10, fontweight='bold')
    plt.xlabel("Aylar", fontsize=8)
    plt.ylabel("Uretim (kWh)", fontsize=8)
    plt.grid(axis='y', linestyle='--', alpha=0.3)
    plt.xticks(months, fontsize=8)
    plt.yticks(fontsize=8)

    for bar in bars:
        height = bar.get_height()
        plt.text(bar.get_x() + bar.get_width() / 2., height,
                 f'{int(height)}',
                 ha='center', va='bottom', fontsize=7)

    path = "temp_monthly_plot.png"
    plt.savefig(path, bbox_inches='tight', dpi=100)
    plt.close()
    return path


class SD_Report(FPDF):
    def __init__(self):
        super().__init__()
        self.report_id = ""

    def header(self):
        self.set_fill_color(28, 90, 186)
        self.rect(0, 0, 210, 35, 'F')
        self.set_font('Arial', 'B', 18)
        self.set_text_color(255, 255, 255)
        self.cell(0, 15, clean_text("GES TEKNIK VE FINANSAL FIZIBILITE RAPORU"), ln=True, align='C')
        self.set_font('Arial', '', 9)
        self.cell(0, 5, clean_text(f"Rapor No: {self.report_id} | Tarih: {datetime.now().strftime('%d/%m/%Y')}"),
                  ln=True, align='C')
        self.ln(10)

    def footer(self):
        self.set_y(-15)
        self.set_font('Arial', 'I', 8)
        self.set_text_color(128, 128, 128)
        self.cell(0, 10, f"Sayfa {self.page_no()} | SD Enerji Analiz Platformu - Gizli ve Teknik Dokumandir", 0, 0, 'C')


def generate_full_report(d):
    pdf = SD_Report()

    # ID OLUŞTURMA
    username_tag = clean_text(d.get('username', 'MISAFIR')).upper()
    timestamp_tag = datetime.now().strftime('%Y%m%d-%H%M')
    pdf.report_id = f"{username_tag}-{timestamp_tag}"

    pdf.set_auto_page_break(auto=True, margin=15)
    pdf.add_page()

    # --- 1. YONETICI OZETI ---
    pdf.set_font('Arial', 'B', 12)
    pdf.set_text_color(28, 90, 186)
    pdf.cell(0, 10, clean_text("1. YONETICI OZETI (EXECUTIVE SUMMARY)"), ln=True)
    pdf.set_text_color(0, 0, 0)
    pdf.set_font('Arial', '', 10)

    pdf.set_font('Arial', 'B', 12)
    pdf.set_text_color(28, 90, 186)
    pdf.cell(0, 10, clean_text("1. YONETICI OZETI"), ln=True)

    # AI Özeti Varsa Şık Bir Kutuda Göster
    if d.get('ai_summary'):
        pdf.set_fill_color(248, 249, 250)  # Çok hafif gri/mavi fon
        pdf.set_font('Arial', 'I', 10)
        pdf.set_text_color(50, 50, 50)
        pdf.multi_cell(0, 6, clean_text(d['ai_summary']), border=1, fill=True)
        pdf.ln(5)

    pdf.set_fill_color(245, 245, 245)
    metrics = [
        ["Toplam Kurulu Guc", f"{d['kwp']} kWp", "Yillik Tahmini Uretim", f"{d['kwh']:,} kWh"],
        ["Yatirim Maliyeti (CAPEX)", f"{d['cost']:,} $", "Geri Donus Suresi (ROI)", f"{d['roi']} Yil"],
        ["Ic Verim Orani (IRR)", f"%{d['irr']}", "Net Bugunku Deger (NPV)", f"{d['npv']:,} $"],
        ["LCOE (Birim Maliyet)", f"{round(d['cost'] / (d['kwh'] * 20), 3)} $/kWh", "Karbon Tasarrufu",
         f"{d['co2']} Ton/Yil"]
    ]

    for row in metrics:
        pdf.set_font('Arial', 'B', 9)
        pdf.cell(45, 8, clean_text(row[0]), 1, 0, 'L', fill=True)
        pdf.set_font('Arial', '', 9)
        pdf.cell(50, 8, clean_text(row[1]), 1, 0, 'C')
        pdf.set_font('Arial', 'B', 9)
        pdf.cell(45, 8, clean_text(row[2]), 1, 0, 'L', fill=True)
        pdf.set_font('Arial', '', 9)
        pdf.cell(50, 8, clean_text(row[3]), 1, 1, 'C')

    # --- 2. TEKNIK EKIPMAN VE SAHA ANALIZI ---
    pdf.ln(10)
    pdf.set_font('Arial', 'B', 12)
    pdf.set_text_color(28, 90, 186)
    pdf.cell(0, 10, clean_text("2. TEKNIK EKIPMAN VE SAHA ANALIZI"), ln=True)
    pdf.set_text_color(0, 0, 0)

    layout_info = d.get('layout_data', {})
    pdf.set_font('Arial', '', 10)
    pdf.cell(0, 7, clean_text(f"- Panel Modeli: {d['panel_model']} (Bi-Facial Yuksek Verim)"), ln=True)
    pdf.cell(0, 7, clean_text(f"- Toplam Panel Adedi: {layout_info.get('count', 0)} Adet"), ln=True)
    pdf.cell(0, 7, clean_text(f"- Inverter Modeli: {d['inv_model']}"), ln=True)
    pdf.cell(0, 7, clean_text(f"- Saha Egimi: %{d['slope']} | Bakisi: {d['aspect']}"), ln=True)

    # --- HARİTA VE PARSEL BİLGİSİ (DÜZENLENDİ) ---
    map_path = "temp_report_map.png"
    if os.path.exists(map_path):
        pdf.ln(5)

        # 1. Parsel Görünümü Başlığı
        pdf.set_font('Arial', 'B', 10)
        pdf.set_text_color(50, 50, 50)
        pdf.cell(0, 6, clean_text("SAHA VE PARSEL GORUNUMU"), ln=True, align='C')

        # 2. Resmi Küçültüp Ortala (w=180 -> w=130)
        # A4 genişlik ~210mm. w=130 ise x = (210-130)/2 = 40
        pdf.image(map_path, x=40, w=130)
        pdf.ln(1)  # Resim ile yazı arasına az boşluk

        # 3. Tapu Bilgilerini Bas
        loc = d.get('location_data', {})
        if loc:
            pdf.set_fill_color(240, 240, 240)  # Hafif gri
            pdf.set_font('Arial', 'B', 9)
            pdf.set_text_color(0, 0, 0)

            # Veri Hazırlığı (Hata önleyici .get ile)
            il = str(loc.get('il', '-')).upper()
            ilce = str(loc.get('ilce', '-')).upper()
            mah = str(loc.get('mahalle', '-')).upper()
            ada = str(loc.get('ada', '-'))
            parsel = str(loc.get('parsel', '-'))

            # Tapu Stringi
            info_str = clean_text(f"TAPU KAYDI: {il} / {ilce} - {mah} Mh. | ADA: {ada} | PARSEL: {parsel}")

            # Tablo gibi görünen tek satır (Border=1)
            pdf.cell(0, 8, info_str, ln=True, align='C', fill=True, border=1)

        pdf.ln(5)

    # --- MÜHENDİSLİK NOTU (BURAYA EKLENEBİLİR) ---
    if d.get('engineering_note'):
        pdf.set_text_color(200, 50, 50)  # Kırmızımsı uyarı rengi
        pdf.set_font('Arial', 'I', 9)
        pdf.multi_cell(0, 5, clean_text(f"MUHENDISLIK NOTU: {d['engineering_note']}"))
        pdf.set_text_color(0, 0, 0)
        pdf.ln(5)

    if d.get('monthly_data'):
        monthly_chart = generate_monthly_plot(d['monthly_data'])
        if monthly_chart and os.path.exists(monthly_chart):
            # Grafik de sayfaya sığsın diye biraz ortalanabilir
            pdf.image(monthly_chart, x=25, w=160)

            # --- YORUM ALANI ---
            if d.get('monthly_comment'):
                pdf.ln(2)
                pdf.set_font('Arial', 'I', 9)
                pdf.multi_cell(0, 5, clean_text(f"Analiz: {d['monthly_comment']}"))
            pdf.ln(5)

    # --- 3. UFUK ANALIZI ---
    pdf.add_page()
    pdf.set_font('Arial', 'B', 12)
    pdf.set_text_color(28, 90, 186)
    pdf.cell(0, 10, clean_text("3. UFUK VE GOLGE ANALIZI (PVGIS)"), ln=True)
    pdf.set_text_color(0, 0, 0)

    horizon_path = "temp_horizon_plot.png"
    if os.path.exists(horizon_path):
        pdf.image(horizon_path, x=15, w=180)
        # --- YORUM ALANI ---
        if d.get('shading_comment'):
            pdf.ln(2)
            pdf.set_font('Arial', 'I', 9)
            pdf.multi_cell(0, 5, clean_text(f"Teknik Yorum: {d['shading_comment']}"))
        else:
            pdf.multi_cell(0, 5, clean_text("Yukaridaki grafik, sahanin topografik engellerini gostermektedir."))

    # --- 4. FINANSAL ANALIZ ---
    pdf.ln(10)
    pdf.set_font('Arial', 'B', 12)
    pdf.set_text_color(28, 90, 186)
    pdf.cell(0, 10, clean_text("4. FINANSAL PROJEKSIYON VE NAKIT AKISI"), ln=True)
    pdf.set_text_color(0, 0, 0)

    graph_path = d.get('graph_path')
    if graph_path and os.path.exists(graph_path):
        pdf.image(graph_path, x=15, w=180)
        # --- YORUM ALANI ---
        if d.get('cash_comment'):
            pdf.ln(2)
            pdf.set_font('Arial', 'I', 9)
            pdf.multi_cell(0, 5, clean_text(f"Finansal Ozet: {d['cash_comment']}"))
        pdf.ln(5)

    pdf.set_font('Arial', 'B', 8)
    pdf.set_fill_color(28, 90, 186)
    pdf.set_text_color(255, 255, 255)
    pdf.cell(15, 8, "YIL", 1, 0, 'C', fill=True)
    pdf.cell(35, 8, "URETIM", 1, 0, 'C', fill=True)
    pdf.cell(35, 8, "GELIR ($)", 1, 0, 'C', fill=True)
    pdf.cell(35, 8, "OPEX", 1, 0, 'C', fill=True)
    pdf.cell(35, 8, "NET NAKIT", 1, 0, 'C', fill=True)
    pdf.cell(35, 8, "KUMULATIF", 1, 1, 'C', fill=True)

    pdf.set_font('Arial', '', 8)
    pdf.set_text_color(0, 0, 0)
    for row in d['cash_flow'][:25]:
        pdf.cell(15, 6, str(row['yil']), 1, 0, 'C')
        pdf.cell(35, 6, f"{row['uretim']:,}", 1, 0, 'R')
        pdf.cell(35, 6, f"{row['gelir']:,}", 1, 0, 'R')
        pdf.cell(35, 6, f"{row['gider']:,}", 1, 0, 'R')
        pdf.cell(35, 6, f"{row['net']:,}", 1, 0, 'R')
        pdf.cell(35, 6, f"{row['kumulatif']:,}", 1, 1, 'R')

    pdf.ln(10)
    pdf.set_fill_color(232, 245, 233)
    pdf.set_font('Arial', 'B', 11)
    pdf.cell(0, 12, clean_text(f"ESG ETKISI: Bu tesis yillik {d['trees']} agacin karbon emilimine denk katki saglar."),
             0, 1, 'C', fill=True)

    return pdf.output(dest='S').encode('latin-1', errors='replace')