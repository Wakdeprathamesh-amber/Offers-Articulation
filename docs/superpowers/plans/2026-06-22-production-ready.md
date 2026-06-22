# Production-Readiness Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Close the SOP-fidelity and safety gaps in the offer generator and harden the Flask app for production, using a layered defense (prompt → deterministic sanitizers → live SOP-check warnings).

**Architecture:** Keep the existing single-module Flask layout. Add pure, idempotent sanitizers to `postprocess()` in `app.py`; thread `country` and model-reported `detected_operator_names` through; run `check_compliance` after postprocess and attach `warnings`. Fix the wrong few-shot in `prompts.py`. Surface warnings in `index.html`.

**Tech Stack:** Python 3.12+, Flask, OpenAI SDK, pytest. Run from the repo's `venv`.

---

## File Map

| File | Responsibility | Change |
|------|----------------|--------|
| `prompts.py` | SOP prompt, few-shot, output contract | Fix Example 3; add `detected_operator_names` + `source_has_tncs` to contract |
| `app.py` | routes, pipeline, OpenAI call, hardening | New sanitizers; new pipeline order + `country`; live SOP gate; hardening |
| `sop_checker.py` | rule linter | No rule changes (reused by the gate) |
| `templates/index.html` | UI | Render per-offer ⚠ warnings panel |
| `tests/*` | regression suite | New + extended tests |

**Pipeline order (final):**
```
_normalize → _strip_dashes → _strip_contact_info → _fix_currency
→ _fix_first_person → _clean_agent_terms → _rename_operator(detected) → _annotate
```

All commands run from the repo root with the venv active:
```bash
cd "offer-content-automation" && source venv/bin/activate
```

---

## Task 1: Fix few-shot Example 3 + extend the output contract (`prompts.py`)

**Files:**
- Modify: `prompts.py` (Example 3 block; OUTPUT FORMAT block)
- Test: `tests/test_prompts.py`

- [ ] **Step 1: Write failing tests**

Add to `tests/test_prompts.py`:
```python
def test_example3_rewrites_provided_tncs_not_generic(prompts):
    fs = prompts.FEW_SHOT_EXAMPLES
    # Example 3 (Radford Mill) had T&Cs in a screenshot -> must show rewritten terms,
    # NOT instruct "use the 7 generic T&Cs".
    start = fs.index("EXAMPLE 3")
    end = fs.index("EXAMPLE 4")
    block = fs[start:end]
    assert "use the 7 GENERIC T&Cs" not in block
    assert "51 week tenancy" in block or "51-week" in block
    assert "Property Management reserves the right" in block

def test_output_contract_has_new_fields(prompts):
    sp = prompts.SYSTEM_PROMPT
    assert '"detected_operator_names"' in sp
    assert '"source_has_tncs"' in sp
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `python -m pytest tests/test_prompts.py::test_example3_rewrites_provided_tncs_not_generic tests/test_prompts.py::test_output_contract_has_new_fields -v`
Expected: FAIL (current text says "use the 7 GENERIC T&Cs"; fields absent).

- [ ] **Step 3: Replace the Example 3 block**

In `prompts.py`, replace the entire `EXAMPLE 3` section (from `==================== EXAMPLE 3` up to `==================== EXAMPLE 4`) with:
```python
==================== EXAMPLE 3 — UK, short blurb + T&Cs in an attached screenshot ====================
COUNTRY: United Kingdom (£)
PROPERTY: Radford Mill, Nottingham
SOURCE: "Book now and receive a £500 discount!" 51-week tenancy, 2026-2027
academic year, all room types. A screenshot was attached containing the full
Terms & Conditions (discount mechanics, eligibility, first-come basis, no
semester lets, cancellation forfeits the discount, etc.). A private note
confirmed the offer is valid for international agents.

CORRECT OUTPUT:
title: "Hot Deal Alert: Enjoy £500 Rent DISCOUNT Today!"
body:
"Book a 51-week tenancy for the 2026-2027 academic year and receive a £500 rent DISCOUNT on any room type!

The discount will be applied to your total contract value once all booking requirements have been completed.

