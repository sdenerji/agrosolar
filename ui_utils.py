import json
import os
import streamlit as st


def hide_header_footer():
    """Sidebar yüksekliğini optimize eder ve arayüzü temizler."""
    st.markdown("""
        <style>
        [data-testid="stSidebarUserContent"] { padding-top: 0.5rem !important; }
        [data-testid="stSidebarCollapseButton"], [data-testid="collapsedControl"] { display: none !important; }
        header, footer { visibility: hidden; height: 0px !important; }
        [data-testid="stToolbar"] { visibility: hidden !important; }
        [data-testid="stSidebar"] { min-width: 300px !important; max-width: 300px !important; }
        </style>
    """, unsafe_allow_html=True)


def render_google_login():
    """Google giriş butonu"""
    auth_url = "#"
    try:
        if "supabase" in st.secrets:
            base_url = st.secrets["supabase"]["url"]
            auth_url = f"{base_url}/auth/v1/authorize?provider=google"
    except:
        pass

    google_html = f'''
    <div style="display: flex; flex-direction: column; align-items: center; width: 100%; margin-top: 10px;">
        <div style="display: flex; align-items: center; width: 100%; margin: 15px 0;">
            <div style="flex-grow: 1; border-top: 1px solid #dfe1e5;"></div>
            <div style="padding: 0 10px; color: #70757a; font-size: 14px;">veya</div>
            <div style="flex-grow: 1; border-top: 1px solid #dfe1e5;"></div>
        </div>
        <a href="{auth_url}" target="_self" style="display: flex; align-items: center; justify-content: center; background-color: white; color: #3c4043; border: 1px solid #dadce0; border-radius: 4px; padding: 10px 16px; font-size: 14px; font-weight: 500; text-decoration: none; width: 100%; cursor: pointer;">
            <img src="https://upload.wikimedia.org/wikipedia/commons/c/c1/Google_%22G%22_logo.svg" style="width: 18px; margin-right: 10px;">
            Continue with Google
        </a>
    </div>
    '''
    st.markdown(google_html, unsafe_allow_html=True)


def render_analysis_box(label, status, color):
    """Analiz sonuçları için standart renkli kutucuk oluşturur."""
    st.markdown(f"""
        <div style='background-color:{color}; color:white; padding:10px; 
        border-radius:5px; text-align:center; font-weight:bold; margin-bottom:10px;'>
            {label.upper()}: {status}
        </div>
    """, unsafe_allow_html=True)


def get_grid_color(mw_val):
    """Kapasiteye göre renk skalası (Eski fonksiyon uyumluluk için duruyor)"""
    if mw_val > 50:
        return "green"
    elif mw_val > 20:
        return "orange"
    return "red"


# --- GÜNCELLENMİŞ POPUP FONKSİYONU ---
def create_substation_popup(data):
    """
    TEİAŞ verilerini içeren şık HTML popup oluşturur.
    data: gis_service.get_substation_data() çıktısı olan sözlük.
    """
    # Veri sözlük olarak (dict) geliyor, parçalayıp kullanıyoruz
    html = f"""
    <div style="font-family: Arial, sans-serif; width: 260px; padding: 5px;">
        <h4 style="margin: 0 0 10px 0; color: #2c3e50; border-bottom: 2px solid {data['color']}; padding-bottom: 5px;">
            ⚡ {data['name']}
        </h4>

        <table style="width: 100%; font-size: 12px; border-collapse: collapse;">
            <tr>
                <td style="color: #7f8c8d;">Gerilim Seviyesi:</td>
                <td style="font-weight: bold; text-align: right;">{data['voltage']}</td>
            </tr>
            <tr>
                <td style="color: #7f8c8d;">Toplam Güç:</td>
                <td style="font-weight: bold; text-align: right;">{data['total_mw']} MW</td>
            </tr>
            <tr>
                <td style="color: #7f8c8d;">Kullanılan:</td>
                <td style="font-weight: bold; text-align: right;">{data['used_mw']} MW</td>
            </tr>
            <tr style="background-color: #f8f9fa; border-top: 1px solid #eee;">
                <td style="padding: 8px 0; color: {data['color']}; font-weight: bold;">BOŞ KAPASİTE:</td>
                <td style="padding: 8px 0; font-weight: bold; color: {data['color']}; text-align: right; font-size: 14px;">
                    {data['free_mw']} MW
                </td>
            </tr>
        </table>

        <div style="margin-top: 8px;">
            <div style="font-size: 10px; color: #666; margin-bottom: 2px; display:flex; justify-content:space-between;">
                <span>Doluluk:</span>
                <span>%{data['usage_rate']}</span>
            </div>
            <div style="background-color: #e0e0e0; border-radius: 4px; height: 6px; width: 100%;">
                <div style="background-color: {data['color']}; width: {data['usage_rate']}%; height: 6px; border-radius: 4px;"></div>
            </div>
        </div>

        <div style="margin-top: 8px; font-size: 9px; color: #95a5a6; text-align: right; font-style:italic;">
            Veri Kaynağı: TEİAŞ (Canlı)
        </div>
    </div>
    """
    return html


