import os
import subprocess
import sys

print("SSL Sorunu Düzeltiliyor ve Yükleme Başlatılıyor...")

# 1. Sorun çıkaran PostgreSQL sertifika ayarını geçici olarak sil
if 'SSL_CERT_FILE' in os.environ:
    del os.environ['SSL_CERT_FILE']
    print("- Hatalı SSL yolu temizlendi.")

# 2. pip install komutunu Python içinden çalıştır
try:
    subprocess.check_call([sys.executable, "-m", "pip", "install", "requests"])
    print("\n✅ BAŞARILI: 'requests' kütüphanesi yüklendi.")
except subprocess.CalledProcessError:
    print("\n❌ HATA: Yükleme başarısız oldu.")