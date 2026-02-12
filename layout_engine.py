from shapely.geometry import Polygon, Point
import numpy as np


class SolarLayoutEngine:
    def __init__(self, geometry_geojson):
        """
        geometry_geojson: GeoJSON formatındaki Polygon geometrisi
        """
        coords = geometry_geojson.get("coordinates", [])

        if geometry_geojson["type"] == "Polygon":
            self.polygon = Polygon(coords[0])
        elif geometry_geojson["type"] == "MultiPolygon":
            polys = [Polygon(p[0]) for p in coords]
            self.polygon = max(polys, key=lambda a: a.area)
        else:
            self.polygon = None

    def generate_layout(self, panel_width, panel_height, setback, row_spacing, col_spacing, table_rows, table_cols):
        """
        Sadeleştirilmiş Yerleşim Motoru + Verimlilik Analizi
        """
        if not self.polygon or not self.polygon.is_valid:
            return {"panels": [], "capacity_kw": 0, "count": 0, "area_m2": 0, "skipped_rows": 0}

        # 1. ÇEKME PAYI (Setback)
        buffer_deg = -setback * 0.000009
        safe_zone = self.polygon.buffer(buffer_deg)

        if safe_zone.is_empty:
            return {"panels": [], "capacity_kw": 0, "count": 0, "area_m2": 0, "skipped_rows": 0}

        # 2. SINIR KUTUSU
        minx, miny, maxx, maxy = safe_zone.bounds

        # 3. MASA BOYUTLARI
        table_width = (panel_width * table_cols) + (col_spacing * (table_cols - 1 if table_cols > 1 else 0))
        table_depth = (panel_height * table_rows) + (0.02 * (table_rows - 1))

        # 4. IZGARA OLUŞTURMA (GRID)
        panels = []
        panel_count = 0

        y_step = (table_depth + row_spacing) * 0.000009
        x_step = (table_width + col_spacing) * 0.000011

        # --- YENİ EKLENEN: SATIR ANALİZİ ---
        total_rows_scanned = 0
        filled_rows = 0

        current_y = miny
        while current_y + (table_depth * 0.000009) < maxy:
            total_rows_scanned += 1
            row_has_panel = False  # Bu satıra hiç panel koyduk mu?

            current_x = minx
            while current_x + (table_width * 0.000011) < maxx:
                p1 = (current_x, current_y)
                p2 = (current_x + x_step - (col_spacing * 0.000011), current_y)
                p3 = (current_x + x_step - (col_spacing * 0.000011), current_y + (table_depth * 0.000009))
                p4 = (current_x, current_y + (table_depth * 0.000009))

                table_poly = Polygon([p1, p2, p3, p4])

                if safe_zone.contains(table_poly):
                    panels.append(list(table_poly.exterior.coords))
                    panel_count += (table_rows * table_cols)
                    row_has_panel = True  # Evet, bu satıra panel koyduk

                current_x += x_step

            if row_has_panel:
                filled_rows += 1

            current_y += y_step

        capacity = round(panel_count * 0.550, 2)
        skipped_rows = total_rows_scanned - filled_rows

        return {
            "panels": panels,
            "capacity_kw": capacity,
            "count": panel_count,
            "area_m2": self.polygon.area * 100000000,
            "kiosk": [],
            "skipped_rows": skipped_rows  # Yeni Veri
        }