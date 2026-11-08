import streamlit as st
import psycopg2
from psycopg2.extras import RealDictCursor
from werkzeug.security import generate_password_hash, check_password_hash

def get_connection():
    return psycopg2.connect(st.secrets["database"]["url"], cursor_factory=RealDictCursor)

# --- دوال الطلبات والمسافات (PostGIS) ---
def create_request(service, name, phone, gender, age, desc, loc_text, lat, lng, min_p, max_p):
    conn = get_connection()
    cur = conn.cursor()
    try:
        cur.execute(
            """INSERT INTO requests 
            (service_type, patient_name, patient_phone, patient_gender, patient_age, service_desc, location_text, location_lat, location_lng, min_price, max_price) 
            VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s) RETURNING id""",
            (service, name, phone, gender, age, desc, loc_text, lat, lng, min_p, max_p)
        )
        req_id = cur.fetchone()['id']
        conn.commit()
        return req_id
    except Exception:
        conn.rollback()
        raise
    finally:
        cur.close()
        conn.close()

def get_nearby_pending_requests(nurse_gender, nurse_lat, nurse_lng, max_radius_km=10):
    conn = get_connection()
    cur = conn.cursor()
    try:
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
        return requests
    except Exception:
        conn.rollback()
        raise
    finally:
        cur.close()
        conn.close()

def get_all_requests():
    conn = get_connection()
    cur = conn.cursor()
    try:
        # Task 4 & 5: JOIN with nurses to fetch nurse name dynamically
        query = """
            SELECT r.*, n.name AS accepted_by
            FROM requests r
            LEFT JOIN nurses n ON r.accepted_nurse_id = n.id
            ORDER BY r.created_at DESC
        """
        cur.execute(query)
        requests = cur.fetchall()
        return requests
    except Exception:
        conn.rollback()
        raise
    finally:
        cur.close()
        conn.close()

def accept_request(req_id, nurse_id):
    """
    Race condition guard + Debt standing validation check.
    """
    conn = get_connection()
    cur = conn.cursor()
    try:
        cur.execute(
            """UPDATE requests 
               SET status = 'accepted', accepted_nurse_id = %s 
               WHERE id = %s AND status = 'pending'""", 
            (nurse_id, req_id)
        )
        if cur.rowcount == 0:
            conn.rollback()
            return False

        # التحقق من أن الممرض في وضع جيد وليست عليه ديون متجاوزة
        cur.execute("SELECT status FROM nurses WHERE id = %s", (nurse_id,))
        nurse = cur.fetchone()
        if not nurse or nurse['status'] != 'approved':
            conn.rollback()
            return False

        cur.execute("UPDATE nurses SET debt = debt + 10 WHERE id = %s RETURNING debt", (nurse_id,))
        nurse_row = cur.fetchone()
        if nurse_row and nurse_row['debt'] >= 50:
            cur.execute("UPDATE nurses SET status = 'debt_blocked' WHERE id = %s", (nurse_id,))

        conn.commit()
        return True
    except Exception:
        conn.rollback()
        raise
    finally:
        cur.close()
        conn.close()

def get_request_status(req_id):
    conn = get_connection()
    cur = conn.cursor()
    try:
        cur.execute("""
            SELECT r.status, n.name as accepted_by, n.phone as nurse_phone 
            FROM requests r 
            LEFT JOIN nurses n ON r.accepted_nurse_id = n.id 
            WHERE r.id = %s
        """, (req_id,))
        res = cur.fetchone()
        return res
    except Exception:
        conn.rollback()
        raise
    finally:
        cur.close()
        conn.close()

