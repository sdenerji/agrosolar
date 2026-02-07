# user_service.py
from datetime import datetime, date, timedelta, timezone
from db_base import get_supabase


# --- 1. ABONELİK SENKRONİZASYONU (OTOMATİK KONTROL) ---
def check_and_update_subscription(user_id):
    """
    Kullanıcının abonelik süresini kontrol eder.
    Eğer süre dolmuşsa ve bekleyen bir rol değişimi varsa onu uygular.
    """
    supabase = get_supabase()
    try:
        # ID ile sorgulama
        res = supabase.table("users").select("role, next_role, subscription_end_date").eq("id", user_id).execute()

        if res.data:
            user = res.data[0]
            next_role = user.get("next_role")
            end_date_str = user.get("subscription_end_date")

            if next_role and end_date_str:
                end_date = None

                # A. Tarihi Parse Etme Denemeleri
                try:
                    # ISO formatı (Örn: 2026-02-05T15:14:05+00:00 veya Z)
                    end_date = datetime.fromisoformat(end_date_str.replace('Z', '+00:00'))
                except ValueError:
                    try:
                        # Sadece YYYY-MM-DD ise
                        end_date = datetime.strptime(end_date_str[:10], "%Y-%m-%d").replace(tzinfo=timezone.utc)
                    except:
                        pass

                if end_date:
                    # B. Şu anki zamanı UTC olarak al (Supabase UTC kullanır)
                    now_utc = datetime.now(timezone.utc)

                    # Eğer end_date'in timezone bilgisi yoksa UTC kabul et
                    if end_date.tzinfo is None:
                        end_date = end_date.replace(tzinfo=timezone.utc)

                    # C. Karşılaştırma: Şu an >= Bitiş Tarihi
                    if now_utc >= end_date:
                        target_role = next_role
                        new_end_date = None

                        # Eğer yeni paket de paralıysa (örn: Pro -> Ultra) 30 gün ekle
                        if target_role in ["Pro", "Ultra"]:
                            new_end_date = (now_utc + timedelta(days=30)).isoformat()

                        # D. Veritabanını Güncelle
                        supabase.table("users").update({
                            "role": target_role,
                            "next_role": None,
                            "subscription_end_date": new_end_date
                        }).eq("id", user_id).execute()

                        return True, target_role
    except Exception as e:
        print(f"Abonelik Kontrol Hatası Detay: {e}")
    return False, None


# --- 2. KULLANICI VERİSİ ---
def get_user_data(user_id):
    """
    Kullanıcı verisini çeker. Çekerken abonelik kontrolünü de tetikler.
    """
    supabase = get_supabase()
    try:
        # Önce kontrolü yap (Gerekirse günceller)
        check_and_update_subscription(user_id)

        # Sonra güncel veriyi çek
        res = supabase.table("users").select("*").eq("id", user_id).execute()
        if res.data:
            return res.data[0]
    except Exception as e:
        print(f"Kullanıcı Verisi Çekme Hatası: {e}")
    return None


# --- 3. ABONELİK İŞLEMLERİ ---
def schedule_role_change(user_id, target_role):
    """
    Paket değişikliği talebi oluşturur.
    ARGUMAN: username DEĞİL, user_id alır.
    """
    supabase = get_supabase()
    user = get_user_data(user_id)

    if not user:
        return False, "Kullanıcı bulunamadı."

    current_role = user.get("role", "Free")

    try:
        # SENARYO A: Şu an Free ise veya süresi yoksa -> HEMEN GEÇİR
        if current_role == "Free" or not user.get("subscription_end_date"):
            new_end_date = (datetime.now(timezone.utc) + timedelta(days=30)).isoformat()

            supabase.table("users").update({
                "role": target_role,
                "subscription_end_date": new_end_date,
                "next_role": None
            }).eq("id", user_id).execute()

            return True, f"Aboneliğiniz anında **{target_role}** olarak güncellendi."

        # SENARYO B: Zaten paralı ise -> SIRAYA AL (Next Role)
        else:
            supabase.table("users").update({"next_role": target_role}).eq("id", user_id).execute()

            # Bitiş tarihini kullanıcıya göstermek için al
            current_end = user.get("subscription_end_date", "")
            end_date_display = current_end[:10] if current_end else "Dönem Sonu"

            return True, f"Talebiniz alındı. **{end_date_display}** tarihinde paketiniz **{target_role}** olacak."

    except Exception as e:
        return False, f"İşlem Hatası: {e}"


def cancel_pending_change(user_id):
    """Bekleyen paket değişikliğini iptal eder."""
    supabase = get_supabase()
    try:
        supabase.table("users").update({"next_role": None}).eq("id", user_id).execute()
        return True
    except:
        return False


# --- 4. ANALİZ KAYDI ---
def save_analysis_to_history(user_id, lat, lon, rakim, egim, baki, kw, kwh, roi):
    supabase = get_supabase()
    data = {
        "user_id": user_id,
        "latitude": float(lat),
        "longitude": float(lon),
        "rakim": int(rakim),
        "egim": float(egim),
        "baki": str(baki),
        "kw_power": float(kw),
        "annual_kwh": float(kwh),
        "roi": float(roi),
        "created_at": datetime.now().isoformat()
    }
    try:
        supabase.table("analysis_history").insert(data).execute()
        return True
    except Exception as e:
        print(f"🔴 Analiz Kayıt Hatası: {e}")
        return False