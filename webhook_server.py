# webhook_server.py
# Bu dosya PayTR'dan gelen ödeme bildirimlerini dinler ve Supabase'i günceller.

from flask import Flask, request, Response
import base64
import hmac
import hashlib
import toml
import os
from supabase import create_client, Client

app = Flask(__name__)

# --- 1. AYARLARI YÜKLE ---
# .streamlit/secrets.toml dosyasından şifreleri okuyoruz
try:
    secrets = toml.load(".streamlit/secrets.toml")
    PAYTR_KEY = secrets["paytr"]["merchant_key"]
    PAYTR_SALT = secrets["paytr"]["merchant_salt"]
    SUPABASE_URL = secrets["supabase"]["url"]
    SUPABASE_KEY = secrets["supabase"]["key"]
    print("✅ Ayarlar başarıyla yüklendi.")
except Exception as e:
    print(f"❌ Ayarlar yüklenirken hata: {e}")
    exit()

# Supabase Bağlantısı
supabase: Client = create_client(SUPABASE_URL, SUPABASE_KEY)


@app.route('/callback', methods=['POST'])
def paytr_callback():
    # PayTR'dan gelen POST verisini al
    try:
        data = request.form.to_dict()

        # Gerekli parametreler
        merchant_oid = data.get('merchant_oid')
        status = data.get('status')
        total_amount = data.get('total_amount')
        received_hash = data.get('hash')

        # --- 2. GÜVENLİK KONTROLÜ (HASH DOĞRULAMA) ---
        # PayTR dokümantasyonuna uygun hash oluşturma
        hash_str = f"{merchant_oid}{PAYTR_SALT}{status}{total_amount}"
        token = hmac.new(PAYTR_KEY.encode(), hash_str.encode(), hashlib.sha256).digest()
        calculated_hash = base64.b64encode(token).decode()

        if calculated_hash != received_hash:
            print(f"⚠️ HACK GİRİŞİMİ? Hash uyuşmuyor! Gelen: {received_hash}, Hesaplanan: {calculated_hash}")
            return Response("PAYTR notification failed: bad hash", status=400)

        # --- 3. İŞLEM BAŞARILI MI? ---
        if status == 'success':
            print(f"💰 Ödeme Başarılı! Sipariş No: {merchant_oid}")

            # merchant_oid formatımız: SD{user_id}{timestamp}
            # Buradan user_id'yi ayıklamamız lazım.
            # SD ile başlıyor, son 10 hane timestamp. Arası user_id.

            try:
                # Terminalde gördüğümüz o uzun ID'yi (Clean ID) alıyoruz
                clean_user_id = merchant_oid[2:-10]
                print(f"🔍 Kullanıcı ID ile Aranıyor: {clean_user_id}")

                # Supabase'de 'id' sütununda bu temizlenmiş ID'yi içeren kullanıcıyı bul
                # Not: UUID'deki tireler silindiği için 'ilike' (benzerlik) kullanıyoruz
                user_query = supabase.table("users").select("*").execute()

                target_user = None
                for u in user_query.data:
                    if u['id'].replace("-", "") == clean_user_id:
                        target_user = u
                        break

                if target_user:
                    user_email = target_user['email']
                    # GÜNCELLEME ANI
                    supabase.table("users").update({"role": "Ultra"}).eq("id", target_user['id']).execute()
                    print(f"✅ KULLANICI YÜKSELTİLDİ: {user_email} -> Ultra")
                else:
                    print(f"❌ ID ile eşleşen kullanıcı bulunamadı: {clean_user_id}")

            except Exception as e:
                print(f"❌ Veritabanı ID eşleştirme hatası: {e}")

        else:
            print(f"❌ Ödeme Başarısız. Sipariş: {merchant_oid}")

        # PayTR'a "Tamam, aldım" mesajı (ZORUNLU)
        return "OK"

    except Exception as e:
        print(f"Genel Hata: {e}")
        return Response("Error", status=500)


if __name__ == '__main__':
    # Streamlit 8501'de çalışıyor, bunu 5000'de çalıştıralım
    app.run(host='0.0.0.0', port=5000)