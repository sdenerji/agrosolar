import streamlit as st
import time
from datetime import datetime, timedelta
from db_base import get_supabase
import uuid

# AYARLAR
SESSION_TIMEOUT_SEC = 7200  # 2 Saat hareketsizlikten sonra kapanır
LOCK_TIMEOUT_MIN = 5  # Son işlemden sonra kaç dakika 'Kilitli' kalsın?


def check_timeout():
    if "last_active" not in st.session_state:
        st.session_state.last_active = time.time()
        return

    idle_time = time.time() - st.session_state.last_active
    if idle_time > SESSION_TIMEOUT_SEC:
        st.warning("⏳ Oturumunuz zaman aşımına uğradı.")
        try:
            get_supabase().auth.sign_out()
        except:
            pass
        st.session_state.logged_in = False
        st.rerun()
    else:
        st.session_state.last_active = time.time()


def handle_session_limit():
    if not st.session_state.get("logged_in", False):
        return

    user_id = st.session_state.get("user_id")
    if not user_id: return

    check_timeout()

    if "browser_id" not in st.session_state:
        st.session_state.browser_id = uuid.uuid4().hex

    current_browser_id = st.session_state.browser_id
    supabase = get_supabase()
    now = datetime.utcnow()

    try:
        response = supabase.table('active_sessions').select("*").eq('user_id', user_id).execute()
        existing_session = response.data[0] if response.data else None

        if existing_session:
            db_browser_id = existing_session.get('ip_address')
            last_active_str = existing_session.get('last_active')

            try:
                last_active_dt = datetime.fromisoformat(last_active_str.replace('Z', '+00:00'))
                if last_active_dt.tzinfo: last_active_dt = last_active_dt.replace(tzinfo=None)
                time_diff = now - last_active_dt
            except:
                time_diff = timedelta(seconds=0)

            # --- DURUM 1: AYNI OTURUM ---
            if db_browser_id == current_browser_id:
                supabase.table('active_sessions').update({'last_active': now.isoformat()}).eq('user_id',
                                                                                              user_id).execute()
                return

            # --- DURUM 2: FARKLI CİHAZ VE OTURUM TAZE (SERT KİLİT) ---
            elif time_diff < timedelta(minutes=LOCK_TIMEOUT_MIN):
                st.error("🚫 **ERİŞİM REDDEDİLDİ:** Bu hesap şu an başka bir cihazda aktif olarak kullanılmaktadır.")
                st.info(
                    f"Güvenlik nedeniyle aynı anda sadece tek bir oturuma izin verilir. Mevcut oturumun kapanmasını bekleyin veya {LOCK_TIMEOUT_MIN} dakika sonra tekrar deneyin.")

                if st.button("🚪 Giriş Ekranına Dön", use_container_width=True):
                    # 🎯 KRİTİK FİKS: Sadece state'i değil, Supabase oturumunu da tamamen siliyoruz
                    try:
                        supabase.auth.sign_out()
                    except:
                        pass
                    st.session_state.logged_in = False
                    st.session_state.user_id = None
                    st.session_state.page = 'analiz'  # Analiz ekranına (Landing Page) zorla döndür
                    st.rerun()
                st.stop()

                # --- DURUM 3: FARKLI CİHAZ AMA ÖNCEKİ OTURUM TERK EDİLMİŞ ---
            else:
                supabase.table('active_sessions').update({
                    'ip_address': current_browser_id,
                    'last_active': now.isoformat()
                }).eq('user_id', user_id).execute()
                return

        else:
            new_data = {"user_id": user_id, "ip_address": current_browser_id, "last_active": now.isoformat()}
            supabase.table('active_sessions').upsert(new_data, on_conflict="user_id").execute()

    except Exception as e:
        print(f"Oturum Hatası: {e}")