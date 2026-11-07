import streamlit as st
import database
import pandas as pd

st.set_page_config(
    page_title="نظام رعايتي - لوحة الإدارة",
    page_icon="⚙️",
    layout="wide"
)

with open('style.css') as f:
    st.markdown(f'<style>{f.read()}</style>', unsafe_allow_html=True)

# ── CSS إضافي خاص بالإدارة ──
st.markdown("""
<style>
/* لوحة الإدارة: تخطيط أعرض */
.main .block-container { max-width: 1100px !important; }

/* بطاقات الإحصاء */
[data-testid="stMetricValue"] {
  font-size: 2.2rem !important;
  font-weight: 900 !important;
}

/* الشريط الجانبي للأدمن */
[data-testid="stSidebar"] .stToggle span {
  color: #e0f2f1 !important;
}
</style>
""", unsafe_allow_html=True)

# ══════════════════════════════════════════════
# الشريط الجانبي - تحكم النظام
# ══════════════════════════════════════════════
st.sidebar.markdown("""
<div style="text-align:center;padding:1rem 0 0.5rem;direction:rtl;">
  <div style="font-size:2rem;">⚙️</div>
  <div style="font-size:1.1rem;font-weight:800;color:#e0f2f1;">تحكم المنظومة</div>
  <div style="font-size:0.8rem;color:#80cbc4;">لوحة الإدارة · نظام رعايتي</div>
</div>
""", unsafe_allow_html=True)

is_system_active = database.get_system_status()

st.sidebar.markdown("---")

if is_system_active:
    st.sidebar.success("🟢 المنظومة تعمل")
else:
    st.sidebar.error("🔴 المنظومة متوقفة")

st.sidebar.info("عند إيقاف المنظومة، لن يتمكن المرضى من طلب الخدمة ولن يتمكن الممرضون من الدخول.")

new_status = st.sidebar.toggle("تشغيل المنظومة", value=is_system_active)
if new_status != is_system_active:
    database.set_system_status(new_status)
    st.rerun()

st.sidebar.markdown("---")
if st.sidebar.button("🔄 تحديث البيانات", use_container_width=True):
    st.rerun()

# ══════════════════════════════════════════════
# الهيدر الرئيسي
# ══════════════════════════════════════════════
st.markdown("""
<div class="app-header-banner">
  <h1>⚙️ لوحة الإدارة ☽⭐</h1>
  <p>نظام رعايتي · مركز العمليات والإشراف</p>
</div>
""", unsafe_allow_html=True)

if not is_system_active:
    st.error("🚨 تنبيه: المنظومة الآن متوقفة بالكامل. المرضى والممرضون لا يستطيعون الدخول.")

# ══════════════════════════════════════════════
# الإحصاءات السريعة
# ══════════════════════════════════════════════
all_requests = database.get_all_requests()
all_nurses   = database.get_all_nurses()
pending_nurses   = database.get_pending_nurses()
pending_payments = database.get_pending_payments()

pending_req_count  = sum(1 for r in all_requests if r['status'] == 'pending')
accepted_req_count = sum(1 for r in all_requests if r['status'] == 'accepted')
active_nurses      = sum(1 for n in all_nurses if n['status'] == 'approved')

m1, m2, m3, m4 = st.columns(4)
m1.metric("🩺 طلبات معلقة",   pending_req_count)
m2.metric("✅ طلبات نشطة",    accepted_req_count)
m3.metric("👨‍⚕️ ممرضون نشطون", active_nurses)
m4.metric("⏳ طلبات انضمام",  len(pending_nurses))

st.markdown("---")

# ══════════════════════════════════════════════
# التبويبات
# ══════════════════════════════════════════════
tab1, tab2, tab3, tab4 = st.tabs([
    "🩺 العمليات",
    "👨‍⚕️ طلبات العضوية",
    "🛡️ الممرضون والحظر",
    "💳 الخزينة والمدفوعات"
])

