import streamlit as st
import folium
from folium import plugins
from streamlit_folium import st_folium
from streamlit_autorefresh import st_autorefresh
import database

st.set_page_config(
    page_title="نظام رعايتي - طلب ممرض",
    page_icon="🏥",
    layout="centered",
    initial_sidebar_state="collapsed"
)

with open('style.css') as f:
    st.markdown(f'<style>{f.read()}</style>', unsafe_allow_html=True)

# ── التحقق من أن المنظومة تعمل ──
if not database.get_system_status():
    st.markdown("""
    <div class="app-header-banner">
      <h1>🏥 نظام رعايتي ☽⭐</h1>
      <p>خدمة التمريض المنزلي - طرابلس</p>
    </div>
    """, unsafe_allow_html=True)
    st.error("🚨 المنظومة متوقفة مؤقتاً من قبل الإدارة. يرجى المحاولة لاحقاً.")
    st.stop()

# ── الهيدر ──
st.markdown("""
<div class="app-header-banner">
  <h1>🏥 نظام رعايتي ☽⭐</h1>
  <p>خدمة التمريض المنزلي المتخصصة · طرابلس الكبرى</p>
</div>
""", unsafe_allow_html=True)

# ── تهيئة الجلسة ──
if 'request_id' not in st.session_state:
    st.session_state['request_id'] = None

# حدود طرابلس
TRIPOLI_BOUNDS = {"min_lat": 32.83, "max_lat": 32.92, "min_lng": 13.11, "max_lng": 13.28}

# ══════════════════════════════════════════════
# شاشة تقديم الطلب
# ══════════════════════════════════════════════
if st.session_state['request_id'] is None:

    st.info("📍 الخدمة متوفرة حالياً في: **طرابلس المركز · سوق الجمعة · حي الأندلس · قرجي**")

    # ── 1. بيانات المريض ──
    st.markdown("---")
    st.markdown("### 👤 أولاً: بيانات المريض")

    name = st.text_input("الاسم الكامل", placeholder="مثال: محمد عبدالله الورفلي")
    phone = st.text_input("رقم الهاتف", placeholder="09xxxxxxxx  ·  سيُرسل للممرض بعد القبول فقط")

    col1, col2 = st.columns(2)
    with col1:
        gender = st.selectbox("الجنس", ["ذكر", "أنثى"])
    with col2:
        age = st.number_input("العمر", min_value=1, max_value=120, value=30)

    # ── 2. الخدمة المطلوبة ──
    st.markdown("---")
    st.markdown("### 💉 ثانياً: الخدمة المطلوبة")

    service = st.selectbox(
        "نوع الخدمة",
        ["علاج طبيعي", "حقن عضل / وريد / تحت الجلد", "مداواة الجروح", "تركيب قسطرة بولية"]
    )
    service_desc = st.text_area(
        "تفاصيل إضافية (اختياري)",
        placeholder="صف حالة المريض أو أي تفاصيل تساعد الممرض...",
        height=100
    )

    # ── 3. الميزانية والموقع ──
    st.markdown("---")
    st.markdown("### 📍 ثالثاً: الميزانية والموقع")

    col_min, col_max = st.columns(2)
    with col_min:
        min_price = st.number_input("الحد الأدنى للدفع (د.ل)", min_value=0, value=15, step=5)
    with col_max:
        max_price = st.number_input("الحد الأقصى للدفع (د.ل)", min_value=0, value=50, step=5)

    location_text = st.text_input(
        "العنوان التفصيلي",
        placeholder="مثال: سوق الجمعة، شارع جمال عبدالناصر، بجانب المسجد"
    )

    st.markdown("**🗺️ حدد موقعك على الخريطة** (اضغط زر 📍 للتحديد التلقائي أو انقر مباشرة)")

    m = folium.Map(location=[32.8872, 13.1913], zoom_start=12, tiles="OpenStreetMap")
    plugins.LocateControl(
        position="topleft",
        drawCircle=False,
        drawMarker=True,
        strings={"title": "📍 تحديد موقعي الحالي"}
    ).add_to(m)
    folium.Rectangle(
        bounds=[[TRIPOLI_BOUNDS["min_lat"], TRIPOLI_BOUNDS["min_lng"]],
                [TRIPOLI_BOUNDS["max_lat"], TRIPOLI_BOUNDS["max_lng"]]],
        color='#0d6e6e', fill=True, fill_color='#1a9e9e', fill_opacity=0.08,
        tooltip="نطاق تغطية الخدمة"
    ).add_to(m)
    m.add_child(folium.LatLngPopup())
    map_data = st_folium(m, height=320, use_container_width=True)

    lat, lng = None, None
    if map_data and map_data.get("last_clicked"):
        lat = map_data["last_clicked"]["lat"]
        lng = map_data["last_clicked"]["lng"]
        in_bounds = (
            TRIPOLI_BOUNDS["min_lat"] <= lat <= TRIPOLI_BOUNDS["max_lat"] and
            TRIPOLI_BOUNDS["min_lng"] <= lng <= TRIPOLI_BOUNDS["max_lng"]
        )
        if not in_bounds:
            st.error("⚠️ الموقع المختار خارج نطاق الخدمة الحالي. يرجى اختيار موقع داخل طرابلس.")
            lat, lng = None, None
        else:
            st.success("✅ تم تحديد موقعك بنجاح — ضمن نطاق الخدمة.")

    st.markdown("---")

    if st.button("🚑 تأكيد وإرسال الطلب", type="primary", use_container_width=True):
        if not name:
            st.error("⚠️ الرجاء إدخال الاسم الكامل.")
        elif not phone:
            st.error("⚠️ الرجاء إدخال رقم الهاتف.")
        elif not location_text:
            st.error("⚠️ الرجاء إدخال العنوان التفصيلي.")
        elif not lat or not lng:
            st.error("⚠️ الرجاء تحديد موقعك على الخريطة.")
        else:
            req_id = database.create_request(
                service, name, phone, gender, age,
                service_desc, location_text, lat, lng, min_price, max_price
            )
            st.session_state['request_id'] = req_id
            st.rerun()