Secure your room today and enjoy amazing savings on your student accommodation!"
terms: T&Cs WERE provided (in the attached screenshot), so REWRITE them, one numbered
term each, with the operator name replaced by "Property Management". Do NOT fall back to
the generic list:
(1) The £500 discount applies to all room types on a 51-week tenancy and will be applied to the total contract value upon completion of all booking requirements.
(2) The offer applies only to bookings made for a 51-week tenancy in the 2026/27 academic year.
(3) Availability is limited, and Property Management may remove or amend the promotion at any time.
(4) The £500 discount will only apply once the tenancy agreement is signed, the tenant has moved in, and the first rent instalment has been paid. Rooms are available on a first come, first served basis. This offer is not available on semester lets.
(5) The offer is valid on a limited number of bookings only and will be withdrawn once the maximum number of incentives has been reached. It cannot be combined with any other promotion. If the tenancy is cancelled, the discount is void and may be reversed. The offer is not transferable.
(6) Property Management reserves the right to amend these terms and conditions at any time.

```

- [ ] **Step 4: Extend the OUTPUT FORMAT contract**

In `prompts.py`, inside the `OUTPUT FORMAT (STRICT)` JSON shape, add the two fields just after `"needs_kam_confirmation": true | false,`:
```python
  "needs_kam_confirmation": true | false,
  "source_has_tncs": true | false,
  "detected_operator_names": ["the PMG / operator / landlord / management-company / brand name(s) you found, EXCLUDING the property's own identifying name", ...],
```
And add to the `JSON rules:` list:
```python
- "source_has_tncs" is true if the source contained ANY Terms & Conditions block
  (including an attached/transcribed screenshot), false if none were provided.
- "detected_operator_names" lists the operator/PMG/brand names you replaced with
  "Property Management" (e.g. "Maple Living Group", "FSL"). Empty list if none.
```

- [ ] **Step 5: Run tests to verify they pass**

Run: `python -m pytest tests/test_prompts.py -v`
Expected: PASS (all, including the two new tests).

- [ ] **Step 6: Commit**

```bash
git add prompts.py tests/test_prompts.py
git commit -m "fix(prompts): correct Example 3 to rewrite provided T&Cs; add detected_operator_names + source_has_tncs to contract"
```

---

## Task 2: Normalize the two new fields (`app.py::_normalize`)

**Files:**
- Modify: `app.py` (`_normalize`)
- Test: `tests/test_normalize.py`

- [ ] **Step 1: Write failing tests**

Add to `tests/test_normalize.py`:
```python
def test_detected_operator_names_defaults_empty(appmod):
    assert appmod._normalize({})["detected_operator_names"] == []

def test_detected_operator_names_string_becomes_list(appmod):
    out = appmod._normalize({"detected_operator_names": "Maple Living Group"})
    assert out["detected_operator_names"] == ["Maple Living Group"]

def test_detected_operator_names_filters_blanks(appmod):
    out = appmod._normalize({"detected_operator_names": ["", "  ", "FSL"]})
    assert out["detected_operator_names"] == ["FSL"]

def test_source_has_tncs_coerced_to_bool(appmod):
    assert appmod._normalize({"source_has_tncs": "yes"})["source_has_tncs"] is True
    assert appmod._normalize({})["source_has_tncs"] is False
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `python -m pytest tests/test_normalize.py -k "detected or source_has" -v`
Expected: FAIL (KeyError / missing keys).

- [ ] **Step 3: Implement**

In `app.py::_normalize`, just before `return data`, add:
```python
    names = data.get("detected_operator_names")
    if isinstance(names, str):
        names = [names]
    elif not isinstance(names, list):
        names = []
    data["detected_operator_names"] = [str(n).strip() for n in names if str(n).strip()]
    data["source_has_tncs"] = bool(data.get("source_has_tncs", False))
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `python -m pytest tests/test_normalize.py -v`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add app.py tests/test_normalize.py
git commit -m "feat(normalize): coerce detected_operator_names + source_has_tncs"
```

---

## Task 3: Contact-info stripper (`app.py::_strip_contact_info`)

**Files:**
- Modify: `app.py` (add regexes + function)
- Test: `tests/test_strip_contact.py` (create)

- [ ] **Step 1: Write failing tests**

