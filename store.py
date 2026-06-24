"""Run-logging backend selector.

Picks whichever logging backend is configured, in priority order:
  1. Google Sheets  (GOOGLE_SHEET_ID + credentials)  -- reachable from anywhere
  2. PostgreSQL     (WAKDE_DB_*)                      -- for inside-network deploys
  3. none           -> logging disabled (generation still works)

The app talks only to this module so the backend can change with zero app changes.
"""

import db
import sheets


def active():
    if sheets.is_enabled():
        return sheets
    if db.is_enabled():
        return db
    return None


def backend_name() -> str:
    b = active()
    if b is sheets:
        return "google_sheets"
    if b is db:
        return "postgres"
    return "none"


def is_enabled() -> bool:
    return active() is not None


def init() -> bool:
    b = active()
    if b is None:
        return False
    # db exposes init_db(); sheets exposes init()
    return b.init() if hasattr(b, "init") else b.init_db()


def log_run(*args, **kwargs):
    b = active()
    return b.log_run(*args, **kwargs) if b else None


def save_feedback(*args, **kwargs):
    b = active()
    return b.save_feedback(*args, **kwargs) if b else False
