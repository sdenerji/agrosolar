import folium
from folium.plugins import MarkerCluster, LocateControl
from gis_service import parse_grid_data, get_substation_data
from ui_utils import create_substation_popup
from equipment_db import PANEL_LIBRARY
import streamlit as st


def create_base_map(lat, lon, tile_config, auto_locate=False):
    """
    Temel harita objesini oluşturur.
    auto_locate: True ise açılışta GPS konumuna uçar.
    """
    m = folium.Map(location=[lat, lon], zoom_start=18, tiles=tile_config["tiles"], attr=tile_config["attr"])

    # KONUM BUTONU AYARI
    # auto_start=True -> Sayfa yüklenince otomatik gider
    # auto_start=False -> Sadece kullanıcı butona basarsa gider
    LocateControl(
        auto_start=auto_locate,
        position='topleft',
        strings={"title": "Konumuma Git", "popup": "Konumunuz"}
    ).add_to(m)

    # Merkez Markeri
    folium.Marker(
        [lat, lon],
        tooltip="Seçili Konum",
        popup=f"{lat:.5f}, {lon:.5f}",
        icon=folium.Icon(color="red", icon="map-pin", prefix="fa")
    ).add_to(m)

    return m


def add_teias_layer(m):
    """TEİAŞ Şebeke verilerini haritaya ekler."""
    import os
    base_dir = os.path.dirname(os.path.abspath(__file__))
    geojson_path = os.path.join(base_dir, "data", "sebeke_verisi.geojson")

    if os.path.exists(geojson_path):
        grid_data = parse_grid_data(geojson_path)
        if grid_data:
            marker_cluster = MarkerCluster(name="Trafo Merkezleri").add_to(m)
            for item in grid_data:
                if item['type'] == 'Point':
                    teias_live_data = get_substation_data(item['name'])
                    popup_html = create_substation_popup(teias_live_data)
                    folium.CircleMarker(
                        location=item['coords'], radius=8,
                        color=teias_live_data['color'], fill=True, fill_opacity=1,
                        popup=folium.Popup(popup_html, max_width=260),
                        tooltip=f"{item['name']}"
                    ).add_to(marker_cluster)
                elif item['type'] == 'Line':
                    folium.PolyLine(
                        item['path'], color="blue", weight=2, opacity=0.4,
                        tooltip=f"ENH: {item['name']}"
                    ).add_to(m)
            return True
    return False


def add_parsel_layer(m, parsel_geojson, analysis_results, layout_data):
    """Parsel sınırlarını ve bilgi kutucuğunu (Tooltip) ekler."""
    if not parsel_geojson:
        return

    geojson_display = dict(parsel_geojson)

    disp_area = analysis_results.get("area", 0)
    disp_prod = analysis_results.get("production", 0)

    cap_kw = 0;
    p_count = 0
    if layout_data:
        cap_kw = layout_data.get('capacity_kw', 0)
        p_count = layout_data.get('count', 0)

    if "features" in geojson_display and len(geojson_display["features"]) > 0:
        geojson_display["features"][0]["properties"] = {
            "alan": f"{disp_area:,.0f} m²",
            "guc": f"{cap_kw} kWp",
            "panel": f"{p_count} Adet",
            "uretim": f"{disp_prod:,.0f} kWh/Yıl"
        }

    parsel_tooltip = folium.GeoJsonTooltip(
        fields=["alan", "guc", "panel", "uretim"],
        aliases=["Parsel Alanı:", "Kurulu Güç:", "Panel Sayısı:", "Tahmini Üretim:"],
        style="background-color: white; border: 2px solid orange; font-weight: bold;"
    )

    folium.GeoJson(
        geojson_display,
        style_function=lambda x: {'fillColor': '#ffaf00', 'color': '#ff4500', 'weight': 3, 'fillOpacity': 0.1},
        tooltip=parsel_tooltip
    ).add_to(m)


def add_panel_layer(m, layout_data, selected_brand, selected_model):
    """Panel yerleşimini haritaya çizer."""
    if not layout_data:
        return False

    if "kiosk" in layout_data and layout_data["kiosk"]:
        folium.Polygon(
            locations=layout_data["kiosk"], color="#444444", fill=True,
            fill_color="#777777", fill_opacity=0.9, popup="Trafo Köşkü"
        ).add_to(m)

    current_panel_data = PANEL_LIBRARY[selected_brand][selected_model]

    geojson_features = []
    if "panels" in layout_data and layout_data["panels"]:
        for p_coords in layout_data["panels"]:
            poly_coords = [list(c) for c in p_coords]
            geojson_features.append({
                "type": "Feature",
                "geometry": {"type": "Polygon", "coordinates": [poly_coords]},
                "properties": {
                    "marka": f"{selected_brand}",
                    "model": f"{selected_model}",
                    "guc": f"{current_panel_data['p_max']} Wp"
                }
            })

    if geojson_features:
        panel_tooltip = folium.GeoJsonTooltip(
            fields=["marka", "model", "guc"],
            aliases=["Marka:", "Model:", "Güç:"],
            style="background-color: white; border: 1px solid #1c5a7a; font-size: 11px;"
        )
        folium.GeoJson(
            {"type": "FeatureCollection", "features": geojson_features},
            style_function=lambda x: {'fillColor': '#2b8cbe', 'color': '#1c5a7a', 'weight': 1, 'fillOpacity': 0.7},
            tooltip=panel_tooltip
        ).add_to(m)
        return True

    return False