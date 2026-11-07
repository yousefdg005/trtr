import streamlit as st
import folium
from folium import plugins
from streamlit_folium import st_folium
from streamlit_autorefresh import st_autorefresh
import pandas as pd
import database

st.set_page_config(page_title="بوابة الممرضين", page_icon="👨‍⚕️", layout="centered")

with open('style.css') as f: 
    st.markdown(f'<style>{f.read()}</style>', unsafe_allow_html=True)

# 1. التحقق من حالة المنظومة
if not database.get_system_status():
    st.error("🚨 المنظومة متوقفة حالياً من قبل الإدارة. يرجى العودة لاحقاً.")
    st.stop()

# 2. تهيئة متغيرات الجلسة (السطر الذي تسبب في الخطأ)
if 'nurse_data' not in st.session_state:
    st.session_state['nurse_data'] = None

if 'auth_mode' not in st.session_state:
    st.session_state['auth_mode'] = 'login'

# 3. شاشة تسجيل الدخول أو إنشاء الحساب
if st.session_state['nurse_data'] is None:
    st.image("https://cdn-icons-png.flaticon.com/512/2966/2966327.png", width=80)
    st.title("بوابة الممرضين")
    
    if st.session_state['auth_mode'] == 'login':
        st.subheader("تسجيل الدخول")
        with st.form("login_form"):
            username = st.text_input("اسم المستخدم:")
            password = st.text_input("كلمة المرور:", type="password")
            submit = st.form_submit_button("دخول", type="primary", use_container_width=True)
            
            if submit:
                nurse = database.login_nurse(username, password)
                if nurse:
                    if nurse['status'] == 'pending':
                        st.warning("حسابك قيد المراجعة. يرجى انتظار موافقة الإدارة.")
                    elif nurse['status'] == 'rejected':
                        st.error("نأسف، تم رفض طلب انضمامك من قبل الإدارة.")
                    elif nurse['status'] == 'blocked':
                        st.error("🚫 تم حظر حسابك من قبل الإدارة. يرجى مراجعة الدعم الفني.")
                    else:
                        st.session_state['nurse_data'] = nurse
                        st.rerun()
                else:
                    st.error("اسم المستخدم أو كلمة المرور غير صحيحة.")
                    
        if st.button("ليس لديك حساب؟ اضغط هنا لإنشاء عضوية جديدة"):
            st.session_state['auth_mode'] = 'register'
            st.rerun()

    elif st.session_state['auth_mode'] == 'register':
        st.subheader("طلب انضمام لمنظومة الرعاية")
        with st.form("register_form"):
            name = st.text_input("الاسم الكامل (كما سيظهر للمرضى):")
            username = st.text_input("اسم المستخدم (لتسجيل الدخول):")
            password = st.text_input("كلمة المرور:", type="password")
            phone = st.text_input("رقم الهاتف:")
            gender = st.selectbox("الجنس:", ["ذكر", "أنثى"])
            specialty = st.selectbox("التخصص الدقيق:", ["علاج طبيعي", "تمريض عام", "إسعاف وطوارئ"])
            proof_info = st.text_area("إثبات المزاولة (أدخل رقم الترخيص أو رابط لشهاداتك):")
            
            submit_reg = st.form_submit_button("إرسال الطلب للإدارة", type="primary", use_container_width=True)
            
            if submit_reg:
                if username and password and name and proof_info:
                    success, msg = database.register_nurse(username, password, name, phone, gender, specialty, proof_info)
                    if success:
                        st.success(msg)
                        st.session_state['auth_mode'] = 'login'
                    else:
                        st.error(msg)
                else:
                    st.error("الرجاء تعبئة جميع الحقول الأساسية.")
                    
        if st.button("العودة لشاشة تسجيل الدخول"):
            st.session_state['auth_mode'] = 'login'
            st.rerun()

