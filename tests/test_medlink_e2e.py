"""MedLink end-to-end integration tests.

Structure
---------
``TestMedLinkEndToEndJourney``
    The complete user journey from the product spec, one test method per step,
    executed in definition order on ONE shared database state:

      1. Admin activates the system
      2. Nurse 1 registers -> admin approves
      3. Nurse 2 registers -> admin approves
      4. Patient creates a request at PostGIS coordinates
      5. Nurse 1 fetches nearby pending requests -> sees the new request
      6. RACE: nurses 1 & 2 accept the same request concurrently -> exactly one wins
      7. Winning nurse reaches 50 LYD debt after 5 accepts -> auto debt_blocked
      8. Blocked nurse submits a Madar card -> admin approves -> debt cleared, unblocked
      9. New accept + patient cancellation -> 10 LYD commission refunded

``known_bug`` marked tests
    Reproduce defects that exist in ``database.py`` today (see BUGFIXES.md for
    the drop-in fixes). They FAIL on the current code and pass once the fixes
    are applied. Run the happy path only with:  pytest -m "not known_bug"

Race tests use real threads on real connections — ``accept_request`` opens its
own connection per call, so this faithfully simulates two nurses clicking at
the same instant on two different app servers.
"""

import threading

import pytest
from werkzeug.security import check_password_hash

import database

# Central Tripoli — same default the portal apps use. (lat, lng)
TRIPOLI_LAT, TRIPOLI_LNG = 32.8872, 13.1913
KM_PER_DEGREE_LAT = 111.32  # good enough for test-coord arithmetic


# ─────────────────────────── helpers ───────────────────────────

def run_concurrent_accept(req_id, nurse_ids):
    """Fire accept_request from one thread per nurse, released simultaneously."""
    barrier = threading.Barrier(len(nurse_ids))
    results = [None] * len(nurse_ids)

    def worker(idx, nurse_id):
        try:
            barrier.wait(timeout=15)
            results[idx] = database.accept_request(req_id, nurse_id)
        except Exception as exc:  # surface any crash into the assertions below
            results[idx] = exc

    threads = [
        threading.Thread(target=worker, args=(i, nid), name=f"nurse-{nid}")
        for i, nid in enumerate(nurse_ids)
    ]
    for t in threads:
        t.start()
    for t in threads:
        t.join(timeout=30)
    assert not any(t.is_alive() for t in threads), (
        "accept_request appears deadlocked under concurrent calls"
    )
    for r in results:
        assert not isinstance(r, Exception), f"accept_request raised under concurrency: {r!r}"
        assert r is not None, "accept_request returned None (must be True/False)"
    return results


def nurse_row(db, nurse_id):
    return db.fetchone("SELECT * FROM nurses WHERE id = %s", (nurse_id,))


def request_row(db, req_id):
    return db.fetchone("SELECT * FROM requests WHERE id = %s", (req_id,))


# ─────────────────── the full end-to-end journey ───────────────────

