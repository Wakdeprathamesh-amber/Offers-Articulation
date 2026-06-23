# Offer Content Automation — Version 1

**Repo:** https://github.com/Wakdeprathamesh-amber/Offers-Articulation
**Status:** Ready for team testing (deployed on Render)
**Model:** OpenAI `gpt-5.5` (multimodal)

---

## 1. Goal

The supply team copies a raw promotional offer (from a PMG website or a forwarded
marketing email, often a screenshot) into the tool. The tool rewrites it into
amber's house style — **Offer Title, Offer Body and Terms & Conditions** — following
`SOP - Offer.docx`, and flags offers that are **not applicable to amber**. A human
reviews and approves before publishing.

```
Raw offer (text / PDF / screenshot)
   → applicability & exclusion check
   → Title + Body + T&Cs (one per offer found)
   → deterministic SOP clean-up + ⚠ review warnings
```

---

## 2. User flow

1. Pick the **Country** (sets the currency).
2. Enter the **property name(s)**.
3. **Paste** the offer text, or **upload a PDF / screenshot / image** and click
   *Extract from PDF / Image*.
4. Click **Generate offer content**.
5. Review the output (Title with live character count, Body, numbered T&Cs, anything
   missing from the source, and any ⚠ review flags), then copy each field.

---

## 3. Features in v1

| Area | What it does |
|------|--------------|
| **Applicability check** | Marks offers ✓ applicable / ✗ not applicable / ⚠ needs-KAM. Excludes direct-booking-only, lucky-draw, refer-a-friend, and pure low-rate offers. Correctly treats agent/commission mentions as **applicable** (amber is a booking agent). |
| **Title generation** | ≤60 chars (hard cap 72) with live counter, Title Case, exactly one capitalised power word, digits not words, no "Book" start, correct currency, varied hooks across multiple offers. |
| **Body generation** | Punchy opener, room types, validity window, booking caps, lease window, reward tiers as bullets, clear CTA. Captures every real detail; never invents (gaps → "missing from source"). |
| **T&Cs** | Rewrites the **provided** T&Cs (numbered) or falls back to the 7 generic T&Cs only when none are provided. |
| **Brand generalisation** | Removes ALL brand names from the copy — the specific property name → "the property", the operator/PMG company → "Property Management" — so amber does not advertise the operator and students stay on the amber page. |
| **Offer / T&C separation** | Offer body is built only from the offer text; T&Cs only from the source T&Cs; no mixing, no inventing. |
| **Auto-clean (deterministic)** | Removes em/en dashes, agent/commission clauses (and renumbers), emails/phones/URLs, first-person wording; normalises the currency symbol to the country. |
| **⚠ Review warnings** | Anything the auto-cleaner can't safely fix (e.g. unusual first-person) is flagged in a per-offer "Review before publishing" panel. |
| **Input: PDF / image / vision** | Text PDFs read directly; scanned/screenshot PDFs and image uploads (PNG/JPG/WEBP) are read by `gpt-5.5` vision and transcribed into the box for review. |
| **Multiple offers** | One source can produce several offers (different properties/promos), each with a varied title. |

---

## 4. SOP rules enforced (checklist)

- [x] Applicability: direct-only / lucky-draw / refer-a-friend / low-rate excluded
- [x] Agents = applicable (not excluded)
- [x] Title ≤60 / ≤72, Title Case, one power word, digits, no "Book", correct currency
- [x] Body: all source details, tiers, dates, caps, CTA; no invention
- [x] T&Cs rewritten when provided; generic only when none provided
- [x] No brand names (property or operator) anywhere in the copy
- [x] No em/en dashes anywhere
- [x] No first-person (we/us/our) in T&Cs
- [x] No agent/commission clauses in T&Cs
- [x] No emails / phones / addresses in the output
- [x] Numbered T&Cs (never bulleted), renumbered after removals

---

## 5. Quality & testing

- **173 automated tests** (offline, no network) — run on every change.
- **Live SOP eval:** 23 diverse real-world scenarios across countries / reward types /
  exclusions graded by an automated SOP checker → **23/23 passed, 0 errors** on `gpt-5.5`.
- A live **SOP checker** runs on every generation and attaches any residual issues as
  warnings (defence-in-depth: prompt → deterministic clean-up → live check).

---

## 6. Model & infrastructure

- **Model:** `gpt-5.5` (set via `OPENAI_MODEL`; the OpenAI call is model-agnostic and
  auto-adapts to models that reject a custom temperature).
- **Hosting:** Render web service (gunicorn), auto-deploys on push to `main`.
- **Config (env vars):** `OPENAI_API_KEY` (secret), `OPENAI_MODEL=gpt-5.5`,
  `OPENAI_TIMEOUT=60`, `PYTHON_VERSION=3.12.6`.
- **Hardening:** debug off by default, 8 MB upload cap, 20k-char input cap, sanitised
  error messages (full traces in server logs only), request timeout + retries.
- **Security:** API key only in env vars; never committed.

---

## 7. Known limitations (v1)

- Vision transcription quality depends on image clarity; the user always reviews the
  extracted text before generating.
- First-person / currency auto-fixes are best-effort; the ⚠ warning is the backstop.
- No run history / analytics yet (in progress — see roadmap).
- No authentication / rate-limiting on the public URL (relies on the secret key).

---

## 8. Roadmap / next

- **In progress:** PostgreSQL run-logging (input, output, model, timestamp) for history
  and analytics. Wires to a `DATABASE_URL` env var.
- **Candidate:** generate directly from an image (skip the transcription step);
  per-property analytics; auth on the public URL; "already live on amber" pre-check.
