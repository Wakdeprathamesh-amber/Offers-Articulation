"""Google Sheets run-logging backend.

Logs each run as a row and lets /feedback update that row's rating + comment.
Reliability notes:
  * the authorised worksheet is cached (module level) so we do NOT re-authorise
    and re-open the spreadsheet on every request (that hit Google's per-minute
    API quota and silently dropped rows);
  * writes retry once on a transient error with a fresh handle;
  * everything is best-effort: functions log and return a falsy value on failure,
    never raise, so generation is never blocked by the sheet.

Config (env vars):
  GOOGLE_SHEET_ID                 the spreadsheet id (from its URL)
  GOOGLE_SHEETS_CREDENTIALS_FILE  path to the service-account JSON (local), OR
  GOOGLE_SHEETS_CREDENTIALS_JSON  the service-account JSON content (Render)
  GOOGLE_SHEETS_WORKSHEET         optional tab name (default "runs")

The service-account email must be granted EDIT access to the sheet.
"""

import json
import logging
import os
import time

log = logging.getLogger(__name__)

HEADERS = [
    "run_id", "created_at", "country", "property_name", "model",
    "input_offer", "input_tnc", "output_offer", "output_tnc",
    "offer_code", "offer_start_date", "offer_end_date",
    "lease_min", "lease_max", "lease_unit",
    "output_json", "rating", "comment",
]
_RATING_COL = HEADERS.index("rating") + 1     # 1-indexed
_COMMENT_COL = HEADERS.index("comment") + 1

_WS = None  # cached worksheet handle


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


def _worksheet(force: bool = False):
    """Return the cached worksheet, opening/authorising only when needed."""
    global _WS
    if _WS is not None and not force:
        return _WS
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
    _WS = ws
    return ws


def _run_op(op):
    """Run op(worksheet); on any error, refresh the handle once and retry."""
    global _WS
    last = None
    for attempt in (1, 2):
        try:
            return op(_worksheet(force=(attempt == 2)))
        except Exception as exc:  # transient quota/timeout/auth -> retry once
            last = exc
            _WS = None
            log.warning("sheets op failed (attempt %d): %s", attempt, exc)
            if attempt == 1:
                time.sleep(1.0)
    log.error("sheets op failed after retry: %s", last)
    return None


def init() -> bool:
    """Ensure the worksheet exists and its header row matches HEADERS."""
    def op(ws):
        header = ws.row_values(1)
        if header != HEADERS:
            ws.update(range_name="A1", values=[HEADERS])
        return True
    return bool(_run_op(op))


def log_run(country, property_name, model, input_offer, input_tnc,
            output_offer, output_tnc, output_json,
            offer_code="", offer_start_date="", offer_end_date="",
            lease_min="", lease_max="", lease_unit=""):
    """Append one run row and return a generated run_id (string), or None."""
    import uuid
    from datetime import datetime, timezone

    run_id = uuid.uuid4().hex[:12]
    values_by_header = {
        "run_id": run_id,
        "created_at": datetime.now(timezone.utc).isoformat(),
        "country": country, "property_name": property_name, "model": model,
        "input_offer": input_offer, "input_tnc": input_tnc,
        "output_offer": output_offer, "output_tnc": output_tnc,
        "offer_code": offer_code,
        "offer_start_date": offer_start_date, "offer_end_date": offer_end_date,
        "lease_min": lease_min, "lease_max": lease_max, "lease_unit": lease_unit,
        "output_json": json.dumps(output_json),
        "rating": "", "comment": "",
    }
    row = [values_by_header.get(h, "") for h in HEADERS]

    def op(ws):
        ws.append_row(row, value_input_option="RAW")
        return run_id

    return _run_op(op)


def save_feedback(run_id, rating, comment) -> bool:
    """Find the row by run_id and set its rating + comment."""
    def op(ws):
        cell = ws.find(str(run_id), in_column=1)
        if not cell:
            return False
        ws.update_cell(cell.row, _RATING_COL, rating if rating is not None else "")
        ws.update_cell(cell.row, _COMMENT_COL, comment or "")
        return True

    return bool(_run_op(op))
