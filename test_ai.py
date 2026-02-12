from google import genai
import streamlit as st

# 1. Anahtarı Al
try:
    api_key = st.secrets["general"]["gemini_api_key"]
    print(f"🔑 Anahtar: {api_key[:5]}... (Okundu)")
except:
    print("❌ Secrets dosyası okunamadı!")
    exit()

# 2. Bağlan
client = genai.Client(api_key=api_key)
print("📡 Modeller listeleniyor...")

try:
    # 3. İsimleri Basitçe Listele
    for m in client.models.list():
        # Sadece ismini yazdıralım (Hata riskini sıfıra indirmek için)
        print(f"📦 Model Bulundu: {m.name}")

except Exception as e:
    print(f"❌ Hata Detayı: {e}")