Create `tests/test_strip_contact.py`:
```python
"""Tests for _strip_contact_info — removes emails/URLs/phones from body+terms."""


def test_email_removed_from_body(appmod):
    out = appmod._strip_contact_info(
        {"offers": [{"body": "Save now! Email leasing@pmg.com to apply.", "terms": []}]}
    )
    assert "leasing@pmg.com" not in out["offers"][0]["body"]


def test_url_removed_from_body(appmod):
    out = appmod._strip_contact_info(
        {"offers": [{"body": "Visit https://pmg.com/offer for details.", "terms": []}]}
    )
    assert "http" not in out["offers"][0]["body"]


def test_phone_removed_from_terms(appmod):
    out = appmod._strip_contact_info(
        {"offers": [{"body": "", "terms": ["(1) Call +61 3 9000 0000 for help.", "(2) Keeper term here."]}]}
    )
    joined = " ".join(out["offers"][0]["terms"])
    assert "9000 0000" not in joined
    assert "Keeper term" in joined


def test_contact_only_term_dropped_and_renumbered(appmod):
    out = appmod._strip_contact_info(
        {"offers": [{"body": "", "terms": [
            "(1) A real condition applies.",
            "(2) Contact bookings@pmg.com for queries.",
            "(3) Another real condition.",
        ]}]}
    )
    terms = out["offers"][0]["terms"]
    assert terms == ["(1) A real condition applies.", "(2) Another real condition."]


def test_term_with_embedded_email_kept_but_scrubbed(appmod):
    out = appmod._strip_contact_info(
        {"offers": [{"body": "", "terms": [
            "(1) The discount is applied after move-in; queries to leasing@pmg.com are welcome."
        ]}]}
    )
    t = out["offers"][0]["terms"][0]
    assert "leasing@pmg.com" not in t
    assert "discount is applied after move-in" in t


def test_no_contact_is_idempotent(appmod):
    data = {"offers": [{"body": "Plain body, no contacts.", "terms": ["(1) Plain term."]}]}
    once = appmod._strip_contact_info({"offers": [dict(data["offers"][0])]})
    assert once["offers"][0]["body"] == "Plain body, no contacts."
    assert once["offers"][0]["terms"] == ["(1) Plain term."]


def test_date_range_not_treated_as_phone(appmod):
    out = appmod._strip_contact_info(
        {"offers": [{"body": "Valid 15/06/2026 to 10/08/2026.", "terms": []}]}
    )
    assert "15/06/2026" in out["offers"][0]["body"]
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `python -m pytest tests/test_strip_contact.py -v`
Expected: FAIL (`AttributeError: module 'app' has no attribute '_strip_contact_info'`).

- [ ] **Step 3: Add a module-level `re` import**

At the top of `app.py` (with `import json`, `import os`), add:
```python
import re
```
(The file already has `import re as _re` lower down for the operator regexes; leave it. The new code uses the top-level `re`.)

- [ ] **Step 3b: Implement the stripper**

In `app.py`, add near the other helpers (after `_clean_dashes`):
```python
_EMAIL_RE = re.compile(r"[\w.+-]+@[\w-]+\.[\w.-]+")
_URL_RE = re.compile(r"\b(?:https?://|www\.)\S+", re.I)
_PHONE_RE = re.compile(r"(?:\+\d[\d\s\-()]{7,}\d)|(?:\b\d{3}[\s.\-]\d{3}[\s.\-]\d{4}\b)")
_CONTACT_LEADINS = (
    "contact", "email", "e-mail", "call", "phone", "questions", "queries",
    "for queries", "for details", "for more", "reach us", "reach out",
)


def _scrub_contact_text(text: str) -> str:
    import re
    if not isinstance(text, str):
        return text
    text = _EMAIL_RE.sub("", text)
    text = _URL_RE.sub("", text)
    text = _PHONE_RE.sub("", text)
    text = re.sub(r"\(\s*\)", "", text)        # empty parens left behind
    text = re.sub(r"\s+([.,;:!?])", r"\1", text)  # space before punctuation
    text = re.sub(r"\s{2,}", " ", text)
    return text.strip()


def _strip_contact_info(data: dict) -> dict:
    """Remove emails/URLs/phone numbers from body and terms. Drop a term that is
    only a contact instruction; keep and scrub a term with embedded contact info."""
    import re
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
```
> The inline `import re` inside `_scrub_contact_text`/`_strip_contact_info` matches the existing style in `_clean_agent_terms`; the module-level `re` (Step 3) powers the compiled regexes.

- [ ] **Step 4: Run tests to verify they pass**

Run: `python -m pytest tests/test_strip_contact.py -v`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add app.py tests/test_strip_contact.py
git commit -m "feat(sanitize): strip emails/URLs/phones from body+terms, drop contact-only terms"
```

---

## Task 4: Currency fixer (`app.py::_fix_currency`)

**Files:**
- Modify: `app.py` (add function + token regex)
- Test: `tests/test_fix_currency.py` (create)

- [ ] **Step 1: Write failing tests**

