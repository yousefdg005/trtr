"""
Unit and Logic test suite for MedLink platform.
Runs without requiring an external PostgreSQL instance.
"""
import io
import html
import time
import pandas as pd
import pytest
from werkzeug.security import generate_password_hash, check_password_hash

import streamlit as st

import session_token  # noqa: E402
import database  # noqa: E402
from database import is_valid_libyan_phone  # noqa: E402
from reports import export_requests_excel, export_requests_csv  # noqa: E402


@pytest.fixture(autouse=True, scope="module")
def _test_secret_key():
    """مفتاح توقيع جلسات ثابت للاختبارات فقط (session_token صار fail-closed)."""

    class _FakeSecrets(dict):
        pass

    original = st.secrets
    st.secrets = _FakeSecrets({"auth": {"secret_key": "test-only-session-key-not-for-production"}})
    yield
    st.secrets = original


# =====================================================================
# 1. اختبارات التحقق من رقم الهاتف الليبي (Phone Validation Tests)
# =====================================================================

class TestPhoneValidation:
    """فحص خوارزمية التحقق من أرقام الهواتف المحمولة في ليبيا"""

    @pytest.mark.parametrize("valid_phone", [
        "0912345678",
        "0923456789",
        "0945556677",
        "0931234567",
        "0950001122",
        "+218912345678",
        "+218 92 345 6789",
        "00218912345678",
        "091-234-5678",
        "(091) 2345678",
    ])
    def test_valid_libyan_phones(self, valid_phone):
        assert is_valid_libyan_phone(valid_phone) is True, f"Failed for valid: {valid_phone}"

    @pytest.mark.parametrize("invalid_phone", [
        None,
        "",
        "   ",
        "12345678",           # قصير
        "091234567",          # 9 أرقام فقط
        "09123456789",        # 11 رقم
        "0812345678",         # لا يبدأ بـ 09
        "0712345678",
        "+201012345678",      # كود دولة أخرى
        "091234567a",         # أحرف
        "abcdefghij",
    ])
    def test_invalid_libyan_phones(self, invalid_phone):
        assert is_valid_libyan_phone(invalid_phone) is False, f"Should be invalid: {invalid_phone}"


# =====================================================================
# 2. اختبارات نظام الجلسات والتوقيع الرقمي (Session Token Tests)
# =====================================================================

class TestSessionTokens:
    """فحص توليد والتحقق من رموز الجلسات عبر HMAC-SHA256"""

    def test_nurse_token_generation_and_validation(self):
        token = session_token.make_token("nurse", 42, ttl=3600)
        assert isinstance(token, str) and "." in token

        # قراءة الرمز والتحقق منه
        subject = session_token.read_token(token, role="nurse")
        assert subject == 42

    def test_patient_token_generation_and_validation(self):
        token = session_token.make_token("patient", 105, ttl=1800)
        subject = session_token.read_token(token, role="patient")
        assert subject == 105

    def test_admin_token_with_secret_binding(self):
        admin_bind = "hash_of_super_secret_password_123"
        token = session_token.make_token("admin", "admin_user", ttl=3600, bind=admin_bind)

        # قراءة مع البصمة الصحيحة
        assert session_token.read_token(token, role="admin", bind=admin_bind) == "admin_user"

        # قراءة ببصمة مختلفة (تغيير كلمة السر) تفشل فوراً
        wrong_bind = "hash_of_new_password_456"
        assert session_token.read_token(token, role="admin", bind=wrong_bind) is None

    def test_role_mismatch_rejection(self):
        # رمز ممرض يُستخدم كرمز أدمن يجب رفضه
        nurse_token = session_token.make_token("nurse", 10, ttl=3600)
        assert session_token.read_token(nurse_token, role="admin") is None
        assert session_token.read_token(nurse_token, role="patient") is None

    def test_expired_token_rejection(self):
        # رمز منتهي الصلاحية (ttl سلبي)
        expired_token = session_token.make_token("nurse", 10, ttl=-10)
        assert session_token.read_token(expired_token, role="nurse") is None

    def test_tampered_payload_rejection(self):
        token = session_token.make_token("nurse", 10, ttl=3600)
        body, sig = token.rsplit(".", 1)

        # تزوير المحتوى (محاولة تغيير المعرف من 10 إلى 1)
        tampered_body = session_token._b64e(b'{"r":"nurse","s":1,"e":9999999999}')
        tampered_token = f"{tampered_body}.{sig}"
        assert session_token.read_token(tampered_token, role="nurse") is None

    def test_tampered_signature_rejection(self):
        token = session_token.make_token("nurse", 10, ttl=3600)
        body, sig = token.rsplit(".", 1)
        tampered_sig = sig[:-2] + ("AA" if sig[-2:] != "AA" else "BB")
        tampered_token = f"{body}.{tampered_sig}"
        assert session_token.read_token(tampered_token, role="nurse") is None

    @pytest.mark.parametrize("malformed", [
        None,
        "",
        "nodottoken",
        "a.b.c",
        "invalidbase64.invalidsig",
        "bm90anNvbg==.sig",
    ])
    def test_malformed_token_safety(self, malformed):
        # التأكد من عدم انهيار الدالة (Crash-proof) وإرجاعها None بأمان
        assert session_token.read_token(malformed, role="nurse") is None


