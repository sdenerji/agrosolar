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
    """Google giriş butonu (Mevcut özellik korunuyor)"""
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


# --- ŞEBEKE ANALİZİNE ÖZEL YENİ GÖRSEL FONKSİYONLAR ---

def get_grid_color(available_mw):
    """Kapasiteye göre mühendislik renk skalası belirler."""
    if available_mw > 5:
        return '#28a745'  # Yeşil
    elif available_mw > 0:
        return '#fd7e14'  # Turuncu
    return '#dc3545'  # Kırmızı


def create_substation_popup(name, available_mw, total_mw):
    """Trafo merkezi (TM) için profesyonel HTML popup şablonu."""
    color = get_grid_color(available_mw)
    load_ratio = (1 - (available_mw / total_mw)) * 100 if total_mw > 0 else 0

    return f"""
    <div style='width:220px; font-family:sans-serif; line-height:1.5; color:#31333F;'>
        <h4 style='margin:0 0 10px 0; padding-bottom:5px; border-bottom:2px solid {color};'>{name}</h4>
        <table style='width:100%; font-size:13px;'>
            <tr><td><b>Boş Kapasite:</b></td><td style='color:{color}; font-weight:bold;'>{available_mw} MW</td></tr>
            <tr><td><b>Toplam Güç:</b></td><td>{total_mw} MW</td></tr>
            <tr><td><b>Yüklenme:</b></td><td>%{load_ratio:.1f}</td></tr>
        </table>
        <div style='margin-top:10px; font-size:10px; color:gray; text-align:right;'>SD ENERJİ Altyapı Analizi</div>
    </div>
    """


def create_line_popup(name, kv_level="Bilinmiyor"):
    """Enerji Nakil Hatları (ENH) için popup şablonu."""
    return f"""
    <div style='width:180px; font-family:sans-serif;'>
        <h5 style='margin:0; color:#007bff;'>ENH: {name}</h5>
        <div style='font-size:12px; margin-top:5px;'>
            <b>Gerilim Seviyesi:</b> {kv_level}
        </div>
    </div>
    """