Create `tests/test_fix_currency.py`:
```python
"""Tests for _fix_currency — swaps wrong currency symbols for the expected one."""


def test_wrong_symbol_in_title_swapped(appmod):
    out = appmod._fix_currency(
        {"offers": [{"title": "Save US$500 OFF!", "body": ""}]}, "£"
    )
    assert out["offers"][0]["title"] == "Save £500 OFF!"


def test_us_token_not_confused_with_s(appmod):
    # Expected S$ (Singapore); US$ must become S$, not be left as "US$".
    out = appmod._fix_currency(
        {"offers": [{"title": "Get US$500 GIFT CARD!", "body": "Enjoy US$500 today."}]}, "S$"
    )
    assert "US$" not in out["offers"][0]["title"]
    assert out["offers"][0]["title"] == "Get S$500 GIFT CARD!"


def test_correct_symbol_untouched(appmod):
    out = appmod._fix_currency({"offers": [{"title": "Save £500 OFF!", "body": ""}]}, "£")
    assert out["offers"][0]["title"] == "Save £500 OFF!"


def test_unknown_country_is_noop(appmod):
    out = appmod._fix_currency({"offers": [{"title": "Save US$500!", "body": ""}]}, None)
    assert out["offers"][0]["title"] == "Save US$500!"


def test_multiple_symbols_all_normalized(appmod):
    out = appmod._fix_currency({"offers": [{"title": "", "body": "AU$50 or €50 or £50"}]}, "£")
    assert out["offers"][0]["body"] == "£50 or £50 or £50"
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `python -m pytest tests/test_fix_currency.py -v`
Expected: FAIL (`_fix_currency` not defined).

- [ ] **Step 3: Implement**

In `app.py`, add:
```python
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
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `python -m pytest tests/test_fix_currency.py -v`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add app.py tests/test_fix_currency.py
git commit -m "feat(sanitize): normalize wrong currency symbols to the country's expected symbol"
```

---

## Task 5: First-person fixer (`app.py::_fix_first_person`)

**Files:**
- Modify: `app.py` (add function + substitution table)
- Test: `tests/test_fix_first_person.py` (create)

- [ ] **Step 1: Write failing tests**

Create `tests/test_fix_first_person.py`:
```python
"""Tests for _fix_first_person — conservative first-person -> Property Management swaps."""

import pytest


@pytest.mark.parametrize("before,after_contains", [
    ("(1) We reserve the right to amend.", "Property Management reserves the right to amend"),
    ("(1) we reserve the right to cancel.", "Property Management reserves the right to cancel"),
    ("(1) We will credit the cashback after move-in.", "Property Management will credit"),
    ("(1) We may withdraw this offer.", "Property Management may withdraw"),
    ("(1) Subject to our terms and conditions.", "Property Management's terms and conditions"),
])
def test_common_first_person_swapped(appmod, before, after_contains):
    out = appmod._fix_first_person({"offers": [{"body": "", "terms": [before]}]})
    assert after_contains in out["offers"][0]["terms"][0]


def test_no_lingering_we_in_handled_patterns(appmod):
    out = appmod._fix_first_person({"offers": [{"body": "We will apply the discount.", "terms": []}]})
    assert "We will" not in out["offers"][0]["body"]
    assert "Property Management will apply" in out["offers"][0]["body"]


def test_idempotent(appmod):
    data = {"offers": [{"body": "", "terms": ["(1) We reserve the right to amend."]}]}
    once = appmod._fix_first_person({"offers": [dict(data["offers"][0])]})
    twice = appmod._fix_first_person({"offers": [dict(once["offers"][0])]})
    assert once["offers"][0]["terms"] == twice["offers"][0]["terms"]


def test_plain_text_untouched(appmod):
    term = "(1) The discount is applied after the first instalment is paid."
    out = appmod._fix_first_person({"offers": [{"body": "", "terms": [term]}]})
    assert out["offers"][0]["terms"][0] == term
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `python -m pytest tests/test_fix_first_person.py -v`
Expected: FAIL (`_fix_first_person` not defined).

- [ ] **Step 3: Implement**

In `app.py`, add:
```python
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
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `python -m pytest tests/test_fix_first_person.py -v`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add app.py tests/test_fix_first_person.py
git commit -m "feat(sanitize): best-effort first-person -> Property Management rewrites"
```

---

## Task 6: Operator rename via model-reported names (`app.py::_rename_operator`)

**Files:**
- Modify: `app.py` (`_rename_operator` signature + body)
- Test: `tests/test_operator_rename.py`

- [ ] **Step 1: Write failing tests**