# --- دوال الإلغاء واسترداد العمولة ---
def cancel_request_by_patient(req_id):
    """
    Atomic conditional cancellation: transitions the request in a single
    statement and never overwrites an existing cancellation or an unknown id.
    Returns: True if cancelled now (refund applied when a nurse was attached),
    False if the request does not exist or was already cancelled.
    """
    conn = get_connection()
    cur = conn.cursor()
    try:
        cur.execute(
            """UPDATE requests 
               SET status = 'cancelled_by_patient' 
               WHERE id = %s AND status IN ('pending', 'accepted') 
               RETURNING accepted_nurse_id""",
            (req_id,)
        )
        row = cur.fetchone()
        if row is None:
            # الطلب غير موجود أو أُلغي مسبقاً — لا يُعدّل شيئاً ولا يسترد عمولة
            conn.rollback()
            return False

        if row['accepted_nurse_id']:
            cur.execute("UPDATE nurses SET debt = GREATEST(debt - 10, 0) WHERE id = %s RETURNING debt",
                        (row['accepted_nurse_id'],))
            nurse_row = cur.fetchone()
            if nurse_row and nurse_row['debt'] < 50:
                cur.execute("UPDATE nurses SET status = 'approved' WHERE id = %s AND status = 'debt_blocked'",
                            (row['accepted_nurse_id'],))

        conn.commit()
        return True
    except Exception:
        conn.rollback()
        raise
    finally:
        cur.close()
        conn.close()

def get_accepted_request_for_nurse(nurse_id):
    conn = get_connection()
    cur = conn.cursor()
    try:
        cur.execute(
            "SELECT * FROM requests WHERE status = 'accepted' AND accepted_nurse_id = %s ORDER BY created_at DESC LIMIT 1",
            (nurse_id,)
        )
        req = cur.fetchone()
        return req
    except Exception:
        conn.rollback()
        raise
    finally:
        cur.close()
        conn.close()

def cancel_request_by_nurse(req_id, nurse_id):
    """
    Ownership-guarded cancellation: only the assigned nurse may cancel a request
    she currently holds (status = 'accepted' AND accepted_nurse_id matches).
    Returns: True if cancelled now and the commission was refunded,
    False if the request is not hers / not active / unknown — nothing is touched.
    """
    conn = get_connection()
    cur = conn.cursor()
    try:
        cur.execute(
            """UPDATE requests 
               SET status = 'cancelled_by_nurse' 
               WHERE id = %s AND status = 'accepted' AND accepted_nurse_id = %s""",
            (req_id, nurse_id)
        )
        if cur.rowcount == 0:
            # الطلب ليس مخصصاً لهذا الممرض أو لم يعد نشطاً — لا خصم ولا إلغاء
            conn.rollback()
            return False

        cur.execute("UPDATE nurses SET debt = GREATEST(debt - 10, 0) WHERE id = %s RETURNING debt",
                    (nurse_id,))
        nurse_row = cur.fetchone()
        if nurse_row and nurse_row['debt'] < 50:
            cur.execute("UPDATE nurses SET status = 'approved' WHERE id = %s AND status = 'debt_blocked'",
                        (nurse_id,))

        conn.commit()
        return True
    except Exception:
        conn.rollback()
        raise
    finally:
        cur.close()
        conn.close()

# --- دوال الممرضين والعضوية ---
def register_nurse(username, password, name, phone, gender, specialty, proof_info):
    """
    Task 1: Secure password hashing using werkzeug.security generate_password_hash.
    """
    conn = get_connection()
    cur = conn.cursor()
    try:
        hashed_password = generate_password_hash(password)
        cur.execute(
            """INSERT INTO nurses (username, password, name, phone, gender, specialty, proof_info) 
            VALUES (%s, %s, %s, %s, %s, %s, %s)""",
            (username, hashed_password, name, phone, gender, specialty, proof_info)
        )
        conn.commit()
        return True, "تم إرسال طلبك للإدارة بنجاح. يرجى انتظار القبول."
    except psycopg2.errors.UniqueViolation:
        conn.rollback()
        return False, "اسم المستخدم هذا موجود مسبقاً، اختر اسماً آخر."
    except Exception as e:
        conn.rollback()
        return False, str(e)
    finally:
        cur.close()
        conn.close()

def login_nurse(username, password):
    """
    Task 1: Retrieve user by username only, then securely verify password hash.
    """
    conn = get_connection()
    cur = conn.cursor()
    try:
        cur.execute("SELECT * FROM nurses WHERE username = %s", (username,))
        nurse = cur.fetchone()
        if nurse and check_password_hash(nurse['password'], password):
            return nurse
        return None
    except Exception:
        conn.rollback()
        raise
    finally:
        cur.close()
        conn.close()

def get_nurse_by_id(nurse_id):
    """
    Helper to refresh nurse profile/session by ID.
    """
    conn = get_connection()
    cur = conn.cursor()
    try:
        cur.execute("SELECT * FROM nurses WHERE id = %s", (nurse_id,))
        nurse = cur.fetchone()
        return nurse
    except Exception:
        conn.rollback()
        raise
    finally:
        cur.close()
        conn.close()

