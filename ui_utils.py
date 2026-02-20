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
    """Google giriş butonu - Supabase Python SDK ile yenilendi"""

    # Supabase objesini db_base'den çekiyoruz
    try:
        from db_base import get_supabase
        supabase = get_supabase()
    except Exception as e:
        st.error(f"Veritabanı bağlantı hatası: {e}")
        return

    st.markdown("""
        <div style="display: flex; align-items: center; width: 100%; margin: 15px 0;">
            <div style="flex-grow: 1; border-top: 1px solid #dfe1e5;"></div>
            <div style="padding: 0 10px; color: #70757a; font-size: 14px;">veya</div>
            <div style="flex-grow: 1; border-top: 1px solid #dfe1e5;"></div>
        </div>
    """, unsafe_allow_html=True)

    # Streamlit'in kendi butonunu kullanıyoruz (Güvenli State Yönetimi için şart)
    if st.button("🔵 Google ile Güvenli Giriş Yap", use_container_width=True):
        try:
            # Doğrudan SDK üzerinden tetikleme yapılıyor
            res = supabase.auth.sign_in_with_oauth({
                "provider": "google",
                "options": {
                    "redirect_to": "https://analiz.sdenerji.com"  # Canlı URL
                }
            })

            # SDK bize yönlendirme linkini veriyor, biz de Streamlit'e "Oraya Git" diyoruz
            if res.url:
                # JavaScript ile güvenli yönlendirme (URL'yi yeni sekmede açmaz, mevcut sekmeyi yönlendirir)
                st.markdown(f'<meta http-equiv="refresh" content="0;url={res.url}">', unsafe_allow_html=True)

        except Exception as e:
            st.error(f"Google bağlantı hatası: {e}")


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
def create_substation_popup(data):
    """
    Sadece TEİAŞ'ın verdiği resmi 'Boş Kapasite' verisini gösterir.
    Varsayılan (Tahmini) toplam güç verilerini gizler.
    """
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
    </div>
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