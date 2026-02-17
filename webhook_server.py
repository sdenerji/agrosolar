# webhook_server.py - SON (DİLİMLEME VERSİYONU)

from flask import Flask, request, Response
import base64, hmac, hashlib, toml, os
from supabase import create_client, Client

app = Flask(__name__)

# Ayarlar
secrets = toml.load(".streamlit/secrets.toml")
PAYTR_KEY = secrets["paytr"]["merchant_key"]
PAYTR_SALT = secrets["paytr"]["merchant_salt"]
SUPABASE_URL = secrets["supabase"]["url"]
SUPABASE_KEY = secrets["supabase"]["key"]

supabase: Client = create_client(SUPABASE_URL, SUPABASE_KEY)


@app.route('/callback', methods=['POST'])
def paytr_callback():
    try:
        data = request.form.to_dict()
        merchant_oid = data.get('merchant_oid')
        status = data.get('status')
        total_amount = data.get('total_amount')
        received_hash = data.get('hash')

        # 1. Güvenlik Hash Kontrolü
        hash_str = f"{merchant_oid}{PAYTR_SALT}{status}{total_amount}"
        token = hmac.new(PAYTR_KEY.encode(), hash_str.encode(), hashlib.sha256).digest()
        calculated_hash = base64.b64encode(token).decode()

        if calculated_hash != received_hash:
            return Response("FAIL: bad hash", status=400)

        if status == 'success':
            # 🔍 OID PARÇALAMA (Dilimleme Yöntemi)
            # Format: SD[Tag][CleanID][Timestamp]
            # Örn: S D P 550e84... 1708...
            # İndeksler: 0 1 2 3..... -10

            if len(merchant_oid) > 20:  # Basit bir uzunluk kontrolü
                # 3. karakter (indeks 2) bizim etiketimizdir
                package_tag = merchant_oid[2]

                # ID kısmı: 3. karakterden başlar, son 10 hane (zaman) hariç hepsidir
                clean_user_id = merchant_oid[3:-10]

                # 🎯 ROL BELİRLEME
                # Fiyat ne olursa olsun, etikete bak!
                new_role = "Pro" if package_tag == "P" else "Ultra"

                print(f"Tespit: Paket={new_role}, ID={clean_user_id}")

                # Kullanıcıyı Bul ve Güncelle
                # UUID'ler veritabanında tireli olduğu için eşleştirme yapıyoruz
                user_query = supabase.table("users").select("*").execute()
                found = False

                for u in user_query.data:
                    # DB'deki ID'nin tirelerini silip gelen clean_id ile kıyaslıyoruz
                    if str(u['id']).replace("-", "") == clean_user_id:
                        supabase.table("users").update({"role": new_role}).eq("id", u['id']).execute()
                        print(f"✅ GÜNCELLEME BAŞARILI: {u['email']} -> {new_role}")
                        found = True
                        break

                if not found:
                    print(f"❌ Kullanıcı Bulunamadı: {clean_user_id}")
            else:
                print("⚠️ OID Formatı Geçersiz veya Çok Kısa")

        return "OK"
    except Exception as e:
        print(f"❌ Kritik Hata: {e}")
        return Response("Error", status=500)


if __name__ == '__main__':
    app.run(host='0.0.0.0', port=5000)