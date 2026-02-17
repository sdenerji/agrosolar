# user_config.py - YENİ TIER VE MÜHENDİSLİK YETKİ SİSTEMİ

ROLE_PERMISSIONS = {
    "Free": {
        "label": "Standart",
        "panel_placement": False,    # Tasarım kapalı
        "financials": False,         # Finansal analiz kapalı
        "3d_srtm": False,            # 3D Kapalı
        "dxf_export": False,
        "ai_report": False,
        "tm_proximity": False,
        "coord_transform": False,
        "3d_precision_data": False   # Milimetrik hesap kapalı
    },
    "Pro": {
        "label": "Professional",
        "panel_placement": True,     # Tasarım ve yerleşim açık
        "financials": True,
        "3d_srtm": True,             # ✅ SRTM verisiyle standart kazı-dolgu açık
        "dxf_export": False,
        "ai_report": False,
        "tm_proximity": False,
        "coord_transform": False,
        "3d_precision_data": False   # Pro'da milimetrik hesap kapalı (Sadece SRTM)
    },
    "Ultra": {
        "label": "Ultra (Kurumsal)",
        "panel_placement": True,
        "financials": True,
        "3d_srtm": True,
        "dxf_export": True,          # ✅ DXF İndirme açık
        "ai_report": True,           # ✅ Yapay Zeka özeti açık
        "tm_proximity": True,        # ✅ TM (Trafo) Mesafe hesabı açık
        "coord_transform": True,     # ✅ ITRF/ED50 Koordinat Dönüşümü açık
        "3d_precision_data": True,   # ✅ NCN, CSV, TXT ile milimetrik hesap açık
        "3d_point_cloud": True       # Nokta bulutu işleme açık
    }
}

def has_permission(role, permission_key):
    """
    Kullanıcının belirli bir işleme yetkisi olup olmadığını kontrol eder.
    Hata almamak için bu fonksiyonun dosya içinde olması şarttır!
    """
    if role not in ROLE_PERMISSIONS:
        return False
    return ROLE_PERMISSIONS[role].get(permission_key, False)