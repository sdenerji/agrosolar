import streamlit as st
from supabase import create_client, Client

@st.cache_resource
def get_supabase() -> Client:
    """
    Supabase bağlantısını kurar ve önbelleğe alır.
    Tüm servisler bağlantıyı buradan çekecek.
    """
    try:
        if "supabase" not in st.secrets:
            st.error("❌ secrets.toml içinde [supabase] ayarları bulunamadı!")
            st.stop()

        url = st.secrets["supabase"]["url"]
        key = st.secrets["supabase"]["key"]
        return create_client(url, key)
    except Exception as e:
        st.error(f"⚠️ Veritabanı Bağlantı Hatası: {e}")
        st.stop()
    return None