def get_pending_nurses():
    conn = get_connection()
    cur = conn.cursor()
    try:
        cur.execute("SELECT * FROM nurses WHERE status = 'pending' ORDER BY created_at DESC")
        nurses = cur.fetchall()
        return nurses
    except Exception:
        conn.rollback()
        raise
    finally:
        cur.close()
        conn.close()

def update_nurse_status(nurse_id, status):
    conn = get_connection()
    cur = conn.cursor()
    try:
        cur.execute("UPDATE nurses SET status = %s WHERE id = %s", (status, nurse_id))
        conn.commit()
    except Exception:
        conn.rollback()
        raise
    finally:
        cur.close()
        conn.close()

def get_all_nurses():
    conn = get_connection()
    cur = conn.cursor()
    try:
        cur.execute("SELECT * FROM nurses ORDER BY created_at DESC")
        nurses = cur.fetchall()
        return nurses
    except Exception:
        conn.rollback()
        raise
    finally:
        cur.close()
        conn.close()

# --- دوال النظام والمدفوعات ---
def get_system_status():
    conn = get_connection()
    cur = conn.cursor()
    try:
        cur.execute("SELECT value FROM system_settings WHERE key = 'is_active'")
        res = cur.fetchone()
        return res['value'] == 'true' if res else True
    except Exception:
        conn.rollback()
        raise
    finally:
        cur.close()
        conn.close()

def set_system_status(is_active):
    """
    UPSERT implementation to safely update or insert system status.
    """
    val = 'true' if is_active else 'false'
    conn = get_connection()
    cur = conn.cursor()
    try:
        cur.execute(
            """INSERT INTO system_settings (key, value) VALUES ('is_active', %s)
               ON CONFLICT (key) DO UPDATE SET value = EXCLUDED.value""",
            (val,)
        )
        conn.commit()
        return True
    except Exception:
        conn.rollback()
        raise
    finally:
        cur.close()
        conn.close()

def submit_payment(nurse_id, card_number, amount):
    """
    Task 4: Store nurse_id (Integer FK) instead of nurse_username.
    """
    conn = get_connection()
    cur = conn.cursor()
    try:
        cur.execute("INSERT INTO payments (nurse_id, card_number, amount) VALUES (%s, %s, %s)",
                    (nurse_id, card_number, amount))
        conn.commit()
    except Exception:
        conn.rollback()
        raise
    finally:
        cur.close()
        conn.close()

def get_pending_payments():
    """
    Task 4: JOIN payments on p.nurse_id = n.id instead of nurse_username.
    """
    conn = get_connection()
    cur = conn.cursor()
    try:
        cur.execute("""
            SELECT p.*, n.name as nurse_name, n.phone 
            FROM payments p 
            JOIN nurses n ON p.nurse_id = n.id 
            WHERE p.status = 'pending' ORDER BY p.created_at ASC
        """)
        payments = cur.fetchall()
        return payments
    except Exception:
        conn.rollback()
        raise
    finally:
        cur.close()
        conn.close()

def review_payment(payment_id, nurse_id, amount, action):
    """
    Double refund prevention by enforcing status = 'pending' check.
    """
    if action not in ('approved', 'rejected'):
        raise ValueError(f"invalid payment action: {action!r}")
    if action == 'approved' and (amount is None or amount <= 0):
        raise ValueError("payment amount must be positive")

    conn = get_connection()
    cur = conn.cursor()
    try:
        cur.execute(
            "UPDATE payments SET status = %s WHERE id = %s AND status = 'pending'",
            (action, payment_id)
        )
        if cur.rowcount == 0:
            conn.rollback()
            return False

        if action == 'approved':
            cur.execute("UPDATE nurses SET debt = GREATEST(debt - %s, 0) WHERE id = %s RETURNING debt",
                        (amount, nurse_id))
            nurse_row = cur.fetchone()
            if nurse_row and nurse_row['debt'] < 50:
                cur.execute("UPDATE nurses SET status = 'approved' WHERE id = %s AND status = 'debt_blocked'",
                            (nurse_id,))
        conn.commit()
        return True
    except Exception:
        conn.rollback()
        raise
    finally:
        cur.close()
        conn.close()