class TestMedLinkEndToEndJourney:
    """Steps 1–9 run sequentially on a single shared database state."""

    state = {}  # carries ids across the ordered steps

    @pytest.fixture(autouse=True, scope="class")
    def _reset_once(self, db_url):
        from conftest import reset_database

        reset_database(db_url)
        TestMedLinkEndToEndJourney.state = {}
        yield

    def test_step01_admin_activates_system(self, db):
        database.set_system_status(True)
        assert database.get_system_status() is True, \
            "system should be active after set_system_status(True)"

        # sanity: the master switch actually toggles both ways
        database.set_system_status(False)
        assert database.get_system_status() is False, "system switch did not turn OFF"
        database.set_system_status(True)
        assert database.get_system_status() is True, "system switch did not turn back ON"

    def test_step02_nurse1_registers_and_admin_approves(self, make_nurse, db):
        nurse1 = make_nurse()  # default: approved=False at registration time
        assert nurse1["id"], "register_nurse must create a nurse row"

        pending = database.get_pending_nurses()
        assert any(n["id"] == nurse1["id"] for n in pending), \
            "freshly registered nurse must appear in get_pending_nurses()"
        assert all(n["status"] == "pending" for n in pending), \
            "new registrations must default to status 'pending'"

        # wrong password must not authenticate, even before approval
        assert database.login_nurse(nurse1["username"], "totally-wrong") is None, \
            "login_nurse accepted a wrong password"

        database.update_nurse_status(nurse1["id"], "approved")

        refreshed = database.get_nurse_by_id(nurse1["id"])
        assert refreshed["status"] == "approved", "admin approval did not stick"
        assert refreshed["debt"] == 0, "new nurse must start with zero debt"

        logged_in = database.login_nurse(nurse1["username"], nurse1["password"])
        assert logged_in is not None, "correct credentials must log the nurse in"
        assert logged_in["id"] == nurse1["id"]

        self.state["nurse1"] = nurse1

    def test_step03_nurse2_registers_and_admin_approves(self, make_nurse):
        nurse2 = make_nurse()
        database.update_nurse_status(nurse2["id"], "approved")
        assert database.get_nurse_by_id(nurse2["id"])["status"] == "approved"
        self.state["nurse2"] = nurse2

    def test_step04_patient_creates_request(self, make_request, db):
        req_id = make_request()  # male patient at central Tripoli
        assert isinstance(req_id, int), "create_request must return the new request id"

        row = request_row(db, req_id)
        assert row["status"] == "pending", "new request must start 'pending'"
        assert row["accepted_nurse_id"] is None

        status = database.get_request_status(req_id)
        assert status["status"] == "pending"
        assert status["accepted_by"] is None, "unaccepted request must have no nurse joined"

        self.state["req_id"] = req_id

    def test_step05_nurse1_sees_request_nearby(self, db):
        req_id = self.state["req_id"]

        nearby = database.get_nearby_pending_requests(
            "ذكر", TRIPOLI_LAT, TRIPOLI_LNG, max_radius_km=10
        )
        ids = {r["id"] for r in nearby}
        assert req_id in ids, (
            f"request {req_id} created ~0km from the nurse must appear in "
            f"get_nearby_pending_requests(); got {ids}"
        )
        mine = next(r for r in nearby if r["id"] == req_id)
        assert mine["distance_km"] <= 10, "distance_km must respect the 10km radius"
        assert 0 <= mine["distance_km"] < 1, "co-located request should be ~0km away"

    def test_step06_race_condition_exactly_one_winner(self, db):
        nurse1, nurse2 = self.state["nurse1"], self.state["nurse2"]
        req_id = self.state["req_id"]

        results = run_concurrent_accept(req_id, [nurse1["id"], nurse2["id"]])
        winners = [nid for nid, ok in zip([nurse1["id"], nurse2["id"]], results) if ok]

        assert len(winners) == 1, (
            f"exactly one nurse must win the race, but results were {results!r} "
            f"(True count = {results.count(True)})"
        )
        winner_id, loser_id = winners[0], (
            nurse2["id"] if winners[0] == nurse1["id"] else nurse1["id"]
        )

        row = request_row(db, req_id)
        assert row["status"] == "accepted", "winner's accept must mark request accepted"
        assert row["accepted_nurse_id"] == winner_id, \
            "request must be assigned to the winning nurse only"

        # winner pays the 10 LYD commission, loser pays nothing
        assert nurse_row(db, winner_id)["debt"] == 10, \
            "race winner must be charged exactly 10 LYD commission"
        assert nurse_row(db, loser_id)["debt"] == 0, \
            "race loser must NOT be charged any commission"

        assert database.get_request_status(req_id)["accepted_by"] is not None, \
            "patient tracking view must now see the accepting nurse's name"

        self.state["winner_id"] = winner_id
        self.state["loser_id"] = loser_id

    def test_step07_five_accepts_reach_50_lyd_and_block(self, make_request, db):
        winner_id = self.state["winner_id"]
        # The race win was accept #1 (debt 10). Four more accepts = 5 total in a row.
        for expected_debt in (20, 30, 40, 50):
            req_id = make_request()
            assert database.accept_request(req_id, winner_id) is True, (
                f"approved nurse with {expected_debt - 10} LYD debt must be able to "
                f"accept a new request"
            )
            row = nurse_row(db, winner_id)
            assert row["debt"] == expected_debt, \
                f"after {expected_debt // 10} accepts debt must be {expected_debt} LYD, got {row['debt']}"
            if expected_debt < 50:
                assert row["status"] == "approved", \
                    "nurse below the 50 LYD threshold must remain 'approved'"

        row = nurse_row(db, winner_id)
        assert row["debt"] == 50, f"debt must reach exactly 50 LYD, got {row['debt']}"
        assert row["status"] == "debt_blocked", (
            "reaching 50 LYD debt must automatically switch the nurse to 'debt_blocked'"
        )
        assert database.get_accepted_request_for_nurse(winner_id) is not None, \
            "blocked nurse keeps ownership of already-accepted work"

    def test_step08_payment_flow_unblocks_nurse(self, db):
        winner_id = self.state["winner_id"]

        database.submit_payment(winner_id, "41111111111111", 50)

        pending = database.get_pending_payments()
        match = [p for p in pending if p["nurse_id"] == winner_id]
        assert len(match) == 1, "submitted card must appear in get_pending_payments()"
        payment = match[0]
        assert payment["amount"] == 50
        assert payment["card_number"] == "41111111111111"
        assert payment["nurse_name"], "payments JOIN must expose the nurse name for the admin"
        assert payment["phone"], "payments JOIN must expose the nurse phone for the admin"

        database.review_payment(payment["id"], winner_id, 50, "approved")

        row = nurse_row(db, winner_id)
        assert row["debt"] == 0, f"50 LYD approval must clear the 50 LYD debt, got {row['debt']}"
        assert row["status"] == "approved", \
            "paying off the debt must return the nurse to 'approved'"
        assert db.fetchone("SELECT status FROM payments WHERE id = %s",
                           (payment["id"],))["status"] == "approved"

        # the paid card must leave the admin's pending queue
        assert all(p["id"] != payment["id"] for p in database.get_pending_payments()), \
            "reviewed payment must no longer be listed as pending"

    def test_step09_patient_cancellation_refunds_commission(self, make_request, db):
        winner = (self.state["nurse1"] if self.state["winner_id"] == self.state["nurse1"]["id"]
                  else self.state["nurse2"])

        req_id = make_request()
        assert database.accept_request(req_id, self.state["winner_id"]) is True
        assert nurse_row(db, self.state["winner_id"])["debt"] == 10, \
            "fresh accept must add 10 LYD commission"

        database.cancel_request_by_patient(req_id)

        row = request_row(db, req_id)
        assert row["status"] == "cancelled_by_patient", \
            "patient cancellation must mark the request 'cancelled_by_patient'"
        assert nurse_row(db, self.state["winner_id"])["debt"] == 0, (
            "cancelling an accepted request must refund the nurse's 10 LYD commission "
            f"(debt is {nurse_row(db, self.state['winner_id'])['debt']})"
        )
        assert nurse_row(db, self.state["winner_id"])["status"] == "approved", \
            "a refunded nurse below the threshold must not stay blocked"

        status = database.get_request_status(req_id)
        assert status["status"] == "cancelled_by_patient"
        assert status["accepted_by"] == winner["name"], \
            "history must still show which nurse had been assigned"

        # admin operations log JOIN (Task 4 & 5)
        logged = next(r for r in database.get_all_requests() if r["id"] == req_id)
        assert logged["accepted_by"] == winner["name"], \
            "get_all_requests must LEFT-JOIN the assigned nurse's name"


