# BUGFIXES.md — defects found while writing the integration suite

Every issue below is caught by a test in `tests/test_medlink_e2e.py`. Tests marked
`known_bug` FAIL against the current `database.py` and pass once the corresponding
drop-in replacement here is applied.

> Run first without the fixes to see the failures:
> `pytest -m known_bug -v` → then apply → `pytest -v` → all green.

---

## P0 — SECURITY: live database credentials committed to GitHub

`.streamlit/secrets.toml` is **tracked in git** and published to
`github.com/yousefdg005/trtr` with a working Neon owner connection string. Anyone
can clone the repo and read/write your entire production database right now.

Also: your `.gitignore` is saved as **UTF-16**, which git does not parse — so its
rules (`venv/`, `.streamlit/`, `__pycache__/`) have never actually worked.

**Do immediately:**
1. Rotate the database password in the Neon console (assume the old one is burned).
2. Re-save `.gitignore` as UTF-8, then purge the file from history:
   ```bash
   git rm --cached .streamlit/secrets.toml
   echo "*.log" >> .gitignore   # after converting to UTF-8
   # rewrite history (BFG or git-filter-repo), force-push, then:
   #   git filter-repo --path .streamlit/secrets.toml --invert-paths
   ```
3. Keep secrets in local `secrets.toml` (untracked) or Streamlit Cloud secrets.

The test suite also refuses to run against that production endpoint as a guard
(see `tests/conftest.py`).

---

## BUG-1 — `accept_request` never enforces the debt block (P1)

**Caught by:** `test_known_bug_blocked_nurse_can_still_accept_requests`

The 50 LYD rule ("providers cannot accept new requests if their debt reaches 50
LYD") exists only in the Streamlit UI. `accept_request()` happily assigns work to
a `debt_blocked` nurse and pushes their debt to 60, 70, … Any client that calls
the data layer directly — or a stale browser tab — bypasses the business rule.

**Fix — check nurse standing inside the transaction, after the conditional
request UPDATE (this keeps the 5th-accept-then-block semantics and the lock
order request → nurse consistent with the cancel functions below):**

```python
def accept_request(req_id, nurse_id):
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

        # NEW: refuse service to nurses who are not in good standing
        cur.execute("SELECT status FROM nurses WHERE id = %s", (nurse_id,))
        nurse = cur.fetchone()
        if not nurse or nurse['status'] != 'approved':
            conn.rollback()          # releases the request; it stays 'pending'
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
```

---

## BUG-2 — `cancel_request_by_nurse` lets any nurse cancel anyone's request (P1)

**Caught by:** `test_known_bug_nurse_can_cancel_someone_elses_request`

The function refunds `nurse_id` and cancels the request **unconditionally**:
- Nurse B can cancel a request accepted by Nurse A (A loses the job, keeps the debt).
- Cancelling a `pending` request (never accepted) credits the caller 10 LYD of
  debt they never incurred — a free-money exploit.
- There is also a concurrent double-refund window with `cancel_request_by_patient`
  (both read "accepted", both refund).
- It returns `None` instead of a success flag, so callers can't detect failure.

**Fix — make ownership part of the conditional UPDATE, refund only on success:**

```python
def cancel_request_by_nurse(req_id, nurse_id):
    """Only the assigned nurse may cancel a request she currently holds."""
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
            conn.rollback()          # not her request / not active / unknown id
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
```

---

## BUG-3 — `review_payment` can be applied twice (double refund) (P1)

**Caught by:** `test_known_bug_payment_can_be_approved_twice_for_double_refund`

`UPDATE payments SET status = %s WHERE id = %s` has no `status = 'pending'`
guard. Two admin tabs (or one stale tab after a rerun) approving the same card
deduct the debt twice — `GREATEST(debt - 20, 0)` happily zeroes out debt the
nurse still owes. `amount` is also trusted blindly (a negative amount would
*increase* debt through `GREATEST(debt - (-50), 0)`).

**Fix:**

```python
def review_payment(payment_id, nurse_id, amount, action):
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
            conn.rollback()          # already reviewed — never apply credit twice
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
```

Fraud hardening (business decision): Madar cards are single-use — add a partial
unique index so the same card can never be approved twice, even across nurses:

```sql
CREATE UNIQUE INDEX IF NOT EXISTS uq_payments_approved_card
    ON payments (card_number) WHERE status = 'approved';
```

---

## BUG-4 — `set_system_status` silently does nothing on a fresh database (P2)

**Caught by:** `test_known_bug_system_toggle_is_silently_lost_without_seed_row`

`UPDATE system_settings SET value = ... WHERE key = 'is_active'` matches zero
rows when the setting was never seeded. `get_system_status()` then always
returns the default `True` — the admin's "system offline" switch is lost with
no error.

**Fix — UPSERT:**

```python
def set_system_status(is_active):
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
```

---

## BUG-5 — patient cancellation overwrites the audit trail (P2)

**Caught by:** `test_known_bug_patient_cancel_overwrites_nurse_cancellation_audit`

`cancel_request_by_patient` re-runs its status UPDATE regardless of the current
state, so a stale patient tab can rewrite `cancelled_by_nurse` →
`cancelled_by_patient`, corrupting who cancelled what. It also (harmlessly)
updates rows that don't exist.

**Fix — one conditional transition; refund only if a nurse was actually attached:**

```python
def cancel_request_by_patient(req_id):
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
            conn.rollback()          # unknown id or already cancelled — no-op
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
```

This single-statement form also closes the concurrent patient-cancel /
nurse-cancel double-refund window: both paths now transition the request
conditionally before touching the nurse, so only one of them can win.

---

## Hardening notes (no test, recommended)

1. **There is no schema file in the repo.** The schema exists only implicitly in
   the SQL. Commit a `schema.sql` (the one in `tests/conftest.py` is a faithful
   reconstruction) so environments don't drift.
2. `submit_payment` trusts the client on card number/amount. Mirror the UI rules
   in the data layer (card 10–19 digits, amount ∈ {10,20,30,40,50}) and reject a
   duplicate *pending* submission of the same card by the same nurse.
3. `register_nurse`'s generic `except Exception as e: return False, str(e)` leaks
   raw SQL error text to the UI. Log the exception server-side; return a generic
   Arabic message. Also call `conn.rollback()` in the except paths (closing the
   connection rolls back implicitly, but be explicit).
4. `login_nurse` returns `None` immediately for unknown usernames — a timing side
   channel for username enumeration. Low risk for an MVP; note for later.
5. Magic numbers `10` / `50` are scattered across five functions. Hoist them to
   module constants: `COMMISSION_LYD = 10`, `DEBT_LIMIT_LYD = 50`.
6. `ST_DistanceSphere` is deprecated since PostGIS 3. Prefer
   `ST_Distance(location::geography, ST_MakePoint(%s,%s)::geography) / 1000.0`.
7. The debt refund `GREATEST(debt - 10, 0)` destroys overpayment: a nurse who
   pays 50 LYD with 30 LYD debt loses 20 LYD of credit. Consider a separate
   `balance` column, or clamp `amount` to the current debt at review time.
8. `create_request` accepts `min_price > max_price`, negative ages, and any
   coordinates — the UI validates, the data layer doesn't (same defense-in-depth
   gap as BUG-1).
9. Consider `ON DELETE SET NULL` for `requests.accepted_nurse_id` /
   `payments.nurse_id` and connection pooling (`psycopg2.pool.SimpleConnectionPool`)
   — every call currently opens a fresh TCP+TLS connection, which is especially
   expensive against Neon.
