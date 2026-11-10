-- ==========================================================
-- MedLink — ترحيل تقوية أمنية (001)
-- شغّله على قاعدة الإنتاج بعد أخذ نسخة احتياطية.
-- آمن للتشغيل المتكرر (IF NOT EXISTS).
-- ==========================================================

BEGIN;

-- ----------------------------------------------------------
-- 1. منع الممرض من امتلاك أكثر من مهمة نشطة واحدة
--    (H-3: الفحص في الكود لم يكن محكوماً بقفل، فنقرتان متزامنتان
--     تمنحان مهمتين. القيد هنا هو الضمان الحقيقي.)
-- ----------------------------------------------------------
CREATE UNIQUE INDEX IF NOT EXISTS uq_one_active_task_per_nurse
    ON requests (accepted_nurse_id)
    WHERE status = 'accepted' AND accepted_nurse_id IS NOT NULL;

-- ----------------------------------------------------------
-- 2. منع اعتماد نفس كرت المدار أكثر من مرة (M-1)
--    كروت مدار أحادية الاستخدام: لا يجوز أن يُعتمد الرقم مرتين
--    ولو من ممرضين مختلفين.
-- ----------------------------------------------------------
CREATE UNIQUE INDEX IF NOT EXISTS uq_payments_approved_card
    ON payments (card_number)
    WHERE status = 'approved';

-- ----------------------------------------------------------
-- 3. عمود الرصيد الدائن (M-2)
--    سابقاً كان GREATEST(debt - amount, 0) يحرق الدفع الزائد.
--    الآن يُحفظ الفائض رصيداً للممرض بدل أن يضيع.
-- ----------------------------------------------------------
ALTER TABLE nurses
    ADD COLUMN IF NOT EXISTS balance NUMERIC(10, 2) DEFAULT 0.00 NOT NULL;

-- ----------------------------------------------------------
-- 4. قيود سلامة على قيم الطلب (دفاع في العمق)
-- ----------------------------------------------------------
ALTER TABLE requests
    DROP CONSTRAINT IF EXISTS chk_requests_price_order;
ALTER TABLE requests
    ADD CONSTRAINT chk_requests_price_order CHECK (min_price <= max_price);

ALTER TABLE requests
    DROP CONSTRAINT IF EXISTS chk_requests_age;
ALTER TABLE requests
    ADD CONSTRAINT chk_requests_age CHECK (patient_age > 0 AND patient_age <= 120);

ALTER TABLE requests
    DROP CONSTRAINT IF EXISTS chk_requests_latlng;
ALTER TABLE requests
    ADD CONSTRAINT chk_requests_latlng CHECK (
        location_lat BETWEEN -90 AND 90 AND location_lng BETWEEN -180 AND 180
    );

-- ----------------------------------------------------------
-- 5. فهرس لتسريع استعلام المسافة بعد التحويل إلى geography
-- ----------------------------------------------------------
CREATE INDEX IF NOT EXISTS idx_requests_geo
    ON requests USING GIST (
        ST_SetSRID(ST_MakePoint(location_lng, location_lat), 4326)::geography
    );

COMMIT;

-- ==========================================================
-- تحقق بعد التشغيل (شغّله منفصلاً واقرأ النتيجة):
-- ==========================================================
-- SELECT indexname FROM pg_indexes
--  WHERE indexname IN ('uq_one_active_task_per_nurse','uq_payments_approved_card','idx_requests_geo');
--
-- SELECT column_name, data_type FROM information_schema.columns
--  WHERE table_name = 'nurses' AND column_name = 'balance';
--
-- كشف أي ممرض يملك فعلاً أكثر من مهمة نشطة (يجب أن يكون صفراً،
-- وإلا فالقيد أعلاه سيفشل وتحتاج تنظيف البيانات أولاً):
-- SELECT accepted_nurse_id, COUNT(*) FROM requests
--  WHERE status = 'accepted' AND accepted_nurse_id IS NOT NULL
--  GROUP BY accepted_nurse_id HAVING COUNT(*) > 1;
