import base64
import hmac
import hashlib
import requests
import time
import streamlit as st
import certifi


def get_paytr_iframe_token(user_id, email, amount, plan_name):
    """
    PayTR API'den iFrame token'ı alır.
    amount: TL cinsinden tutar (örn: 49)
    plan_name: "Pro" veya "Ultra"
    """
    try:
        # 1. Secrets'tan Mağaza Bilgilerini Al
        # .streamlit/secrets.toml dosyasına bunları eklemeniz gerekecek
        merchant_id = st.secrets["paytr"]["merchant_id"]
        merchant_key = st.secrets["paytr"]["merchant_key"]
        merchant_salt = st.secrets["paytr"]["merchant_salt"]
    except Exception:
        return {"status": "error", "reason": "PayTR API anahtarları secrets.toml dosyasında bulunamadı!"}

    # 2. Ödeme Parametreleri
    clean_id = str(user_id).replace("-", "").replace("_", "")
    merchant_oid = f"SD{clean_id}{int(time.time())}"
    email_str = email
    payment_amount = int(amount * 100)  # PayTR kuruş ister (49 TL -> 4900)

    # Sepet İçeriği (Zorunlu)
    user_basket = base64.b64encode(
        f'[["{plan_name} Paket Abonelik", "{amount}", 1]]'.encode()
    ).decode()

    # Diğer Ayarlar
    # Not: Canlıda request.headers'dan IP almak daha doğrudur, şimdilik sunucu IP'si gider
    user_ip = "91.99.100.41"
    timeout_limit = "300"
    debug_on = "1"  # Canlıda "0" yapın
    test_mode = "1"  # CANLI ÖDEME ALMAK İÇİN BUNU "0" YAPMALISINIZ
    no_installment = "0"  # Taksit yapılsın mı? 0=Evet
    max_installment = "12"
    currency = "TL"
    lang = "tr"

    # Başarılı/Hatalı Dönüş URL'leri (Wix siteniz veya Streamlit app linki)
    # Webhook ile arka planda onaylayacağız ama kullanıcı buraya dönecek.
    merchant_ok_url = "https://analiz.sdenerji.com/?payment_status=success"
    merchant_fail_url = "https://analiz.sdenerji.com/?payment_status=fail"

    # 3. Hash Oluşturma (PayTR Güvenlik İmzas)
    # Sıralama: merchant_id + user_ip + merchant_oid + email + payment_amount + user_basket + no_installment + max_installment + currency + test_mode
    hash_str = f"{merchant_id}{user_ip}{merchant_oid}{email_str}{payment_amount}{user_basket}{no_installment}{max_installment}{currency}{test_mode}"

    # Token oluştur
    paytr_token = base64.b64encode(
        hmac.new(merchant_key.encode(), hash_str.encode() + merchant_salt.encode(), hashlib.sha256).digest()
    ).decode()

    # 4. API İsteği
    params = {
        'merchant_id': merchant_id,
        'user_ip': user_ip,
        'merchant_oid': merchant_oid,
        'email': email_str,
        'payment_amount': payment_amount,
        'paytr_token': paytr_token,
        'user_basket': user_basket,
        'debug_on': debug_on,
        'no_installment': no_installment,
        'max_installment': max_installment,
        'user_name': "AgroSolar Kullanicisi",  # Veritabanından ad soyad da çekilebilir
        'user_address': "Turkiye",
        'user_phone': "905555555555",  # Zorunlu alan
        'merchant_ok_url': merchant_ok_url,
        'merchant_fail_url': merchant_fail_url,
        'timeout_limit': timeout_limit,
        'currency': currency,
        'test_mode': test_mode,
        'lang': lang
    }

    try:
        # verify=certifi.where() parametresini ekleyerek doğru sertifikayı zorluyoruz
        result = requests.post(
            'https://www.paytr.com/odeme/api/get-token',
            data=params,
            verify=certifi.where()  # <--- KRİTİK DÜZELTME BURADA
        )
        res = result.json()

        if res['status'] == 'success':
            return {"status": "success", "token": res['token']}
        else:
            return {"status": "error", "reason": res['reason']}
    except Exception as e:
        return {"status": "error", "reason": str(e)}