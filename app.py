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

from flask import Flask, jsonify, render_template, request

from prompts import SYSTEM_PROMPT, build_user_prompt

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
    """Call the OpenAI API and return the parsed JSON result."""
    from openai import OpenAI

    client = OpenAI()  # reads OPENAI_API_KEY from env
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
    return postprocess(data)


def postprocess(data: dict) -> dict:
    """Full deterministic post-processing pipeline applied to the model output.

    Order matters: normalise shape first so every downstream step can assume a
    well-formed dict, then clean dashes, strip agent/commission terms (and
    renumber), and finally annotate title lengths.
    """
    return _annotate(_clean_agent_terms(_strip_dashes(_normalize(data))))


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
