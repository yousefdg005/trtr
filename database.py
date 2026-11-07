import streamlit as st
import psycopg2
from psycopg2.extras import RealDictCursor

def get_connection():
    return psycopg2.connect(st.secrets["database"]["url"], cursor_factory=RealDictCursor)

# --- دوال الطلبات والمسافات (PostGIS) ---
def create_request(service, name, phone, gender, age, desc, loc_text, lat, lng, min_p, max_p):
    conn = get_connection()
    cur = conn.cursor()
    cur.execute(
        """INSERT INTO requests 
        (service_type, patient_name, patient_phone, patient_gender, patient_age, service_desc, location_text, location_lat, location_lng, min_price, max_price) 
        VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s) RETURNING id""",
        (service, name, phone, gender, age, desc, loc_text, lat, lng, min_p, max_p)
    )
    req_id = cur.fetchone()['id']
    conn.commit()
    cur.close()
    conn.close()
    return req_id

def get_nearby_pending_requests(nurse_gender, nurse_lat, nurse_lng, max_radius_km=10):
    conn = get_connection()
    cur = conn.cursor()
    query = """
        SELECT *, 
        (ST_DistanceSphere(ST_MakePoint(location_lng, location_lat), ST_MakePoint(%s, %s)) / 1000.0) as distance_km
        FROM requests 
        WHERE status = 'pending' AND patient_gender = %s 
        AND (ST_DistanceSphere(ST_MakePoint(location_lng, location_lat), ST_MakePoint(%s, %s)) / 1000.0) <= %s
        ORDER BY distance_km ASC
    """
    cur.execute(query, (nurse_lng, nurse_lat, nurse_gender, nurse_lng, nurse_lat, max_radius_km))
    requests = cur.fetchall()
    cur.close()
    conn.close()
    return requests

# الدالة التي كانت مفقودة وتسببت بالخطأ
def get_all_requests():
    conn = get_connection()
    cur = conn.cursor()
    cur.execute("SELECT * FROM requests ORDER BY created_at DESC")
    requests = cur.fetchall()
    cur.close()
    conn.close()
    return requests

def accept_request(req_id, nurse_username, nurse_name):
    conn = get_connection()
    cur = conn.cursor()
    cur.execute("UPDATE requests SET status = 'accepted', accepted_by = %s, accepted_nurse_username = %s WHERE id = %s", 
                (nurse_name, nurse_username, req_id))
    cur.execute("UPDATE nurses SET debt = debt + 10 WHERE username = %s RETURNING debt", (nurse_username,))
    new_debt = cur.fetchone()['debt']
    if new_debt >= 50:
        cur.execute("UPDATE nurses SET status = 'debt_blocked' WHERE username = %s", (nurse_username,))
    conn.commit()
    cur.close()
    conn.close()

def get_request_status(req_id):
    conn = get_connection()
    cur = conn.cursor()
    cur.execute("""
        SELECT r.status, r.accepted_by, n.phone as nurse_phone 
        FROM requests r 
        LEFT JOIN nurses n ON r.accepted_nurse_username = n.username 
        WHERE r.id = %s
    """, (req_id,))
    res = cur.fetchone()
    cur.close()
    conn.close()
    return res

# --- دوال الإلغاء واسترداد العمولة ---
def cancel_request_by_patient(req_id):
    conn = get_connection()
    cur = conn.cursor()
    cur.execute("SELECT status, accepted_nurse_username FROM requests WHERE id = %s", (req_id,))
    req = cur.fetchone()
    
    if req and req['status'] == 'accepted' and req['accepted_nurse_username']:
        cur.execute("UPDATE nurses SET debt = GREATEST(debt - 10, 0) WHERE username = %s RETURNING debt", (req['accepted_nurse_username'],))
        new_debt = cur.fetchone()['debt']
        if new_debt < 50:
            cur.execute("UPDATE nurses SET status = 'approved' WHERE username = %s AND status = 'debt_blocked'", (req['accepted_nurse_username'],))
            
    cur.execute("UPDATE requests SET status = 'cancelled_by_patient' WHERE id = %s", (req_id,))
    conn.commit()
    cur.close()
    conn.close()

def get_accepted_request_for_nurse(nurse_username):
    conn = get_connection()
    cur = conn.cursor()
    cur.execute("SELECT * FROM requests WHERE status = 'accepted' AND accepted_nurse_username = %s ORDER BY created_at DESC LIMIT 1", (nurse_username,))
    req = cur.fetchone()
    cur.close()
    conn.close()
    return req

