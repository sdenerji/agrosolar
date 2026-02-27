import streamlit as st
import os
import json
import time


def hide_header_footer():
    """Sidebar yüksekliğini optimize eder ve arayüzü temizler."""
    st.markdown("""
        <style>
        /* Sidebar açma-kapama butonunu görünür yap */
        [data-testid="collapsedControl"] {
            display: block !important;
            top: 0.5rem;
            left: 0.5rem;
            color: #1c5aba; /* Ok rengini SD Enerji mavisi yapalım */
        }
        </style>
    """, unsafe_allow_html=True)


def render_google_login():
    """Google giriş butonu - Orijinal görsel tasarım geri getirildi"""
    # 🎯 Kritik: Sizin orijinal Supabase adresiniz direkt gömüldü
    auth_url = "https://crbpizylnliouefxkwxy.supabase.co/auth/v1/authorize?provider=google&redirect_to=https://analiz.sdenerji.com"

    google_html = f'''
    <div style="display: flex; flex-direction: column; align-items: center; width: 100%; margin-top: 10px;">
        <div style="display: flex; align-items: center; width: 100%; margin: 15px 0;">
            <div style="flex-grow: 1; border-top: 1px solid #dfe1e5;"></div>
            <div style="padding: 0 10px; color: #70757a; font-size: 14px;">veya</div>
            <div style="flex-grow: 1; border-top: 1px solid #dfe1e5;"></div>
        </div>
        <a href="{auth_url}" target="_self" style="display: flex; align-items: center; justify-content: center; background-color: white; color: #3c4043; border: 1px solid #dadce0; border-radius: 4px; padding: 10px 16px; font-size: 14px; font-weight: 500; text-decoration: none; width: 100%; cursor: pointer; box-shadow: 0 1px 2px rgba(0,0,0,0.1);">
            <img src="https://upload.wikimedia.org/wikipedia/commons/c/c1/Google_%22G%22_logo.svg" style="width: 18px; margin-right: 10px;">
            Google ile Devam Et
        </a>
    </div>
    '''
    st.markdown(google_html, unsafe_allow_html=True)


def render_analysis_box(label, status, color):
    st.markdown(
        f"<div style='background-color:{color}; color:white; padding:10px; border-radius:5px; text-align:center; font-weight:bold; margin-bottom:10px;'>{label.upper()}: {status}</div>",
        unsafe_allow_html=True)


def get_grid_color(mw_val):
    if mw_val > 50:
        return "green"
    elif mw_val > 20:
        return "orange"
    return "red"


# --- GÜNCELLENMİŞ POPUP (SADELEŞTİRİLDİ) ---
def create_substation_popup(data, coords):
    """
    Sadece TEİAŞ'ın verdiği resmi 'Boş Kapasite' verisini gösterir.
    Varsayılan (Tahmini) toplam güç verilerini gizler.
    """
    lat, lon = coords[0], coords[1]
    nav_link = f"https://www.google.com/maps/dir/?api=1&destination={lat},{lon}"
    html = f"""
    <div style="font-family: Arial, sans-serif; width: 240px; padding: 5px;">
        <h4 style="margin: 0 0 10px 0; color: #2c3e50; border-bottom: 2px solid {data['color']}; padding-bottom: 5px;">
            ⚡ {data['name']}
        </h4>

        <table style="width: 100%; font-size: 13px; border-collapse: collapse;">
            <tr style="border-bottom: 1px solid #eee;">
                <td style="padding: 5px 0; color: #7f8c8d;">Gerilim:</td>
                <td style="padding: 5px 0; font-weight: bold; text-align: right;">{data['voltage']}</td>
            </tr>
            <tr style="background-color: #f8f9fa;">
                <td style="padding: 10px 0; color: {data['color']}; font-weight: bold;">BOŞ KAPASİTE:</td>
                <td style="padding: 10px 0; font-weight: bold; color: {data['color']}; text-align: right; font-size: 16px;">
                    {data['free_mw']} MW
                </td>
            </tr>
        </table>                
        <div style="margin-top: 10px; font-size: 10px; color: #95a5a6; text-align: center; font-style:italic;">
            Veri Kaynağı: TEİAŞ (Resmi Duyuru)
        </div>

        <hr style="margin: 10px 0 5px 0; border: 0; border-top: 1px solid #eee;">
        <a href="{nav_link}" target="_blank" style="display: block; text-align: center; background-color: #1a73e8; color: white; padding: 8px; border-radius: 4px; text-decoration: none; font-weight: bold; font-size: 13px;">
            🚗 Yol Tarifi Al
        </a>
    </div>
    """

    nav_button_html = f"""
            <hr style="margin: 10px 0; border: 0; border-top: 1px solid #eee;">
            <a href="{nav_link}" target="_blank" style="
                display: block; 
                text-align: center; 
                background-color: #4285F4; 
                color: white; 
                text-decoration: none; 
                padding: 8px; 
                border-radius: 4px; 
                font-weight: bold; 
                font-family: sans-serif;
                font-size: 12px;
                box-shadow: 0 2px 4px rgba(0,0,0,0.1);">
                📍 Yol Tarifi Al (Navigasyon)
            </a>
        """
    return html


