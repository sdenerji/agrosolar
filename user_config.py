# user_config.py

ROLE_PERMISSIONS = {
    "Free": {
        "label": "Tier 1: Standart",
        "description": "Temel Harita ve Arazi Analizleri",
        # ARTIK HEPSİ AÇIK:
        "map_layers": ["Sokak (OSM)", "Uydu (Esri)", "Topoğrafik (Esri)"],
        "permissions": [
            "basic_terrain",    # Eğim, Bakı (AÇIK)
            "horizon_analysis"  # Ufuk Gölge Analizi (ARTIK AÇIK)
        ]
        # financials YOK, grid_network_view YOK, report_access YOK
    },
    "Pro": {
        "label": "Tier 2: Professional",
        "description": "Finansal Analiz ve Şebeke Verisi",
        "map_layers": ["Sokak (OSM)", "Uydu (Esri)", "Topoğrafik (Esri)"],
        "permissions": [
            "basic_terrain",
            "horizon_analysis",
            "grid_network_view", # Şebeke Gösterimi (AÇIK)
            "financials",        # ROI, Gelir Tablosu (AÇIK)
            "report_access",     # PDF Rapor (AÇIK)
            "kml_import"
        ]
    },
    "Ultra": {
        "label": "Tier 3: Enterprise",
        "description": "Tam Kapsamlı Mühendislik Motoru",
        "map_layers": ["Sokak (OSM)", "Uydu (Esri)", "Topoğrafik (Esri)"],
        "permissions": [
            "basic_terrain",
            "horizon_analysis",
            "grid_network_view",
            "financials",
            "report_access",
            "kml_import",
            "electrical_engine",  # String/Voltaj Hesabı (ULTRA'YA ÖZEL)
            "panel_placement"     # Otomatik Yerleşim (ULTRA'YA ÖZEL)
        ]
    }
}

def has_permission(role, permission_key):
    """Kullanıcının belirli bir işlem için izni var mı kontrol eder."""
    role_data = ROLE_PERMISSIONS.get(role, ROLE_PERMISSIONS["Free"])
    # permissions listesinde bu anahtar var mı?
    return permission_key in role_data.get("permissions", [])