# ─────────────────── standalone edge-case tests ───────────────────

def test_nearby_filters_respect_gender_radius_and_status(fresh_db, make_nurse, make_request):
    nurse = make_nurse()  # male nurse
    close_same_gender = make_request(patient_gender="ذكر")                    # ~0 km
    make_request(patient_gender="أنثى")                                       # ~0 km, wrong gender
    make_request(patient_gender="ذكر", lat=TRIPOLI_LAT + 0.2)                 # ~22 km, too far
    assert 0.2 * KM_PER_DEGREE_LAT > 10, "test coord assumption broken"

    nearby = database.get_nearby_pending_requests("ذكر", TRIPOLI_LAT, TRIPOLI_LNG)
    ids = {r["id"] for r in nearby}
    assert ids == {close_same_gender}, (
        f"only the close same-gender pending request should match, got {ids} "
        f"(expected {{{close_same_gender}}})"
    )

    # accepted work must disappear from the pending feed
    assert database.accept_request(close_same_gender, nurse["id"]) is True
    nearby_after = database.get_nearby_pending_requests("ذكر", TRIPOLI_LAT, TRIPOLI_LNG)
    assert close_same_gender not in {r["id"] for r in nearby_after}, \
        "an accepted request must no longer be offered to other nurses"


def test_race_loser_gets_no_side_effects(fresh_db, make_nurse, make_request, db):
    n1, n2 = make_nurse(), make_nurse()
    req_id = make_request()

    results = run_concurrent_accept(req_id, [n1["id"], n2["id"]])
    assert set(results) == {True, False}, \
        f"exactly one accept must succeed, got {results!r}"

    winner_id = n1["id"] if results[0] else n2["id"]
    loser_id = n2["id"] if results[0] else n1["id"]

    assert database.get_accepted_request_for_nurse(loser_id) is None, \
        "the losing nurse must not see the request as her active task"
    assert database.get_accepted_request_for_nurse(winner_id)["id"] == req_id
    assert nurse_row(db, loser_id)["debt"] == 0, "loser's debt must be untouched"
    assert nurse_row(db, winner_id)["debt"] == 10


