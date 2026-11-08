import streamlit as st
import database
import pandas as pd
import os

st.set_page_config(
    page_title="نظام رعايتي - لوحة الإدارة",
    page_icon="⚙️",
    layout="wide",
    initial_sidebar_state="expanded"
)

with open('style.css') as f:
    st.markdown(f'<style>{f.read()}</style>', unsafe_allow_html=True)

# ── تحسين تخطيط الإدارة ──
st.markdown("""
<style>
.main .block-container { max-width: 1100px !important; }
</style>
""", unsafe_allow_html=True)

# ══════════════════════════════════════════════
# الشريط الجانبي - تحكم النظام
# ══════════════════════════════════════════════
st.sidebar.markdown("""
<div style="text-align:center;padding:1rem 0 0.5rem;direction:rtl;">
  <div style="font-size:2.2rem;margin-bottom:0.2rem;">⚙️</div>
  <div style="font-size:1.2rem;font-weight:800;">تحكم المنظومة</div>
  <div style="font-size:0.85rem;opacity:0.8;">لوحة الإدارة · نظام رعايتي</div>
</div>
""", unsafe_allow_html=True)

is_system_active = database.get_system_status()

st.sidebar.markdown("---")

if is_system_active:
    st.sidebar.success("🟢 المنظومة تعمل بشكل طبيعي ومتاحة للجميع")
else:
    st.sidebar.error("🔴 المنظومة متوقفة حالياً عن استقبال الطلبات")

st.sidebar.info("عند إيقاف المنظومة، لن يتمكن المرضى من طلب الخدمة ولن يتمكن الممرضون من الدخول.")

new_status = st.sidebar.toggle("تشغيل المنظومة (متاحة للجميع)", value=is_system_active)
if new_status != is_system_active:
    database.set_system_status(new_status)
    st.rerun()

st.sidebar.markdown("---")
if st.sidebar.button("🔄 تحديث البيانات الآن", use_container_width=True):
    st.rerun()

# ══════════════════════════════════════════════
# الهيدر الرئيسي
# ══════════════════════════════════════════════
st.markdown("""
<div class="app-header-banner">
  <div class="banner-title">⚙️ لوحة الإدارة ☽⭐</div>
  <div class="banner-subtitle">نظام رعايتي للتمريض المنزلي · مركز العمليات والتحكم المركزي</div>
</div>
""", unsafe_allow_html=True)

if not is_system_active:
    st.error("🚨 تنبيه إداري: المنظومة متوقفة بالكامل الآن. لا يمكن للمرضى أو الممرضين استخدام المنصة.")

# ══════════════════════════════════════════════
# الإحصاءات السريعة (Metrics)
# ══════════════════════════════════════════════
all_requests = database.get_all_requests()
all_nurses = database.get_all_nurses()
pending_nurses = database.get_pending_nurses()
pending_payments = database.get_pending_payments()

pending_req_count = sum(1 for r in all_requests if r['status'] == 'pending')
accepted_req_count = sum(1 for r in all_requests if r['status'] == 'accepted')
active_nurses = sum(1 for n in all_nurses if n['status'] == 'approved')

m1, m2, m3, m4 = st.columns(4)
m1.metric("🩺 طلبات معلقة", pending_req_count)
m2.metric("✅ مهام نشطة", accepted_req_count)
m3.metric("👨‍⚕️ ممرضون نشطون", active_nurses)
m4.metric("⏳ طلبات انضمام", len(pending_nurses))

st.markdown("---")

# ══════════════════════════════════════════════
# التبويبات (Tabs)
# ══════════════════════════════════════════════
tab1, tab2, tab3, tab4 = st.tabs([
    "🩺 سجل العمليات",
    "👨‍⚕️ طلبات الانضمام",
    "🛡️ الممرضون والديون",
    "💳 كروت الشحن والمدفوعات"
])