def cancel_request_by_nurse(req_id, nurse_username):
    conn = get_connection()
    cur = conn.cursor()
    cur.execute("UPDATE nurses SET debt = GREATEST(debt - 10, 0) WHERE username = %s RETURNING debt", (nurse_username,))
    new_debt = cur.fetchone()['debt']
    if new_debt < 50:
        cur.execute("UPDATE nurses SET status = 'approved' WHERE username = %s AND status = 'debt_blocked'", (nurse_username,))
        
    cur.execute("UPDATE requests SET status = 'cancelled_by_nurse' WHERE id = %s", (req_id,))
    conn.commit()
    cur.close()
    conn.close()

# --- دوال الممرضين والعضوية ---
def register_nurse(username, password, name, phone, gender, specialty, proof_info):
    conn = get_connection()
    cur = conn.cursor()
    try:
        cur.execute(
            """INSERT INTO nurses (username, password, name, phone, gender, specialty, proof_info) 
            VALUES (%s, %s, %s, %s, %s, %s, %s)""",
            (username, password, name, phone, gender, specialty, proof_info)
        )
        conn.commit()
        return True, "تم إرسال طلبك للإدارة بنجاح. يرجى انتظار القبول."
    except psycopg2.errors.UniqueViolation:
        return False, "اسم المستخدم هذا موجود مسبقاً، اختر اسماً آخر."
    except Exception as e:
        return False, str(e)
    finally:
        cur.close()
        conn.close()

def login_nurse(username, password):
    conn = get_connection()
    cur = conn.cursor()
    cur.execute("SELECT * FROM nurses WHERE username = %s AND password = %s", (username, password))
    nurse = cur.fetchone()
    cur.close()
    conn.close()
    return nurse

def get_pending_nurses():
    conn = get_connection()
    cur = conn.cursor()
    cur.execute("SELECT * FROM nurses WHERE status = 'pending' ORDER BY created_at DESC")
    nurses = cur.fetchall()
    cur.close()
    conn.close()
    return nurses

def update_nurse_status(nurse_id, status):
    conn = get_connection()
    cur = conn.cursor()
    cur.execute("UPDATE nurses SET status = %s WHERE id = %s", (status, nurse_id))
    conn.commit()
    cur.close()
    conn.close()

def get_all_nurses():
    conn = get_connection()
    cur = conn.cursor()
    cur.execute("SELECT * FROM nurses ORDER BY created_at DESC")
    nurses = cur.fetchall()
    cur.close()
    conn.close()
    return nurses

# --- دوال النظام والمدفوعات ---
def get_system_status():
    conn = get_connection()
    cur = conn.cursor()
    cur.execute("SELECT value FROM system_settings WHERE key = 'is_active'")
    res = cur.fetchone()
    cur.close()
    conn.close()
    return res['value'] == 'true' if res else True

def set_system_status(is_active):
    val = 'true' if is_active else 'false'
    conn = get_connection()
    cur = conn.cursor()
    cur.execute("UPDATE system_settings SET value = %s WHERE key = 'is_active'", (val,))
    conn.commit()
    cur.close()
    conn.close()

def submit_payment(username, card_number, amount):
    conn = get_connection()
    cur = conn.cursor()
    cur.execute("INSERT INTO payments (nurse_username, card_number, amount) VALUES (%s, %s, %s)", (username, card_number, amount))
    conn.commit()
    cur.close()
    conn.close()

def get_pending_payments():
    conn = get_connection()
    cur = conn.cursor()
    cur.execute("""
        SELECT p.*, n.name as nurse_name, n.phone 
        FROM payments p 
        JOIN nurses n ON p.nurse_username = n.username 
        WHERE p.status = 'pending' ORDER BY p.created_at ASC
    """)
    payments = cur.fetchall()
    cur.close()
    conn.close()
    return payments

def review_payment(payment_id, username, amount, action):
    conn = get_connection()
    cur = conn.cursor()
    cur.execute("UPDATE payments SET status = %s WHERE id = %s", (action, payment_id))
    if action == 'approved':
        cur.execute("UPDATE nurses SET debt = GREATEST(debt - %s, 0) WHERE username = %s RETURNING debt", (amount, username))
        new_debt = cur.fetchone()['debt']
        if new_debt < 50:
            cur.execute("UPDATE nurses SET status = 'approved' WHERE username = %s AND status = 'debt_blocked'", (username,))
    conn.commit()
    cur.close()
    conn.close()