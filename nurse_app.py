import streamlit as st
import folium
from folium import plugins
from streamlit_folium import st_folium
from streamlit_autorefresh import st_autorefresh
import os
import uuid
import html
import database
import session_token

st.set_page_config(
    page_title="نظام رعايتي - بوابة الممرضين",
    page_icon="👨‍⚕️",
    layout="centered",
    initial_sidebar_state="collapsed"
)

with open('style.css') as f:
    st.markdown(f'<style>{f.read()}</style>', unsafe_allow_html=True)

# ── فشل-مغلق: لا عمل بدون مفتاح توقيع جلسات معرّف في الأسرار ──
session_token.ensure_configured()

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
def _accept_request_cb(req_id, nurse_id):
    """تُنفَّذ عند الضغط على زر القبول قبل إعادة تشغيل السكربت."""
    try:
        success, msg = database.accept_request(req_id, nurse_id)
    except Exception as exc:
        success, msg = False, f"تعذر قبول الطلب بسبب خطأ في الخادم: {exc}"
    if not success:
        st.session_state['accept_error'] = msg

if 'nurse_data' not in st.session_state:
    st.session_state['nurse_data'] = None
if 'auth_mode' not in st.session_state:
    st.session_state['auth_mode'] = 'login'
if 'nurse_loc' not in st.session_state:
    st.session_state['nurse_loc'] = None

# ── استعادة الجلسة بعد إعادة تحميل الصفحة (رمز موقّع في الرابط) ──
if st.session_state['nurse_data'] is None:
    restored_id = session_token.load_session("nurse")
    if restored_id is not None:
        restored = database.get_nurse_by_id(restored_id)
        if restored and restored['status'] in ('approved', 'debt_blocked'):
            st.session_state['nurse_data'] = restored
        else:
            session_token.clear_session()

# ── استعادة آخر موقع محدد للممرض (محفوظ في الرابط أيضاً) ──
if st.session_state['nurse_loc'] is None and st.query_params.get("loc"):
    try:
        _lat, _lng = (float(v) for v in st.query_params.get("loc").split(","))
        st.session_state['nurse_loc'] = (_lat, _lng)
    except Exception:
        pass

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
                        session_token.save_session("nurse", nurse['id'], session_token.NURSE_TTL)
                        st.rerun()
                else:
                    st.error("⚠️ اسم المستخدم أو كلمة المرور غير صحيحة.")

        st.markdown("---")
        if st.button("📝 ليس لديك حساب؟ سجّل عضوية جديدة الآن", use_container_width=True):
            st.session_state['auth_mode'] = 'register'
            st.rerun()

    # ── إنشاء حساب جديد (طلب العضوية) ──
    elif st.session_state['auth_mode'] == 'register':
        st.markdown("### 📋 طلب الانضمام لمنظومة التمريض")
        st.info("🛡️ يشترط إرفاق صورة وثيقة مزاولة المهنة أو المؤهل الطبي للمراجعة والاعتماد.")

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

            # 📄 Task 2: طلب صورة وثيقة إثبات المزاولة وحفظها في uploads/licenses/
            uploaded_doc = st.file_uploader(
                "📸 صورة وثيقة أو رخصة مزاولة المهنة (إجباري):",
                type=["png", "jpg", "jpeg", "webp"],
                help="التقط صورة واضحة لرخصة المزاولة أو بطاقة النقابة أو إفادة التخرج الطبية"
            )

            extra_notes = st.text_area(
                "ملاحظات أو رقم القيد بالنقابة (اختياري):",
                placeholder="رقم القيد أو سنوات الخبرة...",
                height=70
            )

            submit_reg = st.form_submit_button(
                "📤 إرسال طلب العضوية للإدارة", type="primary", use_container_width=True
            )

            if submit_reg:
                if not (username and password and name and phone):
                    st.error("⚠️ الرجاء تعبئة جميع الحقول الشخصية الأساسية.")
                elif not uploaded_doc:
                    st.error("⚠️ يجب إرفاق صورة وثيقة إثبات مزاولة المهنة لإكمال الطلب.")
                else:
                    # Task 2: حفظ الملف على القرص بمسار آمن واسم فريد
                    upload_dir = os.path.join("uploads", "licenses")
                    os.makedirs(upload_dir, exist_ok=True)
                    
                    file_ext = os.path.splitext(uploaded_doc.name)[1].lower() or ".jpg"
                    unique_filename = f"{uuid.uuid4().hex}{file_ext}"
                    saved_file_path = os.path.join(upload_dir, unique_filename)
                    
                    with open(saved_file_path, "wb") as f_out:
                        f_out.write(uploaded_doc.getbuffer())
                    
                    # حفظ مسار الملف والملاحظات في proof_info
                    notes_text = f"ملاحظات: {extra_notes}" if extra_notes else "لا توجد ملاحظات إضافية"
                    proof_info = f"FILE_PATH:{saved_file_path}###{notes_text}"

                    success, msg = database.register_nurse(
                        username, password, name, phone, gender, specialty, proof_info
                    )
                    if success:
                        st.success(f"✅ {msg}")
                        st.session_state['auth_mode'] = 'login'
                    else:
                        st.error(f"❌ {msg}")

        st.markdown("---")
        if st.button("← العودة لشاشة تسجيل الدخول", use_container_width=True):
            st.session_state['auth_mode'] = 'login'
            st.rerun()

