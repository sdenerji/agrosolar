import streamlit as st
import uuid
import time
from database import get_user_data, update_user_session_id

def get_device_uuid():
    """Tarayıcı sekmesi için benzersiz ID oluşturur."""
    if 'my_session_id' not in st.session_state:
        st.session_state.my_session_id = str(uuid.uuid4())
    return st.session_state.my_session_id

def handle_session_limit():
    """
    MAIN.PY BAŞINDA ÇAĞRILIR:
    Oturumun geçerliliğini kontrol eder.
    """
    if not st.session_state.get("logged_in", False):
        return

    username = st.session_state.get("username")
    current_uuid = get_device_uuid()

    # Database.py'den veriyi çek (SQL yok, fonksiyon var)
    user_data = get_user_data(username)

    if user_data:
        db_session_id = user_data.get("current_session_id")

        # Durum 1: DB'de session yoksa (İlk giriş veya temizlenmiş) -> Kaydet
        if not db_session_id:
            update_user_session_id(username, current_uuid)

        # Durum 2: DB'deki session ile benimki farklıysa -> AT!
        elif db_session_id != current_uuid:
            st.warning("⚠️ Bu hesap başka bir cihazda açıldı. Güvenlik nedeniyle oturum sonlandırılıyor.")
            time.sleep(3)
            st.session_state.logged_in = False
            st.session_state.user_role = "Free"
            st.session_state.username = "Misafir"
            st.rerun()

def register_new_session_login(username):
    """
    LOGIN OLURKEN ÇAĞRILIR:
    Yeni cihazı 'yetkili cihaz' yapar.
    """
    new_uuid = get_device_uuid()
    update_user_session_id(username, new_uuid)