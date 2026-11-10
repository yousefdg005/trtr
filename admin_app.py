import streamlit as st
import database
import pandas as pd
import os
import io
from datetime import datetime
from reports import export_requests_excel, export_requests_csv
import html
import session_token

_export_requests_excel = export_requests_excel
_export_requests_csv = export_requests_csv

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

# ── فشل-مغلق: لا عمل بدون مفتاح توقيع جلسات معرّف في الأسرار ──
session_token.ensure_configured()

# ══════════════════════════════════════════════
# حماية ومصادقة لوحة الإدارة
# ══════════════════════════════════════════════
import hmac

if "admin_authenticated" not in st.session_state:
    st.session_state["admin_authenticated"] = False

# فشل-مغلق: لا توجد كلمة سر افتراضية أبداً — بيانات الإدارة تأتي من الأسرار فقط.
# أي قيمة افتراضية في الكود المنشور تعني أن أي شخص يستطيع فتح اللوحة.
_admin_cfg = st.secrets.get("admin", {}) if "admin" in st.secrets else {}
ADMIN_USERNAME = _admin_cfg.get("username")
ADMIN_PASSWORD = _admin_cfg.get("password")

if not ADMIN_USERNAME or not ADMIN_PASSWORD:
    st.error(
        "🚨 لم يتم تكوين بيانات دخول الإدارة بعد.\n\n"
        "أضف القسم التالي في **Secrets** الخاص بتطبيق Streamlit Cloud ثم أعد تحميل الصفحة:\n\n"
        "```toml\n[admin]\nusername = \"اسم_الإدارة\"\npassword = \"كلمة_سر_قوية_جديدة\"\n```"
    )
    st.stop()

# بصمة بيانات الإدارة تدخل في توقيع رمز الجلسة: تغيير كلمة السر يُبطل كل الجلسات القديمة.
import hashlib
import session_token
_ADMIN_BIND = hashlib.sha256(f"{ADMIN_USERNAME}\x00{ADMIN_PASSWORD}".encode()).hexdigest()

# استعادة جلسة الإدارة بعد إعادة تحميل الصفحة
if not st.session_state["admin_authenticated"]:
    if session_token.load_session("admin", bind=_ADMIN_BIND) == "admin":
        st.session_state["admin_authenticated"] = True

if not st.session_state["admin_authenticated"]:
    st.markdown("""
    <div class="app-header-banner" style="max-width:520px;margin:3rem auto 1.5rem auto;">
      <div class="banner-title">🔐 تسجيل دخول الإدارة</div>
      <div class="banner-subtitle">منطقة محمية · مركز العمليات والتحكم المركزي لنظام رعايتي</div>
    </div>
    """, unsafe_allow_html=True)

    col_l, col_center, col_r = st.columns([1, 2, 1])
    with col_center:
        with st.form("admin_login_form"):
            user_in = st.text_input("اسم المستخدم", placeholder="admin")
            pass_in = st.text_input("كلمة المرور", type="password", placeholder="••••••••")
            login_btn = st.form_submit_button("🚀 تسجيل الدخول", type="primary", use_container_width=True)

            if login_btn:
                # compare_digest يرفع TypeError على النصوص غير ASCII (كلمة سر عربية)،
                # لذلك نقارن البايتات بعد الترميز.
                ok_user = hmac.compare_digest(str(user_in).encode("utf-8"), str(ADMIN_USERNAME).encode("utf-8"))
                ok_pass = hmac.compare_digest(str(pass_in).encode("utf-8"), str(ADMIN_PASSWORD).encode("utf-8"))
                if ok_user and ok_pass:
                    st.session_state["admin_authenticated"] = True
                    session_token.save_session("admin", "admin", session_token.ADMIN_TTL, bind=_ADMIN_BIND)
                    st.success("✅ تم التحقق بنجاح. جاري فتح لوحة التحكم...")
                    st.rerun()
                else:
                    st.error("⚠️ اسم المستخدم أو كلمة المرور غير صحيحة.")

        st.caption("🔒 يتم تكوين بيانات اعتماد المسؤول في ملف `.streamlit/secrets.toml`.")
    st.stop()

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