# =====================================================================
# 3. اختبارات تصدير التقارير (Excel / CSV Export Tests)
# =====================================================================

class TestReportExports:
    """فحص سلامة توليد ملفات Excel و CSV باللغة العربية"""

    sample_requests = [
        {
            "id": 1,
            "created_at": "2026-11-09 10:30:00",
            "service_type": "علاج طبيعي",
            "patient_name": "عبدالسلام الترهوني",
            "patient_phone": "0912233445",
            "patient_gender": "ذكر",
            "patient_age": 45,
            "location_text": "سوق الجمعة، طريق السبعة",
            "min_price": 20,
            "max_price": 50,
            "status": "completed",
            "accepted_by": "سارة الورفلي",
            "service_desc": "جلسة تأهيلية بعد جراحة",
        },
        {
            "id": 2,
            "created_at": "2026-11-09 11:15:00",
            "service_type": "مداواة الجروح",
            "patient_name": "فاطمة القرقني",
            "patient_phone": "0921122334",
            "patient_gender": "أنثى",
            "patient_age": 60,
            "location_text": "حي الأندلس، خلف جامع الصقع",
            "min_price": 15,
            "max_price": 30,
            "status": "accepted",
            "accepted_by": "أحمد الزنتاني",
            "service_desc": "تغيير ضماد جرح سكري",
        },
        {
            "id": 3,
            "created_at": "2026-11-09 12:00:00",
            "service_type": "حقن عضل",
            "patient_name": "علي المصراتي",
            "patient_phone": "0945566778",
            "patient_gender": "ذكر",
            "patient_age": 30,
            "location_text": "قرجي، محطة الكهرباء",
            "min_price": 10,
            "max_price": 25,
            "status": "cancelled_by_admin",
            "accepted_by": None,
            "service_desc": "",
        }
    ]

    def test_export_excel_structure_and_types(self):
        excel_bytes = export_requests_excel(self.sample_requests)
        assert isinstance(excel_bytes, bytes)
        assert len(excel_bytes) > 0

        # قراءة ملف الإكسل الناتج والتأكد من توافق الأعمدة والقيم
        df = pd.read_excel(io.BytesIO(excel_bytes), sheet_name='سجل طلبات التمريض')
        assert len(df) == 3
        assert "رقم الطلب" in df.columns
        assert "نوع الخدمة" in df.columns
        assert "اسم المريض" in df.columns
        assert "حالة الطلب" in df.columns
        assert df.iloc[0]["اسم المريض"] == "عبدالسلام الترهوني"
        assert df.iloc[0]["حالة الطلب"] == "مكتمل بنجاح"
        assert df.iloc[1]["حالة الطلب"] == "جاري التنفيذ"
        assert df.iloc[2]["حالة الطلب"] == "ملغى من الإدارة"

    def test_export_excel_empty_list(self):
        excel_bytes = export_requests_excel([])
        assert isinstance(excel_bytes, bytes)
        df = pd.read_excel(io.BytesIO(excel_bytes))
        assert len(df) == 0

    def test_export_csv_with_utf8_bom(self):
        csv_bytes = export_requests_csv(self.sample_requests)
        assert isinstance(csv_bytes, bytes)
        # التأكد من وجود علامة BOM لـ UTF-8 لضمان الفتح النظيف في إكسل
        assert csv_bytes.startswith(b'\xef\xbb\xbf')
        text = csv_bytes.decode('utf-8-sig')
        assert "عبدالسلام الترهوني" in text
        assert "فاطمة القرقني" in text
        assert "ملغى من الإدارة" in text


