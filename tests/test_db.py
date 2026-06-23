"""Unit tests for db.py run-logging. The DB connection is mocked, so these are
hermetic and never touch a real database."""

import db


class _FakeCursor:
    def __init__(self, fetch=None, rowcount=0):
        self._fetch = fetch
        self.rowcount = rowcount
        self.executed = []

    def __enter__(self):
        return self

    def __exit__(self, *a):
        return False

    def execute(self, sql, params=None):
        self.executed.append((sql, params))

    def fetchone(self):
        return self._fetch


class _FakeConn:
    def __init__(self, cursor):
        self._cursor = cursor

    def __enter__(self):
        return self

    def __exit__(self, *a):
        return False

    def cursor(self):
        return self._cursor

    def close(self):
        pass


def test_not_configured_is_disabled(monkeypatch):
    monkeypatch.setattr(db, "_config", lambda: None)
    assert db.is_enabled() is False
    assert db.log_run("UK", "P", "m", "off", "tnc", "oo", "ot", {"a": 1}) is None
    assert db.save_feedback(1, 5, "good") is False
    assert db.init_db() is False


def test_log_run_returns_id(monkeypatch):
    cur = _FakeCursor(fetch=(123,))
    monkeypatch.setattr(db, "_connect", lambda: _FakeConn(cur))
    rid = db.log_run("United Kingdom", "Crown Place", "gpt-5.5",
                     "raw offer", "raw tnc", "out offer", "out tnc", {"applicable": True})
    assert rid == 123
    assert "INSERT INTO" in cur.executed[0][0]


def test_save_feedback_success(monkeypatch):
    cur = _FakeCursor(rowcount=1)
    monkeypatch.setattr(db, "_connect", lambda: _FakeConn(cur))
    assert db.save_feedback(123, 4, "nice") is True
    assert "UPDATE" in cur.executed[0][0]


def test_save_feedback_no_row(monkeypatch):
    cur = _FakeCursor(rowcount=0)
    monkeypatch.setattr(db, "_connect", lambda: _FakeConn(cur))
    assert db.save_feedback(999, 4, "nice") is False


def test_errors_never_raise(monkeypatch):
    def boom():
        raise RuntimeError("db down")

    monkeypatch.setattr(db, "_connect", boom)
    assert db.log_run("UK", "P", "m", "o", "t", "oo", "ot", {}) is None
    assert db.save_feedback(1, 5, "x") is False
    assert db.init_db() is False


def test_config_from_env(monkeypatch):
    for k in ("HOST", "NAME", "USER", "PASSWORD"):
        monkeypatch.setenv(f"WAKDE_DB_{k}", "x")
    monkeypatch.setenv("WAKDE_DB_PORT", "5432")
    cfg = db._config()
    assert cfg and cfg["dbname"] == "x" and cfg["port"] == 5432


def test_config_none_when_missing(monkeypatch):
    for k in ("WAKDE_DB_HOST", "WAKDE_DB_NAME", "WAKDE_DB_USER", "WAKDE_DB_PASSWORD"):
        monkeypatch.delenv(k, raising=False)
    assert db._config() is None