# ── تبويب 1: العمليات ──
with tab1:
    st.subheader("📋 سجل طلبات التمريض")

    if len(all_requests) == 0:
        st.info("لا توجد طلبات مسجلة حتى الآن في قاعدة البيانات.")
    else:
        df = pd.DataFrame(all_requests)
        df['الميزانية'] = df['min_price'].astype(str) + " – " + df['max_price'].astype(str) + " د.ل"
        display_df = df[['id', 'service_type', 'patient_name', 'patient_gender',
                          'location_text', 'الميزانية', 'status', 'accepted_by']].copy()
        display_df.columns = ["#", "الخدمة", "المريض", "الجنس", "العنوان", "الميزانية", "الحالة", "الممرض"]
        display_df['الحالة'] = display_df['الحالة'].replace({
            'pending':              '⏳ معلق',
            'accepted':             '✅ جاري التنفيذ',
            'cancelled_by_patient': '🔴 مُلغى من المريض',
            'cancelled_by_nurse':   '🟠 مُلغى من الممرض',
        })
        st.dataframe(display_df, use_container_width=True, hide_index=True)

# ── تبويب 2: طلبات الانضمام مع عرض صورة الوثيقة من مسار الملف (Task 2) ──
with tab2:
    st.subheader("👨‍⚕️ طلبات العضوية المعلقة للمراجعة والتدقيق")

    if len(pending_nurses) == 0:
        st.success("✅ لا توجد طلبات انضمام معلقة حالياً.")
    else:
        for n in pending_nurses:
            proof = n['proof_info'] or ""
            file_img_path = None
            base64_data = None
            notes = proof

            # دعم المسار الجديد للملف على القرص (Task 2) مع دعم التوافق مع الصور القديمة base64 إن وُجدت
            if proof.startswith("FILE_PATH:"):
                parts = proof.replace("FILE_PATH:", "").split("###", 1)
                file_img_path = parts[0]
                notes = parts[1] if len(parts) > 1 else ""
            elif proof.startswith("DATA_IMAGE:"):
                parts = proof.replace("DATA_IMAGE:", "").split("###", 1)
                base64_data = "data:" + parts[0]
                notes = parts[1] if len(parts) > 1 else ""

            st.markdown(f"""
            <div class="custom-card">
              <div style="display:flex;justify-content:space-between;align-items:center;flex-wrap:wrap;gap:8px;">
                <div>
                  <strong style="font-size:1.05rem;">👤 {n['name']}</strong>
                  <span style="opacity:0.75;font-size:0.85rem;">(@{n['username']})</span>
                  <span class="status-badge badge-orange" style="margin-right:8px;">⏳ قيد المراجعة</span>
                </div>
                <div>
                  📞 {n['phone']} &nbsp;|&nbsp; 🏥 {n['specialty']} &nbsp;|&nbsp;
                  {"👨" if n['gender'] == "ذكر" else "👩"} {n['gender']}
                </div>
              </div>
              <div style="margin-top:0.4rem;font-size:0.9rem;opacity:0.9;">
                📝 <strong>معلومات المزاولة:</strong> {notes}
              </div>
            </div>
            """, unsafe_allow_html=True)

            # Task 2: عرض صورة وثيقة المزاولة من الملف المحلي على القرص
            if file_img_path and os.path.exists(file_img_path):
                with st.expander("🔍 اضغط هنا لمعاينة صورة وثيقة / ترخيص المزاولة"):
                    st.image(file_img_path, caption=f"وثيقة مزاولة المهنة للممرض: {n['name']}", use_container_width=True)
            elif base64_data:
                with st.expander("🔍 اضغط هنا لمعاينة صورة وثيقة / ترخيص المزاولة"):
                    st.image(base64_data, caption=f"وثيقة مزاولة المهنة للممرض: {n['name']}", use_container_width=True)

            col_a, col_r = st.columns(2)
            with col_a:
                if st.button("✅ قبول وتفعيل العضوية", key=f"accept_{n['id']}", type="primary", use_container_width=True):
                    database.update_nurse_status(n['id'], 'approved')
                    st.rerun()
            with col_r:
                if st.button("❌ رفض الطلب", key=f"reject_{n['id']}", use_container_width=True):
                    database.update_nurse_status(n['id'], 'rejected')
                    st.rerun()

            st.markdown("<div style='margin-bottom:0.75rem;'></div>", unsafe_allow_html=True)

