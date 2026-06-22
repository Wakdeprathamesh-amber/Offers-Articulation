# amber · Offer Content Automation (v1)

Turns a raw promotional offer (pasted text or a text-based PDF) into
**SOP-compliant Offer Title, Offer Body and Terms & Conditions**, and flags
offers that are **not applicable to Amber** (direct-booking-only, lucky draw,
refer-a-friend, borderline low-rate). It encodes `SOP - Offer.docx` and is
anchored on the four real example tickets (UK ×2, US, AUS).

## How it works

```
Raw offer  ──►  applicability / exclusion check  ──►  Title + Body + T&Cs
(text/PDF)        (flag + KAM-confirm needed?)         (one per offer found)
```

The SOP rules live in `prompts.py` (title rules, currency map, the 7 generic
T&Cs, exclusion logic). The backend (`app.py`) sends the offer + rules to the
OpenAI API and returns structured JSON the UI renders with one-click copy.

## Setup

```bash
cd "offer content automation"
python3 -m venv venv && source venv/bin/activate
pip install -r requirements.txt

cp .env.example .env        # then edit .env and paste your OpenAI key
# or: export OPENAI_API_KEY=sk-...

python app.py
```

Open <http://127.0.0.1:5000>.

## Using it

1. Pick the **Country** (sets the correct currency: £ / US$ / AU$ / CA$ / S$).
2. Enter the **property name(s)**.
3. Paste the **raw offer text**, or upload a **text-based PDF** and click
   *Extract from PDF*.
4. Click **Generate offer content**.

Output shows an applicability verdict (✓ / ✗ / ⚠ needs KAM), exclusion flags,
and for each offer the Title (with live character count vs the 60/72 limits),
Body, numbered T&Cs, and anything missing from the source.

The app deterministically cleans the model output before showing it (removes em/en
dashes, agent/commission clauses, contact details; renames the operator to
"Property Management"; normalises the currency; fixes common first-person wording).
Anything the automatic cleaner cannot safely fix is listed in a **⚠ Review before
publishing** panel so the reviewer can correct it before copying.

## Notes / limits (v1)

- **Text only.** Image / screenshot offers must be copied out and pasted — a
  scanned PDF with no text layer will warn you. (Vision support is a v2 item.)
- Model defaults to `gpt-4o` in code; production (Render) is set to `gpt-5.5` for
  best articulation. Override with `OPENAI_MODEL`. The OpenAI call is model-agnostic
  (it drops `temperature` automatically for models that reject a custom value, e.g.
  gpt-5/gpt-5.5). Tune the per-request timeout with `OPENAI_TIMEOUT` (default 60s).
- The app never hardcodes your key — it reads `OPENAI_API_KEY` from the env/.env.

## Deploy to Render

This repo is Render-ready (`render.yaml` + `gunicorn`).

1. Push to GitHub (see prompt below) — `.env` is gitignored, so your key stays local.
2. In Render: **New + → Blueprint**, pick this repo. It reads `render.yaml`:
   - Build: `pip install -r requirements.txt`
   - Start: `gunicorn app:app --bind 0.0.0.0:$PORT`
3. In the service's **Environment** tab, set `OPENAI_API_KEY` to your key
   (never commit it). `OPENAI_MODEL` defaults to `gpt-4o`.
4. Deploy. Render serves the app on its public URL.

> Security: the API key lives only in Render's env vars and your local `.env`.
> It is never in the code or the Git history.

## Files

| File | Purpose |
|------|---------|
| `app.py` | Flask server: routes, PDF text extraction, OpenAI call |
| `prompts.py` | SOP-encoded system prompt, currency map, generic T&Cs, few-shot examples |
| `templates/index.html` | Single-page UI |
| `requirements.txt` | Dependencies |
| `.env.example` | Template for your OpenAI key |
