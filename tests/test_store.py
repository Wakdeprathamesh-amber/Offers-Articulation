"""Tests for the run-logging backend selector (store) and Sheets config detection.
All network/credential access is mocked or env-driven; hermetic."""

import store
import sheets
import db


def test_no_backend_when_unconfigured(monkeypatch):
    monkeypatch.setattr(sheets, "is_enabled", lambda: False)
    monkeypatch.setattr(db, "is_enabled", lambda: False)
    assert store.active() is None
    assert store.is_enabled() is False
    assert store.backend_name() == "none"
    assert store.log_run("a", "b", "c", "d", "e", "f", "g", {}) is None
    assert store.save_feedback("x", 5, "c") is False
    assert store.init() is False


def test_sheets_preferred_over_db(monkeypatch):
    monkeypatch.setattr(sheets, "is_enabled", lambda: True)
    monkeypatch.setattr(db, "is_enabled", lambda: True)
    assert store.active() is sheets
    assert store.backend_name() == "google_sheets"


def test_db_used_when_only_db(monkeypatch):
    monkeypatch.setattr(sheets, "is_enabled", lambda: False)
    monkeypatch.setattr(db, "is_enabled", lambda: True)
    assert store.active() is db
    assert store.backend_name() == "postgres"


def test_store_dispatches_log_and_feedback(monkeypatch):
    monkeypatch.setattr(sheets, "is_enabled", lambda: True)
    monkeypatch.setattr(sheets, "log_run", lambda *a, **k: "abc123")
    monkeypatch.setattr(sheets, "save_feedback", lambda *a, **k: True)
    assert store.log_run("a", "b", "c", "d", "e", "f", "g", {}) == "abc123"
    assert store.save_feedback("abc123", 4, "good") is True


# ---- Sheets config detection (no network) ----
def test_sheets_disabled_without_config(monkeypatch):
    for k in ("GOOGLE_SHEET_ID", "GOOGLE_SHEETS_CREDENTIALS_JSON", "GOOGLE_SHEETS_CREDENTIALS_FILE"):
        monkeypatch.delenv(k, raising=False)
    assert sheets.is_enabled() is False


def test_sheets_enabled_with_json_env(monkeypatch):
    monkeypatch.setenv("GOOGLE_SHEET_ID", "sheet123")
    monkeypatch.setenv("GOOGLE_SHEETS_CREDENTIALS_JSON", '{"type": "service_account", "client_email": "x@y.iam"}')
    monkeypatch.delenv("GOOGLE_SHEETS_CREDENTIALS_FILE", raising=False)
    assert sheets.is_enabled() is True
    assert sheets._creds_info()["client_email"] == "x@y.iam"


def test_sheets_bad_json_disables(monkeypatch):
    monkeypatch.setenv("GOOGLE_SHEET_ID", "sheet123")
    monkeypatch.setenv("GOOGLE_SHEETS_CREDENTIALS_JSON", "{not valid json")
    monkeypatch.delenv("GOOGLE_SHEETS_CREDENTIALS_FILE", raising=False)
    assert sheets.is_enabled() is False


def test_sheets_log_run_returns_none_on_error(monkeypatch):
    # _worksheet will raise (no real creds) -> log_run returns None, never raises
    monkeypatch.setenv("GOOGLE_SHEET_ID", "sheet123")
    monkeypatch.setenv("GOOGLE_SHEETS_CREDENTIALS_JSON", '{"type":"service_account"}')
    assert sheets.log_run("a", "b", "c", "d", "e", "f", "g", {}) is None


def test_sheets_headers_include_new_fields():
    for col in ("offer_code", "offer_start_date", "offer_end_date",
                "lease_min", "lease_max", "lease_unit", "rating", "comment"):
        assert col in sheets.HEADERS
    # rating/comment column indices are derived from HEADERS (not hardcoded)
    assert sheets._RATING_COL == sheets.HEADERS.index("rating") + 1
    assert sheets._COMMENT_COL == sheets.HEADERS.index("comment") + 1
