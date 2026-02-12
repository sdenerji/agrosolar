import streamlit as st
import time
from datetime import datetime, timedelta
from db_base import get_supabase
from streamlit import runtime
from streamlit.runtime.scriptrunner import get_script_run_ctx

# AYAR: Oturum kaç saniye hareketsiz kalırsa kapansın? (2 Saat = 7200 sn)
SESSION_TIMEOUT_SEC = 7200


def get_remote_ip():
    """
    Kullanıcının IP adresini tespit eder.
    Yerel çalışmada (localhost) bazen IP görünmeyebilir, bu durumda varsayılan değer döner.
    """
    try:
        ctx = get_script_run_ctx()
        if ctx is None: return "0.0.0.0"

        session_info = runtime.get_instance().get_client(ctx.session_id)
        if session_info:
            return session_info.request.remote_ip
    except Exception:
        return "0.0.0.0"
    return "0.0.0.0"


def check_timeout():
    """
    İstemci tarafında (Streamlit Session State) zaman aşımı kontrolü.
    """
    if "last_active" not in st.session_state:
        st.session_state.last_active = time.time()
        return

    idle_time = time.time() - st.session_state.last_active

    if idle_time > SESSION_TIMEOUT_SEC:
        st.warning("⏳ Uzun süre işlem yapmadığınız için oturumunuz sonlandırıldı.")
        try:
            get_supabase().auth.sign_out()
        except:
            pass
        st.session_state.logged_in = False
        st.session_state.username = "Misafir"
        st.session_state.user_id = None
        time.sleep(2)
        st.rerun()
        st.stop()
    else:
        st.session_state.last_active = time.time()


def handle_session_limit():
    """
    MAIN.PY BAŞINDA ÇAĞRILIR:
    active_sessions tablosu üzerinden IP tabanlı tek oturum kontrolü yapar.
    """
    # 1. Giriş yoksa işlem yapma
    if not st.session_state.get("logged_in", False):
        return

    user_id = st.session_state.get("user_id")
    if not user_id: return

    # 2. İstemci tarafı zaman aşımı kontrolü
    check_timeout()

    # 3. IP ve Veritabanı Kontrolü
    current_ip = get_remote_ip()
    supabase = get_supabase()
    now = datetime.utcnow()

    try:
        # DB'deki aktif oturumu sorgula
        response = supabase.table('active_sessions').select("*").eq('user_id', user_id).execute()
        existing_session = response.data[0] if response.data else None

        if existing_session:
            db_ip = existing_session.get('ip_address')
            last_active_str = existing_session.get('last_active')

            # Zaman farkı hesabı (DB tarafında bayat oturum kontrolü için)
            try:
                # Supabase formatı genelde: 2023-10-10T15:30:00+00:00
                last_active_dt = datetime.fromisoformat(last_active_str.replace('Z', '+00:00'))
                if last_active_dt.tzinfo:
                    last_active_dt = last_active_dt.replace(tzinfo=None)
                time_diff = now - last_active_dt
            except:
                time_diff = timedelta(seconds=0)

            # --- SENARYO A: IP AYNI (Sayfa Yenileme / F5) ---
            # IP değişmediyse sorun yok, süreyi güncelle ve devam et.
            if db_ip == current_ip:
                supabase.table('active_sessions').update({
                    'last_active': now.isoformat()
                }).eq('user_id', user_id).execute()
                return

            # --- SENARYO B: IP FARKLI ama Oturum Çok Eski (>60 dk) ---
            # Kullanıcı başka yerde kapatmayı unutmuş ama 1 saattir işlem yapmamış.
            # Otomatik devral.
            elif time_diff > timedelta(minutes=60):
                supabase.table('active_sessions').update({
                    'ip_address': current_ip,
                    'last_active': now.isoformat()
                }).eq('user_id', user_id).execute()
                return

            # --- SENARYO C: IP FARKLI ve Oturum Taze (ÇAKIŞMA!) ---
            else:
                st.error(f"⚠️ **GÜVENLİK UYARISI:** Hesabınız şu an başka bir cihazda ({db_ip}) açık görünüyor.")
                st.warning("Veri güvenliği nedeniyle aynı anda sadece tek cihazdan giriş yapabilirsiniz.")

                col1, col2 = st.columns(2)

                # Seçenek 1: Çıkış Yap
                if col1.button("🚪 Buradan Çıkış Yap"):
                    st.session_state.logged_in = False
                    st.session_state.page = "analiz"
                    st.rerun()

                # Seçenek 2: Devral
                if col2.button("🚫 Diğerini Kapat ve Buradan Gir", type="primary"):
                    # Diğer IP'yi sil, benim IP'mi yaz
                    supabase.table('active_sessions').update({
                        'ip_address': current_ip,
                        'last_active': now.isoformat()
                    }).eq('user_id', user_id).execute()

                    st.success("Oturum bu cihaza taşındı! Sayfa yenileniyor...")
                    time.sleep(1)
                    st.rerun()

                st.stop()  # Uygulamanın geri kalanını yükleme

        else:
            # 4. Hiç kayıt yoksa (İlk Giriş) -> Yeni kayıt oluştur
            new_data = {
                "user_id": user_id,
                "ip_address": current_ip,
                "last_active": now.isoformat()
            }
            # upsert: varsa güncelle, yoksa ekle (User ID unique olduğu için güvenli)
            supabase.table('active_sessions').upsert(new_data, on_conflict="user_id").execute()

    except Exception as e:
        # Veritabanı hatası olursa (örneğin internet koptuysa) kullanıcıyı engellememek için
        # log basıp devam edebiliriz veya hata gösterebiliriz.
        print(f"Session Manager Hatası: {e}")
        pass


def register_new_session_login(user_id):
    """
    LOGIN OLURKEN ÇAĞRILIR (Auth Service içinden)
    Kullanıcı şifresini girdiğinde active_sessions tablosunu günceller.
    """
    st.session_state.last_active = time.time()
    current_ip = get_remote_ip()
    now = datetime.utcnow().isoformat()
    supabase = get_supabase()

    new_data = {
        "user_id": user_id,
        "ip_address": current_ip,
        "last_active": now
    }
    try:
        supabase.table('active_sessions').upsert(new_data, on_conflict="user_id").execute()
    except Exception as e:
        print(f"Login Register Hatası: {e}")