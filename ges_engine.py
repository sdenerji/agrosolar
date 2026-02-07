#Panel yerleşimi, String tasarımı ve elektriksel hesaplar.
# Bu dosya, "Dijital İkiz" geliştirmesi başladığında ana beyin olacak.
import math

def calculate_string_voltage(t_min, v_oc_stc, temp_coeff):
    """
    Örnek: En düşük sıcaklıkta panel açık devre gerilimi hesabı.
    """
    delta_t = t_min - 25
    v_oc_max = v_oc_stc * (1 + (temp_coeff / 100) * delta_t)
    return v_oc_max

# def optimize_rack_placement(polygon, azimuth):
#    ...