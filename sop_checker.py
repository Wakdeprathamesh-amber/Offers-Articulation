"""
SOP compliance checker for generated offer content.

This is the rulebook turned into code. Given a generated result (the dict from
app.generate_offer) plus context about the source, it returns a list of
violations. Each rule maps directly to a line in "SOP - Offer.docx".

It is deterministic and dependency-free so it can be:
  * unit-tested against known-good / known-bad samples, and
  * run as assertions over live model output (see tests/test_sop_compliance_live.py).

Severity:
  "error" = a hard SOP violation that must never ship.
  "warn"  = a soft/style issue worth reviewing.
"""

import re

from prompts import CURRENCY_MAP, GENERIC_TNC, POWER_WORDS

# Distinctive currency symbols by region (used to catch wrong-currency leaks).
_DISTINCTIVE_CURRENCIES = {
    "£": "United Kingdom",
    "€": "Eurozone",
    "US$": "United States",
    "AU$": "Australia",
    "CA$": "Canada",
    "S$": "Singapore",
    "NZ$": "New Zealand",
}

# Lowercase function words that should NOT be capitalised in Title Case
# (unless first word or right after a colon).
_FUNCTION_WORDS = {
    "a", "an", "the", "and", "or", "but", "nor", "for", "on", "in", "at",
    "to", "of", "by", "up", "as", "with", "from", "into", "over", "per",
}

_DASHES = ("—", "–", "―")  # em, en, horizontal bar

_AGENT_MARKERS = (
    "agent booking", "booking agent", "education agent", "referral agent",
    "agent code", "agent commission", "referral commission", "agent portal",
    "agent referral", "commissionable",
)

_EMAIL_RE = re.compile(r"[\w.+-]+@[\w-]+\.[\w.-]+")
_URL_RE = re.compile(r"(https?://|www\.)", re.I)
_PHONE_RE = re.compile(r"(\+\d[\d\s\-()]{7,}\d)|(\b\d{3}[\s.\-]\d{3}[\s.\-]\d{4}\b)")
# First-person pronouns. "us" is handled separately and case-sensitively so the
# all-caps country/currency token "US" / "US$" is not misread as the pronoun "us".
_FIRST_PERSON_RE = re.compile(r"\b(we|our|ours|we're|we've|we'll|i'm)\b", re.I)
_US_PRONOUN_RE = re.compile(r"\bus\b")  # lowercase only: matches the pronoun, not "US"/"US$"
_NUMBER_WORD_UNIT_RE = re.compile(
    r"\b(one|two|three|four|five|six|seven|eight|nine|ten|eleven|twelve)\s+"
    r"(week|weeks|month|months|day|days|bedroom|bedrooms|year|years)\b",
    re.I,
)


def _v(severity, rule, msg, offer_index=None):
    return {"severity": severity, "rule": rule, "message": msg, "offer_index": offer_index}


def _has_dash(text):
    return any(d in text for d in _DASHES)


# Ordered longest-first so "US$" is matched as one token, never as "S$".
_CURRENCY_TOKEN_RE = re.compile(r"US\$|AU\$|CA\$|NZ\$|HK\$|S\$|£|€")


def _wrong_currencies(text, expected_symbol):
    """Return distinctive currency tokens present in text that are NOT expected.

    Uses a tokenizer so 'US$' is read as one token (it will not falsely report
    the 'S$' substring inside 'US$')."""
    found = []
    for tok in _CURRENCY_TOKEN_RE.findall(text):
        if tok != expected_symbol and tok not in found:
            found.append(tok)
    return found


