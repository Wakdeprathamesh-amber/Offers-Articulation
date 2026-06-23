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

import io
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

import db  # PostgreSQL run-logging (best-effort; no-ops if not configured)

app = Flask(__name__)
app.config["MAX_CONTENT_LENGTH"] = 8 * 1024 * 1024  # 8 MB upload cap

# Best-effort: ensure the runs table exists. Never blocks startup.
try:
    if db.is_enabled():
        db.init_db()
except Exception:
    pass

MODEL = os.environ.get("OPENAI_MODEL", "gpt-4o")
TEMPERATURE = float(os.environ.get("OPENAI_TEMPERATURE", "0.3"))
# Per-attempt request timeout (seconds). Flagship models (gpt-5/5.5) are slower
# than gpt-4o, so default generously; override with OPENAI_TIMEOUT.
OPENAI_TIMEOUT = float(os.environ.get("OPENAI_TIMEOUT", "60"))
MAX_TITLE = 60
HARD_TITLE_CAP = 72
MAX_RAW_OFFER_CHARS = 20000

# Some models (e.g. gpt-5 / gpt-5.5) only accept the default temperature and reject
# a custom one with a 400. We optimistically send TEMPERATURE; if the model rejects
# it we drop it for the rest of the session so only the first call pays the retry.
_SEND_TEMPERATURE = True


@app.errorhandler(413)
def _too_large(_e):
    return jsonify({"error": "File too large. Maximum upload size is 8 MB."}), 413


def extract_pdf_text(file_storage) -> str:
    """Extract text from an uploaded PDF. Returns '' if no text layer."""
    from pypdf import PdfReader

    reader = PdfReader(file_storage)
    chunks = []
    for page in reader.pages:
        chunks.append(page.extract_text() or "")
    return "\n".join(chunks).strip()


def _chat_completion(messages, json_mode: bool = False):
    """Shared OpenAI chat call. Sends the configured temperature, and if the model
    rejects a custom temperature (gpt-5/gpt-5.5), retries without it once and
    remembers that for the session."""
    from openai import OpenAI

    global _SEND_TEMPERATURE
    client = OpenAI(timeout=OPENAI_TIMEOUT, max_retries=2)  # reads OPENAI_API_KEY from env

    def _create(send_temperature: bool):
        kwargs = {"model": MODEL, "messages": messages}
        if json_mode:
            kwargs["response_format"] = {"type": "json_object"}
        if send_temperature:
            kwargs["temperature"] = TEMPERATURE
        return client.chat.completions.create(**kwargs)

    try:
        return _create(_SEND_TEMPERATURE)
    except Exception as exc:
        if _SEND_TEMPERATURE and "temperature" in str(exc).lower():
            _SEND_TEMPERATURE = False
            return _create(False)
        raise


def generate_offer(country: str, property_name: str, raw_offer: str, raw_tnc: str = "") -> dict:
    """Call the OpenAI API and return the parsed, post-processed, SOP-checked result."""
    user_prompt = build_user_prompt(country, property_name, raw_offer, raw_tnc)
    messages = [
        {"role": "system", "content": SYSTEM_PROMPT},
        {"role": "user", "content": user_prompt},
    ]
    response = _chat_completion(messages, json_mode=True)
    data = json.loads(response.choices[0].message.content)
    result = postprocess(data, country=country, property_name=property_name)
    result["warnings"] = _compliance_warnings(result, country, property_name)
    return result


# ---- Vision OCR for image / scanned PDFs -----------------------------------
VISION_PROMPT = (
    "You are reading a promotional student-accommodation offer (and possibly its "
    "Terms & Conditions) from an image or screenshot. Transcribe ALL the visible "
    "text VERBATIM, preserving the offer details and the full Terms & Conditions "
    "if present. Keep the original wording. Do not summarise, do not translate, do "
    "not add anything. Output plain text only."
)