# ── تبويب 3: إدارة الممرضين والديون ──
with tab3:
    st.subheader("🛡️ قائمة الممرضين المسجلين")

    all_nurses_list = database.get_all_nurses()
    if len(all_nurses_list) == 0:
        st.info("لا يوجد ممرضون مسجلون.")
    else:
        for n in all_nurses_list:
            if n['status'] == 'pending':
                continue

            # شارات الحالة
            if n['status'] == 'approved':
                badge_html = "<span class='status-badge badge-green'>🟢 نشط</span>"
            elif n['status'] == 'debt_blocked':
                badge_html = "<span class='status-badge badge-orange'>🛑 موقوف (ديون)</span>"
            elif n['status'] == 'blocked':
                badge_html = "<span class='status-badge badge-red'>🚫 محظور إدارياً</span>"
            else:
                badge_html = "<span class='status-badge badge-gray'>⚫ مرفوض</span>"

            st.markdown(f"""
            <div class="custom-card">
              <div style="display:flex;justify-content:space-between;align-items:center;flex-wrap:wrap;gap:8px;">
                <div>
                  <strong style="font-size:1.05rem;">{n['name']}</strong>
                  <span style="opacity:0.75;font-size:0.85rem;">(@{n['username']})</span>
                  {badge_html}
                </div>
                <div>
                  📞 {n['phone']} &nbsp;|&nbsp; الديون المستحقة: <strong>{n['debt']} د.ل</strong>
                </div>
              </div>
            </div>
            """, unsafe_allow_html=True)

            col_b1, col_b2 = st.columns(2)
            with col_b1:
                if n['status'] in ['approved', 'debt_blocked']:
                    if st.button("🚫 حظر الممرض", key=f"block_{n['id']}", use_container_width=True):
                        database.update_nurse_status(n['id'], 'blocked')
                        st.rerun()
                elif n['status'] == 'blocked':
                    if st.button("✅ رفع الحظر", key=f"unblock_{n['id']}", type="primary", use_container_width=True):
                        new_st = 'debt_blocked' if n['debt'] >= 50 else 'approved'
                        database.update_nurse_status(n['id'], new_st)
                        st.rerun()

            st.markdown("<div style='margin-bottom:0.75rem;'></div>", unsafe_allow_html=True)

# ── تبويب 4: المدفوعات (Task 4: nurse_id) ──
with tab4:
    st.subheader("💳 كروت شحن مدار قيد المراجعة")

    pending_payments = database.get_pending_payments()

    if len(pending_payments) == 0:
        st.success("✅ لا توجد كروت شحن معلقة للمراجعة حالياً.")
    else:
        for p in pending_payments:
            st.markdown(f"""
            <div class="custom-card" style="border-right-color:#f59e0b !important;">
              <div style="display:flex;justify-content:space-between;align-items:center;flex-wrap:wrap;gap:8px;">
                <div>
                  💳 <strong>الممرض:</strong> {p['nurse_name']}
                  <span style="opacity:0.8;font-size:0.85rem;">(📞 {p['phone']})</span>
                </div>
                <div>
                  القيمة: <strong style="font-size:1.1rem;color:#10b981;">{p['amount']} د.ل</strong>
                </div>
              </div>
              <div style="margin-top:0.4rem;font-size:1rem;font-weight:700;letter-spacing:1px;">
                🔢 رقم الكرت: {p['card_number']}
              </div>
            </div>
            """, unsafe_allow_html=True)

            col_ok, col_bad = st.columns(2)
            with col_ok:
                if st.button("✅ كرت صحيح (خصم الدين فوراً)", key=f"pay_ok_{p['id']}", type="primary", use_container_width=True):
                    database.review_payment(p['id'], p['nurse_id'], p['amount'], 'approved')
                    st.rerun()
            with col_bad:
                if st.button("❌ كرت غير صحيح / مستعمل", key=f"pay_bad_{p['id']}", use_container_width=True):
                    database.review_payment(p['id'], p['nurse_id'], p['amount'], 'rejected')
                    st.rerun()

            st.markdown("<div style='margin-bottom:0.75rem;'></div>", unsafe_allow_html=True)
