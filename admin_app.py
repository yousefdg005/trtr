import streamlit as st
import database
import pandas as pd

st.set_page_config(page_title="لوحة الإدارة", page_icon="⚙️", layout="wide")

with open('style.css') as f: 
    st.markdown(f'<style>{f.read()}</style>', unsafe_allow_html=True)

# --- القائمة الجانبية: التحكم العام في المنظومة ---
st.sidebar.title("تحكم النظام ⚠️")
is_system_active = database.get_system_status()

st.sidebar.info("عند إيقاف المنظومة، لن يتمكن المرضى من طلب الخدمة ولن يتمكن الممرضون من الدخول.")
new_status = st.sidebar.toggle("المنظومة تعمل (متاحة للجميع)", value=is_system_active)

if new_status != is_system_active:
    database.set_system_status(new_status)
    st.rerun()

if not is_system_active:
    st.error("🚨 المنظومة الآن متوقفة بالكامل.")

st.title("لوحة الإدارة - مركز العمليات")

if st.button("🔄 جلب أحدث البيانات"):
    st.rerun()

# 4 تبويبات الآن
tab1, tab2, tab3, tab4 = st.tabs(["🩺 العمليات", "👨‍⚕️ طلبات العضوية", "🛡️ الحظر", "💳 الخزينة والمدفوعات"])

with tab1:
    st.subheader("سجل الطلبات الحية")
    all_requests = database.get_all_requests()
    if len(all_requests) == 0:
        st.info("لا توجد عمليات مسجلة.")
    else:
        df = pd.DataFrame(all_requests)
        df['الميزانية'] = df['min_price'].astype(str) + " - " + df['max_price'].astype(str)
        display_df = df[['id', 'service_type', 'patient_name', 'patient_gender', 'location_text', 'الميزانية', 'status', 'accepted_by']]
        display_df.columns = ["الرقم", "الخدمة", "المريض", "الجنس", "العنوان", "الميزانية", "الحالة", "الممرض"]
        display_df['الحالة'] = display_df['الحالة'].replace({'pending': '⏳ معلق', 'accepted': '✅ تم القبول'})
        st.dataframe(display_df, use_container_width=True, hide_index=True)

with tab2:
    st.subheader("الممرضون بانتظار الموافقة")
    pending_nurses = database.get_pending_nurses()
    if len(pending_nurses) == 0:
        st.success("لا توجد طلبات انضمام معلقة.")
    else:
        for n in pending_nurses:
            with st.container():
                col1, col2 = st.columns([3, 1])
                with col1:
                    st.write(f"**الاسم:** {n['name']} | **الهاتف:** {n['phone']}")
                    st.write(f"**التخصص:** {n['specialty']} | **الجنس:** {n['gender']}")
                with col2:
                    if st.button("✅ قبول العضوية", key=f"accept_{n['id']}", type="primary"):
                        database.update_nurse_status(n['id'], 'approved')
                        st.rerun()
                    if st.button("❌ رفض", key=f"reject_{n['id']}"):
                        database.update_nurse_status(n['id'], 'rejected')
                        st.rerun()
                st.divider()

with tab3:
    st.subheader("إدارة الممرضين (الديون والحظر)")
    all_nurses = database.get_all_nurses()
    if len(all_nurses) == 0:
        st.info("لا يوجد ممرضون مسجلون.")
    else:
        for n in all_nurses:
            if n['status'] == 'pending':
                continue
                
            with st.container():
                col1, col2 = st.columns([3, 1])
                with col1:
                    # تلوين الحالة
                    if n['status'] == 'approved': status_badge = "🟢 نشط"
                    elif n['status'] == 'debt_blocked': status_badge = "🛑 محظور للديون"
                    elif n['status'] == 'blocked': status_badge = "🚫 محظور إدارياً"
                    else: status_badge = "⚫ مرفوض"
                    
                    st.write(f"**الاسم:** {n['name']} ({n['username']}) - {status_badge}")
                    st.write(f"**الهاتف:** {n['phone']} | **الديون الحالية:** <span style='color:red;'>{n['debt']} د.ل</span>", unsafe_allow_html=True)
                with col2:
                    if n['status'] in ['approved', 'debt_blocked']:
                        if st.button("🚫 حظر العضو", key=f"block_{n['id']}"):
                            database.update_nurse_status(n['id'], 'blocked')
                            st.rerun()
                    elif n['status'] == 'blocked':
                        if st.button("✅ إلغاء الحظر", key=f"unblock_{n['id']}", type="primary"):
                            # إذا فكينا الحظر ودينه مازال 50، نرجعه لـ debt_blocked
                            new_st = 'debt_blocked' if n['debt'] >= 50 else 'approved'
                            database.update_nurse_status(n['id'], new_st)
                            st.rerun()
                st.divider()

with tab4:
    st.subheader("💳 كروت المدار بانتظار المراجعة")
    pending_payments = database.get_pending_payments()
    
    if len(pending_payments) == 0:
        st.success("لا توجد كروت شحن معلقة للمراجعة.")
    else:
        for p in pending_payments:
            with st.container():
                col_p1, col_p2 = st.columns([3, 1])
                with col_p1:
                    st.write(f"**الممرض:** {p['nurse_name']} | **الهاتف:** {p['phone']}")
                    st.info(f"**رقم الكرت:** {p['card_number']} (قيمة: {p['amount']} د.ل)")
                with col_p2:
                    if st.button("✅ كرت صحيح (خصم الدين)", key=f"pay_ok_{p['id']}", type="primary"):
                        database.review_payment(p['id'], p['nurse_username'], p['amount'], 'approved')
                        st.rerun()
                    if st.button("❌ كرت وهمي/مستعمل", key=f"pay_bad_{p['id']}"):
                        database.review_payment(p['id'], p['nurse_username'], p['amount'], 'rejected')
                        st.rerun()
                st.divider()