Add to `tests/test_operator_rename.py`:
```python
def test_detected_name_blanket_replaced_in_terms(appmod):
    out = appmod._rename_operator(
        {"offers": [{"properties": ["Maple Heights Residences, Toronto"],
                     "terms": ["(1) The cashback is credited by Maple Living Group after move-in."]}]},
        detected_names=["Maple Living Group"],
    )
    t = out["offers"][0]["terms"][0]
    assert "Maple Living Group" not in t
    assert "credited by Property Management after move-in" in t


def test_detected_name_in_body_replaced(appmod):
    out = appmod._rename_operator(
        {"offers": [{"properties": ["Radford Mill, Nottingham"],
                     "body": "As per FSL policy, the discount applies after move-in."}]},
        detected_names=["FSL"],
    )
    assert "FSL" not in out["offers"][0]["body"]
    assert "As per Property Management policy" in out["offers"][0]["body"]


def test_detected_name_overlapping_property_not_blanket_replaced(appmod):
    # Operator brand IS part of the property name -> must NOT blanket-replace the
    # property-identifying mention; the regex net still fixes 'reserves'/'any other'.
    out = appmod._rename_operator(
        {"offers": [{"properties": ["UniLodge Melbourne Central"],
                     "terms": ["(1) You must be a resident at UniLodge Melbourne Central to qualify.",
                               "(2) UniLodge reserves the right to amend."]}]},
        detected_names=["UniLodge"],
    )
    terms = out["offers"][0]["terms"]
    assert "resident at UniLodge Melbourne Central" in terms[0]   # kept
    assert terms[1] == "(2) Property Management reserves the right to amend."  # regex net


def test_generic_detected_names_ignored(appmod):
    out = appmod._rename_operator(
        {"offers": [{"properties": ["X"], "terms": ["(1) Management will review applications."]}]},
        detected_names=["Management"],
    )
    assert out["offers"][0]["terms"][0] == "(1) Management will review applications."
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `python -m pytest tests/test_operator_rename.py -k detected -v`
Expected: FAIL (`_rename_operator` takes 1 positional arg / no `detected_names`).

- [ ] **Step 3: Implement**

Replace the body of `_rename_operator` in `app.py` with:
```python
_OP_STOPWORDS = {
    "property management", "the operator", "operator", "landlord",
    "management", "the property", "student", "living", "group", "residences",
}


def _safe_operator_names(detected, props_blob):
    """Operator names safe to blanket-replace: not generic, not part of the
    property's own name."""
    out = []
    for n in detected or ():
        s = (n or "").strip()
        if len(s) < 3:
            continue
        low = s.lower()
        if low in _OP_STOPWORDS:
            continue
        if low in props_blob:           # overlaps the property name -> leave to regex net
            continue
        out.append(s)
    return out


