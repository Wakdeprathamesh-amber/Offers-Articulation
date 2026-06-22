"""
amber Offer Content Automation — v1

A small local web app that turns a raw promotional offer (pasted text or an
uploaded PDF) into SOP-compliant Offer Title, Offer Body and Terms & Conditions,
and flags offers that are not applicable to Amber.

Powered by the OpenAI API. Set OPENAI_API_KEY in the environment (or a .env
file) before running:

    export OPENAI_API_KEY=sk-...
    python app.py

Then open http://127.0.0.1:5000
"""

import json
import os
import re

from flask import Flask, jsonify, render_template, request

from prompts import SYSTEM_PROMPT, build_user_prompt, CURRENCY_MAP

# Load .env if python-dotenv is available (optional convenience).
try:
    from dotenv import load_dotenv

    load_dotenv()
except Exception:
    pass

app = Flask(__name__)

MODEL = os.environ.get("OPENAI_MODEL", "gpt-4o")
MAX_TITLE = 60
HARD_TITLE_CAP = 72


def extract_pdf_text(file_storage) -> str:
    """Extract text from an uploaded PDF. Returns '' if no text layer."""
    from pypdf import PdfReader

    reader = PdfReader(file_storage)
    chunks = []
    for page in reader.pages:
        chunks.append(page.extract_text() or "")
    return "\n".join(chunks).strip()


def generate_offer(country: str, property_name: str, raw_offer: str) -> dict:
    """Call the OpenAI API and return the parsed, post-processed, SOP-checked result."""
    from openai import OpenAI

    client = OpenAI(timeout=30, max_retries=2)  # reads OPENAI_API_KEY from env
    user_prompt = build_user_prompt(country, property_name, raw_offer)

    response = client.chat.completions.create(
        model=MODEL,
        temperature=0.3,
        response_format={"type": "json_object"},
        messages=[
            {"role": "system", "content": SYSTEM_PROMPT},
            {"role": "user", "content": user_prompt},
        ],
    )
    data = json.loads(response.choices[0].message.content)
    result = postprocess(data, country=country)
    result["warnings"] = _compliance_warnings(result, country)
    return result


def _compliance_warnings(result: dict, country: str) -> list:
    """Run the SOP checker over the final output and return any violations.
    Informational only; never raises."""
    from sop_checker import check_compliance

    ctx = {
        "country": country,
        "operator_names": result.get("detected_operator_names", []),
        "source_has_tncs": result.get("source_has_tncs", False),
    }
    try:
        return check_compliance(result, ctx)
    except Exception:
        app.logger.exception("compliance check failed")
        return []


def postprocess(data: dict, country: str = "") -> dict:
    """Full deterministic post-processing pipeline applied to the model output.

    Order matters: normalise shape first so every downstream step can assume a
    well-formed dict, then strip dashes, strip contact info, fix currency, fix
    first person, drop agent/commission terms (and renumber), rename the operator,
    and finally annotate title lengths.
    """
    data = _normalize(data)
    expected_symbol = CURRENCY_MAP.get((country or "").strip())
    detected = data.get("detected_operator_names", [])
    data = _strip_dashes(data)
    data = _strip_contact_info(data)
    data = _fix_currency(data, expected_symbol)
    data = _fix_first_person(data)
    data = _clean_agent_terms(data)
    data = _rename_operator(data, detected)
    data = _annotate(data)
    return data


def _normalize(data: dict) -> dict:
    """Guarantee the output contract so the UI never breaks on odd model output."""
    if not isinstance(data, dict):
        data = {}
    data["applicable"] = bool(data.get("applicable", False))
    data["assessment"] = data.get("assessment") if isinstance(data.get("assessment"), str) else ""
    data["needs_kam_confirmation"] = bool(data.get("needs_kam_confirmation", False))

    flags = data.get("flags")
    if isinstance(flags, str):
        flags = [flags]
    elif not isinstance(flags, list):
        flags = []
    data["flags"] = [str(f) for f in flags] or ["none"]

    offers = data.get("offers")
    if not isinstance(offers, list):
        offers = []
    clean_offers = []
    for o in offers:
        if not isinstance(o, dict):
            continue
        props = o.get("properties")
        if isinstance(props, str):
            props = [props]
        elif not isinstance(props, list):
            props = []
        terms = o.get("terms")
        if not isinstance(terms, list):
            terms = [terms] if isinstance(terms, str) and terms.strip() else []
        missing = o.get("missing_info")
        if isinstance(missing, str):
            missing = [missing]
        elif not isinstance(missing, list):
            missing = []
        clean_offers.append(
            {
                "properties": [str(p) for p in props],
                "title": o.get("title") if isinstance(o.get("title"), str) else "",
                "body": o.get("body") if isinstance(o.get("body"), str) else "",
                "terms": [str(t) for t in terms],
                "missing_info": [str(m) for m in missing],
            }
        )
    data["offers"] = clean_offers

    names = data.get("detected_operator_names")
    if isinstance(names, str):
        names = [names]
    elif not isinstance(names, list):
        names = []
    data["detected_operator_names"] = [str(n).strip() for n in names if str(n).strip()]
    data["source_has_tncs"] = bool(data.get("source_has_tncs", False))
    return data


