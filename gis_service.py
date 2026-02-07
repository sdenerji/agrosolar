#TM verilerini çekmek, GeoJSON işlemek ve ileride eklenecek mesafe analizleri.
from db_base import get_supabase

def get_substation_data(substation_name):
    """
    Şebeke kapasite verilerini veritabanından çeker.
    """
    supabase = get_supabase()
    try:
        res = supabase.table("substation_capacities") \
            .select("available_capacity_mw, total_capacity_mw") \
            .eq("substation_name", substation_name) \
            .execute()
        if res.data:
            return {
                "mw": res.data[0]["available_capacity_mw"],
                "total": res.data[0]["total_capacity_mw"]
            }
    except Exception as e:
        pass
    # Veri bulunamazsa varsayılan döndür
    return {"mw": 0, "total": 0.01}

# --- GELECEKTE BURAYA EKLENECEK ---
# def process_uploaded_geojson(file):
#    ...
# def calculate_distance_to_grid(polygon, grid_lines):
#    ...