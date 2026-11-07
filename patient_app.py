import streamlit as st
import folium
from folium import plugins  # مكتبة الإضافات الخاصة بزر تحديد الموقع
from streamlit_folium import st_folium
from streamlit_autorefresh import st_autorefresh
import database

st.set_page_config(page_title="طلب ممرض", page_icon="🩹", layout="centered")

with open('style.css') as f: 
    st.markdown(f'<style>{f.read()}</style>', unsafe_allow_html=True)

# التحقق من أن المنظومة تعمل وغير متوقفة من الإدارة
if not database.get_system_status():
    st.error("🚨 المنظومة متوقفة حالياً. يرجى العودة لاحقاً.")
    st.stop()

st.title("طلب خدمة تمريض منزلية")

# تهيئة الجلسة
if 'request_id' not in st.session_state:
    st.session_state['request_id'] = None

# حدود طرابلس (المركز، قرجي، الأندلس، سوق الجمعة) - لتقييد الخدمة
TRIPOLI_BOUNDS = {"min_lat": 32.83, "max_lat": 32.92, "min_lng": 13.11, "max_lng": 13.28}

# --- شاشة تقديم الطلب ---
if st.session_state['request_id'] is None:
    st.info("📍 الخدمة متوفرة حالياً في: (طرابلس المركز، سوق الجمعة، حي الأندلس، قرجي).")
    
    st.markdown("### 1. بيانات المريض")
    name = st.text_input("الاسم الكامل:")
    phone = st.text_input("رقم الهاتف (سيظهر للممرض بعد القبول فقط):")
    col1, col2 = st.columns(2)
    with col1: gender = st.selectbox("الجنس:", ["ذكر", "أنثى"])
    with col2: age = st.number_input("العمر:", min_value=1, value=30)
    
    st.markdown("### 2. الخدمة المطلوبة")
    service = st.selectbox("نوع الخدمة:", ["علاج طبيعي", "حقن عضل/وريد/تحت الجلد", "مداواة الجروح", "تركيب قسطرة بولية"])
    service_desc = st.text_area("تفاصيل إضافية:")

    st.markdown("### 3. الميزانية والموقع")
    col_min, col_max = st.columns(2)
    with col_min: min_price = st.number_input("الأدنى للدفع (د.ل):", min_value=0, value=15)
    with col_max: max_price = st.number_input("الأقصى للدفع (د.ل):", min_value=0, value=50)

    location_text = st.text_input("العنوان بالتفصيل:")
    
    st.write("حدد موقعك بدقة على الخريطة (يمكنك الضغط على زر 📍 لتحديد مكانك تلقائياً):")
    
    m = folium.Map(location=[32.8872, 13.1913], zoom_start=12)
    
    # --- إضافة زر الـ GPS (تحديد الموقع التلقائي) ---
    plugins.LocateControl(
        position="topleft",
        drawCircle=False,
        drawMarker=True,
        strings={"title": "تحديد موقعي الحالي"}
    ).add_to(m)
    # -----------------------------------------------

    # رسم مربع التغطية على الخريطة
    folium.Rectangle(
        bounds=[[TRIPOLI_BOUNDS["min_lat"], TRIPOLI_BOUNDS["min_lng"]], [TRIPOLI_BOUNDS["max_lat"], TRIPOLI_BOUNDS["max_lng"]]],
        color='#ff7800', fill=True, fill_color='#ffff00', fill_opacity=0.1, tooltip="نطاق التغطية"
    ).add_to(m)
    
    m.add_child(folium.LatLngPopup())
    map_data = st_folium(m, height=300, width=700)

    lat, lng = None, None
    if map_data and map_data.get("last_clicked"):
        lat, lng = map_data["last_clicked"]["lat"], map_data["last_clicked"]["lng"]
        
        # التحقق هل الموقع المختار يقع داخل المربع المحدد لطرابلس
        if not (TRIPOLI_BOUNDS["min_lat"] <= lat <= TRIPOLI_BOUNDS["max_lat"] and TRIPOLI_BOUNDS["min_lng"] <= lng <= TRIPOLI_BOUNDS["max_lng"]):
            st.error("عذراً! موقعك المختار يقع خارج نطاق التغطية الحالي المدعوم.")
            lat, lng = None, None
        else:
            st.success("✅ تم التقاط موقعك وهو ضمن نطاق الخدمة.")

    if st.button("تأكيد وإرسال الطلب", type="primary", use_container_width=True):
        if name and phone and location_text and lat and lng:
            req_id = database.create_request(service, name, phone, gender, age, service_desc, location_text, lat, lng, min_price, max_price)
            st.session_state['request_id'] = req_id
            st.rerun()
        else:
            st.error("الرجاء التأكد من تعبئة الاسم، رقم الهاتف، العنوان، وتحديد موقعك صحيح على الخريطة.")
            
# --- شاشة الانتظار والمتابعة (تعمل بالتحديث التلقائي) ---
else:
    # التحديث التلقائي كل 5 ثواني لمعرفة الرد بدون تدخل المريض
    st_autorefresh(interval=5000, key="patient_refresh") 
    
    status_data = database.get_request_status(st.session_state['request_id'])
    
    if status_data['status'] == 'accepted':
        st.balloons()
        st.success(f"🎉 تم قبول طلبك من قبل الممرض: {status_data['accepted_by']}")
        st.info(f"📞 رقم هاتف الممرض للتواصل: **{status_data['nurse_phone']}**")
        st.write("التسعيرة النهائية يتم التفاهم عليها مع الممرض.")
        
        if st.button("إلغاء الطلبية (لظرف طارئ)"):
            database.cancel_request_by_patient(st.session_state['request_id'])
            st.session_state['request_id'] = None
            st.rerun()
            
    elif status_data['status'] == 'pending':
        st.warning("⏳ الطلب معلق... جاري البحث عن أقرب ممرض في منطقتك.")
        if st.button("إلغاء الطلب"):
            database.cancel_request_by_patient(st.session_state['request_id'])
            st.session_state['request_id'] = None
            st.rerun()
            
    else: # cancelled_by_nurse أو cancelled_by_patient
        st.error("تم إلغاء الطلبية.")
        if st.button("العودة للرئيسية لتقديم طلب جديد"):
            st.session_state['request_id'] = None
            st.rerun()