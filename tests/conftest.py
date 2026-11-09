"""Shared fixtures for the MedLink integration suite.

These are REAL integration tests: every call goes through ``database.py`` and
executes its SQL against a live PostgreSQL + PostGIS server. Nothing is mocked
except the connection target, which is redirected to a DEDICATED test database
so the production data is never touched.

Setup — pick ONE:

  A) Throwaway Docker container (recommended, fully local):

       docker run --rm -d --name medlink-pg-test -p 5432:5432 \
         -e POSTGRES_PASSWORD=test -e POSTGRES_DB=medlink_test \
         postgis/postgis:16-3.4

       export MEDLINK_TEST_DATABASE_URL="postgresql://postgres:test@localhost:5432/medlink_test"
       pytest -v

  B) A second, EMPTY database on your existing PostgreSQL/Neon project
     (create e.g. ``medlink_test``; never point this at the app database).

The repository contains no schema/migration file, so the fixture below
reconstructs the schema exactly as implied by the queries in ``database.py``.
If you later add a real schema.sql, keep the two in sync.

Safety:
  * the suite refuses to run against the production Neon endpoint that is
    committed in .streamlit/secrets.toml (see BUGFIXES.md — rotate that
    credential!);
  * everything lives inside a dedicated ``medlink_tests`` schema that is
    dropped and recreated on every run, so nothing outside that schema is
    ever touched — even in a shared test database.
"""

import os
import re
import urllib.parse
from pathlib import Path

import psycopg2
import pytest
from psycopg2.extras import RealDictCursor

import database

TEST_URL_ENV = "MEDLINK_TEST_DATABASE_URL"
TEST_SCHEMA = "medlink_tests"

# The production endpoint leaked in .streamlit/secrets.toml — never, ever test against it.
PROD_HOST_FRAGMENTS = ("ep-nameless-queen-b918teg6",)

EXPECTED_TABLES = {"nurses", "requests", "payments", "system_settings"}

SCHEMA_SQL = """
CREATE EXTENSION IF NOT EXISTS postgis;

CREATE TABLE IF NOT EXISTS nurses (
    id          SERIAL PRIMARY KEY,
    username    VARCHAR(100) NOT NULL UNIQUE,
    password    TEXT NOT NULL,
    name        VARCHAR(200) NOT NULL,
    phone       VARCHAR(30)  NOT NULL,
    gender      VARCHAR(10)  NOT NULL,
    specialty   VARCHAR(100) NOT NULL,
    proof_info  TEXT,
    status      VARCHAR(30)  NOT NULL DEFAULT 'pending',
    debt        INTEGER      NOT NULL DEFAULT 0,
    created_at  TIMESTAMPTZ  NOT NULL DEFAULT now()
);

CREATE TABLE IF NOT EXISTS requests (
    id                SERIAL PRIMARY KEY,
    service_type      VARCHAR(100) NOT NULL,
    patient_name      VARCHAR(200) NOT NULL,
    patient_phone     VARCHAR(30)  NOT NULL,
    patient_gender    VARCHAR(10)  NOT NULL,
    patient_age       INTEGER      NOT NULL,
    service_desc      TEXT,
    location_text     TEXT         NOT NULL,
    location_lat      DOUBLE PRECISION NOT NULL,
    location_lng      DOUBLE PRECISION NOT NULL,
    min_price         INTEGER,
    max_price         INTEGER,
    status            VARCHAR(30)  NOT NULL DEFAULT 'pending',
    accepted_nurse_id INTEGER      REFERENCES nurses(id),
    created_at        TIMESTAMPTZ  NOT NULL DEFAULT now()
);

CREATE TABLE IF NOT EXISTS payments (
    id           SERIAL PRIMARY KEY,
    nurse_id     INTEGER NOT NULL REFERENCES nurses(id),
    card_number  VARCHAR(30) NOT NULL,
    amount       INTEGER     NOT NULL,
    status       VARCHAR(20) NOT NULL DEFAULT 'pending',
    created_at   TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE TABLE IF NOT EXISTS system_settings (
    key    VARCHAR(50) PRIMARY KEY,
    value  VARCHAR(20) NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_requests_accepted_nurse ON requests (accepted_nurse_id);
CREATE INDEX IF NOT EXISTS idx_payments_nurse          ON payments (nurse_id);
"""


def _host_and_db(url: str) -> tuple[str, str]:
    parts = urllib.parse.urlparse(url)
    return (parts.hostname or "", (parts.path or "/").lstrip("/"))


def _sanitize_url(url: str) -> str:
    """Drop libpq params psycopg2 builds may choke on (e.g. channel_binding)."""
    parts = urllib.parse.urlparse(url)
    query = urllib.parse.parse_qsl(parts.query, keep_blank_values=True)
    query = [(k, v) for k, v in query if k != "channel_binding"]
    return urllib.parse.urlunparse(parts._replace(query=urllib.parse.urlencode(query)))