# --- DUYURU SİSTEMİ ---
ANNOUNCEMENT_FILE = os.path.join(os.path.dirname(os.path.abspath(__file__)), "data", "duyurular.json")


def load_announcement():
    if not os.path.exists(ANNOUNCEMENT_FILE):
        return {"text": "", "type": "info", "active": False}
    try:
        with open(ANNOUNCEMENT_FILE, "r", encoding="utf-8") as f:
            return json.load(f)
    except:
        return {"text": "", "type": "info", "active": False}


def save_announcement(text, msg_type, is_active):
    data = {"text": text, "type": msg_type, "active": is_active}
    os.makedirs(os.path.dirname(ANNOUNCEMENT_FILE), exist_ok=True)
    with open(ANNOUNCEMENT_FILE, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=4)


def render_announcement_banner():
    data = load_announcement()
    if not data.get("active", False): return

    styles = {
        "info": {"bg": "#e7f5ff", "border": "#74c0fc", "color": "#1864ab", "icon": "ℹ️"},
        "warning": {"bg": "#fff9db", "border": "#ffec99", "color": "#e67700", "icon": "📢"},
        "danger": {"bg": "#ffe3e3", "border": "#ffa8a8", "color": "#c92a2a", "icon": "🚨"},
        "success": {"bg": "#ebfbee", "border": "#8ce99a", "color": "#2b8a3e", "icon": "✅"}
    }
    s = styles.get(data.get("type", "info"), styles["info"])

    st.markdown(f"""
    <div style="background-color: {s['bg']}; color: {s['color']}; 
        padding: 12px; border-radius: 6px; border-left: 5px solid {s['border']}; 
        margin-bottom: 20px; font-size: 0.95rem; box-shadow: 0 2px 4px rgba(0,0,0,0.05); 
        display: flex; align-items: center;">
        <span style="font-size: 1.2rem; margin-right: 10px;">{s['icon']}</span>
        <div style="font-weight: 500;">{data['text']}</div>
    </div>
    """, unsafe_allow_html=True)


def render_admin_announcement_editor():
    st.info("📢 Duyuru Yönetimi")
    current = load_announcement()
    with st.form("admin_duyuru_form"):
        new_text = st.text_area("Duyuru Metni (HTML Destekli)", value=current.get("text", ""))
        c1, c2 = st.columns(2)
        new_type = c1.selectbox("Renk/Tür", ["info", "warning", "danger", "success"],
                                index=["info", "warning", "danger", "success"].index(current.get("type", "info")))
        is_active = c2.checkbox("Yayında", value=current.get("active", False))
        if st.form_submit_button("💾 Kaydet ve Yayınla"):
            save_announcement(new_text, new_type, is_active)
            st.toast("Duyuru güncellendi!", icon="✅")
            time.sleep(1)
            st.rerun()