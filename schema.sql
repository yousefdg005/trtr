-- ==========================================================
-- MedLink (نظام رعايتي للتمريض المنزلي) - Database Schema
-- PostgreSQL + PostGIS Extension
-- ==========================================================

-- 1. تفعيل ملحق العمليات الجغرافية وحساب المسافات
CREATE EXTENSION IF NOT EXISTS postgis;

-- 2. جدول إعدادات وحالة النظام العامة
CREATE TABLE IF NOT EXISTS system_settings (
    key VARCHAR(50) PRIMARY KEY,
    value VARCHAR(255) NOT NULL
);

-- إدراج القيمة الافتراضية لتشغيل المنظومة تلقائياً
INSERT INTO system_settings (key, value)
VALUES ('is_active', 'true')
ON CONFLICT (key) DO NOTHING;

-- 3. جدول الممرضين ومقدمي الرعاية الطبية
CREATE TABLE IF NOT EXISTS nurses (
    id SERIAL PRIMARY KEY,
    username VARCHAR(100) UNIQUE NOT NULL,
    password VARCHAR(255) NOT NULL,
    name VARCHAR(150) NOT NULL,
    phone VARCHAR(20) NOT NULL,
    gender VARCHAR(10) NOT NULL,              -- 'ذكر' أو 'أنثى'
    specialty VARCHAR(100) NOT NULL,           -- 'علاج طبيعي', 'تمريض عام', 'إسعاف وطوارئ'
    proof_info TEXT,                           -- مسار صورة رخصة المزاولة والملاحظات
    debt NUMERIC(10, 2) DEFAULT 0.00 NOT NULL, -- رصيد الديون المستحقة للمنظومة
    status VARCHAR(20) DEFAULT 'pending' NOT NULL, 
    -- الحالات: 'pending' (قيد المراجعة), 'approved' (معتمد نشط), 
    -- 'debt_blocked' (موقوف بسبب الديون), 'blocked' (محظور إدارياً), 'rejected' (مرفوض)
    created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP
);

-- 4. جدول طلبات التمريض والرعاية المنزلية من المرضى
CREATE TABLE IF NOT EXISTS requests (
    id SERIAL PRIMARY KEY,
    service_type VARCHAR(100) NOT NULL,
    patient_name VARCHAR(150) NOT NULL,
    patient_phone VARCHAR(20) NOT NULL,
    patient_gender VARCHAR(10) NOT NULL,       -- 'ذكر' أو 'أنثى'
    patient_age INT NOT NULL,
    service_desc TEXT,
    location_text TEXT NOT NULL,
    location_lat DOUBLE PRECISION NOT NULL,
    location_lng DOUBLE PRECISION NOT NULL,
    min_price NUMERIC(10, 2) NOT NULL,
    max_price NUMERIC(10, 2) NOT NULL,
    status VARCHAR(30) DEFAULT 'pending' NOT NULL,
    -- الحالات: 'pending' (معلق), 'accepted' (مقبول جاري التنفيذ), 
    -- 'completed' (مكتمل بنجاح), 'cancelled_by_patient' (ملغى من المريض), 'cancelled_by_nurse' (ملغى من الممرض)
    accepted_nurse_id INT REFERENCES nurses(id) ON DELETE SET NULL,
    created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP
);

-- 5. جدول كروت الشحن وسداد الديون (كروت مدار)
CREATE TABLE IF NOT EXISTS payments (
    id SERIAL PRIMARY KEY,
    nurse_id INT NOT NULL REFERENCES nurses(id) ON DELETE CASCADE,
    card_number VARCHAR(30) NOT NULL,
    amount NUMERIC(10, 2) NOT NULL,
    status VARCHAR(20) DEFAULT 'pending' NOT NULL, 
    -- الحالات: 'pending' (قيد التدقيق), 'approved' (تم الخصم), 'rejected' (مرفوض)
    created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP
);

-- ==========================================================
-- فهارس تحسين الأداء والسرعة (Performance Indexes)
-- ==========================================================

-- تسريع جلب الطلبات القريبة والمعلقة
CREATE INDEX IF NOT EXISTS idx_requests_status_gender ON requests(status, patient_gender);

-- تسريع فحص المهمة النشطة للممرض
CREATE INDEX IF NOT EXISTS idx_requests_accepted_nurse ON requests(accepted_nurse_id, status);

-- تسريع مراجعة كروت الشحن المعلقة
CREATE INDEX IF NOT EXISTS idx_payments_status ON payments(status);

-- تسريع استعلامات الممرضين حسب الحالة
CREATE INDEX IF NOT EXISTS idx_nurses_status ON nurses(status);