def _clean_dashes(text: str) -> str:
    """Remove em/en dashes per brand rule. En dash -> hyphen (ranges),
    em dash -> comma. Then tidy any doubled spaces/commas/leading comma."""
    if not isinstance(text, str):
        return text
    text = text.replace("–", "-")          # en dash – -> hyphen
    text = text.replace("—", ", ")         # em dash — -> comma
    text = text.replace("―", ", ")         # horizontal bar
    # tidy artefacts
    text = text.replace(" ,", ",").replace(", ,", ",").replace(",,", ",")
    while "  " in text:
        text = text.replace("  ", " ")
    # remove a leading comma left by an em dash at the start of a line/string
    if text.startswith(", "):
        text = text[2:]
    text = text.replace("\n, ", "\n")
    return text


# Contact-info patterns (used to scrub emails / URLs / phone numbers per SOP).
_EMAIL_RE = re.compile(r"[\w.+-]+@[\w-]+\.[\w.-]+")
_URL_RE = re.compile(r"\b(?:https?://|www\.)\S+", re.I)
_PHONE_RE = re.compile(r"(?:\+\d[\d\s\-()]{7,}\d)|(?:\b\d{3}[\s.\-]\d{3}[\s.\-]\d{4}\b)")
_CONTACT_LEADINS = (
    "contact", "email", "e-mail", "call", "phone", "questions", "queries",
    "for queries", "for details", "for more", "reach us", "reach out",
)


def _scrub_contact_text(text: str) -> str:
    """Remove email/URL/phone tokens from a string and tidy the leftover artefacts."""
    if not isinstance(text, str):
        return text
    text = _EMAIL_RE.sub("", text)
    text = _URL_RE.sub("", text)
    text = _PHONE_RE.sub("", text)
    text = re.sub(r"\(\s*\)", "", text)            # empty parens left behind
    text = re.sub(r"\s+([.,;:!?])", r"\1", text)   # space before punctuation
    text = re.sub(r"\s{2,}", " ", text)
    return text.strip()


def _strip_contact_info(data: dict) -> dict:
    """Remove emails/URLs/phone numbers from body and terms. Drop a term that is
    only a contact instruction; keep and scrub a term with embedded contact info."""
    for offer in data.get("offers", []) or []:
        if isinstance(offer.get("body"), str):
            offer["body"] = _scrub_contact_text(offer["body"])
        terms = offer.get("terms")
        if not isinstance(terms, list):
            continue
        kept = []
        for t in terms:
            body = re.sub(r"^\s*\(?\d+\)?[.)]?\s*", "", str(t))  # strip leading (n)/n.
            had_contact = bool(
                _EMAIL_RE.search(body) or _URL_RE.search(body) or _PHONE_RE.search(body)
            )
            scrubbed = _scrub_contact_text(body)
            if not re.sub(r"[^A-Za-z0-9]", "", scrubbed):
                continue  # nothing substantive remains
            low = scrubbed.lower()
            if had_contact and len(scrubbed.split()) <= 6 and any(
                low.startswith(c) for c in _CONTACT_LEADINS
            ):
                continue  # contact-only stub
            kept.append(scrubbed)
        offer["terms"] = [f"({i+1}) {b}" for i, b in enumerate(kept)]
    return data


# Distinctive currency tokens, ordered longest-first so "US$" is one token, never "S$".
_CURRENCY_TOKEN_RE = re.compile(r"US\$|AU\$|CA\$|NZ\$|HK\$|S\$|£|€")


