import streamlit as st
import folium
from folium import plugins
from streamlit_folium import st_folium
from streamlit_autorefresh import st_autorefresh
import pandas as pd
import database

st.set_page_config(
    page_title="نظام رعايتي - بوابة الممرضين",
    page_icon="👨‍⚕️",
    layout="centered",
    initial_sidebar_state="collapsed"
)

with open('style.css') as f:
    st.markdown(f'<style>{f.read()}</style>', unsafe_allow_html=True)

# ── التحقق من المنظومة ──
if not database.get_system_status():
    st.markdown("""
    <div class="app-header-banner">
      <h1>👨‍⚕️ بوابة الممرضين ☽⭐</h1>
      <p>نظام رعايتي · طرابلس الكبرى</p>
    </div>
    """, unsafe_allow_html=True)
    st.error("🚨 المنظومة متوقفة مؤقتاً من قبل الإدارة. يرجى العودة لاحقاً.")
    st.stop()

# ── تهيئة الجلسة ──
if 'nurse_data' not in st.session_state:
    st.session_state['nurse_data'] = None
if 'auth_mode' not in st.session_state:
    st.session_state['auth_mode'] = 'login'

# ══════════════════════════════════════════════
# شاشة المصادقة (تسجيل الدخول / التسجيل)
# ══════════════════════════════════════════════
if st.session_state['nurse_data'] is None:

    st.markdown("""
    <div class="app-header-banner">
      <h1>👨‍⚕️ بوابة الممرضين ☽⭐</h1>
      <p>نظام رعايتي · خدمة التمريض المنزلي · طرابلس</p>
    </div>
    """, unsafe_allow_html=True)

    # ── تسجيل الدخول ──
    if st.session_state['auth_mode'] == 'login':
        st.markdown("### 🔐 تسجيل الدخول")

        with st.form("login_form"):
            username = st.text_input("اسم المستخدم", placeholder="أدخل اسم المستخدم")
            password = st.text_input("كلمة المرور", type="password", placeholder="••••••••")
            submit = st.form_submit_button("🚀 دخول", type="primary", use_container_width=True)

            if submit:
                nurse = database.login_nurse(username, password)
                if nurse:
                    if nurse['status'] == 'pending':
                        st.warning("⏳ حسابك قيد المراجعة من قِبل الإدارة. يُرجى الانتظار.")
                    elif nurse['status'] == 'rejected':
                        st.error("❌ نأسف، تم رفض طلب انضمامك. يُرجى التواصل مع الإدارة.")
                    elif nurse['status'] == 'blocked':
                        st.error("🚫 تم حظر حسابك من قبل الإدارة. يُرجى مراجعة الدعم الفني.")
                    else:
                        st.session_state['nurse_data'] = nurse
                        st.rerun()
                else:
                    st.error("⚠️ اسم المستخدم أو كلمة المرور غير صحيحة.")

        st.markdown("---")
        if st.button("📝 ليس لديك حساب؟ سجّل عضوية جديدة", use_container_width=True):
            st.session_state['auth_mode'] = 'register'
            st.rerun()

        st.markdown("""
        <div style="text-align:center;color:#5a7a80;font-size:0.82rem;margin-top:1.5rem;direction:rtl;">
          🏥 نظام رعايتي · خدمة التمريض المنزلي المتخصصة بطرابلس الكبرى
        </div>
        """, unsafe_allow_html=True)

    # ── إنشاء حساب جديد ──
    elif st.session_state['auth_mode'] == 'register':
        st.markdown("### 📋 طلب الانضمام إلى منظومة رعايتي")
        st.info("🛡️ سيتم مراجعة طلبك من قِبل الإدارة قبل تفعيل الحساب.")

        with st.form("register_form"):
            name = st.text_input("الاسم الكامل", placeholder="كما سيظهر للمرضى")
            username = st.text_input("اسم المستخدم", placeholder="للدخول للنظام")
            password = st.text_input("كلمة المرور", type="password", placeholder="••••••••")
            phone = st.text_input("رقم الهاتف", placeholder="09xxxxxxxx")

            col_g, col_s = st.columns(2)
            with col_g:
                gender = st.selectbox("الجنس", ["ذكر", "أنثى"])
            with col_s:
                specialty = st.selectbox("التخصص", ["علاج طبيعي", "تمريض عام", "إسعاف وطوارئ"])

            proof_info = st.text_area(
                "إثبات المزاولة",
                placeholder="رقم الترخيص المهني أو رابط الشهادات...",
                height=80
            )

            submit_reg = st.form_submit_button(
                "📤 إرسال الطلب للإدارة", type="primary", use_container_width=True
            )

            if submit_reg:
                if username and password and name and proof_info:
                    success, msg = database.register_nurse(
                        username, password, name, phone, gender, specialty, proof_info
                    )
                    if success:
                        st.success(f"✅ {msg}")
                        st.session_state['auth_mode'] = 'login'
                    else:
                        st.error(f"❌ {msg}")
                else:
                    st.error("⚠️ الرجاء تعبئة جميع الحقول الأساسية.")

        st.markdown("---")
        if st.button("← العودة لتسجيل الدخول", use_container_width=True):
            st.session_state['auth_mode'] = 'login'
            st.rerun()

