import streamlit as st
import folium
from folium import plugins
from streamlit_folium import st_folium
from streamlit_autorefresh import st_autorefresh
import database

st.set_page_config(
    page_title="نظام رعايتي - طلب ممرض منزلي",
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
      <div class="banner-title">🏥 نظام رعايتي ☽⭐</div>
      <div class="banner-subtitle">خدمة التمريض المنزلي المباشرة · طرابلس</div>
    </div>
    """, unsafe_allow_html=True)
    st.error("🚨 المنظومة متوقفة مؤقتاً للصيانة من قبل الإدارة. يرجى العودة لاحقاً.")
    st.stop()

# ── الهيدر ──
st.markdown("""
<div class="app-header-banner">
  <div class="banner-title">🏥 نظام رعايتي ☽⭐</div>
  <div class="banner-subtitle">طلب خدمة تمريض ورعاية منزلية فورية · طرابلس الكبرى</div>
</div>
""", unsafe_allow_html=True)

# ── تهيئة الجلسة ──
if 'request_id' not in st.session_state:
    st.session_state['request_id'] = None

# حدود طرابلس (المركز، قرجي، الأندلس، سوق الجمعة)
TRIPOLI_BOUNDS = {"min_lat": 32.83, "max_lat": 32.92, "min_lng": 13.11, "max_lng": 13.28}

# ══════════════════════════════════════════════
# شاشة تقديم الطلب
# ══════════════════════════════════════════════
if st.session_state['request_id'] is None:

    st.info("📍 نطاق الخدمة الميدانية الحالي: **طرابلس المركز · سوق الجمعة · حي الأندلس · قرجي**")

    # ── 1. بيانات المريض ──
    st.markdown("---")
    st.markdown("### 👤 أولاً: بيانات المريض")

    name = st.text_input("الاسم الكامل للمريض", placeholder="مثال: محمد عبدالله الورفلي")
    phone = st.text_input("رقم الهاتف للتواصل", placeholder="09xxxxxxxx (يظهر للممرض بعد القبول فقط)")

    col1, col2 = st.columns(2)
    with col1:
        gender = st.selectbox("جنس المريض", ["ذكر", "أنثى"])
    with col2:
        age = st.number_input("العمر (بالسنوات)", min_value=1, max_value=120, value=30)

    # ── 2. الخدمة المطلوبة ──
    st.markdown("---")
    st.markdown("### 💉 ثانياً: الخدمة الطبية المطلوبة")

    service = st.selectbox(
        "نوع الإجراء أو الخدمة",
        ["علاج طبيعي", "حقن عضل / وريد / تحت الجلد", "مداواة الجروح", "تركيب قسطرة بولية"]
    )
    service_desc = st.text_area(
        "تفاصيل إضافية عن الحالة (اختياري)",
        placeholder="صف الحالة الصحية أو أي متطلبات خاصة للممرض...",
        height=90
    )

    # ── 3. الميزانية والموقع ──
    st.markdown("---")
    st.markdown("### 📍 ثالثاً: الميزانية والموقع الجغرافي")

    col_min, col_max = st.columns(2)
    with col_min:
        min_price = st.number_input("الحد الأدنى للدفع المقترح (د.ل)", min_value=0, value=15, step=5)
    with col_max:
        max_price = st.number_input("الحد الأقصى للدفع المقترح (د.ل)", min_value=0, value=50, step=5)

    location_text = st.text_input(
        "العنوان بالتفصيل وعلامة مميزة",
        placeholder="مثال: سوق الجمعة، بالقرب من جامع الحاراتي"
    )

    st.markdown("**🗺️ حدد موقع البيت على الخريطة** (اضغط زر 📍 لتحديد مكانك تلقائياً عبر GPS)")

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
        color='#0e7490', fill=True, fill_color='#059669', fill_opacity=0.08,
        tooltip="نطاق التغطية المعتمد"
    ).add_to(m)
    m.add_child(folium.LatLngPopup())
    map_data = st_folium(m, height=300, use_container_width=True)

    lat, lng = None, None
    if map_data and map_data.get("last_clicked"):
        lat = map_data["last_clicked"]["lat"]
        lng = map_data["last_clicked"]["lng"]
        in_bounds = (
            TRIPOLI_BOUNDS["min_lat"] <= lat <= TRIPOLI_BOUNDS["max_lat"] and
            TRIPOLI_BOUNDS["min_lng"] <= lng <= TRIPOLI_BOUNDS["max_lng"]
        )
        if not in_bounds:
            st.error("⚠️ الموقع المختار خارج نطاق التغطية المدعوم حالياً في طرابلس.")
            lat, lng = None, None
        else:
            st.success("✅ تم تحديد الموقع بنجاح — يقع ضمن نطاق الخدمة الميدانية.")

    st.markdown("---")

    if st.button("🚑 تأكيد وإرسال طلب التمريض", type="primary", use_container_width=True):
        if not name:
            st.error("⚠️ الرجاء كتابة اسم المريض.")
        elif not phone:
            st.error("⚠️ الرجاء كتابة رقم الهاتف للتواصل.")
        elif min_price > max_price:
            st.error("⚠️ الحد الأدنى للميزانية لا يمكن أن يتجاوز الحد الأقصى.")
        elif not location_text:
            st.error("⚠️ الرجاء إدخال وصف العنوان.")
        elif not lat or not lng:
            st.error("⚠️ الرجاء تحديد الموقع على الخريطة عبر النقر أو زر 📍.")
        else:
            req_id = database.create_request(
                service, name, phone, gender, age,
                service_desc, location_text, lat, lng, min_price, max_price
            )
            st.session_state['request_id'] = req_id
            st.rerun()

# ══════════════════════════════════════════════
# شاشة المتابعة التلقائية (بعد إرسال الطلب)
# ══════════════════════════════════════════════
else:
    st_autorefresh(interval=5000, key="patient_refresh")
    status_data = database.get_request_status(st.session_state['request_id'])

    # ── في حال قبول الطلب من ممرض ──
    if status_data and status_data['status'] == 'accepted':
        st.balloons()
        st.markdown("""
        <div class="app-header-banner">
          <div class="banner-title">🎉 تم قبول طلبك بنجاح!</div>
          <div class="banner-subtitle">قام أحد الممرضين المعتمدين باستلام المهمة وهو في طريقه إليك</div>
        </div>
        """, unsafe_allow_html=True)

        st.success(f"✅ **الممرض المستلم:** {status_data['accepted_by']}")

        st.markdown(f"""
        <div class="custom-card">
          <div style="font-size:0.9rem;opacity:0.8;margin-bottom:4px;">رقم هاتف الممرض المباشر للتواصل:</div>
          <div style="font-size:1.6rem;font-weight:900;color:#059669;letter-spacing:1px;">
            📞 {status_data['nurse_phone']}
          </div>
        </div>
        """, unsafe_allow_html=True)

        st.info("💬 التسعيرة النهائية يتم تأكيدها والاتفاق عليها ودياً مع الممرض.")

        st.markdown("---")
        if st.button("❌ إلغاء الطلبية (لظرف طارئ)", use_container_width=True):
            database.cancel_request_by_patient(st.session_state['request_id'])
            st.session_state['request_id'] = None
            st.rerun()

    # ── في حال اكتمال الخدمة بنجاح ──
    elif status_data and status_data['status'] == 'completed':
        st.balloons()
        st.markdown("""
        <div class="app-header-banner">
          <div class="banner-title">✨ تم إكمال الخدمة الطبية بنجاح!</div>
          <div class="banner-subtitle">حمداً لله على سلامتكم · شكراً لاختياركم نظام رعايتي</div>
        </div>
        """, unsafe_allow_html=True)

        nurse_name = status_data.get('accepted_by') or "الممرض المعتمد"
        st.success(f"✅ تم تقديم الرعاية المطلوبة بنجاح بواسطة: **{nurse_name}**")
        st.info("نتمنى لكم دوام الصحة والعافية! بإمكانكم تقديم طلب رعاية جديد في أي وقت.")

        st.markdown("---")
        if st.button("🔄 تقديم طلب رعاية جديد", type="primary", use_container_width=True):
            st.session_state['request_id'] = None
            st.rerun()

    # ── في انتظار قبول ممرض ──
    elif status_data and status_data['status'] == 'pending':
        st.markdown("""
        <div class="app-header-banner">
          <div class="banner-title">⏳ جاري البحث عن ممرض...</div>
          <div class="banner-subtitle">يتم الآن إشعار أقرب الممرضين المتاحين لموقعك الجغرافي</div>
        </div>
        """, unsafe_allow_html=True)

        st.warning("🔍 طلبك معروض حالياً للممرضين في منطقتك. ستتحدث هذه الصفحة تلقائياً فور القبول.")
        st.caption("🔄 يتم التحديث الآلي كل 5 ثوانٍ...")

        st.markdown("---")
        if st.button("❌ إلغاء الطلب", use_container_width=True):
            database.cancel_request_by_patient(st.session_state['request_id'])
            st.session_state['request_id'] = None
            st.rerun()

    # ── إذا أُلغيت الطلبية ──
    else:
        st.error("❌ تم إلغاء هذه الطلبية.")
        st.markdown("---")
        if st.button("🔄 العودة لتقديم طلب جديد", type="primary", use_container_width=True):
            st.session_state['request_id'] = None
            st.rerun()