def _fix_currency(data: dict, expected_symbol) -> dict:
    """When the country maps to a known symbol, replace any other distinctive
    currency token in title/body with the expected one (the number is preserved).
    No-op when the symbol is unknown."""
    if not expected_symbol:
        return data

    def fix(text):
        if not isinstance(text, str):
            return text
        return _CURRENCY_TOKEN_RE.sub(
            lambda m: expected_symbol if m.group(0) != expected_symbol else m.group(0),
            text,
        )

    for offer in data.get("offers", []) or []:
        if isinstance(offer.get("title"), str):
            offer["title"] = fix(offer["title"])
        if isinstance(offer.get("body"), str):
            offer["body"] = fix(offer["body"])
    return data


# Conservative, grammar-safe first-person rewrites. Order matters (specific first).
# Anything not covered here is left for the live SOP-check warning layer.
_FIRST_PERSON_SUBS = [
    (re.compile(r"\bwe reserve the right\b", re.I), "Property Management reserves the right"),
    (re.compile(r"\bwe accept no responsibility\b", re.I), "Property Management accepts no responsibility"),
    (re.compile(r"\bwe are not liable\b", re.I), "Property Management is not liable"),
    (re.compile(r"\bwe will\b", re.I), "Property Management will"),
    (re.compile(r"\bwe may\b", re.I), "Property Management may"),
    (re.compile(r"\bour terms and conditions\b", re.I), "Property Management's terms and conditions"),
    (re.compile(r"\bour terms\b", re.I), "Property Management's terms"),
    (re.compile(r"\bour discretion\b", re.I), "Property Management's discretion"),
    (re.compile(r"\bour website\b", re.I), "the property website"),
    (re.compile(r"\bour property\b", re.I), "the property"),
]


def _apply_first_person(text: str) -> str:
    if not isinstance(text, str):
        return text
    for pat, repl in _FIRST_PERSON_SUBS:
        text = pat.sub(repl, text)
    return text


def _fix_first_person(data: dict) -> dict:
    """Best-effort deterministic removal of common first-person phrasing.
    Residual first-person is caught by the live SOP-check warnings."""
    for offer in data.get("offers", []) or []:
        if isinstance(offer.get("body"), str):
            offer["body"] = _apply_first_person(offer["body"])
        if isinstance(offer.get("terms"), list):
            offer["terms"] = [_apply_first_person(t) for t in offer["terms"]]
    return data


def _strip_dashes(data: dict) -> dict:
    """Apply dash cleaning across all generated text fields."""
    if isinstance(data.get("assessment"), str):
        data["assessment"] = _clean_dashes(data["assessment"])
    for offer in data.get("offers", []) or []:
        for key in ("title", "body"):
            if key in offer:
                offer[key] = _clean_dashes(offer[key])
        if isinstance(offer.get("terms"), list):
            offer["terms"] = [_clean_dashes(t) for t in offer["terms"]]
    return data


# Phrases that mark a T&C as agent/commission-channel related (must be removed
# per SOP). Carefully chosen NOT to match legitimate clauses such as
# "referred through a nomination agreement or a referral agreement".
_AGENT_TERM_MARKERS = (
    "agent booking",
    "booking agent",
    "education agent",
    "referral agent",      # matches "referral agents" but not "referral agreement"
    "agent code",
    "agent commission",
    "referral commission",
    "agent portal",
    "agent referral",
    "commissionable",
)


def _clean_agent_terms(data: dict) -> dict:
    """Drop any T&C referencing agent bookings / commission, then renumber."""
    import re

    for offer in data.get("offers", []) or []:
        terms = offer.get("terms")
        if not isinstance(terms, list):
            continue
        kept = []
        for t in terms:
            body = re.sub(r"^\s*\(?\d+\)?[.)]?\s*", "", str(t))  # strip leading (n)/n.
            if any(m in body.lower() for m in _AGENT_TERM_MARKERS):
                continue  # remove agent/commission clause
            kept.append(body.strip())
        offer["terms"] = [f"({i+1}) {b}" for i, b in enumerate(kept)]
    return data


import re as _re

# A capitalised company-style name of 1-6 words (e.g. "Maple Living Group").
_NAME = r"[A-Z][A-Za-z&.'-]*(?:\s+[A-Z0-9][A-Za-z&.'0-9-]*){0,5}"
_RESERVES_RE = _re.compile(rf"\b{_NAME}\s+reserves the right")
_OTHER_PROP_RE = _re.compile(rf"\bany other\s+{_NAME}\s+(propert(?:y|ies))")