st.sidebar.markdown("---")
if st.sidebar.button("🚪 تسجيل خروج الإدارة", use_container_width=True):
    st.session_state["admin_authenticated"] = False
    session_token.clear_session()
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
completed_req_count = sum(1 for r in all_requests if r['status'] == 'completed')
active_nurses = sum(1 for n in all_nurses if n['status'] == 'approved')

m1, m2, m3, m4, m5 = st.columns(5)
m1.metric("🩺 طلبات معلقة", pending_req_count)
m2.metric("🚑 مهام نشطة", accepted_req_count)
m3.metric("✨ مهام مكتملة", completed_req_count)
m4.metric("👨‍⚕️ ممرضون نشطون", active_nurses)
m5.metric("⏳ طلبات انضمام", len(pending_nurses))

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
    st.subheader("📋 سجل طلبات وعمليات التمريض")

    # 1. شريط الأدوات: سحب السجل كملف Excel أو CSV
    if len(all_requests) > 0:
        today_str = datetime.now().strftime("%Y%m%d_%H%M")
        col_down1, col_down2, _spacer = st.columns([2, 1.5, 3])
        with col_down1:
            excel_bytes = _export_requests_excel(all_requests)
            st.download_button(
                label="📥 سحب السجل Excel (.xlsx)",
                data=excel_bytes,
                file_name=f"medlink_requests_{today_str}.xlsx",
                mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                use_container_width=True,
                type="primary"
            )
        with col_down2:
            csv_bytes = _export_requests_csv(all_requests)
            st.download_button(
                label="📄 سحب السجل CSV (UTF-8)",
                data=csv_bytes,
                file_name=f"medlink_requests_{today_str}.csv",
                mime="text/csv",
                use_container_width=True
            )

    st.markdown("---")

    # 2. العمليات النشطة الجارية حالياً (مع إمكانية الإلغاء أو الحذف النهائي)
    active_requests = [r for r in all_requests if r['status'] == 'accepted']
    if len(active_requests) > 0:
        st.markdown(f"#### 🚨 العمليات النشطة قيد التنفيذ الميداني ({len(active_requests)})")
        st.caption("العمليات المقبولة حالياً من الممرضين وفي طريقهم للمرضى. يمكنك إلغاؤها أو حذفها نهائياً مع استرداد العمولة للممرض.")

        for act in active_requests:
            st.markdown(f"""
            <div class="custom-card" style="border-right-color:#0284c7 !important; background:rgba(2,132,199,0.04);">
              <div style="display:flex;justify-content:space-between;align-items:center;flex-wrap:wrap;gap:8px;">
                <div>
                  <strong style="font-size:1.1rem;color:#0e7490;">🏥 {html.escape(str(act['service_type']))} (طلب #{html.escape(str(act['id']))})</strong>
                  <span class="status-badge badge-green" style="margin-right:8px;">✅ جاري التنفيذ</span>
                </div>
                <div style="font-size:1rem;font-weight:800;color:#059669;">
                  💰 الميزانية: {html.escape(str(act['min_price']))} – {html.escape(str(act['max_price']))} د.ل
                </div>
              </div>
              <div style="margin-top:0.4rem;font-size:0.95rem;">
                👤 <strong>المريض:</strong> {html.escape(str(act['patient_name']))} (📞 {html.escape(str(act['patient_phone']))}) &nbsp;|&nbsp;
                👨‍⚕️ <strong>الممرض المستلم:</strong> {html.escape(str(act['accepted_by'] or 'معتمد'))}
              </div>
              <div style="font-size:0.95rem;">
                📍 <strong>العنوان:</strong> {html.escape(str(act['location_text']))}
              </div>
            </div>
            """, unsafe_allow_html=True)

            col_c1, col_c2 = st.columns(2)
            with col_c1:
                with st.popover(f"🛑 إلغاء العملية النشطة #{act['id']}", use_container_width=True):
                    st.warning(f"هل أنت متأكد من إلغاء العملية النشطة للمريض **{act['patient_name']}** والممرض **{act['accepted_by']}**؟\n\nسيتم استرداد العمولة (10 د.ل) لحساب الممرض فوراً وإشعار المريض بالإلغاء.")
                    if st.button("تأكيد إلغاء العملية", key=f"cancel_act_{act['id']}", type="primary", use_container_width=True):
                        ok, msg = database.cancel_request_by_admin(act['id'])
                        if ok:
                            st.success(msg)
                            st.rerun()
                        else:
                            st.error(msg)
            with col_c2:
                with st.popover(f"🗑️ حذف العملية النشطة #{act['id']} نهائياً", use_container_width=True):
                    st.error(f"⚠️ حذف العملية النشطة #{act['id']} نهائياً سيمسح السجل بالكامل من قاعدة البيانات فوراً مع استرداد عمولة الممرض.")
                    if st.button("تأكيد الحذف النهائي", key=f"del_act_{act['id']}", type="primary", use_container_width=True):
                        ok, msg = database.delete_request(act['id'])
                        if ok:
                            st.success(msg)
                            st.rerun()
                        else:
                            st.error(msg)

            st.markdown("<div style='margin-bottom:0.75rem;'></div>", unsafe_allow_html=True)

        st.markdown("---")

    # 3. عرض جدول السجل بالكامل
    st.markdown("#### 📊 جدول السجل الكامل للطلبات")
    if len(all_requests) == 0:
        st.info("لا توجد طلبات مسجلة حتى الآن في قاعدة البيانات.")
    else:
        df = pd.DataFrame(all_requests)
        df['الميزانية'] = df['min_price'].astype(str) + " – " + df['max_price'].astype(str) + " د.ل"
        display_df = df[['id', 'service_type', 'patient_name', 'patient_phone', 'patient_gender',
                          'location_text', 'الميزانية', 'status', 'accepted_by']].copy()
        display_df.columns = ["#", "الخدمة", "المريض", "الهاتف", "الجنس", "العنوان", "الميزانية", "الحالة", "الممرض"]
        display_df['الحالة'] = display_df['الحالة'].replace({
            'pending':              '⏳ معلق',
            'accepted':             '✅ جاري التنفيذ',
            'completed':            '✨ مكتمل بنجاح',
            'cancelled_by_patient': '🔴 مُلغى من المريض',
            'cancelled_by_nurse':   '🟠 مُلغى من الممرض',
            'cancelled_by_admin':   '🛑 مُلغى من الإدارة',
        })
        st.dataframe(display_df, use_container_width=True, hide_index=True)

        # 4. أدوات إدارة وحذف السجل
        st.markdown("---")
        with st.expander("🗑️ أدوات تنظيف وحذف سجل العمليات"):
            st.markdown("##### 1. حذف طلب محدد برقم المعرف (#ID):")
            col_id, col_btn_del = st.columns([3, 1])
            with col_id:
                req_ids = [r['id'] for r in all_requests]
                selected_req_id = st.selectbox("اختر رقم الطلب المراد حذفه نهائياً", req_ids, key="sel_del_req_id")
            with col_btn_del:
                st.markdown("<div style='margin-top:1.8rem;'></div>", unsafe_allow_html=True)
                with st.popover("🗑️ حذف هذا الطلب", use_container_width=True):
                    st.warning(f"هل أنت متأكد من حذف الطلب رقم #{selected_req_id} نهائياً؟")
                    if st.button("تأكيد حذف الطلب", key="confirm_del_single_req", type="primary", use_container_width=True):
                        ok, msg = database.delete_request(selected_req_id)
                        if ok:
                            st.success(msg)
                            st.rerun()
                        else:
                            st.error(msg)

            st.markdown("---")
            col_clean1, col_clean2 = st.columns(2)
            with col_clean1:
                st.markdown("##### 2. تنظيف الطلبات المكتملة والملغاة فقط:")
                st.caption("يحذف كافة الطلبات المنتهية ويُبقي الطلبات المعلقة والنشطة كما هي.")
                with st.popover("🧹 تنظيف السجل من المنتهي", use_container_width=True):
                    st.warning("سيتم مسح كافة الطلبات المكتملة والملغاة نهائياً. هل تود المتابعة؟")
                    if st.button("تأكيد تنظيف المنتهي", key="clean_finished_log", type="primary", use_container_width=True):
                        ok, msg, cnt = database.clear_requests_log('finished_only')
                        if ok:
                            st.success(msg)
                            st.rerun()
                        else:
                            st.error(msg)

            with col_clean2:
                st.markdown("##### 3. تفريغ وحذف كامل سجل العمليات:")
                st.caption("يحذف جميع الطلبات بلا استثناء من قاعدة البيانات مع استرداد عمولة أي مهام جارية.")
                with st.popover("⚠️ تفريغ كامل السجل نهائياً", use_container_width=True):
                    st.error("🚨 تحذير: هذا الإجراء سيفرغ جدول العمليات بالكامل ولا يمكن استرجاع السجل بعد الحذف!")
                    if st.button("🔥 تأكيد تفريغ كامل السجل", key="clear_all_log", type="primary", use_container_width=True):
                        ok, msg, cnt = database.clear_requests_log('all')
                        if ok:
                            st.success(msg)
                            st.rerun()
                        else:
                            st.error(msg)

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
                  <strong style="font-size:1.05rem;">👤 {html.escape(str(n['name']))}</strong>
                  <span style="opacity:0.75;font-size:0.85rem;">(@{html.escape(str(n['username']))})</span>
                  <span class="status-badge badge-orange" style="margin-right:8px;">⏳ قيد المراجعة</span>
                </div>
                <div>
                  📞 {html.escape(str(n['phone']))} &nbsp;|&nbsp; 🏥 {html.escape(str(n['specialty']))} &nbsp;|&nbsp;
                  {"👨" if n['gender'] == "ذكر" else "👩"} {html.escape(str(n['gender']))}
                </div>
              </div>
              <div style="margin-top:0.4rem;font-size:0.9rem;opacity:0.9;">
                📝 <strong>معلومات المزاولة:</strong> {html.escape(str(notes))}
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

            col_a, col_r, col_d = st.columns([1, 1, 1])
            with col_a:
                if st.button("✅ قبول وتفعيل العضوية", key=f"accept_{n['id']}", type="primary", use_container_width=True):
                    database.update_nurse_status(n['id'], 'approved')
                    st.rerun()
            with col_r:
                if st.button("❌ رفض الطلب", key=f"reject_{n['id']}", use_container_width=True):
                    database.update_nurse_status(n['id'], 'rejected')
                    st.rerun()
            with col_d:
                with st.popover("🗑️ حذف نهائي", use_container_width=True):
                    st.caption(f"حذف طلب {n['name']} نهائياً مع وثائقه")
                    if st.button("🔥 تأكيد الحذف", key=f"del_pending_{n['id']}", type="primary", use_container_width=True):
                        ok, msg = database.delete_nurse(n['id'])
                        if ok:
                            st.success(msg)
                            st.rerun()
                        else:
                            st.error(msg)

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
                  <strong style="font-size:1.05rem;">{html.escape(str(n['name']))}</strong>
                  <span style="opacity:0.75;font-size:0.85rem;">(@{html.escape(str(n['username']))})</span>
                  {badge_html}
                </div>
                <div>
                  📞 {html.escape(str(n['phone']))} &nbsp;|&nbsp; الديون المستحقة: <strong>{html.escape(str(n['debt']))} د.ل</strong>
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
                elif n['status'] == 'rejected':
                    if st.button("✅ تفعيل الحساب", key=f"approve_{n['id']}", type="primary", use_container_width=True):
                        database.update_nurse_status(n['id'], 'approved')
                        st.rerun()
            with col_b2:
                with st.popover("🗑️ حذف الحساب نهائياً", use_container_width=True):
                    st.warning(f"⚠️ هل أنت متأكد من حذف حساب الممرض **{n['name']}** نهائياً؟\n\nلا يمكن التراجع عن هذا الإجراء وسيتم مسح كافة سجلاته ووثائقه.")
                    if st.button("🔥 تأكيد الحذف النهائي", key=f"del_nurse_{n['id']}", type="primary", use_container_width=True):
                        ok, msg = database.delete_nurse(n['id'])
                        if ok:
                            st.success(msg)
                            st.rerun()
                        else:
                            st.error(msg)

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
                  💳 <strong>الممرض:</strong> {html.escape(str(p['nurse_name']))}
                  <span style="opacity:0.8;font-size:0.85rem;">(📞 {html.escape(str(p['phone']))})</span>
                </div>
                <div>
                  القيمة: <strong style="font-size:1.1rem;color:#10b981;">{html.escape(str(p['amount']))} د.ل</strong>
                </div>
              </div>
              <div style="margin-top:0.4rem;font-size:1rem;font-weight:700;letter-spacing:1px;">
                🔢 رقم الكرت: {html.escape(str(p['card_number']))}
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