_IMAGE_MIME = {".png": "image/png", ".jpg": "image/jpeg", ".jpeg": "image/jpeg", ".webp": "image/webp"}


def _pdf_to_images(pdf_bytes: bytes, max_pages: int = 10, zoom: float = 2.0) -> list:
    """Render the first max_pages of a PDF to PNG image bytes (for scanned PDFs)."""
    import fitz  # pymupdf

    images = []
    doc = fitz.open(stream=pdf_bytes, filetype="pdf")
    try:
        for page in list(doc)[:max_pages]:
            pix = page.get_pixmap(matrix=fitz.Matrix(zoom, zoom))
            images.append(pix.tobytes("png"))
    finally:
        doc.close()
    return images


def extract_with_vision(images: list, mime: str = "image/png") -> str:
    """Send page/screenshot images to the model and return the transcribed text."""
    import base64

    content = [{"type": "text", "text": VISION_PROMPT}]
    for img in images:
        b64 = base64.b64encode(img).decode()
        content.append({"type": "image_url", "image_url": {"url": f"data:{mime};base64,{b64}"}})
    response = _chat_completion([{"role": "user", "content": content}])
    return (response.choices[0].message.content or "").strip()


def _compliance_warnings(result: dict, country: str, property_name: str = "") -> list:
    """Run the SOP checker over the final output and return any violations.
    Informational only; never raises."""
    from sop_checker import check_compliance

    # Only treat a detected name as a leak risk if it is NOT part of a property
    # name. An operator name that overlaps the property (e.g. "UniLodge" in
    # "UniLodge Melbourne Central") is legitimately kept in the property mention,
    # so passing it would raise a false TERMS_OPERATOR error.
    props_blob = " ".join(
        p for o in (result.get("offers") or []) for p in (o.get("properties") or [])
    ).lower()
    detected = result.get("detected_operator_names", []) or []
    operator_names = [n for n in detected if n and n.lower() not in props_blob]

    property_names = [property_name] if property_name else None
    ctx = {
        "country": country,
        "operator_names": operator_names,
        "property_names": property_names,
        "source_has_tncs": result.get("source_has_tncs", False),
    }
    try:
        return check_compliance(result, ctx)
    except Exception:
        app.logger.exception("compliance check failed")
        return []