def test_duplicate_username_is_rejected(fresh_db, db):
    ok, msg = database.register_nurse("dup_user", "pw-1", "أول", "0910000001",
                                      "ذكر", "تمريض عام", "proof")
    assert ok, f"first registration must succeed: {msg}"

    ok2, msg2 = database.register_nurse("dup_user", "pw-2", "ثانٍ", "0910000002",
                                        "أنثى", "تمريض عام", "proof")
    assert ok2 is False, "duplicate username must be rejected"
    assert "موجود مسبقاً" in msg2, (
        f"duplicate username must return the friendly Arabic message, got: {msg2!r}"
    )
    assert db.fetchone("SELECT COUNT(*) AS c FROM nurses WHERE username = 'dup_user'")["c"] == 1


def test_passwords_are_never_stored_in_plaintext(fresh_db, db):
    database.register_nurse("hash_check", "MyPlainPw123", "اسم", "0910000003",
                            "ذكر", "تمريض عام", "proof")
    stored = db.fetchone("SELECT password FROM nurses WHERE username = 'hash_check'")["password"]
    assert stored != "MyPlainPw123", "password must never be stored in plaintext"
    assert stored.startswith(("pbkdf2:", "scrypt:", "argon2:")), \
        f"expected a werkzeug hash format, got prefix {stored[:12]!r}"
    assert check_password_hash(stored, "MyPlainPw123")
    assert not check_password_hash(stored, "WrongPassword")


def test_patient_can_cancel_a_pending_request_without_refund(fresh_db, make_nurse, make_request, db):
    nurse = make_nurse()
    req_id = make_request()  # stays pending — nobody accepted it

    database.cancel_request_by_patient(req_id)

    assert request_row(db, req_id)["status"] == "cancelled_by_patient"
    assert nurse_row(db, nurse["id"])["debt"] == 0, \
        "cancelling a never-accepted request must not touch any nurse's debt"


def test_rejected_payment_leaves_debt_and_status_untouched(fresh_db, make_nurse, make_request, db):
    nurse = make_nurse()
    database.accept_request(make_request(), nurse["id"])
    database.accept_request(make_request(), nurse["id"])
    assert nurse_row(db, nurse["id"])["debt"] == 20

    database.submit_payment(nurse["id"], "42222222222222", 20)
    payment = database.get_pending_payments()[0]

    database.review_payment(payment["id"], nurse["id"], 20, "rejected")

    assert nurse_row(db, nurse["id"])["debt"] == 20, "a rejected card must not reduce debt"
    assert nurse_row(db, nurse["id"])["status"] == "approved"
    assert db.fetchone("SELECT status FROM payments WHERE id = %s",
                       (payment["id"],))["status"] == "rejected"


# ─────────────── known bugs (fail until BUGFIXES.md applied) ───────────────

@pytest.mark.known_bug
def test_known_bug_blocked_nurse_can_still_accept_requests(fresh_db, make_nurse, make_request, db):
    """BUG-1: accept_request never checks nurse status, so a debt_blocked nurse
    can keep accepting work (the guard lives only in the Streamlit UI)."""
    nurse = make_nurse()
    for _ in range(5):  # push the nurse to 50 LYD -> debt_blocked
        assert database.accept_request(make_request(), nurse["id"]) is True

    sixth = make_request()
    result = database.accept_request(sixth, nurse["id"])

    assert result is False, (
        "debt_blocked nurse accepted a new request — accept_request must refuse "
        "any nurse whose status is not 'approved' (fix: BUGFIXES.md BUG-1)"
    )
    assert request_row(db, sixth)["status"] == "pending", \
        "a refused accept must roll back, leaving the request 'pending'"