def _rename_operator(data: dict, detected_names=()) -> dict:
    """Replace operator/PMG names with 'Property Management'. Two layers:
    (1) blanket-replace any model-reported operator name that does not overlap the
        property name; (2) the conservative regex net for the two leak patterns,
        which also covers names the model failed to report."""

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
```
> The module-level `_NAME`, `_RESERVES_RE`, `_OTHER_PROP_RE` already exist — leave them. If they currently use `import re as _re`, that's fine; the new code uses the top-level `re` from Task 3b.

- [ ] **Step 4: Run tests to verify they pass**

Run: `python -m pytest tests/test_operator_rename.py -v`
Expected: PASS (new + all existing).

- [ ] **Step 5: Commit**

```bash
git add app.py tests/test_operator_rename.py
git commit -m "feat(sanitize): blanket-replace model-reported operator names, preserve property name"
```

---

## Task 7: Wire the new pipeline order + country (`app.py::postprocess`)

**Files:**
- Modify: `app.py` (`postprocess`, imports)
- Test: `tests/test_postprocess.py`

- [ ] **Step 1: Write failing test**

Add to `tests/test_postprocess.py`:
```python
def test_pipeline_runs_all_sanitizers(appmod):
    data = {
        "applicable": True,
        "assessment": "ok",
        "flags": ["none"],
        "needs_kam_confirmation": False,
        "detected_operator_names": ["Maple Living Group"],
        "source_has_tncs": True,
        "offers": [{
            "properties": ["Maple Heights Residences, Toronto"],
            "title": "Special Deal: Get US$750 CASHBACK — Today!",   # wrong currency + em dash
            "body": "We will credit US$750 at Maple Heights Residences! Email x@y.com. Apply now!",
            "terms": [
                "1. We reserve the right to amend.",
                "2. Credited by Maple Living Group after move-in.",
                "3. Contact bookings@maple.ca for queries.",
            ],
        }],
    }
    out = appmod.postprocess(data, country="Canada")
    o = out["offers"][0]
    blob = __import__("json").dumps(out)
    assert "—" not in blob                       # dash cleaned
    assert "US$" not in o["title"] and "CA$750" in o["title"]   # currency fixed
    assert "We will" not in o["body"]            # first person fixed
    assert "x@y.com" not in o["body"]            # contact stripped
    assert "Maple Living Group" not in " ".join(o["terms"])     # operator renamed
    assert o["terms"] == [
        "(1) Property Management reserves the right to amend.",
        "(2) Credited by Property Management after move-in.",
    ]                                            # contact-only term dropped + renumbered
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python -m pytest tests/test_postprocess.py::test_pipeline_runs_all_sanitizers -v`
Expected: FAIL (postprocess takes 1 arg / sanitizers not chained).

- [ ] **Step 3: Implement**

In `app.py`, update the import line:
```python
from prompts import SYSTEM_PROMPT, build_user_prompt, CURRENCY_MAP
```
Replace `postprocess` with:
```python
def postprocess(data: dict, country: str = "") -> dict:
    """Full deterministic post-processing pipeline applied to model output.

    Order: normalise shape, strip dashes, strip contact info, fix currency,
    fix first person, drop agent clauses (+renumber), rename operator, annotate.
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
```

- [ ] **Step 4: Run the FULL suite (catch regressions in existing pipeline tests)**

Run: `python -m pytest tests/test_postprocess.py tests/test_sanitizers.py tests/test_operator_rename.py tests/test_normalize.py tests/test_annotate.py -v`
Expected: PASS (all, including existing `test_postprocess_full_pipeline` and `test_postprocess_idempotent`).

- [ ] **Step 5: Commit**

```bash
git add app.py tests/test_postprocess.py
git commit -m "feat(pipeline): chain new sanitizers in postprocess(), thread country for currency"
```

---

## Task 8: Live SOP-check gate (`app.py::generate_offer`)

**Files:**
- Modify: `app.py` (`generate_offer`, add `_compliance_warnings`)
- Test: `tests/test_live_gate.py` (create)

- [ ] **Step 1: Write failing tests**

Create `tests/test_live_gate.py`:
```python
"""Tests for the live SOP-check gate that attaches warnings to generate_offer output."""

import json


def _fake(appmod, monkeypatch, payload):
    from conftest import make_fake_openai
    monkeypatch.setattr("openai.OpenAI", make_fake_openai(json.dumps(payload)))


def test_clean_output_has_no_warnings(appmod, monkeypatch):
    _fake(appmod, monkeypatch, {
        "applicable": True, "assessment": "ok", "flags": ["none"],
        "needs_kam_confirmation": False, "source_has_tncs": False,
        "detected_operator_names": [],
        "offers": [{
            "properties": ["Test Prop, Austin"],
            "title": "Big Bonus: Get US$500 GIFT CARD!",
            "body": "Sign a lease at Test Prop and receive a US$500 gift card. Apply now!",
            "terms": ["(1) Subject to availability."], "missing_info": [],
        }],
    })
    out = appmod.generate_offer("United States", "Test Prop, Austin", "raw")
    assert "warnings" in out
    errors = [w for w in out["warnings"] if w["severity"] == "error"]
    assert errors == []


def test_residual_first_person_is_flagged(appmod, monkeypatch):
    # 'our' possessive on its own is NOT auto-fixed -> must surface as a warning.
    _fake(appmod, monkeypatch, {
        "applicable": True, "assessment": "ok", "flags": ["none"],
        "needs_kam_confirmation": False, "source_has_tncs": True,
        "detected_operator_names": [],
        "offers": [{
            "properties": ["Test Prop, Austin"],
            "title": "Big Bonus: Get US$500 GIFT CARD!",
            "body": "Receive US$500 at Test Prop. Apply now!",
            "terms": ["(1) Bookings are processed at our sole discretion by us."],
            "missing_info": [],
        }],
    })
    out = appmod.generate_offer("United States", "Test Prop, Austin", "raw")
    rules = {w["rule"] for w in out["warnings"]}
    assert "TERMS_FIRST_PERSON" in rules


def test_warnings_never_crash_on_odd_output(appmod, monkeypatch):
    _fake(appmod, monkeypatch, {"applicable": True, "offers": []})
    out = appmod.generate_offer("United Kingdom", "P", "raw")
    assert isinstance(out["warnings"], list)
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `python -m pytest tests/test_live_gate.py -v`
Expected: FAIL (`KeyError: 'warnings'`).

- [ ] **Step 3: Implement**

In `app.py`, add:
```python
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
```
Update `generate_offer` so its tail reads:
```python
    data = json.loads(response.choices[0].message.content)
    result = postprocess(data, country=country)
    result["warnings"] = _compliance_warnings(result, country)
    return result
```
And construct the client with timeout/retries (also used by Task 10):
```python
    client = OpenAI(timeout=30, max_retries=2)  # reads OPENAI_API_KEY from env
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `python -m pytest tests/test_live_gate.py tests/test_postprocess.py -v`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add app.py tests/test_live_gate.py
git commit -m "feat(gate): run SOP checker on output and attach warnings"
```

---

## Task 9: Surface warnings in the UI (`templates/index.html`)

**Files:**
- Modify: `templates/index.html` (CSS + `renderResult`)
- Test: `tests/test_routes.py` (assert the page still loads; warnings rendering is JS)

- [ ] **Step 1: Add CSS**

In the `<style>` block of `templates/index.html`, after the `.missing` rule, add:
```css
    .review { background: #fff7e6; border: 1px solid #f5d68a; color: var(--warn); border-radius: 8px; padding: 10px 12px; margin-top: 10px; font-size: 13px; }
    .review strong { display: block; margin-bottom: 4px; }
    .review ul { margin: 0; padding-left: 18px; }
```

- [ ] **Step 2: Render per-offer warnings**

In `renderResult`, capture warnings near the top:
```javascript
      const warnings = data.warnings || [];
```
Inside `offers.forEach((o) => { ... })`, change the signature to include the index and append a review block before the closing `</div>`:
```javascript
      offers.forEach((o, idx) => {
        html += `<div class="offer">`;
        // ... existing props/title/body/terms/missing_info rendering ...
        const ws = warnings.filter((w) => w.offer_index === idx);
        if (ws.length) {
          html += `<div class="review"><strong>⚠ Review before publishing</strong><ul>` +
            ws.map((w) => `<li>${escapeHtml(w.message)}</li>`).join("") + `</ul></div>`;
        }
        html += `</div>`;
      });
```

- [ ] **Step 3: Render global (non-offer) warnings**

Immediately after the verdict banner block (after `html += `</div>`;` that closes `.verdict`), add:
```javascript
      const globalWarnings = (data.warnings || []).filter((w) => w.offer_index === null || w.offer_index === undefined);
      if (globalWarnings.length) {
        html += `<div class="review"><strong>⚠ Review before publishing</strong><ul>` +
          globalWarnings.map((w) => `<li>${escapeHtml(w.message)}</li>`).join("") + `</ul></div>`;
      }
```

- [ ] **Step 4: Verify the page still loads**

Run: `python -m pytest tests/test_routes.py::test_index_loads -v`
Expected: PASS.

- [ ] **Step 5: Manual smoke (optional but recommended)**

Run the app with a fake client (see `tests`/harness) and confirm a warning renders. Skip if running headless.

- [ ] **Step 6: Commit**

```bash
git add templates/index.html
git commit -m "feat(ui): show 'Review before publishing' warnings panel per offer"
```

---

## Task 10: App-level hardening (`app.py`)

**Files:**
- Modify: `app.py` (config, routes, run block)
- Test: `tests/test_routes.py`

- [ ] **Step 1: Write failing tests**

Add to `tests/test_routes.py`:
```python
def test_raw_offer_too_long_returns_400(client, monkeypatch):
    monkeypatch.setenv("OPENAI_API_KEY", "sk-test")
    r = client.post("/generate", json={"raw_offer": "x" * 20001})
    assert r.status_code == 400
    assert "too long" in r.get_json()["error"].lower()


def test_generate_error_message_is_sanitized(client, appmod, monkeypatch):
    monkeypatch.setenv("OPENAI_API_KEY", "sk-test")

    def boom(*a, **k):
        raise RuntimeError("super secret internal detail")

    monkeypatch.setattr(appmod, "generate_offer", boom)
    r = client.post("/generate", json={"raw_offer": "offer"})
    assert r.status_code == 500
    body = r.get_json()["error"]
    assert "secret internal detail" not in body
    assert "Generation failed" in body


def test_max_content_length_configured(appmod):
    assert appmod.app.config.get("MAX_CONTENT_LENGTH") == 8 * 1024 * 1024


def test_extract_pdf_missing_filename_guarded(client, appmod, monkeypatch):
    import io
    # filename="" should be a clean 400, not a crash
    data = {"pdf": (io.BytesIO(b"%PDF-1.4"), "")}
    r = client.post("/extract-pdf", data=data, content_type="multipart/form-data")
    assert r.status_code == 400
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `python -m pytest tests/test_routes.py -k "too_long or sanitized or max_content or missing_filename" -v`
Expected: FAIL.

- [ ] **Step 3: Implement config + constants**

In `app.py`, just after `app = Flask(__name__)`:
```python
app.config["MAX_CONTENT_LENGTH"] = 8 * 1024 * 1024  # 8 MB upload cap
MAX_RAW_OFFER_CHARS = 20000


@app.errorhandler(413)
def _too_large(_e):
    return jsonify({"error": "File too large. Maximum upload size is 8 MB."}), 413
```

- [ ] **Step 4: Harden `/generate`**

In the `generate()` route, after computing `raw_offer`, add the length cap before the key check:
```python
    if not raw_offer:
        return jsonify({"error": "Please provide the raw offer text."}), 400
    if len(raw_offer) > MAX_RAW_OFFER_CHARS:
        return jsonify({"error": f"Offer text is too long (max {MAX_RAW_OFFER_CHARS} characters)."}), 400
```
And replace the exception handler:
```python
    try:
        result = generate_offer(country, property_name, raw_offer)
    except Exception:
        app.logger.exception("generation failed")
        return jsonify({"error": "Generation failed. Please try again."}), 500
```

- [ ] **Step 5: Harden `/extract-pdf`**

Replace the filename check and error handler in `extract_pdf()`:
```python
    f = request.files["pdf"]
    filename = (f.filename or "").lower()
    if not filename.endswith(".pdf"):
        return jsonify({"error": "Please upload a .pdf file."}), 400
    try:
        text = extract_pdf_text(f)
    except Exception:
        app.logger.exception("pdf extraction failed")
        return jsonify({"error": "Could not read PDF. Please ensure it is a valid PDF file."}), 400
```

- [ ] **Step 6: Default debug off**

In the `__main__` block, change the debug default:
```python
    debug = os.environ.get("FLASK_DEBUG", "0").lower() in ("1", "true", "yes")
```

- [ ] **Step 7: Run the route tests**

Run: `python -m pytest tests/test_routes.py -v`
Expected: PASS (new + existing, including `test_generate_handles_exception_as_500` and `test_extract_pdf_extraction_error_returns_400`, which still match the new messages).

- [ ] **Step 8: Commit**

```bash
git add app.py tests/test_routes.py
git commit -m "feat(hardening): debug off by default, upload+input caps, sanitized errors, filename guard"
```

---

## Task 11: Full verification + docs

**Files:**
- Modify: `README.md` (note warnings + v1 limits), `tests/README.md` (new test files)
- Verify: whole suite

- [ ] **Step 1: Run the entire offline suite**

Run: `python -m pytest -q`
Expected: PASS (0 failures); only the live tests skipped.

- [ ] **Step 2: Update `README.md`**

In the "Using it" section, add a bullet:
```markdown
- Output now includes a **⚠ Review before publishing** panel listing any SOP issues
  the automatic cleaner could not fully fix (e.g. residual first-person wording).
```
In "Notes / limits (v1)", confirm the text-only limitation wording is intact.

- [ ] **Step 3: Update `tests/README.md`**

Add rows to the coverage table for `test_strip_contact.py`, `test_fix_currency.py`,
`test_fix_first_person.py`, and `test_live_gate.py`.

- [ ] **Step 4: Commit**

```bash
git add README.md tests/README.md
git commit -m "docs: document warnings panel and new test coverage"
```

- [ ] **Step 5: (Optional) live eval**

If `OPENAI_API_KEY` is available:
```bash
RUN_LIVE_TESTS=1 python -m pytest tests/test_sop_compliance_live.py -v
python run_eval.py --quiet
```
Expected: zero hard SOP errors across scenarios.

---

## Self-Review notes

- **Spec coverage:** Example 3 fix (T1), live gate (T8), operator coverage (T6), deterministic nets for contact/currency/first-person (T3/T4/T5), hardening items 5–8 (T10), UI warnings (T9). All spec sections map to a task.
- **Type consistency:** `_strip_contact_info`, `_fix_currency(data, expected_symbol)`, `_fix_first_person`, `_rename_operator(data, detected_names=())`, `postprocess(data, country="")`, `_compliance_warnings(result, country)` are referenced consistently across Tasks 3–10.
- **Backward compatibility:** new args have defaults; existing one-arg calls in tests still pass. Error-message prefixes ("Generation failed", "Could not read PDF") are preserved so existing route tests pass.