def postprocess(data: dict, country: str = "", property_name: str = "") -> dict:
    """Full deterministic post-processing pipeline applied to the model output.

    Order matters: normalise shape first so every downstream step can assume a
    well-formed dict, then strip dashes, strip contact info, fix currency, fix
    first person, drop agent/commission terms (and renumber), rename the operator,
    generalise the property name, and finally annotate title lengths.
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
    data = _generalise_property(data, property_name)
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


# Trailing contact lead-in left dangling after a token is removed
# (e.g. "...; queries to" once the email is gone). Anchored at the end of string.
_TRAILING_CONTACT_RE = re.compile(
    r"[\s;,.\-]*\b(?:contact|email|e-mail|call|phone|tel|queries|enquiries|inquiries|questions)\b"
    r"(?:\s+(?:us|to|at|on|out|via))*\s*[.:]?\s*$",
    re.I,
)


def _scrub_contact_text(text: str, trim_trailing: bool = False) -> str:
    """Remove email/URL/phone tokens from a string and tidy the leftover artefacts.
    When trim_trailing is set (only when a contact token was actually present),
    also drop a dangling trailing contact lead-in like '; queries to'."""
    if not isinstance(text, str):
        return text
    text = _EMAIL_RE.sub("", text)
    text = _URL_RE.sub("", text)
    text = _PHONE_RE.sub("", text)
    text = re.sub(r"\(\s*\)", "", text)            # empty parens left behind
    text = re.sub(r"\s+([.,;:!?])", r"\1", text)   # space before punctuation
    text = re.sub(r"\s{2,}", " ", text)
    if trim_trailing:
        text = _TRAILING_CONTACT_RE.sub("", text)
    return text.strip()


def _strip_contact_info(data: dict) -> dict:
    """Remove emails/URLs/phone numbers from body and terms. Drop a term that is
    only a contact instruction; keep and scrub a term with embedded contact info."""
    for offer in data.get("offers", []) or []:
        if isinstance(offer.get("body"), str):
            body_text = offer["body"]
            body_had_contact = bool(
                _EMAIL_RE.search(body_text) or _URL_RE.search(body_text) or _PHONE_RE.search(body_text)
            )
            offer["body"] = _scrub_contact_text(body_text, trim_trailing=body_had_contact)
        terms = offer.get("terms")
        if not isinstance(terms, list):
            continue
        kept = []
        for t in terms:
            body = re.sub(r"^\s*\(?\d+\)?[.)]?\s*", "", str(t))  # strip leading (n)/n.
            had_contact = bool(
                _EMAIL_RE.search(body) or _URL_RE.search(body) or _PHONE_RE.search(body)
            )
            scrubbed = _scrub_contact_text(body, trim_trailing=had_contact)
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


def _generalise_property(data: dict, property_name: str) -> dict:
    """Replace the specific property's brand name with 'the property' in the copy.
    The offer is shown on the property's own page on amber, so the brand name is
    not needed and we do not advertise the operator's branding. Operator/company
    names are handled separately by _rename_operator -> 'Property Management'."""
    name = (property_name or "").strip()
    if not name:
        return data
    variants = {name}
    core = name.split(",")[0].strip()
    if core:
        variants.add(core)
    pats = [re.compile(rf"\b{re.escape(v)}\b", re.I)
            for v in sorted(variants, key=len, reverse=True)]

    def fix(text):
        if not isinstance(text, str):
            return text
        for p in pats:
            text = p.sub("the property", text)
        text = re.sub(r"\bthe\s+the property\b", "the property", text, flags=re.I)
        return text

    for offer in data.get("offers", []) or []:
        for key in ("title", "body"):
            if isinstance(offer.get(key), str):
                offer[key] = fix(offer[key])
        if isinstance(offer.get("terms"), list):
            offer["terms"] = [fix(t) for t in offer["terms"]]
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


_ALLOWED_UPLOAD_EXTS = (".pdf", ".png", ".jpg", ".jpeg", ".webp")


@app.route("/extract-pdf", methods=["POST"])
def extract_pdf():
    """Extract text from an uploaded PDF or image for the user to review before
    generating. Text-based PDFs are read directly; scanned/screenshot PDFs and
    image uploads are read with the model's vision (when an API key is set)."""
    if "pdf" not in request.files:
        return jsonify({"error": "No PDF uploaded."}), 400
    f = request.files["pdf"]
    filename = (f.filename or "").lower()
    if not filename.endswith(_ALLOWED_UPLOAD_EXTS):
        return jsonify({"error": "Please upload a .pdf, .png, .jpg or .webp file."}), 400

    data = f.read()
    is_pdf = filename.endswith(".pdf")

    # 1) Text-based PDF: use the real text layer, no AI needed.
    if is_pdf:
        try:
            text = extract_pdf_text(io.BytesIO(data))
        except Exception:
            app.logger.exception("pdf extraction failed")
            return jsonify({"error": "Could not read PDF. Please ensure it is a valid PDF file."}), 400
        if text:
            return jsonify({"text": text, "source": "text"})

    # 2) Scanned/screenshot PDF or image upload: read with vision (needs a key).
    if not os.environ.get("OPENAI_API_KEY"):
        return jsonify(
            {
                "text": "",
                "warning": (
                    "This file has no selectable text (it looks like a scan or "
                    "screenshot) and AI reading is unavailable because OPENAI_API_KEY "
                    "is not set. Please copy the offer text and paste it in the box above."
                ),
            }
        )
    try:
        if is_pdf:
            images = _pdf_to_images(data)
            mime = "image/png"
        else:
            ext = filename[filename.rfind("."):]
            images = [data]
            mime = _IMAGE_MIME.get(ext, "image/png")
        vision_text = extract_with_vision(images, mime=mime)
    except Exception:
        app.logger.exception("vision extraction failed")
        return jsonify({"error": "Could not read the file with AI. Please paste the text manually."}), 400

    if not vision_text:
        return jsonify(
            {"text": "", "warning": "No text could be read from this file. Please paste the offer text manually."}
        )
    return jsonify({"text": vision_text, "source": "vision"})