# ══════════════════════════════════════════════
# لوحة تحكم الممرض (بعد الدخول)
# ══════════════════════════════════════════════
else:
    nurse = st.session_state['nurse_data']

    # فحص أمني وتحديث الحالة لحظياً عبر معرف الممرض nurse['id']
    current_status = database.get_nurse_by_id(nurse['id'])
    if not current_status or current_status['status'] not in ('approved', 'debt_blocked'):
        st.session_state['nurse_data'] = None
        session_token.clear_session()
        st.rerun()

    nurse = current_status
    st.session_state['nurse_data'] = nurse

    # ── الهيدر ──
    col_title, col_logout = st.columns([4, 1])
    with col_title:
        st.markdown(f"""
        <div class="app-header-banner" style="margin-bottom:0.8rem;">
          <div class="banner-title">👨‍⚕️ مرحباً، {html.escape(str(nurse['name']))}</div>
          <div class="banner-subtitle">التخصص: {html.escape(str(nurse['specialty']))} &nbsp;|&nbsp; الجنس: {html.escape(str(nurse['gender']))}</div>
        </div>
        """, unsafe_allow_html=True)
    with col_logout:
        st.markdown("<div style='margin-top:0.4rem;'></div>", unsafe_allow_html=True)
        if st.button("🚪 خروج", use_container_width=True):
            st.session_state['nurse_data'] = None
            st.session_state['nurse_loc'] = None
            session_token.clear_session()
            if "loc" in st.query_params:
                del st.query_params["loc"]
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

    # ── فحص إذا كان هناك طلب نشط ومقبول للممرض (Task 4: nurse['id']) ──
    active_request = database.get_accepted_request_for_nurse(nurse['id'])

    if active_request:
        st.markdown("---")
        st.success("🚨 لديك مهمة تمريضية نشطة قيد التنفيذ حالياً!")

        st.markdown(f"""
        <div class="custom-card">
          <div style="font-size:1.1rem;font-weight:800;color:#0e7490;margin-bottom:0.5rem;">
            🏥 الخدمة المطلوبة: {html.escape(str(active_request['service_type']))}
          </div>
          <div style="font-size:1rem;margin-bottom:0.3rem;">
            👤 <strong>اسم المريض:</strong> {html.escape(str(active_request['patient_name']))}
          </div>
          <div style="font-size:1.15rem;font-weight:800;color:#059669;margin-bottom:0.3rem;">
            📞 <strong>هاتف المريض:</strong> {html.escape(str(active_request['patient_phone']))}
          </div>
          <div style="font-size:0.95rem;">
            📍 <strong>العنوان التفصيلي:</strong> {html.escape(str(active_request['location_text']))}
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
        col_comp, col_canc = st.columns(2)
        with col_comp:
            if st.button("✅ إتمام المهمة بنجاح (إنهاء الخدمة)", type="primary", use_container_width=True):
                if database.complete_request(active_request['id'], nurse['id']):
                    st.success("🎉 أحسنت! تم إتمام المهمة الطبية بنجاح وتحديث السجل.")
                    st.rerun()
                else:
                    st.error("تعذر إتمام المهمة، يرجى المحاولة لاحقاً.")
        with col_canc:
            if st.button("❌ إلغاء المهمة (استرداد العمولة وإلغاء الطلب)", use_container_width=True):
                database.cancel_request_by_nurse(active_request['id'], nurse['id'])
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
                    database.submit_payment(nurse['id'], card_num, amount)
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
                        database.submit_payment(nurse['id'], card_num, amount)
                        st.success("✅ تم إرسال الدفعة للإدارة للمراجعة.")
                    else:
                        st.error("⚠️ رقم الكرت غير صالح.")

        st.markdown("---")
        st.markdown("### 🗺️ تحديد موقعك الميداني لتلقي الطلبات")
        st.info("📍 انقر على موقعك في الخريطة لتحديده (زر 📍 يقرّب الخريطة إلى مكانك الحالي، ثم انقر عليه).")

        saved_loc = st.session_state['nurse_loc']
        m_loc = folium.Map(location=list(saved_loc) if saved_loc else [32.8872, 13.1913],
                           zoom_start=14 if saved_loc else 12)
        plugins.LocateControl(
            position="topleft", drawCircle=False, drawMarker=True,
            strings={"title": "📍 موقعي الحالي"}
        ).add_to(m_loc)
        m_loc.add_child(folium.LatLngPopup())
        if saved_loc:
            folium.Marker(list(saved_loc), tooltip="📍 موقعي المحدد",
                          icon=folium.Icon(color='green', icon='user')).add_to(m_loc)

        # إصلاح زر القبول: مفتاح ثابت للخريطة + إرجاع النقرة فقط.
        # سابقاً كان ظهور قائمة الطلبات وزر "قبول" مرتبطاً بقيمة last_clicked القادمة
        # من الخريطة في نفس الدورة؛ عند الضغط على الزر (أو التحديث التلقائي كل 5 ثوانٍ)
        # يُعاد تشغيل السكربت وتُبنى الخريطة من جديد فتعود last_clicked فارغة،
        # فيختفي الزر قبل معالجة الضغطة ولا يحدث شيء.
        loc_data = st_folium(
            m_loc, height=260, use_container_width=True,
            key="nurse_location_map", returned_objects=["last_clicked"]
        )

        if loc_data and loc_data.get("last_clicked"):
            clicked = (round(loc_data["last_clicked"]["lat"], 6),
                       round(loc_data["last_clicked"]["lng"], 6))
            if clicked != st.session_state['nurse_loc']:
                # حفظ الموقع في الجلسة وفي الرابط حتى لا يضيع مع التحديث أو إعادة التحميل
                st.session_state['nurse_loc'] = clicked
                st.query_params["loc"] = f"{clicked[0]},{clicked[1]}"
                st.rerun()

        if st.session_state['nurse_loc']:
            my_lat, my_lng = st.session_state['nurse_loc']
            st.success("✅ تم تحديد موقعك الجغرافي بنجاح. نطاق البحث: 10 كم. (انقر على الخريطة لتغييره)")

            is_online = st.toggle("🟢 أنا متاح الآن (بدء استقبال الطلبات القريبة)", key="nurse_online")

            if is_online:
                st_autorefresh(interval=5000, key="nurse_refresh")
                pending_requests = database.get_nearby_pending_requests(
                    nurse['gender'], my_lat, my_lng, max_radius_km=10
                )

                st.markdown("---")
                st.markdown("### 📋 الطلبات القريبة المتاحة")

                if st.session_state.get('accept_error'):
                    st.error(st.session_state.pop('accept_error'))

                if len(pending_requests) == 0:
                    st.info("🔍 لا توجد طلبات معلقة قريبة منك حالياً. يتم التحديث تلقائياً كل 5 ثوانٍ...")
                else:
                    for req in pending_requests:
                        st.markdown(f"""
                        <div class="custom-card">
                          <div style="display:flex;justify-content:space-between;align-items:center;flex-wrap:wrap;gap:8px;">
                            <div>
                              <strong style="font-size:1.1rem;color:#0e7490;">🏥 {html.escape(str(req['service_type']))}</strong>
                              <span style="opacity:0.8;font-size:0.85rem;margin-right:8px;">(يبعد: {req['distance_km']:.1f} كم 📍)</span>
                            </div>
                            <div style="font-size:1rem;font-weight:800;color:#059669;">
                              💰 الميزانية: {html.escape(str(req['min_price']))} – {html.escape(str(req['max_price']))} د.ل
                            </div>
                          </div>
                          <div style="margin-top:0.4rem;font-size:0.95rem;">
                            👤 <strong>المريض:</strong> {html.escape(str(req['patient_name']))} (العمر: {html.escape(str(req['patient_age']))})
                          </div>
                          <div style="font-size:0.95rem;">
                            📍 <strong>العنوان:</strong> {html.escape(str(req['location_text']))}
                          </div>
                        </div>
                        """, unsafe_allow_html=True)

                        # Task 3: معالجة الـ Race Condition مع منع تكرار المهام
                        # نستخدم on_click: يُنفَّذ القبول قبل إعادة رسم الصفحة مباشرة،
                        # فلا يضيع الضغط حتى لو تزامن مع التحديث التلقائي.
                        st.button(
                            "✅ قبول واستلام هذا الطلب",
                            key=f"btn_{req['id']}",
                            type="primary",
                            use_container_width=True,
                            on_click=_accept_request_cb,
                            args=(req['id'], nurse['id']),
                        )

                        st.markdown("<div style='margin-bottom:0.75rem;'></div>", unsafe_allow_html=True)
        else:
            st.warning("⚠️ يرجى النقر على الخريطة أو زر 📍 لتحديد موقعك أولاً حتى تظهر لك الطلبات الميدانية القريبة.")