@pytest.mark.known_bug
def test_known_bug_nurse_can_cancel_someone_elses_request(fresh_db, make_nurse, make_request, db):
    """BUG-2: cancel_request_by_nurse never verifies the request belongs to the
    calling nurse, and refunds/cancels unconditionally."""
    holder = make_nurse()
    outsider = make_nurse()
    req_id = make_request()
    assert database.accept_request(req_id, holder["id"]) is True

    database.cancel_request_by_nurse(req_id, outsider["id"])

    row = request_row(db, req_id)
    assert row["status"] == "accepted", (
        f"an unrelated nurse must not be able to cancel a request held by someone "
        f"else (status became {row['status']!r}) — fix: BUGFIXES.md BUG-2"
    )
    assert row["accepted_nurse_id"] == holder["id"]
    assert nurse_row(db, holder["id"])["debt"] == 10, "holder's debt must be untouched"


@pytest.mark.known_bug
def test_known_bug_payment_can_be_approved_twice_for_double_refund(fresh_db, make_nurse,
                                                                   make_request, db):
    """BUG-3: review_payment re-applies credit because the status UPDATE has no
    `AND status = 'pending'` guard — approving the same card twice deducts twice."""
    nurse = make_nurse()
    for _ in range(3):
        database.accept_request(make_request(), nurse["id"])
    assert nurse_row(db, nurse["id"])["debt"] == 30

    database.submit_payment(nurse["id"], "43333333333333", 20)
    payment = database.get_pending_payments()[0]

    assert database.review_payment(payment["id"], nurse["id"], 20, "approved") is True
    assert nurse_row(db, nurse["id"])["debt"] == 10

    database.review_payment(payment["id"], nurse["id"], 20, "approved")  # duplicate click

    assert nurse_row(db, nurse["id"])["debt"] == 10, (
        "approving the same payment twice must be a no-op (second call must be "
        "rejected because the payment is no longer pending) — fix: BUGFIXES.md BUG-3"
    )


@pytest.mark.known_bug
def test_known_bug_system_toggle_is_silently_lost_without_seed_row(fresh_db, db):
    """BUG-4: set_system_status only runs UPDATE — on a database where the
    'is_active' row was never seeded, the admin's toggle disappears silently."""
    db.execute("DELETE FROM system_settings WHERE key = 'is_active'")

    database.set_system_status(False)

    assert database.get_system_status() is False, (
        "set_system_status(False) was lost because the settings row did not exist; "
        "it must UPSERT (fix: BUGFIXES.md BUG-4)"
    )


@pytest.mark.known_bug
def test_known_bug_patient_cancel_overwrites_nurse_cancellation_audit(fresh_db, make_nurse,
                                                                      make_request, db):
    """BUG-5: cancel_request_by_patient overwrites an already-cancelled request,
    corrupting who-cancelled-what in the operations log."""
    nurse = make_nurse()
    req_id = make_request()
    database.accept_request(req_id, nurse["id"])
    database.cancel_request_by_nurse(req_id, nurse["id"])
    assert request_row(db, req_id)["status"] == "cancelled_by_nurse"

    database.cancel_request_by_patient(req_id)  # stale patient tab clicks cancel

    assert request_row(db, req_id)["status"] == "cancelled_by_nurse", (
        "a second cancellation must not rewrite the first actor "
        "(status became 'cancelled_by_patient') — fix: BUGFIXES.md BUG-5"
    )


# ─────────────── privacy & input validation ───────────────

def test_nearby_feed_hides_patient_phone_until_accepted(fresh_db, make_nurse, make_request):
    """The pre-acceptance feed must never expose the patient's phone number;
    the assigned nurse sees it only after accepting (get_accepted_request_for_nurse)."""
    nurse = make_nurse()
    req_id = make_request()

    nearby = database.get_nearby_pending_requests("ذكر", TRIPOLI_LAT, TRIPOLI_LNG)
    row = next(r for r in nearby if r["id"] == req_id)
    assert "patient_phone" not in row, (
        "get_nearby_pending_requests leaks patient_phone to every nearby nurse"
    )
    assert row["patient_name"], "non-sensitive fields must still be present"

    # بعد القبول يصبح الرقم متاحاً للممرض المكلف فقط
    assert database.accept_request(req_id, nurse["id"]) is True
    accepted = database.get_accepted_request_for_nurse(nurse["id"])
    assert accepted["patient_phone"] == "0912222222", (
        "the assigned nurse must still receive the patient's phone after acceptance"
    )


