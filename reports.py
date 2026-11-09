"""
وحدة تصدير تقارير وسجلات منصة رعايتي (MedLink).
تصدير سجل العمليات والطلبات إلى ملفات Excel (.xlsx) و CSV (UTF-8).
"""
import io
import pandas as pd

STATUS_ARABIC_MAP = {
    'pending':              'معلق',
    'accepted':             'جاري التنفيذ',
    'completed':            'مكتمل بنجاح',
    'cancelled_by_patient': 'ملغى من المريض',
    'cancelled_by_nurse':   'ملغى من الممرض',
    'cancelled_by_admin':   'ملغى من الإدارة',
}


def build_requests_dataframe(requests_list):
    """تحويل قائمة قواميس الطلبات إلى DataFrame منسق بأسماء أعمدة عربية واضحة"""
    if not requests_list:
        return pd.DataFrame()

    rows = []
    for r in requests_list:
        created_str = str(r.get('created_at', ''))[:19]
        rows.append({
            'رقم الطلب': r.get('id'),
            'تاريخ ووقت الطلب': created_str,
            'نوع الخدمة': r.get('service_type'),
            'اسم المريض': r.get('patient_name'),
            'هاتف المريض': r.get('patient_phone'),
            'جنس المريض': r.get('patient_gender'),
            'العمر': r.get('patient_age'),
            'العنوان بالتفصيل': r.get('location_text'),
            'الحد الأدنى للسعر (د.ل)': r.get('min_price'),
            'الحد الأقصى للسعر (د.ل)': r.get('max_price'),
            'حالة الطلب': STATUS_ARABIC_MAP.get(r.get('status'), r.get('status')),
            'الممرض المستلم': r.get('accepted_by') or '—',
            'وصف الحالة': r.get('service_desc') or '—',
        })
    return pd.DataFrame(rows)


def export_requests_excel(requests_list) -> bytes:
    """تحويل سجل الطلبات إلى بايتات ملف Excel منسق (.xlsx)"""
    df = build_requests_dataframe(requests_list)
    buf = io.BytesIO()
    with pd.ExcelWriter(buf, engine='openpyxl') as writer:
        df.to_excel(writer, index=False, sheet_name='سجل طلبات التمريض')
    return buf.getvalue()


def export_requests_csv(requests_list) -> bytes:
    """تحويل سجل الطلبات إلى بايتات ملف CSV بترميز UTF-8 مع BOM لدعم إكسل"""
    df = build_requests_dataframe(requests_list)
    if df.empty:
        return b""
    return df.to_csv(index=False).encode('utf-8-sig')