def get_test_url() -> str:
    url = os.environ.get(TEST_URL_ENV, "").strip()
    if not url:
        pytest.skip(
            f"{TEST_URL_ENV} is not set. Point it at a DEDICATED PostgreSQL+PostGIS test "
            f"database (see tests/conftest.py header for a ready-made docker command). "
            f"NEVER point it at the production database."
        )

    _host, _db = _host_and_db(url)
    if any(frag in _host for frag in PROD_HOST_FRAGMENTS):
        raise RuntimeError(
            f"SAFETY ABORT: {TEST_URL_ENV} points at the production Neon endpoint "
            f"({_host}) that is committed in .streamlit/secrets.toml. Create a "
            f"separate test database and use its URL instead."
        )

    _secrets_path = Path(__file__).resolve().parent.parent / ".streamlit" / "secrets.toml"
    if _secrets_path.exists():
        _match = re.search(r'url\s*=\s*"([^"]+)"', _secrets_path.read_text(encoding="utf-8", errors="ignore"))
        if _match and _host_and_db(_match.group(1).strip()) == (_host, _db):
            raise RuntimeError(
                f"SAFETY ABORT: {TEST_URL_ENV} targets the same database "
                f"({_host}/{_db}) as .streamlit/secrets.toml. Use a dedicated test database."
            )

    return _sanitize_url(url)


def _connect(url: str) -> psycopg2.extensions.connection:
    return psycopg2.connect(url, cursor_factory=RealDictCursor,
                            options=f"-c search_path={TEST_SCHEMA}")


def reset_database(url: str) -> None:
    """Wipe all test data and re-seed the system switch to 'active'."""
    conn = _connect(url)
    try:
        with conn, conn.cursor() as cur:
            cur.execute("TRUNCATE requests, payments, nurses RESTART IDENTITY CASCADE")
            cur.execute(
                "INSERT INTO system_settings (key, value) VALUES ('is_active', 'true') "
                "ON CONFLICT (key) DO UPDATE SET value = EXCLUDED.value"
            )
    finally:
        conn.close()


class _DB:
    """Tiny test-side helper for direct SQL assertions (bypasses database.py)."""

    def __init__(self, url: str):
        self._conn = _connect(url)

    def fetchone(self, sql, params=()):
        with self._conn.cursor() as cur:
            cur.execute(sql, params)
            return cur.fetchone()

    def fetchall(self, sql, params=()):
        with self._conn.cursor() as cur:
            cur.execute(sql, params)
            return cur.fetchall()

    def execute(self, sql, params=()):
        with self._conn.cursor() as cur:
            cur.execute(sql, params)
        self._conn.commit()

    def close(self):
        self._conn.close()


@pytest.fixture(scope="session")
def db_url():
    """Create (once) the dedicated test schema mirroring the app's implied schema."""
    url = get_test_url()
    conn = psycopg2.connect(url, cursor_factory=RealDictCursor)
    conn.autocommit = True
    try:
        with conn.cursor() as cur:
            cur.execute("SELECT tablename FROM pg_tables WHERE schemaname = %s", (TEST_SCHEMA,))
            existing = {row["tablename"] for row in cur.fetchall()}
            unexpected = existing - EXPECTED_TABLES
            if unexpected:
                raise RuntimeError(
                    f"Schema '{TEST_SCHEMA}' contains unexpected tables {sorted(unexpected)}; "
                    f"refusing to drop it. Move that data elsewhere or rename the schema."
                )
            cur.execute(f"DROP SCHEMA IF EXISTS {TEST_SCHEMA} CASCADE")
            cur.execute(f"CREATE SCHEMA {TEST_SCHEMA}")
            cur.execute(f"SET search_path TO {TEST_SCHEMA}")
            for statement in SCHEMA_SQL.split(";"):
                if statement.strip():
                    cur.execute(statement)
    except psycopg2.Error as exc:
        raise RuntimeError(
            f"Could not prepare the test schema (does the database have the PostGIS "
            f"extension available?). Original error: {exc}"
        ) from exc
    finally:
        conn.close()
    return url


@pytest.fixture(autouse=True)
def patched_connection(monkeypatch, request):
    """Redirect database.get_connection() to the dedicated test DB for tests using db."""
    if any(f in request.fixturenames for f in ("db", "fresh_db", "db_url", "make_nurse", "make_request")):
        url = request.getfixturevalue("db_url")
        def _test_connection():
            return _connect(url)
        monkeypatch.setattr(database, "get_connection", _test_connection)
    yield


@pytest.fixture
def fresh_db(db_url):
    """Per-test clean slate for the standalone (non-journey) tests."""
    reset_database(db_url)
    yield


@pytest.fixture
def db(db_url):
    helper = _DB(db_url)
    yield helper
    helper.close()


@pytest.fixture
def make_nurse(db):
    """Register (and by default approve) a nurse; returns id/username/name/password."""
    counter = iter(range(1, 10_000))

    def _make(username=None, *, gender="ذكر", approve=True, password="S3cret-Pw!x"):
        n = next(counter)
        username = username or f"nurse_{n}_{os.urandom(4).hex()}"
        name = f"الممرض التجريبي {n}"
        ok, msg = database.register_nurse(username, password, name, "0911111111",
                                          gender, "تمريض عام", "FILE_PATH:tests/fake.jpg###اختبار")
        assert ok, f"register_nurse unexpectedly failed: {msg}"
        row = db.fetchone("SELECT id, status FROM nurses WHERE username = %s", (username,))
        assert row is not None, "registered nurse row not found"
        if approve:
            database.update_nurse_status(row["id"], "approved")
        return {"id": row["id"], "username": username, "name": name, "password": password}

    return _make


@pytest.fixture
def make_request():
    """Create a patient request near central Tripoli; returns the new request id."""
    counter = iter(range(1, 10_000))

    def _make(*, patient_gender="ذكر", lat=32.8872, lng=13.1913,
              service="علاج طبيعي", min_price=15, max_price=50):
        n = next(counter)
        return database.create_request(
            service, f"المريض التجريبي {n}", "0912222222", patient_gender, 30,
            "وصف تجريبي", "طرابلس - حي الأندلس", lat, lng, min_price, max_price,
        )

    return _make
