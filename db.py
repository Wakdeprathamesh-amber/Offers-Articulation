"""PostgreSQL run-logging for the offer generator.

Logs every generation (inputs + outputs) to a `offer_articulation_runs` table and
lets the UI attach a rating + comment afterwards. Everything here is best-effort:
if the DB is not configured or is unreachable, the functions log and return a
falsy value but NEVER raise, so generation is never blocked by the database.

Connection is read from these env vars (set in .env / Render):
  WAKDE_DB_HOST, WAKDE_DB_PORT, WAKDE_DB_NAME, WAKDE_DB_USER, WAKDE_DB_PASSWORD
  WAKDE_DB_SSLMODE (optional, default "prefer")
"""

import json
import logging
import os

log = logging.getLogger(__name__)

TABLE = "offer_articulation_runs"

_DDL = f"""
CREATE TABLE IF NOT EXISTS {TABLE} (
    id               BIGSERIAL PRIMARY KEY,
    created_at       TIMESTAMPTZ NOT NULL DEFAULT now(),
    country          TEXT,
    property_name    TEXT,
    model            TEXT,
    input_offer      TEXT,
    input_tnc        TEXT,
    output_offer     TEXT,
    output_tnc       TEXT,
    offer_code       TEXT,
    offer_start_date TEXT,
    offer_end_date   TEXT,
    lease_min        TEXT,
    lease_max        TEXT,
    lease_unit       TEXT,
    output_json      JSONB,
    rating           SMALLINT,
    comment          TEXT
);
"""
# Backfill columns on an already-existing table (safe no-op if present).
_MIGRATE = [f"ALTER TABLE {TABLE} ADD COLUMN IF NOT EXISTS {c} TEXT"
            for c in ("offer_code", "offer_start_date", "offer_end_date",
                      "lease_min", "lease_max", "lease_unit")]


def _config():
    """Return a psycopg2 connect kwargs dict, or None if not fully configured."""
    host = os.environ.get("WAKDE_DB_HOST")
    name = os.environ.get("WAKDE_DB_NAME")
    user = os.environ.get("WAKDE_DB_USER")
    password = os.environ.get("WAKDE_DB_PASSWORD")
    if not (host and name and user and password):
        return None
    return {
        "host": host,
        "port": int(os.environ.get("WAKDE_DB_PORT", "5432")),
        "dbname": name,
        "user": user,
        "password": password,
        "sslmode": os.environ.get("WAKDE_DB_SSLMODE", "prefer"),
        "connect_timeout": int(os.environ.get("WAKDE_DB_CONNECT_TIMEOUT", "8")),
    }


def is_enabled() -> bool:
    """True if DB credentials are present (used to toggle the UI feedback widget)."""
    return _config() is not None


def _connect():
    cfg = _config()
    if not cfg:
        return None
    import psycopg2
    return psycopg2.connect(**cfg)


def init_db() -> bool:
    """Create the runs table if it does not exist. Best-effort; returns success."""
    try:
        conn = _connect()
        if conn is None:
            return False
        try:
            with conn, conn.cursor() as cur:
                cur.execute(_DDL)
                for stmt in _MIGRATE:
                    cur.execute(stmt)
        finally:
            conn.close()
        return True
    except Exception:
        log.exception("db.init_db failed")
        return False


def log_run(country, property_name, model, input_offer, input_tnc,
            output_offer, output_tnc, output_json,
            offer_code="", offer_start_date="", offer_end_date="",
            lease_min="", lease_max="", lease_unit=""):
    """Insert one run row and return its id, or None on any failure."""
    try:
        conn = _connect()
        if conn is None:
            return None
        try:
            with conn, conn.cursor() as cur:
                cur.execute(
                    f"""INSERT INTO {TABLE}
                        (country, property_name, model, input_offer, input_tnc,
                         output_offer, output_tnc, offer_code, offer_start_date,
                         offer_end_date, lease_min, lease_max, lease_unit, output_json)
                        VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s::jsonb)
                        RETURNING id""",
                    (country, property_name, model, input_offer, input_tnc,
                     output_offer, output_tnc, offer_code, offer_start_date,
                     offer_end_date, lease_min, lease_max, lease_unit, json.dumps(output_json)),
                )
                run_id = cur.fetchone()[0]
        finally:
            conn.close()
        return run_id
    except Exception:
        log.exception("db.log_run failed")
        return None


def save_feedback(run_id, rating, comment) -> bool:
    """Attach a rating (1-5) and/or comment to an existing run. Returns success."""
    try:
        conn = _connect()
        if conn is None:
            return False
        try:
            with conn, conn.cursor() as cur:
                cur.execute(
                    f"UPDATE {TABLE} SET rating = %s, comment = %s WHERE id = %s",
                    (rating, comment, run_id),
                )
                updated = cur.rowcount
        finally:
            conn.close()
        return updated > 0
    except Exception:
        log.exception("db.save_feedback failed")
        return False