# Generic words that must never be blanket-replaced as if they were an operator name.
_OP_STOPWORDS = {
    "property management", "the operator", "operator", "landlord",
    "management", "the property", "student", "living", "group", "residences",
}


def _safe_operator_names(detected, props_blob):
    """Operator names safe to blanket-replace: not generic, not part of the
    property's own name (those are left to the conservative regex net)."""
    out = []
    for n in detected or ():
        s = (n or "").strip()
        if len(s) < 3:
            continue
        low = s.lower()
        if low in _OP_STOPWORDS:
            continue
        if low in props_blob:
            continue
        out.append(s)
    return out


def _rename_operator(data: dict, detected_names=()) -> dict:
    """Replace operator/PMG names with 'Property Management'. Two layers:
    (1) blanket-replace any model-reported operator name that does not overlap the
        property name; (2) the conservative regex net for the two common leak
        patterns ('<Operator> reserves the right', 'any other <Operator> property'),
        which also covers names the model failed to report and never touches a
        property name used elsewhere.
    """

    def fix_patterns(text: str) -> str:
        if not isinstance(text, str):
            return text
        text = _RESERVES_RE.sub("Property Management reserves the right", text)
        text = _OTHER_PROP_RE.sub(
            lambda m: f"any other Property Management {m.group(1)}", text
        )
        return text

    for offer in data.get("offers", []) or []:
        props_blob = " ".join(offer.get("properties") or []).lower()
        safe = _safe_operator_names(detected_names, props_blob)

        def blanket(text):
            if not isinstance(text, str):
                return text
            for name in safe:
                text = re.sub(rf"\b{re.escape(name)}\b", "Property Management", text, flags=re.I)
            return text

        if isinstance(offer.get("body"), str):
            offer["body"] = fix_patterns(blanket(offer["body"]))
        if isinstance(offer.get("terms"), list):
            offer["terms"] = [fix_patterns(blanket(t)) for t in offer["terms"]]
    return data


def _annotate(data: dict) -> dict:
    """Add server-side title length checks so the UI can warn reliably."""
    for offer in data.get("offers", []) or []:
        title = offer.get("title", "") or ""
        length = len(title)
        offer["title_length"] = length
        if length > HARD_TITLE_CAP:
            offer["title_status"] = "over_hard_cap"
        elif length > MAX_TITLE:
            offer["title_status"] = "over_target"
        else:
            offer["title_status"] = "ok"
    return data


@app.route("/")
def index():
    return render_template("index.html")


@app.route("/extract-pdf", methods=["POST"])
def extract_pdf():
    """Extract text from an uploaded PDF for the user to review before generating."""
    if "pdf" not in request.files:
        return jsonify({"error": "No PDF uploaded."}), 400
    f = request.files["pdf"]
    if not f.filename.lower().endswith(".pdf"):
        return jsonify({"error": "Please upload a .pdf file."}), 400
    try:
        text = extract_pdf_text(f)
    except Exception as exc:
        return jsonify({"error": f"Could not read PDF: {exc}"}), 400
    if not text:
        return jsonify(
            {
                "text": "",
                "warning": (
                    "This PDF has no selectable text (it looks like a scan or "
                    "screenshot). v1 is text-only, so please copy the offer text "
                    "and paste it in the box above."
                ),
            }
        )
    return jsonify({"text": text})


@app.route("/generate", methods=["POST"])
def generate():
    payload = request.get_json(force=True, silent=True) or {}
    raw_offer = (payload.get("raw_offer") or "").strip()
    country = (payload.get("country") or "").strip()
    property_name = (payload.get("property_name") or "").strip()

    if not raw_offer:
        return jsonify({"error": "Please provide the raw offer text."}), 400
    if not os.environ.get("OPENAI_API_KEY"):
        return jsonify(
            {"error": "OPENAI_API_KEY is not set. Add it to your environment or .env file."}
        ), 400

    try:
        result = generate_offer(country, property_name, raw_offer)
    except Exception as exc:
        return jsonify({"error": f"Generation failed: {exc}"}), 500

    return jsonify(result)


if __name__ == "__main__":
    # Local/dev entrypoint. In production (Render) gunicorn imports `app` directly
    # via the start command, so this block is not used there.
    port = int(os.environ.get("PORT", 5000))
    debug = os.environ.get("FLASK_DEBUG", "1").lower() in ("1", "true", "yes")
    app.run(host="0.0.0.0", port=port, debug=debug)