def test_create_request_validates_phone_and_price_ordering(fresh_db):
    """create_request rejects malformed phones and inverted budgets; it accepts
    the normalized international +218 form."""
    with pytest.raises(ValueError, match="الهاتف"):
        database.create_request("علاج طبيعي", "مريض", "12345", "ذكر", 30, "", "طرابلس",
                                32.88, 13.19, 15, 50)
    with pytest.raises(ValueError, match="الهاتف"):
        database.create_request("علاج طبيعي", "مريض", "0912345", "ذكر", 30, "", "طرابلس",
                                32.88, 13.19, 15, 50)  # أقل من 10 أرقام
    with pytest.raises(ValueError, match="الحد الأدنى"):
        database.create_request("علاج طبيعي", "مريض", "0912345678", "ذكر", 30, "", "طرابلس",
                                32.88, 13.19, 50, 15)  # min > max

    # الصيغة الدولية +218 تُقبل، والحالة الصحيحة تنشئ طلباً فعلاً
    req_id = database.create_request("علاج طبيعي", "مريض", "+218 91-234-5678", "ذكر", 30,
                                     "", "طرابلس", 32.88, 13.19, 15, 50)
    assert isinstance(req_id, int)


def test_register_nurse_rejects_invalid_phone(fresh_db, db):
    ok, msg = database.register_nurse("bad_phone_nurse", "pw-x", "اسم", "09123", "ذكر",
                                      "تمريض عام", "proof")
    assert ok is False and "الهاتف" in msg, f"expected a phone-format rejection, got: {msg!r}"
    assert db.fetchone("SELECT COUNT(*) AS c FROM nurses")["c"] == 0, \
        "no nurse row must be created for an invalid phone"


def test_admin_delete_nurse_permanently(fresh_db, make_nurse, make_request, db, tmp_path):
    import os
    fake_license = tmp_path / "license.jpg"
    fake_license.write_text("fake license content")
    assert fake_license.exists()

    username = f"nurse_del_{os.urandom(3).hex()}"
    ok, _ = database.register_nurse(username, "pw123456", "ممرض للحذف", "0911223344",
                                    "ذكر", "تمريض عام", f"FILE_PATH:{fake_license}###ملاحظات")
    assert ok
    nurse_row = db.fetchone("SELECT id FROM nurses WHERE username = %s", (username,))
    nurse_id = nurse_row["id"]
    database.update_nurse_status(nurse_id, "approved")

    # دفعة مسجلة للممرض
    database.submit_payment(nurse_id, "12345678901234", 20)
    assert db.fetchone("SELECT COUNT(*) AS c FROM payments WHERE nurse_id = %s", (nurse_id,))["c"] == 1

    # طلب تمريض نشط مقبول بواسطة هذا الممرض
    req_id = make_request(gender="ذكر")
    ok, _ = database.accept_request(req_id, nurse_id)
    assert ok
    assert db.fetchone("SELECT status, accepted_nurse_id FROM requests WHERE id = %s", (req_id,))["status"] == "accepted"

    # حذف الممرض نهائياً عبر الإدارة
    success, msg = database.delete_nurse(nurse_id)
    assert success is True
    assert "تم حذف" in msg

    # التأكد من مسح بيانات الممرض وسجلات الدفع الخاصة به
    assert db.fetchone("SELECT * FROM nurses WHERE id = %s", (nurse_id,)) is None
    assert db.fetchone("SELECT COUNT(*) AS c FROM payments WHERE nurse_id = %s", (nurse_id,))["c"] == 0

    # التأكد من إعادة الطلب النشط للحالة المعلقة وفك الارتباط لكي لا يضيع طلب المريض
    req_after = db.fetchone("SELECT status, accepted_nurse_id FROM requests WHERE id = %s", (req_id,))
    assert req_after["status"] == "pending"
    assert req_after["accepted_nurse_id"] is None

    # التأكد من حذف ملف الوثيقة من القرص
    assert not fake_license.exists()

    # محاولة الحذف مجدداً ترجع خطأ لعدم وجود السجل
    success2, msg2 = database.delete_nurse(nurse_id)
    assert success2 is False
    assert "غير موجود" in msg2