# =====================================================================
# 4. اختبارات التشفير والمصادقة (Auth & Password Security Tests)
# =====================================================================

class TestSecurityAndHashing:
    """فحص تجزئة كلمات المرور الآمنة بدون تخزين نصوص صريحة"""

    def test_password_hash_generation_and_verification(self):
        raw_password = "Super-Strong-Medical-Password!#99"
        hashed = generate_password_hash(raw_password)

        assert hashed != raw_password
        assert not hashed.startswith("Super-Strong")
        assert check_password_hash(hashed, raw_password) is True
        assert check_password_hash(hashed, "wrong_guess_123") is False


# =====================================================================
# 5. اختبارات الإصلاحات الأمنية (Security Hardening Regression Tests)
# =====================================================================

class TestSessionKeyFailClosed:
    """H-1: لا مفتاح احتياطي — غياب [auth] secret_key يجب أن يوقف العمل."""

    def test_missing_secret_key_raises(self, monkeypatch):
        monkeypatch.setattr(st, "secrets", {})
        with pytest.raises(session_token.MissingSecretKey):
            session_token._secret()

    def test_blank_secret_key_raises(self, monkeypatch):
        monkeypatch.setattr(st, "secrets", {"auth": {"secret_key": "   "}})
        with pytest.raises(session_token.MissingSecretKey):
            session_token._secret()

    def test_no_fallback_to_database_url(self, monkeypatch):
        """رابط قاعدة البيانات وحده يجب ألا يكفي لتوقيع الرموز."""
        monkeypatch.setattr(
            st, "secrets",
            {"database": {"url": "postgresql://user:pw@host/db"}},
        )
        with pytest.raises(session_token.MissingSecretKey):
            session_token._secret()

    def test_present_secret_key_works(self, monkeypatch):
        monkeypatch.setattr(st, "secrets", {"auth": {"secret_key": "real-key-value"}})
        assert isinstance(session_token._secret(), bytes)


class TestHtmlEscaping:
    """H-2: قيم المستخدم يجب أن تُهرَّب قبل حقنها في قوالب HTML."""

    @pytest.mark.parametrize("payload", [
        '<script>alert(1)</script>',
        '<img src=x onerror="alert(1)">',
        '"><svg onload=alert(1)>',
        "<iframe src=javascript:alert(1)>",
    ])
    def test_escape_neutralizes_html(self, payload):
        escaped = html.escape(payload)
        assert "<" not in escaped and ">" not in escaped
        assert "&lt;" in escaped or "&gt;" in escaped

    def test_escape_preserves_arabic(self):
        assert html.escape("محمد عبدالله") == "محمد عبدالله"


class TestUploadPathGuard:
    """L-3: حذف الملفات يجب أن يبقى داخل مجلد الرفع فقط."""

    @pytest.mark.parametrize("path", [
        "uploads/licenses/abc.jpg",
        "uploads/licenses/sub/abc.jpg",
    ])
    def test_inside_upload_dir_allowed(self, path):
        assert database._is_inside_upload_dir(path) is True

    @pytest.mark.parametrize("path", [
        "uploads/licenses/../../../etc/passwd",
        "C:/Windows/System32/config/SAM",
        "/etc/passwd",
        "uploads/other/file.jpg",
        "secrets.toml",
    ])
    def test_outside_upload_dir_rejected(self, path):
        assert database._is_inside_upload_dir(path) is False


class TestBusinessConstants:
    """الأرقام السحرية صارت ثوابت مسمّاة."""

    def test_constants_exist_and_match_rules(self):
        assert database.COMMISSION_LYD == 10
        assert database.DEBT_LIMIT_LYD == 50
        assert database.MAX_PAYMENT_AMOUNT == 50