def check_compliance(result, context):
    """Check a full generate_offer() result against the SOP.

    context keys (all optional):
      country, property_names (list), source_has_tncs (bool),
      operator_names (list of brand names that must NOT leak, distinct from
      the property name), expect_applicable (bool or None).
    """
    violations = []
    ctx = context or {}
    country = ctx.get("country", "")
    expected_symbol = CURRENCY_MAP.get(country)
    operator_names = [o.lower() for o in ctx.get("operator_names", [])]
    expect_applicable = ctx.get("expect_applicable")

    # ---- applicability -----------------------------------------------------
    if expect_applicable is True and result.get("applicable") is not True:
        violations.append(_v("error", "APPLICABILITY", "expected applicable=True"))
    if expect_applicable is False:
        if result.get("applicable") is True and not result.get("needs_kam_confirmation"):
            violations.append(
                _v("error", "APPLICABILITY",
                   "expected the offer to be rejected or flagged for KAM, but it was marked applicable")
            )

    # ---- global: no dashes anywhere ---------------------------------------
    if _has_dash(str(result)):
        violations.append(_v("error", "NO_DASHES", "em/en dash present somewhere in the output"))

    offers = result.get("offers") or []
    for i, offer in enumerate(offers):
        title = offer.get("title", "") or ""
        body = offer.get("body", "") or ""
        terms = offer.get("terms", []) or []

        # ---- TITLE --------------------------------------------------------
        if len(title) > 72:
            violations.append(_v("error", "TITLE_HARD_CAP", f"title is {len(title)} chars (>72)", i))
        elif len(title) > 60:
            violations.append(_v("warn", "TITLE_TARGET", f"title is {len(title)} chars (>60 target)", i))

        if title.strip().lower().startswith("book"):
            violations.append(_v("error", "TITLE_BOOK", "title must not begin with 'Book'", i))

        if not any(pw in title for pw in POWER_WORDS):
            violations.append(_v("warn", "TITLE_POWERWORD", "title has no capitalised power word", i))

        # exactly one power word (SOP: capitalise once only)
        pw_count = sum(title.count(pw) for pw in POWER_WORDS)
        # subtract overlaps (e.g. OFF inside no-op) — approximate; flag 2+
        if pw_count >= 2:
            present = [pw for pw in POWER_WORDS if pw in title]
            # ignore the case where one power word is a substring of another
            distinct = [p for p in present if not any(p != q and p in q for q in present)]
            if len(distinct) >= 2:
                violations.append(
                    _v("warn", "TITLE_MULTI_POWERWORD",
                       f"title uses multiple power words {distinct}; SOP says capitalise one only", i))

        if expected_symbol:
            for sym in _wrong_currencies(title, expected_symbol):
                violations.append(_v("warn", "TITLE_CURRENCY", f"title currency '{sym}' does not match {country}; kept as in the source, please verify", i))

        if _NUMBER_WORD_UNIT_RE.search(title):
            violations.append(_v("error", "TITLE_DIGITS", "title spells out a number; SOP requires digits", i))

        # Title Case: function words capitalised mid-title
        tokens = title.split()
        after_colon = False
        for idx, tok in enumerate(tokens):
            word = re.sub(r"[^A-Za-z]", "", tok)
            if not word:
                after_colon = tok.endswith(":")
                continue
            is_first = idx == 0
            low = word.lower()
            # "Up to" is an idiom (capitalised in the SOP's own example), not a
            # preposition here, so don't flag "Up" when it is followed by "to".
            next_word = (
                re.sub(r"[^A-Za-z]", "", tokens[idx + 1]).lower()
                if idx + 1 < len(tokens) else ""
            )
            is_up_to_idiom = low == "up" and next_word == "to"
            if (not is_first and not after_colon and low in _FUNCTION_WORDS
                    and word[0].isupper() and not is_up_to_idiom):
                violations.append(
                    _v("warn", "TITLE_CASE", f"function word '{word}' should be lowercase in Title Case", i))
            after_colon = tok.endswith(":")

        # ---- BODY ---------------------------------------------------------
        if expected_symbol:
            for sym in _wrong_currencies(body, expected_symbol):
                violations.append(_v("warn", "BODY_CURRENCY", f"body currency '{sym}' does not match {country}; kept as in the source, please verify", i))

        if _EMAIL_RE.search(body) or _URL_RE.search(body) or _PHONE_RE.search(body):
            violations.append(_v("error", "BODY_CONTACT", "body contains an email/url/phone number", i))

        # ---- BRAND LEAK ----------------------------------------------------
        # No brand name (specific property OR operator/company) may appear in the
        # copy: the offer sits on the property's own page, and we do not advertise
        # the operator's branding. Should read "the property" / "Property Management".
        brand_terms = []
        for p in (ctx.get("property_names") or offer.get("properties") or []):
            core = str(p).split(",")[0].strip()
            if len(core) >= 4:
                brand_terms.append(core)
        for op in (ctx.get("operator_names") or []):
            if len(str(op).strip()) >= 3:
                brand_terms.append(str(op).strip())
        copy_blob = (title + " " + body + " " + " ".join(terms)).lower()
        for bt in brand_terms:
            if bt.lower() in copy_blob:
                violations.append(
                    _v("warn", "BRAND_LEAK",
                       f"brand name '{bt}' appears in the copy; generalise to 'the property' / 'Property Management'", i))
                break

        cta_words = ("book", "apply", "secure", "claim", "don't miss", "reserve",
                     "enquire", "grab", "act fast", "sign")
        tail = body[-160:].lower()
        if not any(w in tail for w in cta_words):
            violations.append(_v("warn", "BODY_CTA", "body has no clear call-to-action near the end", i))

        # ---- TERMS --------------------------------------------------------
        joined = " ".join(terms)
        low_joined = joined.lower()

        for t in terms:
            if "•" in t or t.strip().startswith("- ") or t.strip().startswith("* "):
                violations.append(_v("error", "TERMS_BULLETS", "terms must be numbered, not bulleted", i))
                break

        if not all(re.match(r"^\(\d+\)", t.strip()) for t in terms) and terms:
            violations.append(_v("warn", "TERMS_NUMBERING", "terms are not all in (n) format", i))

        nums = [re.match(r"^\((\d+)\)", t.strip()) for t in terms]
        seq = [int(m.group(1)) for m in nums if m]
        if seq and seq != list(range(1, len(seq) + 1)):
            violations.append(_v("warn", "TERMS_SEQUENCE", f"terms not numbered sequentially: {seq}", i))

        if _FIRST_PERSON_RE.search(joined) or _US_PRONOUN_RE.search(joined):
            violations.append(_v("error", "TERMS_FIRST_PERSON", "terms use first-person (we/us/our)", i))

        if _EMAIL_RE.search(joined) or _URL_RE.search(joined) or _PHONE_RE.search(joined):
            violations.append(_v("error", "TERMS_CONTACT", "terms contain an email/url/phone number", i))

        for m in _AGENT_MARKERS:
            if m in low_joined:
                violations.append(_v("error", "TERMS_AGENT", f"terms contain agent/commission text ('{m}')", i))
                break

        for op in operator_names:
            if op and op in low_joined:
                violations.append(_v("error", "TERMS_OPERATOR", f"operator name '{op}' leaked into terms", i))

        # generic vs rewritten
        generic_set = {g.strip().lower() for g in GENERIC_TNC}
        term_bodies = {re.sub(r"^\(\d+\)\s*", "", t).strip().lower() for t in terms}
        is_generic = term_bodies and term_bodies.issubset(generic_set)
        if ctx.get("source_has_tncs") and is_generic:
            violations.append(
                _v("warn", "TERMS_GENERIC", "source provided T&Cs but output used the generic set", i))

    # ---- missing-info expectation (don't fabricate; flag gaps) -------------
    if ctx.get("expect_missing_info"):
        if not any((o.get("missing_info") or []) for o in offers):
            violations.append(
                _v("warn", "MISSING_INFO",
                   "source omitted a key detail but nothing was flagged in missing_info"))

    return violations


def summarize(violations):
    errors = [v for v in violations if v["severity"] == "error"]
    warns = [v for v in violations if v["severity"] == "warn"]
    return {"errors": errors, "warnings": warns, "ok": not errors}
