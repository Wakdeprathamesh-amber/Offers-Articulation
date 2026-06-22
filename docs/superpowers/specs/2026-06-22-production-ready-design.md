# Offer Content Automation — Production-Readiness Design

- **Date:** 2026-06-22
- **Status:** Approved (design), pending implementation
- **Author:** Engineering (with product-tools@amberstudent.com)

## 1. Context & goal

The supply team copies a raw promotional offer (from a PMG website or forwarded
marketing email, often transcribed out of a screenshot) into this tool. The tool
rewrites it into amber's house style — a compliant **Offer Title, Offer Body and
Terms & Conditions** — per `SOP - Offer.docx`, and flags offers not applicable to
amber. A human reviews and approves before it goes live.

Pipeline today:

```
raw_offer ──► build_user_prompt (SOP + few-shot) ──► OpenAI (JSON) ──► postprocess() ──► JSON to UI
```

This change hardens that pipeline for production and closes correctness gaps found
during an audit of the code, the SOP, and the four real demo tickets (UniLodge AUS
#538841, Student Roost UK #538902, FSL UK #538696, Cardinal Group US #538774).

## 2. Problems being fixed

**Correctness / SOP fidelity**
1. Few-shot **Example 3 (Radford Mill) is wrong** — `prompts.py` says "no T&Cs →
   use the generic 7," but ticket #538696 shows T&Cs *were* provided and the human
   wrote **6 rewritten** terms. This mis-teaches the core "rewrite when provided" rule.
2. **The SOP checker is not in the live path.** `generate_offer` never calls
   `check_compliance`, so first-person ("we/us/our"), leaked emails/phones/URLs, and
   wrong-currency slips reach the user unflagged.
3. **Operator-name rename covers only two phrasings** ("X reserves the right",
   "any other X property"). Other leaks ("as per X's terms", "credited by X") pass
   through, and the checker can't catch them live because the operator name is unknown
   at runtime.
4. **No deterministic safety net** for first-person, contact info, or currency — all
   rely on the model obeying the prompt.

**Production hardening (app-level)**
5. `app.run(debug=True)` by default → Werkzeug debugger RCE if ever run directly.
6. No upload size limit and no `raw_offer` length cap → unbounded memory / OpenAI cost.
7. Error responses leak raw exception text to the client.
8. No timeout/retry on the OpenAI call.

## 3. Scope

**In scope:** items 1–8 above, with the chosen enforcement model **auto-fix + warn**.

**Out of scope (confirmed):**
- Vision/OCR for screenshot offers — remains a documented v2 item. Tool stays text-only.
- Auth / rate-limiting / infrastructure changes — "app-level only".
- "Skip if already live on amber" (requires a property-page datasource the tool
   does not have) — remains a human pre-check.

## 4. Approach — layered defense

Three independent lines of defense so no single failure ships a bad offer:

1. **Prompt (primary):** clear rules + corrected few-shot. The model also returns
   small metadata (`detected_operator_names`, `source_has_tncs`) used downstream.
2. **Deterministic post-processors (safety net):** pure functions that auto-clean
   what the model missed. Each is independently unit-tested and idempotent.
3. **Live SOP gate (informational):** run `check_compliance` on the final output and
   attach remaining issues as `warnings`. Never blocks; just informs the reviewer.

Rejected alternatives: prompt-only + warnings (under-delivers on auto-fix); two-pass
model self-correction (doubles cost/latency, adds nondeterminism — overkill for v1).

## 5. Components

Each unit: **what it does / interface / depends on.**

### 5.1 `prompts.py`
- **What:** Fix Example 3 to the real rewritten T&Cs from #538696. Add two fields to
  the strict output contract: `detected_operator_names: string[]` (PMG/operator/brand
  names the model identified, excluding the property's own identifying name) and
  `source_has_tncs: boolean`. Minor tightening of first-person/contact/currency rules.
- **Interface:** `SYSTEM_PROMPT` (str), `build_user_prompt(country, property_name, raw_offer) -> str`. Unchanged signatures.
- **Depends on:** nothing new.

### 5.2 `app.py` — new sanitizers (added to `postprocess()`)
All are pure `dict -> dict`, operate only on generated text fields, and are idempotent.

- **`_strip_contact_info(data)`** — remove email/URL/phone tokens from `body` and each
  `term`; if a term becomes empty or contact-only after stripping, drop it and renumber.
- **`_fix_currency(data, expected_symbol)`** — when the country maps to a known symbol,
  replace any *other* distinctive currency token in `title`/`body` with the expected
  symbol (number preserved). No-op when country/symbol unknown.
- **`_fix_first_person(data)`** — conservative regex swaps for high-frequency safe
  patterns (e.g. "we reserve the right" → "Property Management reserves the right",
  "our terms" → "Property Management's terms"); residual first-person is left for the
  warning layer.
- **`_rename_operator(data, detected_names=())`** — extend the existing function to also
  replace each model-reported operator name everywhere in `body`/`terms`, **except**
  where the token is the property's own identifying name. Existing 2-pattern regex net
  stays as a fallback for un-reported names.

**Pipeline order** (matters; normalise first, annotate last):
```
_normalize → _strip_dashes → _strip_contact_info → _fix_currency
→ _fix_first_person → _clean_agent_terms → _rename_operator(detected) → _annotate
```

### 5.3 `app.py` — live SOP gate
- **`generate_offer`** builds a `ctx` from `country`, the model's
  `detected_operator_names`, and `source_has_tncs`, runs `check_compliance(result, ctx)`,
  and sets `result["warnings"] = [{severity, rule, message, offer_index}, ...]`
  (both errors and warns). Compliance never raises and never blocks the response.

### 5.4 `sop_checker.py`
- No rule changes required. Confirm it runs cleanly with the live `ctx`. The result
  list already carries `severity`; the gate passes it through verbatim.

### 5.5 `templates/index.html`
- Render a per-offer "⚠ Review before publishing" panel listing `warnings` for that
  offer index, plus any non-offer-scoped warnings at the top. Pure presentation; no
  behavioural change.

### 5.6 `app.py` — hardening
- `debug = os.environ.get("FLASK_DEBUG", "0") ...` (default **off**).
- `app.config["MAX_CONTENT_LENGTH"] = 8 * 1024 * 1024`; return a clean 413.
- Cap `raw_offer` at 20,000 chars → 400 with a clear message.
- Catch-all in routes logs the full exception server-side (`app.logger`) and returns a
  generic client message (no `exc` text).
- OpenAI client constructed with `timeout=30` and `max_retries=2`.
- Guard `f.filename` being `None`/empty before `.lower()`.

## 6. Data flow

```
raw_offer
  → build_user_prompt(country, property, raw_offer)
  → OpenAI chat.completions (json_object, timeout, retries)
  → json.loads
  → postprocess(): normalize → strip_dashes → strip_contact → fix_currency
                   → fix_first_person → clean_agent_terms → rename_operator(detected) → annotate
  → check_compliance(result, ctx)  → result["warnings"]
  → JSON response → UI (offers + ⚠ warnings)
```

## 7. Error handling

- Model returns invalid JSON → caught, logged, generic 500.
- OpenAI error/timeout → retried (max_retries), then caught, logged, generic 500.
- Upload too large → 413; wrong extension / no file → 400; raw_offer too long → 400.
- A failing sanitizer must never crash the request: postprocess steps are defensive
  (type-guarded), matching existing behaviour.

## 8. Testing strategy

TDD. The offline suite (OpenAI mocked) stays the always-green gate.

- **Unit:** one test file (or section) per new sanitizer — happy path, edge cases,
  non-string passthrough, idempotency. Extend `_rename_operator` tests for
  detected-name replacement and property-name preservation.
- **Pipeline:** update `test_postprocess.py` for the new order; assert combined output
  is clean and idempotent.
- **Live gate:** new test (mocked OpenAI) asserting `warnings` is populated when the
  model slips and empty on clean output.
- **Routes:** size cap (413), raw_offer length cap (400), sanitized error message
  (no exception text), missing-filename guard.
- **Prompt:** assert Example 3 now shows rewritten (non-generic) T&Cs and the new
  output-contract fields are documented.
- **Scenarios/eval:** extend `scenarios.py` ctx where useful; `run_eval.py` and the
  live compliance suite remain opt-in (need `OPENAI_API_KEY`).

**Acceptance:** full offline suite green; the end-to-end harness shows a deliberately
messy model output cleaned to zero hard SOP errors, with residual issues surfaced as
warnings.

## 9. Risks

- First-person / currency auto-fix is best-effort; mitigated by the always-on warning
  layer and the human review gate.
- Model may under- or over-report `detected_operator_names`; the existing regex net
  and the live check both backstop this.