# ── تبويب 1: العمليات ──
with tab1:
    st.subheader("📋 سجل الطلبات الكاملة")

    if len(all_requests) == 0:
        st.info("لا توجد عمليات مسجلة حتى الآن.")
    else:
        df = pd.DataFrame(all_requests)
        df['الميزانية'] = df['min_price'].astype(str) + " – " + df['max_price'].astype(str) + " د.ل"
        display_df = df[['id', 'service_type', 'patient_name', 'patient_gender',
                          'location_text', 'الميزانية', 'status', 'accepted_by']].copy()
        display_df.columns = ["#", "الخدمة", "المريض", "الجنس", "العنوان", "الميزانية", "الحالة", "الممرض"]
        display_df['الحالة'] = display_df['الحالة'].replace({
            'pending':              '⏳ معلق',
            'accepted':             '✅ مقبول',
            'cancelled_by_patient': '🔴 مُلغى من المريض',
            'cancelled_by_nurse':   '🟠 مُلغى من الممرض',
        })
        st.dataframe(display_df, use_container_width=True, hide_index=True)

# ── تبويب 2: طلبات العضوية ──
with tab2:
    st.subheader("👨‍⚕️ طلبات الانضمام المعلقة")

    if len(pending_nurses) == 0:
        st.success("✅ لا توجد طلبات انضمام معلقة حالياً.")
    else:
        for n in pending_nurses:
            with st.container():
                st.markdown(f"""
                <div style="background:#ffffff;border:1px solid #b2dfdb;border-right:4px solid #2980b9;
                            border-radius:10px;padding:0.9rem 1.1rem;margin-bottom:0.5rem;direction:rtl;">
                  <div style="font-size:1rem;font-weight:800;color:#1a2e35;">
                    👤 {n['name']}
                    <span style="font-size:0.82rem;color:#5a7a80;font-weight:600;">
                      (@{n['username']})
                    </span>
                  </div>
                  <div style="font-size:0.88rem;color:#1a2e35;margin-top:0.3rem;">
                    📞 {n['phone']} &nbsp;|&nbsp; 🏥 {n['specialty']} &nbsp;|&nbsp;
                    {'👨' if n['gender'] == 'ذكر' else '👩'} {n['gender']}
                  </div>
                  <div style="font-size:0.82rem;color:#5a7a80;margin-top:0.2rem;">
                    📄 {n['proof_info']}
                  </div>
                </div>
                """, unsafe_allow_html=True)

                col_a, col_r = st.columns(2)
                with col_a:
                    if st.button("✅ قبول العضوية", key=f"accept_{n['id']}", type="primary", use_container_width=True):
                        database.update_nurse_status(n['id'], 'approved')
                        st.rerun()
                with col_r:
                    if st.button("❌ رفض الطلب", key=f"reject_{n['id']}", use_container_width=True):
                        database.update_nurse_status(n['id'], 'rejected')
                        st.rerun()

                st.markdown("<div style='margin-bottom:0.5rem;'></div>", unsafe_allow_html=True)

