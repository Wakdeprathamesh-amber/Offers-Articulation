"""Google Sheets run-logging backend.

A drop-in alternative to db.py for environments where the Postgres host is not
reachable (e.g. Render cannot reach the internal staging DB). Logs each run as a
row and lets /feedback update that row's rating + comment.

Config (env vars):
  GOOGLE_SHEET_ID                 the spreadsheet id (from its URL)
  GOOGLE_SHEETS_CREDENTIALS_FILE  path to the service-account JSON (local), OR
  GOOGLE_SHEETS_CREDENTIALS_JSON  the service-account JSON content (Render)
  GOOGLE_SHEETS_WORKSHEET         optional tab name (default "runs")

The service-account email must be granted EDIT access to the sheet.
Best-effort: every function logs and returns falsy on failure, never raises.
"""

import json
import logging
import os

log = logging.getLogger(__name__)

HEADERS = [
    "run_id", "created_at", "country", "property_name", "model",
    "input_offer", "input_tnc", "output_offer", "output_tnc", "rating", "comment",
]
_RATING_COL = 10   # 1-indexed column of "rating"
_COMMENT_COL = 11  # 1-indexed column of "comment"


def _sheet_id():
    return os.environ.get("GOOGLE_SHEET_ID")


def _creds_info():
    """Return the service-account dict from the JSON env var or file, else None."""
    raw = os.environ.get("GOOGLE_SHEETS_CREDENTIALS_JSON")
    if raw:
        try:
            return json.loads(raw)
        except Exception:
            log.exception("GOOGLE_SHEETS_CREDENTIALS_JSON is not valid JSON")
            return None
    path = os.environ.get("GOOGLE_SHEETS_CREDENTIALS_FILE")
    if path and os.path.exists(path):
        try:
            with open(path) as f:
                return json.load(f)
        except Exception:
            log.exception("could not read GOOGLE_SHEETS_CREDENTIALS_FILE")
            return None
    return None


def is_enabled() -> bool:
    return bool(_sheet_id() and _creds_info())


def _worksheet():
    import gspread
    from google.oauth2.service_account import Credentials

    creds = Credentials.from_service_account_info(
        _creds_info(), scopes=["https://www.googleapis.com/auth/spreadsheets"]
    )
    sh = gspread.authorize(creds).open_by_key(_sheet_id())
    name = os.environ.get("GOOGLE_SHEETS_WORKSHEET", "runs")
    try:
        ws = sh.worksheet(name)
    except Exception:
        ws = sh.add_worksheet(title=name, rows=1000, cols=len(HEADERS))
        ws.append_row(HEADERS)
    if not ws.row_values(1):
        ws.append_row(HEADERS)
    return ws


def init() -> bool:
    try:
        _worksheet()
        return True
    except Exception:
        log.exception("sheets.init failed")
        return False


def log_run(country, property_name, model, input_offer, input_tnc,
            output_offer, output_tnc, output_json):
    """Append one run row and return a generated run_id (string), or None."""
    try:
        import uuid
        from datetime import datetime, timezone

        run_id = uuid.uuid4().hex[:12]
        created = datetime.now(timezone.utc).isoformat()
        _worksheet().append_row(
            [run_id, created, country, property_name, model,
             input_offer, input_tnc, output_offer, output_tnc, "", ""],
            value_input_option="RAW",
        )
        return run_id
    except Exception:
        log.exception("sheets.log_run failed")
        return None


def save_feedback(run_id, rating, comment) -> bool:
    """Find the row by run_id and set its rating + comment."""
    try:
        ws = _worksheet()
        cell = ws.find(str(run_id), in_column=1)
        if not cell:
            return False
        ws.update_cell(cell.row, _RATING_COL, rating if rating is not None else "")
        ws.update_cell(cell.row, _COMMENT_COL, comment or "")
        return True
    except Exception:
        log.exception("sheets.save_feedback failed")
        return False
