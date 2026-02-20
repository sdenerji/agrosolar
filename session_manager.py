import streamlit as st
import time
from datetime import datetime, timedelta
from db_base import get_supabase
import uuid

# AYAR: Oturum kaç saniye hareketsiz kalırsa kapansın? (2 Saat = 7200 sn)
SESSION_TIMEOUT_SEC = 7200

def check_timeout():
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
    if not st.session_state.get("logged_in", False):
        return

    user_id = st.session_state.get("user_id")
    if not user_id: return

    check_timeout()

    # 🎯 KRİTİK ÇÖZÜM: IP yerine her tarayıcıya/cihaza benzersiz bir "Mühür" (Browser ID) veriyoruz
    if "browser_id" not in st.session_state:
        st.session_state.browser_id = uuid.uuid4().hex

    current_browser_id = st.session_state.browser_id
    supabase = get_supabase()
    now = datetime.utcnow()

    try:
        response = supabase.table('active_sessions').select("*").eq('user_id', user_id).execute()
        existing_session = response.data[0] if response.data else None

        if existing_session:
            # DB'de tablo yapısını bozmamak için 'ip_address' kolonuna eşsiz kimliği (uuid) kaydediyoruz
            db_browser_id = existing_session.get('ip_address')
            last_active_str = existing_session.get('last_active')

            try:
                last_active_dt = datetime.fromisoformat(last_active_str.replace('Z', '+00:00'))
                if last_active_dt.tzinfo:
                    last_active_dt = last_active_dt.replace(tzinfo=None)
                time_diff = now - last_active_dt
            except:
                time_diff = timedelta(seconds=0)

            # SENARYO A: Aynı tarayıcı penceresi
            if db_browser_id == current_browser_id:
                supabase.table('active_sessions').update({
                    'last_active': now.isoformat()
                }).eq('user_id', user_id).execute()
                return

            # SENARYO B: Farklı cihaz ama eski oturum (60 dakikadan eski)
            elif time_diff > timedelta(minutes=60):
                supabase.table('active_sessions').update({
                    'ip_address': current_browser_id,
                    'last_active': now.isoformat()
                }).eq('user_id', user_id).execute()
                return

            # SENARYO C: ÇAKIŞMA (Farklı cihaz ve oturum taze) -> AFFETME AT!
            else:
                st.error("⚠️ **GÜVENLİK UYARISI:** Hesabınız şu an başka bir cihazda açık!")
                st.warning("Veri güvenliği nedeniyle aynı anda sadece tek cihazdan/tarayıcıdan giriş yapabilirsiniz.")

                col1, col2 = st.columns(2)
                if col1.button("🚪 Buradan Çıkış Yap"):
                    st.session_state.logged_in = False
                    st.session_state.page = "analiz"
                    st.rerun()

                if col2.button("🚫 Diğerini Kapat ve Buradan Gir", type="primary"):
                    supabase.table('active_sessions').update({
                        'ip_address': current_browser_id,
                        'last_active': now.isoformat()
                    }).eq('user_id', user_id).execute()

                    st.success("Oturum bu cihaza taşındı! Sayfa yenileniyor...")
                    time.sleep(1)
                    st.rerun()

                st.stop()

        else:
            # İlk Giriş
            new_data = {
                "user_id": user_id,
                "ip_address": current_browser_id,
                "last_active": now.isoformat()
            }
            supabase.table('active_sessions').upsert(new_data, on_conflict="user_id").execute()

    except Exception as e:
        print(f"Session Manager Hatası: {e}")
        pass