def _output_strings(result: dict):
    """Flatten the structured result into plain output_offer / output_tnc text for logging."""
    offers = result.get("offers") or []
    offer_parts, tnc_parts = [], []
    for o in offers:
        title = (o.get("title") or "").strip()
        body = (o.get("body") or "").strip()
        offer_parts.append((title + "\n\n" + body).strip())
        terms = o.get("terms") or []
        if terms:
            tnc_parts.append("\n".join(terms))
    return "\n\n---\n\n".join(p for p in offer_parts if p), "\n\n---\n\n".join(tnc_parts)


@app.route("/generate", methods=["POST"])
def generate():
    payload = request.get_json(force=True, silent=True) or {}
    raw_offer = (payload.get("raw_offer") or "").strip()
    raw_tnc = (payload.get("raw_tnc") or "").strip()
    country = (payload.get("country") or "").strip()
    property_name = (payload.get("property_name") or "").strip()

    if not raw_offer:
        return jsonify({"error": "Please provide the raw offer text."}), 400
    if len(raw_offer) + len(raw_tnc) > MAX_RAW_OFFER_CHARS:
        return jsonify(
            {"error": f"Offer text is too long (max {MAX_RAW_OFFER_CHARS} characters)."}
        ), 400
    if not os.environ.get("OPENAI_API_KEY"):
        return jsonify(
            {"error": "OPENAI_API_KEY is not set. Add it to your environment or .env file."}
        ), 400

    try:
        result = generate_offer(country, property_name, raw_offer, raw_tnc)
    except Exception:
        app.logger.exception("generation failed")
        return jsonify({"error": "Generation failed. Please try again."}), 500

    # Best-effort run logging; never blocks the response.
    output_offer, output_tnc = _output_strings(result)
    run_id = db.log_run(country, property_name, MODEL, raw_offer, raw_tnc,
                        output_offer, output_tnc, result)
    if run_id is not None:
        result["run_id"] = run_id

    return jsonify(result)


@app.route("/feedback", methods=["POST"])
def feedback():
    """Attach a rating (1-5) and/or comment to a previously logged run."""
    payload = request.get_json(force=True, silent=True) or {}
    run_id = payload.get("run_id")
    rating = payload.get("rating")
    comment = (payload.get("comment") or "").strip() or None

    if run_id is None:
        return jsonify({"error": "run_id is required."}), 400
    try:
        run_id = int(run_id)
    except (TypeError, ValueError):
        return jsonify({"error": "run_id must be an integer."}), 400

    if rating is not None:
        try:
            rating = int(rating)
        except (TypeError, ValueError):
            return jsonify({"error": "rating must be an integer 1-5."}), 400
        if not (1 <= rating <= 5):
            return jsonify({"error": "rating must be between 1 and 5."}), 400

    if rating is None and comment is None:
        return jsonify({"error": "Provide a rating and/or a comment."}), 400

    ok = db.save_feedback(run_id, rating, comment)
    if not ok:
        return jsonify({"error": "Could not save feedback."}), 500
    return jsonify({"ok": True})


if __name__ == "__main__":
    # Local/dev entrypoint. In production (Render) gunicorn imports `app` directly
    # via the start command, so this block is not used there.
    port = int(os.environ.get("PORT", 5000))
    debug = os.environ.get("FLASK_DEBUG", "0").lower() in ("1", "true", "yes")
    app.run(host="0.0.0.0", port=port, debug=debug)
