import math
from shapely.geometry import Polygon, box
from shapely import affinity


class SolarLayoutEngine:
    """
    Parsel içine güneş panellerini 'Masa/Sehpa' mantığıyla yerleştiren motor.
    GÜNCELLEME: Trafo köşkü artık bounding box köşesine değil, parselin içine sığan ilk noktaya konur.
    """

    def __init__(self, geojson_geometry):
        self.polygon_latlon = self._parse_geojson(geojson_geometry)

        # Parselin merkezini referans (0,0) noktası kabul et
        self.ref_lat = self.polygon_latlon.centroid.y
        self.ref_lon = self.polygon_latlon.centroid.x

        # Metrik sisteme çevir (Hesaplamalar metre cinsinden yapılır)
        self.polygon_meters = self._latlon_to_meters(self.polygon_latlon)

    def _parse_geojson(self, geometry):
        coords = geometry.get('coordinates', [])
        if geometry.get('type') == 'Polygon':
            return Polygon(coords[0])
        elif geometry.get('type') == 'MultiPolygon':
            return Polygon(coords[0][0])
        return Polygon(coords[0])

    def _latlon_to_meters(self, poly):
        new_coords = []
        for lon, lat in poly.exterior.coords:
            y = (lat - self.ref_lat) * 111132.0
            x = (lon - self.ref_lon) * 111132.0 * math.cos(math.radians(self.ref_lat))
            new_coords.append((x, y))
        return Polygon(new_coords)

    def _get_latlon_from_xy(self, x, y):
        lat = self.ref_lat + (y / 111132.0)
        lon = self.ref_lon + (x / (111132.0 * math.cos(math.radians(self.ref_lat))))
        return lat, lon

    def generate_layout(self,
                        panel_width=1.134,
                        panel_height=2.279,
                        table_rows=2,
                        table_cols=20,
                        azimuth=180,
                        row_spacing=3.5,
                        col_spacing=0.5,
                        setback=5.0,
                        kiosk_w=6.0,
                        kiosk_h=3.0):

        # 1. Çekme Payı Uygula (Parsel Daraltma)
        buildable_area = self.polygon_meters.buffer(-setback, join_style=2)

        if buildable_area.is_empty:
            return {"panels": [], "count": 0, "capacity_kw": 0, "error": "Çekme payı sonrası alan kalmadı!"}

        # 2. Poligonu Azimut'a göre düzle
        rotation_angle = 180 - azimuth
        rotated_area = affinity.rotate(buildable_area, rotation_angle, origin='centroid')
        min_x, min_y, max_x, max_y = rotated_area.bounds

        # 3. TRAFO KÖŞKÜ YERLEŞİMİ (AKILLI MOD)
        # Bounding Box'ın köşesi yerine, alanın içinde kalan İLK geçerli noktayı arıyoruz.
        kiosk_box = None
        found_kiosk = False

        # Tarama adımları (Hız için 2'şer metre atlayarak bakıyoruz)
        scan_step = 2.0

        # En Güney-Batı (Sol-Alt) noktadan başlayarak parselin içine girmeye çalış
        curr_k_y = min_y
        while curr_k_y < max_y:
            curr_k_x = min_x
            while curr_k_x < max_x:
                # Aday trafo alanı
                candidate_box = box(curr_k_x, curr_k_y, curr_k_x + kiosk_w, curr_k_y + kiosk_h)

                # Bu kutu tamamen inşaat alanı (rotated_area) içinde mi?
                if rotated_area.contains(candidate_box):
                    kiosk_box = candidate_box
                    found_kiosk = True
                    break  # Bulduk! Döngüden çık.

                curr_k_x += scan_step
            if found_kiosk:
                break
            curr_k_y += scan_step

        # Trafo bulunduysa alanı güncelle, bulunamadıysa uyarı ver ama devam et
        kiosk_coords = []
        if found_kiosk:
            # Paneller trafoya çok yapışmasın diye trafoyu 1 metre büyükmüş gibi çıkaralım (Güvenlik zonu)
            safe_kiosk_zone = kiosk_box.buffer(1.0)
            final_buildable_area = rotated_area.difference(safe_kiosk_zone)

            # Harita görseli için koordinatları hazırla
            kiosk_rotated = affinity.rotate(kiosk_box, -rotation_angle, origin=self.polygon_meters.centroid)
            kiosk_coords = [[self._get_latlon_from_xy(x, y)[0], self._get_latlon_from_xy(x, y)[1]]
                            for x, y in kiosk_rotated.exterior.coords]
        else:
            # Trafo sığmadı (Çok nadir olur)
            final_buildable_area = rotated_area

        # 4. Sehpa Boyutlarını Hesapla
        table_width_m = (panel_width * table_cols) + (0.02 * (table_cols - 1))
        table_height_m = (panel_height * table_rows) + (0.02 * (table_rows - 1))

        panels_latlon = []
        total_panels = 0

        # 5. Panel Grid Tarama
        current_y = min_y
        while current_y + table_height_m <= max_y:
            current_x = min_x
            while current_x + table_width_m <= max_x:
                table_box = box(current_x, current_y, current_x + table_width_m, current_y + table_height_m)

                # Masayı yerleştirmek için 'final_buildable_area' (trafodan arındırılmış alan) içinde mi?
                if final_buildable_area.contains(table_box):
                    # Masayı çiz
                    for r in range(table_rows):
                        for c in range(table_cols):
                            px = current_x + (c * (panel_width + 0.02))
                            py = current_y + (r * (panel_height + 0.02))
                            single_panel = box(px, py, px + panel_width, py + panel_height)

                            # Orijinal açıya döndür ve koordinata çevir
                            orig_panel = affinity.rotate(single_panel, -rotation_angle,
                                                         origin=self.polygon_meters.centroid)
                            coords = [[self._get_latlon_from_xy(x, y)[0], self._get_latlon_from_xy(x, y)[1]]
                                      for x, y in orig_panel.exterior.coords]
                            panels_latlon.append(coords)
                            total_panels += 1

                current_x += table_width_m + col_spacing

            current_y += table_height_m + row_spacing

        return {
            "panels": panels_latlon,
            "kiosk": kiosk_coords,
            "count": total_panels,
            "capacity_kw": round(total_panels * 0.550, 2),  # 550W varsayılan
            "area_m2": round(self.polygon_meters.area, 2)
        }