# ── تبويب 3: الحظر والديون ──
with tab3:
    st.subheader("🛡️ إدارة الممرضين")

    all_nurses_list = database.get_all_nurses()
    if len(all_nurses_list) == 0:
        st.info("لا يوجد ممرضون مسجلون.")
    else:
        for n in all_nurses_list:
            if n['status'] == 'pending':
                continue

            # اختيار لون الشارة
            if n['status'] == 'approved':
                badge_html = "<span class='status-badge badge-green'>🟢 نشط</span>"
            elif n['status'] == 'debt_blocked':
                badge_html = "<span class='status-badge badge-orange'>🛑 موقوف (ديون)</span>"
            elif n['status'] == 'blocked':
                badge_html = "<span class='status-badge badge-red'>🚫 محظور إدارياً</span>"
            else:
                badge_html = "<span class='status-badge badge-gray'>⚫ مرفوض</span>"

            debt_color = "#c0392b" if n['debt'] >= 50 else ("#e67e22" if n['debt'] > 0 else "#27ae60")

            with st.container():
                st.markdown(f"""
                <div style="background:#ffffff;border:1px solid #b2dfdb;border-radius:10px;
                            padding:0.9rem 1.1rem;margin-bottom:0.5rem;direction:rtl;">
                  <div style="display:flex;justify-content:space-between;align-items:center;flex-wrap:wrap;gap:6px;">
                    <div>
                      <span style="font-weight:800;font-size:0.95rem;color:#1a2e35;">
                        {n['name']}
                      </span>
                      <span style="font-size:0.82rem;color:#5a7a80;"> (@{n['username']}) </span>
                      {badge_html}
                    </div>
                    <div style="font-size:0.88rem;color:#1a2e35;">
                      📞 {n['phone']}
                      &nbsp;·&nbsp;
                      الديون: <strong style="color:{debt_color};">{n['debt']} د.ل</strong>
                    </div>
                  </div>
                </div>
                """, unsafe_allow_html=True)

                col_btn1, col_btn2 = st.columns([1, 1])
                with col_btn1:
                    if n['status'] in ['approved', 'debt_blocked']:
                        if st.button("🚫 حظر", key=f"block_{n['id']}", use_container_width=True):
                            database.update_nurse_status(n['id'], 'blocked')
                            st.rerun()
                    elif n['status'] == 'blocked':
                        if st.button("✅ إلغاء الحظر", key=f"unblock_{n['id']}", type="primary", use_container_width=True):
                            new_st = 'debt_blocked' if n['debt'] >= 50 else 'approved'
                            database.update_nurse_status(n['id'], new_st)
                            st.rerun()

                st.markdown("<div style='margin-bottom:0.5rem;'></div>", unsafe_allow_html=True)

# ── تبويب 4: المدفوعات ──
with tab4:
    st.subheader("💳 كروت مدار بانتظار المراجعة")

    pending_payments = database.get_pending_payments()

    if len(pending_payments) == 0:
        st.success("✅ لا توجد كروت شحن معلقة للمراجعة حالياً.")
    else:
        for p in pending_payments:
            with st.container():
                st.markdown(f"""
                <div style="background:#ffffff;border:1px solid #b2dfdb;border-right:4px solid #e67e22;
                            border-radius:10px;padding:0.9rem 1.1rem;margin-bottom:0.5rem;direction:rtl;">
                  <div style="font-size:0.95rem;font-weight:800;color:#1a2e35;">
                    💳 الممرض: {p['nurse_name']}
                    <span style="font-size:0.82rem;color:#5a7a80;"> · 📞 {p['phone']}</span>
                  </div>
                  <div style="font-size:0.88rem;color:#1a2e35;margin-top:0.4rem;">
                    رقم الكرت: <strong style="letter-spacing:1px;">{p['card_number']}</strong>
                    &nbsp;·&nbsp;
                    القيمة: <strong style="color:#27ae60;">{p['amount']} د.ل</strong>
                  </div>
                </div>
                """, unsafe_allow_html=True)

                col_ok, col_bad = st.columns(2)
                with col_ok:
                    if st.button("✅ كرت صحيح — خصم الدين", key=f"pay_ok_{p['id']}", type="primary", use_container_width=True):
                        database.review_payment(p['id'], p['nurse_username'], p['amount'], 'approved')
                        st.rerun()
                with col_bad:
                    if st.button("❌ كرت وهمي / مستعمل", key=f"pay_bad_{p['id']}", use_container_width=True):
                        database.review_payment(p['id'], p['nurse_username'], p['amount'], 'rejected')
                        st.rerun()

                st.markdown("<div style='margin-bottom:0.5rem;'></div>", unsafe_allow_html=True)