# 4. لوحة تحكم الممرض (بعد الدخول)
else:
    nurse = st.session_state['nurse_data']
    
    # فحص أمني مباشر من قاعدة البيانات
    current_status = database.login_nurse(nurse['username'], nurse['password'])
    if not current_status or current_status['status'] == 'blocked':
        st.session_state['nurse_data'] = None
        st.rerun()
        
    nurse = current_status
    st.session_state['nurse_data'] = nurse
    
    col1, col2 = st.columns([3,1])
    with col1: st.title(f"مرحباً، {nurse['name']}")
    with col2:
        if st.button("تسجيل الخروج"): 
            st.session_state['nurse_data'] = None
            st.rerun()

    st.info(f"💰 الديون المستحقة: **{nurse['debt']} دينار**")
    
    # التحقق من وجود طلب جاري
    active_request = database.get_accepted_request_for_nurse(nurse['username'])
    
    if active_request:
        st.success("🚨 لديك مهمة جارية حالياً!")
        st.write(f"**المريض:** {active_request['patient_name']}")
        st.info(f"📞 رقم هاتف المريض: **{active_request['patient_phone']}**")
        st.write(f"**العنوان:** {active_request['location_text']}")
        
        m = folium.Map(location=[active_request['location_lat'], active_request['location_lng']], zoom_start=15)
        folium.Marker([active_request['location_lat'], active_request['location_lng']], popup="موقع المريض").add_to(m)
        st_folium(m, height=300, width=700)
        
        if st.button("إلغاء المهمة (لم أجد المريض/ المريض ألغى) - استرداد العمولة"):
            database.cancel_request_by_nurse(active_request['id'], nurse['username'])
            st.rerun()
            
    elif nurse['status'] == 'debt_blocked':
        st.error("🛑 تم إيقاف حسابك مؤقتاً لتجاوز ديونك الحد الأقصى (50 دينار).")
        with st.form("payment_form"):
            card_num = st.text_input("أدخل رقم كرت المدار (14 رقم):", max_chars=14)
            amount = st.selectbox("اختر فئة الكرت:", [10, 20, 30, 40, 50])
            if st.form_submit_button("إرسال الكرت للإدارة", type="primary"):
                if len(card_num) >= 10:
                    database.submit_payment(nurse['username'], card_num, amount)
                    st.success("✅ تم الإرسال بنجاح! بانتظار مراجعة الإدارة.")
                else:
                    st.error("الرجاء إدخال رقم كرت صحيح.")
    else:
        with st.expander("💸 دفع الديون مبكراً (كروت مدار)"):
            with st.form("early_payment"):
                card_num = st.text_input("أدخل رقم كرت المدار:", max_chars=14)
                amount = st.selectbox("اختر فئة الكرت:", [10, 20, 30, 40, 50])
                if st.form_submit_button("إرسال الدفعة", type="primary"):
                    if len(card_num) >= 10:
                        database.submit_payment(nurse['username'], card_num, amount)
                        st.success("تم إرسال الدفعة للمراجعة.")
                    else:
                        st.error("رقم الكرت غير صالح.")

        st.write("لتلقي الطلبات، حدد موقعك الحالي على الخريطة أولاً (اضغط 📍 لتحديد مكانك تلقائياً):")
        m_loc = folium.Map(location=[32.8872, 13.1913], zoom_start=12)
        plugins.LocateControl(position="topleft", drawCircle=False, drawMarker=True, strings={"title": "موقعي"}).add_to(m_loc)
        m_loc.add_child(folium.LatLngPopup())
        loc_data = st_folium(m_loc, height=250, width=700)
        
        my_lat, my_lng = None, None
        if loc_data and loc_data.get("last_clicked"):
            my_lat, my_lng = loc_data["last_clicked"]["lat"], loc_data["last_clicked"]["lng"]
            st.success("تم تحديد موقعك. أنت جاهز لتلقي الطلبات القريبة (نطاق 10 كم).")
            
            is_online = st.toggle("أنا متاح الآن (تلقي الطلبات)")
            
            if is_online:
                st_autorefresh(interval=5000, key="nurse_refresh") # تحديث تلقائي كل 5 ثواني
                
                pending_requests = database.get_nearby_pending_requests(nurse['gender'], my_lat, my_lng, max_radius_km=10)
                
                if len(pending_requests) == 0:
                    st.info("لا توجد طلبات قريبة منك حالياً...")
                else:
                    for req in pending_requests:
                        with st.container():
                            st.markdown(f"### {req['service_type']} (يبعد: {req['distance_km']:.1f} كم 📍)")
                            st.write(f"**المريض:** {req['patient_name']} (العمر: {req['patient_age']})")
                            st.write(f"**العنوان:** {req['location_text']}")
                            st.markdown(f"**الميزانية المقترحة:** <span style='color:green;'>{req['min_price']} - {req['max_price']} د.ل</span>", unsafe_allow_html=True)
                            
                            if st.button(f"قبول واستلام الطلب", key=f"btn_{req['id']}", type="primary"):
                                database.accept_request(req['id'], nurse['username'], nurse['name'])
                                st.rerun()
                            st.divider()
        else:
            st.warning("انقر على الخريطة أعلاه أو استخدم زر 📍 لتحديد مكانك لتصلك الطلبات القريبة منك فقط.")
    