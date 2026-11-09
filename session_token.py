"""
استمرارية الجلسة عبر إعادة تحميل الصفحة (Session persistence across page reloads).

المشكلة: st.session_state في Streamlit تُحفظ في ذاكرة الخادم وترتبط باتصال
WebSocket واحد. عند إعادة تحميل الصفحة (F5) يُفتح اتصال جديد فتضيع الجلسة
بالكامل، فيُطلب من الممرض/الإدارة تسجيل الدخول مجدداً ويختفي طلب المريض.

الحل: نحفظ "رمز جلسة" موقَّعاً (HMAC-SHA256) في رابط الصفحة (?s=...).
الرابط يبقى كما هو عند إعادة التحميل، فنقرأ الرمز ونتحقق من توقيعه وصلاحيته
ثم نستعيد الجلسة. لا يمكن تزوير الرمز أو تعديله بدون المفتاح السري.

المفتاح السري: يُفضَّل تعريفه في الأسرار:
    [auth]
    secret_key = "قيمة_عشوائية_طويلة"
وإن لم يوجد يُشتق من رابط قاعدة البيانات (وهو سرّي أصلاً).
"""
import base64
import hashlib
import hmac
import json
import time

import streamlit as st

PARAM = "s"

NURSE_TTL = 7 * 24 * 3600      # 7 أيام
ADMIN_TTL = 12 * 3600          # 12 ساعة
PATIENT_TTL = 3 * 24 * 3600    # 3 أيام


def _b64e(raw: bytes) -> str:
    return base64.urlsafe_b64encode(raw).decode().rstrip("=")


def _b64d(text: str) -> bytes:
    return base64.urlsafe_b64decode(text + "=" * (-len(text) % 4))


def _secret() -> bytes:
    key = None
    try:
        key = st.secrets["auth"]["secret_key"]
    except Exception:
        key = None
    if not key:
        key = "medlink-session-v1::" + str(st.secrets["database"]["url"])
    return hashlib.sha256(str(key).encode()).digest()


def _sign(body: str, bind: str) -> str:
    mac = hmac.new(_secret(), f"{body}|{bind}".encode(), hashlib.sha256).digest()
    return _b64e(mac[:20])


def make_token(role: str, subject, ttl: int, bind: str = "") -> str:
    """bind: قيمة سرية إضافية تدخل في التوقيع فقط (مثلاً بصمة كلمة سر الإدارة)
    بحيث يبطل الرمز تلقائياً عند تغييرها."""
    payload = {"r": role, "s": subject, "e": int(time.time()) + int(ttl)}
    body = _b64e(json.dumps(payload, separators=(",", ":")).encode())
    return f"{body}.{_sign(body, bind)}"


def read_token(token, role: str, bind: str = ""):
    """يعيد subject إذا كان الرمز صالحاً ولم تنتهِ صلاحيته، وإلا None."""
    if not token or not isinstance(token, str) or "." not in token:
        return None
    body, sig = token.rsplit(".", 1)
    if not hmac.compare_digest(sig, _sign(body, bind)):
        return None
    try:
        payload = json.loads(_b64d(body))
    except Exception:
        return None
    if payload.get("r") != role or int(payload.get("e", 0)) < time.time():
        return None
    return payload.get("s")


# ── واجهة مبسطة للتطبيقات ──
def save_session(role: str, subject, ttl: int, bind: str = "") -> None:
    st.query_params[PARAM] = make_token(role, subject, ttl, bind)


def load_session(role: str, bind: str = ""):
    return read_token(st.query_params.get(PARAM), role, bind)


def clear_session() -> None:
    if PARAM in st.query_params:
        del st.query_params[PARAM]