# ══════════════════════════════════════════════
# لوحة تحكم الممرض
# ══════════════════════════════════════════════
else:
    nurse = st.session_state['nurse_data']

    # فحص أمني
    current_status = database.login_nurse(nurse['username'], nurse['password'])
    if not current_status or current_status['status'] == 'blocked':
        st.session_state['nurse_data'] = None
        st.rerun()

    nurse = current_status
    st.session_state['nurse_data'] = nurse

    # ── الهيدر ──
    col_title, col_logout = st.columns([4, 1])
    with col_title:
        st.markdown(f"""
        <div class="app-header-banner" style="margin-bottom:0.8rem;">
          <h1>👨‍⚕️ مرحباً، {nurse['name']}</h1>
          <p>{nurse['specialty']} · {nurse['gender']}</p>
        </div>
        """, unsafe_allow_html=True)
    with col_logout:
        st.markdown("<div style='margin-top:0.5rem;'></div>", unsafe_allow_html=True)
        if st.button("🚪 خروج", use_container_width=True):
            st.session_state['nurse_data'] = None
            st.rerun()

    # ── مؤشر الديون ──
    debt = nurse['debt']
    if debt == 0:
        st.success("✅ لا توجد ديون مستحقة عليك.")
    elif debt < 50:
        debt_pct = int((debt / 50) * 100)
        st.warning(f"💰 الديون المستحقة: **{debt} د.ل** (الحد الأقصى: 50 د.ل)")
        st.progress(debt_pct / 100)
    else:
        st.error(f"🛑 الديون بلغت الحد الأقصى: **{debt} د.ل** — الحساب موقوف مؤقتاً.")

    # ── طلب نشط ──
    active_request = database.get_accepted_request_for_nurse(nurse['username'])

    if active_request:
        st.markdown("---")
        st.markdown("""
        <div style="background:#e8f8f0;border-right:5px solid #27ae60;border-radius:10px;
                    padding:1rem 1.2rem;direction:rtl;margin-bottom:0.8rem;">
          <div style="font-size:1.1rem;font-weight:800;color:#155724;">🚨 لديك مهمة جارية الآن!</div>
        </div>
        """, unsafe_allow_html=True)

        c1, c2 = st.columns(2)
        with c1:
            st.metric("👤 المريض", active_request['patient_name'])
        with c2:
            st.metric("🏥 الخدمة", active_request['service_type'])

        st.markdown(f"""
        <div style="background:#e8f8f0;border-right:5px solid #27ae60;border-radius:10px;
                    padding:1rem 1.2rem;direction:rtl;margin:0.5rem 0;">
          <div style="font-size:0.85rem;color:#5a7a80;margin-bottom:4px;">رقم هاتف المريض</div>
          <div style="font-size:1.5rem;font-weight:800;color:#155724;">📞 {active_request['patient_phone']}</div>
        </div>
        """, unsafe_allow_html=True)

        st.info(f"📍 **العنوان:** {active_request['location_text']}")

        m = folium.Map(
            location=[active_request['location_lat'], active_request['location_lng']],
            zoom_start=15
        )
        folium.Marker(
            [active_request['location_lat'], active_request['location_lng']],
            popup="📍 موقع المريض",
            icon=folium.Icon(color='red', icon='plus-sign')
        ).add_to(m)
        st_folium(m, height=280, use_container_width=True)

        st.markdown("---")
        if st.button("❌ إلغاء المهمة واسترداد العمولة", use_container_width=True):
            database.cancel_request_by_nurse(active_request['id'], nurse['username'])
            st.rerun()

    # ── حساب موقوف بسبب الديون ──
    elif nurse['status'] == 'debt_blocked':
        st.markdown("---")
        st.error("🛑 تم إيقاف حسابك مؤقتاً لتجاوز حد الديون (50 دينار). سدّد ديونك لاستئناف العمل.")

        st.markdown("### 💳 سداد الديون بكرت مدار")
        with st.form("payment_form"):
            card_num = st.text_input("رقم كرت المدار (14 رقم)", max_chars=14, placeholder="XXXXXXXXXXXXXX")
            amount = st.selectbox("فئة الكرت (د.ل)", [10, 20, 30, 40, 50])
            if st.form_submit_button("📤 إرسال الكرت للإدارة", type="primary", use_container_width=True):
                if len(card_num) >= 10:
                    database.submit_payment(nurse['username'], card_num, amount)
                    st.success("✅ تم إرسال الكرت بنجاح. بانتظار مراجعة الإدارة.")
                else:
                    st.error("⚠️ رقم الكرت غير صالح.")

    # ── لوحة استقبال الطلبات ──
    else:
        with st.expander("💸 سداد الديون مبكراً (كروت مدار)"):
            with st.form("early_payment"):
                card_num = st.text_input("رقم كرت المدار", max_chars=14, placeholder="XXXXXXXXXXXXXX")
                amount = st.selectbox("فئة الكرت (د.ل)", [10, 20, 30, 40, 50])
                if st.form_submit_button("📤 إرسال الدفعة", type="primary", use_container_width=True):
                    if len(card_num) >= 10:
                        database.submit_payment(nurse['username'], card_num, amount)
                        st.success("✅ تم إرسال الدفعة للمراجعة.")
                    else:
                        st.error("⚠️ رقم الكرت غير صالح.")

        st.markdown("---")
        st.markdown("### 🗺️ تحديد موقعك لاستقبال الطلبات")
        st.info("📍 اضغط زر 📍 على الخريطة أو انقر مباشرة لتحديد مكانك الحالي.")

        m_loc = folium.Map(location=[32.8872, 13.1913], zoom_start=12)
        plugins.LocateControl(
            position="topleft", drawCircle=False, drawMarker=True,
            strings={"title": "📍 موقعي الحالي"}
        ).add_to(m_loc)
        m_loc.add_child(folium.LatLngPopup())
        loc_data = st_folium(m_loc, height=260, use_container_width=True)

        my_lat, my_lng = None, None
        if loc_data and loc_data.get("last_clicked"):
            my_lat = loc_data["last_clicked"]["lat"]
            my_lng = loc_data["last_clicked"]["lng"]
            st.success("✅ تم تحديد موقعك. نطاق البحث: 10 كيلومتر.")

            is_online = st.toggle("🟢 أنا متاح الآن (استقبال الطلبات)")

            if is_online:
                st_autorefresh(interval=5000, key="nurse_refresh")
                pending_requests = database.get_nearby_pending_requests(
                    nurse['gender'], my_lat, my_lng, max_radius_km=10
                )

                st.markdown("---")
                st.markdown("### 📋 الطلبات المتاحة قريباً منك")

                if len(pending_requests) == 0:
                    st.info("🔍 لا توجد طلبات قريبة منك حالياً. يتجدد تلقائياً كل 5 ثوانٍ...")
                else:
                    for req in pending_requests:
                        with st.container():
                            st.markdown(f"""
                            <div style="background:#ffffff;border-right:4px solid #0d6e6e;
                                        border:1px solid #b2dfdb;border-right:4px solid #0d6e6e;
                                        border-radius:10px;padding:0.9rem 1.1rem;
                                        margin-bottom:0.6rem;direction:rtl;">
                              <div style="font-size:1rem;font-weight:800;color:#0d6e6e;">
                                🏥 {req['service_type']}
                                <span style="font-size:0.85rem;color:#5a7a80;font-weight:600;">
                                  · يبعد {req['distance_km']:.1f} كم 📍
                                </span>
                              </div>
                              <div style="margin-top:0.4rem;font-size:0.9rem;color:#1a2e35;">
                                👤 <strong>المريض:</strong> {req['patient_name']} · العمر: {req['patient_age']}
                              </div>
                              <div style="font-size:0.9rem;color:#1a2e35;">
                                📍 <strong>العنوان:</strong> {req['location_text']}
                              </div>
                              <div style="font-size:0.9rem;color:#155724;font-weight:700;margin-top:0.3rem;">
                                💰 الميزانية: {req['min_price']} - {req['max_price']} د.ل
                              </div>
                            </div>
                            """, unsafe_allow_html=True)

                            if st.button(
                                f"✅ قبول واستلام الطلب",
                                key=f"btn_{req['id']}",
                                type="primary",
                                use_container_width=True
                            ):
                                database.accept_request(req['id'], nurse['username'], nurse['name'])
                                st.rerun()

                            st.markdown("<div style='margin-bottom:0.5rem;'></div>", unsafe_allow_html=True)
        else:
            st.warning("⚠️ انقر على الخريطة أو اضغط زر 📍 لتحديد موقعك وتلقي الطلبات القريبة.")