# ══════════════════════════════════════════════
# شاشة المتابعة (بعد الإرسال)
# ══════════════════════════════════════════════
else:
    st_autorefresh(interval=5000, key="patient_refresh")
    status_data = database.get_request_status(st.session_state['request_id'])

    # ── تم القبول ──
    if status_data['status'] == 'accepted':
        st.balloons()
        st.markdown("""
        <div class="app-header-banner">
          <h1>🎉 تم قبول طلبك!</h1>
          <p>ممرض متخصص في طريقه إليك الآن</p>
        </div>
        """, unsafe_allow_html=True)

        st.success(f"✅ **الممرض:** {status_data['accepted_by']}")
        st.markdown(f"""
        <div style="background:#e8f8f0;border-right:5px solid #27ae60;border-radius:10px;
                    padding:1rem 1.2rem;direction:rtl;margin:0.5rem 0;">
          <div style="font-size:0.85rem;color:#5a7a80;margin-bottom:4px;">رقم هاتف الممرض للتواصل</div>
          <div style="font-size:1.5rem;font-weight:800;color:#155724;">📞 {status_data['nurse_phone']}</div>
        </div>
        """, unsafe_allow_html=True)

        st.info("💬 يتم الاتفاق على التسعيرة النهائية مع الممرض مباشرة.")

        st.markdown("---")
        if st.button("❌ إلغاء الطلبية (لظرف طارئ)", use_container_width=True):
            database.cancel_request_by_patient(st.session_state['request_id'])
            st.session_state['request_id'] = None
            st.rerun()

    # ── قيد الانتظار ──
    elif status_data['status'] == 'pending':
        st.markdown("""
        <div class="app-header-banner">
          <h1>⏳ جاري البحث...</h1>
          <p>نبحث لك عن أقرب ممرض متخصص في منطقتك</p>
        </div>
        """, unsafe_allow_html=True)

        st.warning("🔍 طلبك وصلنا وجاري إرساله للممرضين القريبين منك. ستصلك إشعار فور القبول.")
        st.markdown("""
        <div style="text-align:center;padding:1.5rem;color:#0d6e6e;font-size:1rem;font-weight:700;direction:rtl;">
          🔄 يتجدد تلقائياً كل 5 ثوانٍ...
        </div>
        """, unsafe_allow_html=True)

        st.markdown("---")
        if st.button("❌ إلغاء الطلب", use_container_width=True):
            database.cancel_request_by_patient(st.session_state['request_id'])
            st.session_state['request_id'] = None
            st.rerun()

    # ── تم الإلغاء ──
    else:
        st.error("❌ تم إلغاء الطلبية.")
        st.markdown("---")
        if st.button("🔄 العودة للرئيسية وتقديم طلب جديد", type="primary", use_container_width=True):
            st.session_state['request_id'] = None
            st.rerun()
