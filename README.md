# amber · Offer Content Automation (v1)

Turns a raw promotional offer (pasted text or an uploaded PDF/screenshot/image) into
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
3. Either **paste the offer text** (with optional separate T&Cs), **or upload a
   PDF / screenshot / image** of the offer (use one or the other, not both).
4. Click **Generate offer content**. An uploaded file is sent straight to the
   model (`gpt-5.5`) — no separate extraction step.

Output shows an applicability verdict (✓ / ✗ / ⚠ needs KAM), exclusion flags,
and for each offer the Title (with live character count vs the 60/72 limits),
Body, numbered T&Cs, and anything missing from the source.

The app deterministically cleans the model output before showing it (removes em/en
dashes, agent/commission clauses, contact details; renames the operator to
"Property Management"; normalises the currency; fixes common first-person wording).
Anything the automatic cleaner cannot safely fix is listed in a **⚠ Review before
publishing** panel so the reviewer can correct it before copying.

## Notes / limits (v1)

- **PDF, screenshots and images supported.** An uploaded PDF/PNG/JPG/WEBP is sent
  **directly to the model** (`gpt-5.5`, multimodal) — PDF pages are rasterised to
  images first; there is no separate text-extraction step. Paste text instead if
  you prefer.
- **All output copy is brand-generic.** The specific property name and the
  operator/PMG company name are replaced with "the property" / "Property
  Management" so amber does not advertise the operator's branding.
- **Run-logging (optional).** Set `WAKDE_DB_HOST / _PORT / _NAME / _USER /
  _PASSWORD` (PostgreSQL) to log each run (inputs, outputs, model, timestamp) to
  `offer_articulation_runs` and capture the user's 1-5 rating + comment. If unset,
  logging is silently skipped and generation works normally.
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
| `app.py` | Flask server: routes, PDF→image rasterising, OpenAI call, post-processing |
| `prompts.py` | SOP-encoded system prompt, currency map, generic T&Cs, few-shot examples |
| `templates/index.html` | Single-page UI |
| `requirements.txt` | Dependencies |
| `.env.example` | Template for your OpenAI key |
