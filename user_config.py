# SD ENERJİ - AGROSOLAR PLATFORM YETKİ YAPILANDIRMASI

ROLE_PERMISSIONS = {
    "Free": {
        "label": "Tier 1: Standart",
        "map_layers": ["Sokak (OSM)"],
        "max_analysis_per_day": 10,
        "features": ["basic_analysis"],  # Sadece Eğim ve Bakı
        "report_access": False,
        "financials": False
    },
    "Pro": {
        "label": "Tier 2: Professional",
        "map_layers": ["Sokak (OSM)", "Uydu (Esri)"],
        "max_analysis_per_day": 50,
        "features": [
            "basic_analysis",
            "horizon_shading",  # Ufuk Analizi
            "pdf_reporting",   # Rapor Oluşturma
            "history_access"   # Analiz Geçmişi
        ],
        "report_access": True,
        "financials": True
    },
    "Ultra": {
        "label": "Tier 3: Enterprise",
        "map_layers": ["Sokak (OSM)", "Uydu (Esri)", "Topoğrafik (Esri)"],
        "max_analysis_per_day": 9999,  # Sınırsız
        "features": [
            "basic_analysis",
            "horizon_shading",
            "pdf_reporting",
            "history_access",
            "25y_financial_projection", # Gelişmiş Finansal Analiz
            "kmz_export",               # Harita Mühendisleri İçin KMZ Çıktısı
            "grid_network_view",        # TEİAŞ Şebeke Görünümü (Toggle ile çalışacak)
            "capacity_check",           # TEİAŞ Kapasite Sorgulama
            "priority_support"
        ],
        "report_access": True,
        "financials": True
    }
}


def has_permission(role, feature):
    """
    Kullanıcının belirli bir özelliğe yetkisi olup olmadığını kontrol eder.
    """
    if role not in ROLE_PERMISSIONS:
        return False

    permissions = ROLE_PERMISSIONS[role]

    # Doğrudan özellik listesinde mi kontrol et
    if "features" in permissions and feature in permissions["features"]:
        return True

    # Özel flag'leri kontrol et (financials, report_access vb.)
    return permissions.get(feature, False)