# --- DUYURU YÖNETİM SİSTEMİ ---

ANNOUNCEMENT_FILE = os.path.join(os.path.dirname(os.path.abspath(__file__)), "data", "duyurular.json")


def load_announcement():
    """Duyuru dosyasını okur."""
    if not os.path.exists(ANNOUNCEMENT_FILE):
        return {"text": "Sistem günceldir.", "type": "info", "active": True}
    try:
        with open(ANNOUNCEMENT_FILE, "r", encoding="utf-8") as f:
            return json.load(f)
    except:
        return {"text": "Duyuru yüklenemedi.", "type": "error", "active": False}


def save_announcement(text, msg_type, is_active):
    """Yeni duyuruyu kaydeder."""
    data = {"text": text, "type": msg_type, "active": is_active}
    os.makedirs(os.path.dirname(ANNOUNCEMENT_FILE), exist_ok=True)
    with open(ANNOUNCEMENT_FILE, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=4)


def render_announcement_banner():
    """Ana ekranda duyuruyu gösterir."""
    data = load_announcement()

    if not data.get("active", False):
        return  # Duyuru pasifse gösterme

    # Renk Kodları
    colors = {
        "info": {"bg": "#cff4fc", "border": "#b6effb", "text": "#055160", "icon": "ℹ️"},
        "warning": {"bg": "#fff3cd", "border": "#ffecb5", "text": "#856404", "icon": "📢"},
        "danger": {"bg": "#f8d7da", "border": "#f5c6cb", "text": "#721c24", "icon": "⚡"},
        "success": {"bg": "#d1e7dd", "border": "#badbcc", "text": "#0f5132", "icon": "✅"}
    }

    style = colors.get(data.get("type", "info"), colors["info"])

    st.markdown(f"""
    <div style="background-color: {style['bg']}; color: {style['text']}; 
        padding: 12px; border-radius: 6px; border-left: 6px solid {style['border']}; 
        margin-bottom: 20px; font-size: 0.95rem; box-shadow: 0 2px 5px rgba(0,0,0,0.05); 
        display: flex; align-items: center;">
        <span style="font-size: 1.2rem; margin-right: 10px;">{style['icon']}</span>
        <div>{data['text']}</div>
    </div>
    """, unsafe_allow_html=True)


def render_admin_announcement_editor():
    """Sidebar'da admin için düzenleme paneli."""
    st.markdown("### 📢 Duyuru Yönetimi")

    current_data = load_announcement()

    with st.form("duyuru_form"):
        new_text = st.text_area("Duyuru Metni", value=current_data.get("text", ""))
        new_type = st.selectbox("Tür", ["info", "warning", "danger", "success"],
                                index=["info", "warning", "danger", "success"].index(
                                    current_data.get("type", "warning")))
        is_active = st.checkbox("Yayında", value=current_data.get("active", True))

        if st.form_submit_button("💾 Kaydet ve Yayınla"):
            save_announcement(new_text, new_type, is_active)
            st.success("Duyuru güncellendi!")
            st.rerun()