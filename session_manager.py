import streamlit as st
import uuid
import time
from datetime import datetime
from db_base import get_supabase

# AYAR: Oturum kaç saniye hareketsiz kalırsa kapansın? (2 Saat = 7200 sn)
SESSION_TIMEOUT_SEC = 7200


def get_device_uuid():
    """Tarayıcı sekmesi için benzersiz ID oluşturur."""
    if 'my_session_id' not in st.session_state:
        st.session_state.my_session_id = str(uuid.uuid4())
    return st.session_state.my_session_id


def update_user_session_id(user_id, new_session_id):
    """
    Veritabanındaki aktif session ID'yi günceller.
    HEDEF SÜTUN: current_session_id
    """
    supabase = get_supabase()
    try:
        # Debug: Hata alırsak görelim diye execute() sonucunu alıyoruz
        data = supabase.table("users").update({"current_session_id": new_session_id}).eq("id", user_id).execute()
        return True, None
    except Exception as e:
        return False, str(e)


def get_db_session_id(user_id):
    """
    Veritabanından kullanıcının son session ID'sini çeker.
    HEDEF SÜTUN: current_session_id
    """
    supabase = get_supabase()
    try:
        res = supabase.table("users").select("current_session_id").eq("id", user_id).execute()
        if res.data and len(res.data) > 0:
            return res.data[0].get("current_session_id")
    except Exception as e:
        print(f"Session Read Hatası: {e}")
    return None


def check_timeout():
    """Kullanıcı belirli bir süre işlem yapmadıysa oturumu kapatır."""
    if "last_active" not in st.session_state:
        st.session_state.last_active = time.time()
        return

    idle_time = time.time() - st.session_state.last_active

    if idle_time > SESSION_TIMEOUT_SEC:
        st.warning("⏳ 2 saatlik hareketsizlik nedeniyle oturumunuz sonlandırıldı.")
        try:
            get_supabase().auth.sign_out()
        except:
            pass
        st.session_state.logged_in = False
        st.session_state.user_role = "Free"
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
    Oturum çakışması kontrolü.
    """
    # Giriş yoksa işlem yapma
    if not st.session_state.get("logged_in", False):
        return

    user_id = st.session_state.get("user_id")
    if not user_id:
        return

    # Önce zaman aşımı kontrolü
    check_timeout()

    current_uuid = get_device_uuid()
    db_session_id = get_db_session_id(user_id)

    # Durum 1: DB boşsa (veya yeni kayıt) -> Yaz
    if not db_session_id:
        success, err = update_user_session_id(user_id, current_uuid)
        if not success:
            # Burası çalışırsa sütun adında veya yetkide sorun var demektir
            st.error(f"⚠️ Oturum Kayıt Hatası: {err}")

    # Durum 2: ÇAKIŞMA! (DB'deki ID benimkinden farklı)
    elif db_session_id != current_uuid:
        st.error(f"⚠️ DİKKAT: Hesabınız başka bir yerde açık görünüyor.")

        col1, col2 = st.columns(2)
        with col1:
            if st.button("🚪 Çıkış Yap"):
                try:
                    get_supabase().auth.sign_out()
                except:
                    pass
                st.session_state.logged_in = False
                st.session_state.username = "Misafir"
                st.rerun()

        with col2:
            if st.button("🛡️ Oturumu Devral (GİRİŞ YAP)", type="primary"):
                # Zorla benim ID'mi yaz
                success, err = update_user_session_id(user_id, current_uuid)

                if success:
                    st.success("✅ Yetki alındı! Sayfa yenileniyor...")
                    time.sleep(1)
                    st.rerun()
                else:
                    st.error(f"❌ Devralma Başarısız! Hata: {err}")
                    st.info("Lütfen Supabase tablosunda 'current_session_id' sütunu olduğundan emin olun.")

        st.stop()


def register_new_session_login(user_id):
    """LOGIN OLURKEN ÇAĞRILIR"""
    st.session_state.last_active = time.time()
    new_uuid = get_device_uuid()
    update_user_session_id(user_id, new_uuid)