import base64
import hmac
import hashlib
import requests
import time
import streamlit as st
import certifi


def get_paytr_iframe_token(user_id, email, amount, plan_name):
    """
    PayTR API'den token alır.
    OID Formatı: SD + {Etiket} + {TemizID} + {Zaman}
    Örn: SDP550e8400e29b...1708543210 (Alt tire YOK)
    """
    try:
        # 1. Secrets'tan Bilgileri Al
        merchant_id = st.secrets["paytr"]["merchant_id"]
        merchant_key = st.secrets["paytr"]["merchant_key"]
        merchant_salt = st.secrets["paytr"]["merchant_salt"]
    except Exception:
        return {"status": "error", "reason": "PayTR anahtarları secrets.toml içinde bulunamadı!"}

    # --- 🎯 2. MÜHÜRLEME (ALT TİRE YOK) ---
    # 3. Harf paket etiketi olacak: 'P' (Pro) veya 'U' (Ultra)
    tag = "P" if plan_name == "Pro" else "U"

    # UUID içindeki tireleri temizle (PayTR bazen sevmez)
    clean_id = str(user_id).replace("-", "").replace("_", "")

    # OID Oluştur: SD + P + ID + TIMESTAMP
    # Örn: SDP + 550e84... + 1712345678
    merchant_oid = f"SD{tag}{clean_id}{int(time.time())}"

    payment_amount = int(amount * 100)  # Kuruş cinsinden

    # Sepet
    user_basket = base64.b64encode(
        f'[["{plan_name} Paket Abonelik", "{amount}", 1]]'.encode()
    ).decode()

    # 3. Standart Ayarlar
    user_ip = "91.99.100.41"
    timeout_limit = "300"
    debug_on = "1"
    test_mode = "1"  # ⚠️ DİKKAT: GERÇEK SATIŞTA BURAYI "0" YAPIN!
    no_installment = "0"
    max_installment = "12"
    currency = "TL"
    lang = "tr"

    merchant_ok_url = "https://analiz.sdenerji.com/?payment_status=success"
    merchant_fail_url = "https://analiz.sdenerji.com/?payment_status=fail"

    # 4. Hash Hesaplama
    hash_str = f"{merchant_id}{user_ip}{merchant_oid}{email}{payment_amount}{user_basket}{no_installment}{max_installment}{currency}{test_mode}"

    paytr_token = base64.b64encode(
        hmac.new(merchant_key.encode(), hash_str.encode() + merchant_salt.encode(), hashlib.sha256).digest()
    ).decode()

    # 5. İstek Gönder
    params = {
        'merchant_id': merchant_id,
        'user_ip': user_ip,
        'merchant_oid': merchant_oid,
        'email': email,
        'payment_amount': payment_amount,
        'paytr_token': paytr_token,
        'user_basket': user_basket,
        'debug_on': debug_on,
        'no_installment': no_installment,
        'max_installment': max_installment,
        'user_name': "AgroSolar Kullanicisi",
        'user_address': "Turkiye",
        'user_phone': "905555555555",
        'merchant_ok_url': merchant_ok_url,
        'merchant_fail_url': merchant_fail_url,
        'timeout_limit': timeout_limit,
        'currency': currency,
        'test_mode': test_mode,
        'lang': lang
    }

    try:
        result = requests.post(
            'https://www.paytr.com/odeme/api/get-token',
            data=params,
            verify=certifi.where()
        )
        res = result.json()

        if res['status'] == 'success':
            return {"status": "success", "token": res['token']}
        else:
            return {"status": "error", "reason": res['reason']}
    except Exception as e:
        return {"status": "error", "reason": str(e)}