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
      <div class="banner-title">👨‍⚕️ بوابة الممرضين ☽⭐</div>
      <div class="banner-subtitle">نظام رعايتي للتمريض المنزلي · طرابلس الكبرى</div>
    </div>
    """, unsafe_allow_html=True)
    st.error("🚨 المنظومة متوقفة مؤقتاً من قبل الإدارة. يرجى المحاولة لاحقاً.")
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
      <div class="banner-title">👨‍⚕️ بوابة الممرضين ☽⭐</div>
      <div class="banner-subtitle">نظام رعايتي · خدمة التمريض المنزلي التخصصية · طرابلس</div>
    </div>
    """, unsafe_allow_html=True)

    # ── تسجيل الدخول ──
    if st.session_state['auth_mode'] == 'login':
        st.markdown("### 🔐 تسجيل الدخول")

        with st.form("login_form"):
            username = st.text_input("اسم المستخدم", placeholder="أدخل اسم المستخدم المسجل")
            password = st.text_input("كلمة المرور", type="password", placeholder="••••••••")
            submit = st.form_submit_button("🚀 تسجيل الدخول", type="primary", use_container_width=True)

            if submit:
                nurse = database.login_nurse(username, password)
                if nurse:
                    if nurse['status'] == 'pending':
                        st.warning("⏳ حسابك قيد المراجعة والاعتماد من قِبل الإدارة. يُرجى الانتظار.")
                    elif nurse['status'] == 'rejected':
                        st.error("❌ نأسف، لم تتم الموافقة على طلب انضمامك. يُرجى مراجعة الإدارة.")
                    elif nurse['status'] == 'blocked':
                        st.error("🚫 تم حظر حسابك من قبل الإدارة. يُرجى التواصل مع الدعم الفني.")
                    else:
                        st.session_state['nurse_data'] = nurse
                        st.rerun()
                else:
                    st.error("⚠️ اسم المستخدم أو كلمة المرور غير صحيحة.")

        st.markdown("---")
        if st.button("📝 ليس لديك حساب؟ سجّل عضوية جديدة الآن", use_container_width=True):
            st.session_state['auth_mode'] = 'register'
            st.rerun()

    # ── إنشاء حساب جديد ──
    elif st.session_state['auth_mode'] == 'register':
        st.markdown("### 📋 طلب الانضمام لمنظومة التمريض")
        st.info("🛡️ يتم فحص شهادات ومستندات المزاولة من قبل الإدارة قبل تفعيل أي حساب جديد.")

        with st.form("register_form"):
            name = st.text_input("الاسم الكامل", placeholder="كما هو مدون في رخصة المزاولة")
            username = st.text_input("اسم المستخدم", placeholder="للدخول به للمنظومة")
            password = st.text_input("كلمة المرور", type="password", placeholder="••••••••")
            phone = st.text_input("رقم الهاتف", placeholder="09xxxxxxxx")

            col_g, col_s = st.columns(2)
            with col_g:
                gender = st.selectbox("الجنس", ["ذكر", "أنثى"])
            with col_s:
                specialty = st.selectbox("التخصص الدقيق", ["علاج طبيعي", "تمريض عام", "إسعاف وطوارئ"])

            proof_info = st.text_area(
                "بيانات المزاولة والشهادات",
                placeholder="رقم الترخيص المهني أو تفاصيل وسنوات الخبرة...",
                height=90
            )

            submit_reg = st.form_submit_button(
                "📤 إرسال طلب العضوية", type="primary", use_container_width=True
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
                    st.error("⚠️ الرجاء تعبئة جميع الحقول المطلوبة.")

        st.markdown("---")
        if st.button("← العودة لشاشة تسجيل الدخول", use_container_width=True):
            st.session_state['auth_mode'] = 'login'
            st.rerun()

# ══════════════════════════════════════════════
# لوحة تحكم الممرض (بعد الدخول)
# ══════════════════════════════════════════════
else:
    nurse = st.session_state['nurse_data']

    # فحص أمني وتحديث الحالة لحظياً
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
          <div class="banner-title">👨‍⚕️ مرحباً، {nurse['name']}</div>
          <div class="banner-subtitle">التخصص: {nurse['specialty']} &nbsp;|&nbsp; الجنس: {nurse['gender']}</div>
        </div>
        """, unsafe_allow_html=True)
    with col_logout:
        st.markdown("<div style='margin-top:0.4rem;'></div>", unsafe_allow_html=True)
        if st.button("🚪 خروج", use_container_width=True):
            st.session_state['nurse_data'] = None
            st.rerun()

    # ── مؤشر الديون ──
    debt = nurse['debt']
    if debt == 0:
        st.success("✅ حسابك سليم: لا توجد ديون مستحقة عليك حالياً.")
    elif debt < 50:
        debt_pct = int((debt / 50) * 100)
        st.warning(f"💰 الديون المستحقة للنظام: **{debt} د.ل** (الحد المسموح: 50 د.ل)")
        st.progress(debt_pct / 100)
    else:
        st.error(f"🛑 تم إيقاف استقبال الطلبات لتجاوز حد الديون: **{debt} د.ل** — يرجى تسديد الديون للمتابعة.")

    # ── فحص إذا كان هناك طلب نشط ومقبول ──
    active_request = database.get_accepted_request_for_nurse(nurse['username'])

    if active_request:
        st.markdown("---")
        st.success("🚨 لديك مهمة تمريضية نشطة قيد التنفيذ حالياً!")

        st.markdown(f"""
        <div class="custom-card">
          <div style="font-size:1.1rem;font-weight:800;color:#0e7490;margin-bottom:0.5rem;">
            🏥 الخدمة المطلوبة: {active_request['service_type']}
          </div>
          <div style="font-size:1rem;margin-bottom:0.3rem;">
            👤 <strong>اسم المريض:</strong> {active_request['patient_name']}
          </div>
          <div style="font-size:1.15rem;font-weight:800;color:#059669;margin-bottom:0.3rem;">
            📞 <strong>هاتف المريض:</strong> {active_request['patient_phone']}
          </div>
          <div style="font-size:0.95rem;">
            📍 <strong>العنوان التفصيلي:</strong> {active_request['location_text']}
          </div>
        </div>
        """, unsafe_allow_html=True)

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
        if st.button("❌ إلغاء المهمة (استرداد العمولة وإلغاء الطلب)", use_container_width=True):
            database.cancel_request_by_nurse(active_request['id'], nurse['username'])
            st.rerun()

    # ── في حالة الحظر بالديون ──
    elif nurse['status'] == 'debt_blocked':
        st.markdown("---")
        st.error("🛑 تم إيقاف حسابك مؤقتاً لتجاوز ديونك الحد الأقصى (50 د.ل). يرجى إدخال كرت مدار لإعادة التنشيط.")

        st.markdown("### 💳 شحن الرصيد وسداد الديون (كرت مدار)")
        with st.form("payment_form"):
            card_num = st.text_input("رقم كرت المدار (14 رقم)", max_chars=14, placeholder="XXXXXXXXXXXXXX")
            amount = st.selectbox("فئة الكرت (د.ل)", [10, 20, 30, 40, 50])
            if st.form_submit_button("📤 إرسال الكرت للمراجعة والخصم", type="primary", use_container_width=True):
                if len(card_num) >= 10:
                    database.submit_payment(nurse['username'], card_num, amount)
                    st.success("✅ تم إرسال الكرت بنجاح! سيتم خصم القيمة وتفعيل حسابك بعد تدقيق الإدارة.")
                else:
                    st.error("⚠️ رقم الكرت المدخل غير صالح.")

    # ── الحالة الطبيعية: استقبال الطلبات وتحديد الموقع ──
    else:
        with st.expander("💸 سداد مسبق للديون (كروت مدار)"):
            with st.form("early_payment"):
                card_num = st.text_input("رقم كرت المدار", max_chars=14, placeholder="XXXXXXXXXXXXXX")
                amount = st.selectbox("فئة الكرت (د.ل)", [10, 20, 30, 40, 50])
                if st.form_submit_button("📤 إرسال الدفعة", type="primary", use_container_width=True):
                    if len(card_num) >= 10:
                        database.submit_payment(nurse['username'], card_num, amount)
                        st.success("✅ تم إرسال الدفعة للإدارة للمراجعة.")
                    else:
                        st.error("⚠️ رقم الكرت غير صالح.")

        st.markdown("---")
        st.markdown("### 🗺️ تحديد موقعك الميداني لتلقي الطلبات")
        st.info("📍 اضغط على زر 📍 على الخريطة لتحديد موقعك بدقة أو انقر مباشرة.")

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
            st.success("✅ تم تحديد موقعك الجغرافي بنجاح. نطاق البحث: 10 كم.")

            is_online = st.toggle("🟢 أنا متاح الآن (بدء استقبال الطلبات القريبة)")

            if is_online:
                st_autorefresh(interval=5000, key="nurse_refresh")
                pending_requests = database.get_nearby_pending_requests(
                    nurse['gender'], my_lat, my_lng, max_radius_km=10
                )

                st.markdown("---")
                st.markdown("### 📋 الطلبات القريبة المتاحة")

                if len(pending_requests) == 0:
                    st.info("🔍 لا توجد طلبات معلقة قريبة منك حالياً. يتم التحديث تلقائياً كل 5 ثوانٍ...")
                else:
                    for req in pending_requests:
                        st.markdown(f"""
                        <div class="custom-card">
                          <div style="display:flex;justify-content:space-between;align-items:center;flex-wrap:wrap;gap:8px;">
                            <div>
                              <strong style="font-size:1.1rem;color:#0e7490;">🏥 {req['service_type']}</strong>
                              <span style="opacity:0.8;font-size:0.85rem;margin-right:8px;">(يبعد: {req['distance_km']:.1f} كم 📍)</span>
                            </div>
                            <div style="font-size:1rem;font-weight:800;color:#059669;">
                              💰 الميزانية: {req['min_price']} – {req['max_price']} د.ل
                            </div>
                          </div>
                          <div style="margin-top:0.4rem;font-size:0.95rem;">
                            👤 <strong>المريض:</strong> {req['patient_name']} (العمر: {req['patient_age']})
                          </div>
                          <div style="font-size:0.95rem;">
                            📍 <strong>العنوان:</strong> {req['location_text']}
                          </div>
                        </div>
                        """, unsafe_allow_html=True)

                        if st.button(
                            "✅ قبول واستلام هذا الطلب",
                            key=f"btn_{req['id']}",
                            type="primary",
                            use_container_width=True
                        ):
                            database.accept_request(req['id'], nurse['username'], nurse['name'])
                            st.rerun()

                        st.markdown("<div style='margin-bottom:0.75rem;'></div>", unsafe_allow_html=True)
        else:
            st.warning("⚠️ يرجى النقر على الخريطة أو زر 📍 لتحديد موقعك أولاً حتى تظهر لك الطلبات الميدانية القريبة.")