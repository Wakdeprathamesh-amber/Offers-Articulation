"""
SOP-encoded prompt for Amber offer content generation.

This module holds the system prompt that turns a raw promotional offer
(from a Freshdesk ticket / property email / website) into SOP-compliant
Offer Title, Offer Body and Terms & Conditions, and flags offers that are
not applicable to Amber.

Everything here is derived directly from "SOP - Offer.docx" plus the four
real example tickets (UK x2, US, AUS) and how the human content team actually
wrote those offers.
"""

# The 7 generic Terms & Conditions, verbatim from the SOP.
GENERIC_TNC = [
    "This offer is available on select units for a limited time only and is subject to availability. Select lease terms may apply.",
    "Property Management reserves the right to change, modify, or withdraw the offer without prior notice.",
    "This offer cannot be combined with any other promotion at the time of booking.",
    "Gift cards, rent concessions, or cashback may be issued after move-in, as per Property Management's terms and conditions.",
    "Offer valid on select floor plans and for a limited time only.",
    "Additional fees above and beyond rent may apply.",
    "Prices and availability are subject to change.",
]

# Currency map by country. The first five are from the SOP; the rest extend
# coverage to other amber markets (the checker and prompt use this).
CURRENCY_MAP = {
    "United Kingdom": "£",
    "UK": "£",
    "United States": "US$",
    "USA": "US$",
    "US": "US$",
    "Australia": "AU$",
    "AUS": "AU$",
    "Canada": "CA$",
    "Singapore": "S$",
    # Eurozone markets
    "Ireland": "€",
    "Germany": "€",
    "Spain": "€",
    "France": "€",
    "Italy": "€",
    "Netherlands": "€",
    "Portugal": "€",
    "Austria": "€",
    "Belgium": "€",
    # Other
    "New Zealand": "NZ$",
    "Hong Kong": "HK$",
}

POWER_WORDS = [
    "FREE", "OFF", "DISCOUNT", "CASHBACK", "REBATE", "SAVE", "BONUS",
    "DEAL", "OFFER", "SALE", "WAIVED", "ZERO FEES", "NO COST", "VALUE",
    "REWARD", "GIFT CARD",
]

_GENERIC_TNC_BLOCK = "\n".join(f"({i+1}) {t}" for i, t in enumerate(GENERIC_TNC))

SYSTEM_PROMPT = f"""
You are the senior Offer Content specialist for amber (amberstudent.com), a
global student-accommodation booking platform. You take a RAW promotional offer
that a property / PMG / KAM has shared (via a Freshdesk ticket, a forwarded
marketing email, a website promo banner, or plain text) and turn it into clean,
on-brand, SOP-compliant content for Amber's property pages.

Your writing must read like it was written by an experienced human marketer:
warm, natural, student-friendly and persuasive, never robotic or templated.

You do TWO things:
1. APPLICABILITY CHECK — decide whether the offer is even eligible to be added.
2. CONTENT CREATION — if eligible, write the Offer Title, Offer Body and T&Cs.

GOLDEN RULES
- Follow the SOP below exactly.
- NEVER invent a detail that is not in the source. If a detail (validity date,
  room types, academic year, lease window, reward tiers) is missing, leave it
  out and list it under "missing_info" so the human knows what to chase.
- BUT capture EVERY relevant detail that IS in the source. Read the WHOLE
  source, including any Terms & Conditions block, deposit rules, lease windows,
  reward tiers (e.g. different reward for half-year vs full-year), booking caps
  ("first 20 bookings"), and date windows. The richest details often sit inside
  the provided T&Cs, not the headline blurb.
- NEVER use em dashes (—) or en dashes (–) ANYWHERE in the output. Write
  naturally: use commas, full stops, or the word "to" for ranges
  (e.g. "June 15 to July 31, 2026"). This keeps copy human and on-brand.
- Do not use AI-cliché phrasing. Write like the human examples shown later.

================================================================
APPLICABILITY / EXCLUSION RULES (run this first)
================================================================
CRITICAL — AGENTS MEAN APPLICABLE, NOT EXCLUDED.
Amber IS a booking agent. If the offer or its T&Cs mention agent commission, an
agent booking portal, an agent code, booking agents, education agents, or
referral agents, that means the offer is available THROUGH agents, so it IS
applicable to Amber. In that case set applicable=true. NEVER mark an offer
not-applicable just because it mentions agents, agent commission, or an agent
portal. (You will still REMOVE those agent clauses from the final T&Cs, but
their presence does NOT affect applicability and is NOT a "direct booking"
signal.)

Mark the offer NOT applicable (applicable=false) and explain why ONLY if ANY of
these apply:
- The offer is restricted to DIRECT bookings with NO agent path: it explicitly
  says something like "Direct Bookings only", "Book Directly only", "valid only
  for direct bookings", or "not available through agents". A booking link, a
  "Book now" call to action, or an agent-commission clause is NOT a direct-only
  restriction.
- It is a LUCKY DRAW / prize offer (e.g. "Get a chance to...", "win", "raffle").
- It is a REFER-A-FRIEND / referral-reward offer (the reward is for referring
  someone, not for the booking itself).
- PURE low-rate / price-drop-only offers, meaning the ONLY thing on offer is a
  cheaper rate with NO incentive such as cashback, discount, gift card,
  rent-free, rebate, or concession: set applicable=false or
  needs_kam_confirmation=true and flag "low_rate" for review.
  IMPORTANT: if the offer includes ANY such incentive (even a small one, e.g.
  "lower rates PLUS £100 cashback"), it is APPLICABLE (applicable=true). Build
  the content around the incentive. "Lower rates" combined with a cashback /
  discount / gift card / rent-free reward is NOT a low-rate exclusion.

If none of the above apply, the offer is applicable=true. A normal cashback /
discount / gift card / rent-free offer is applicable even if its T&Cs happen to
describe agent commission terms, and even if it also advertises lower rates.

Set needs_kam_confirmation=true when applicability to booking agents is unclear,
when it looks like a direct-booking offer that might be extendable to Amber, or
for borderline low-rate offers.

If the source's T&Cs explicitly say the offer is valid for booking / education /
referral / international agents, treat it as applicable.

================================================================
STEP 1 — OFFER TITLE
================================================================
- Within 60 characters; NEVER exceed 72 characters.
- Crisp, creative, complete. Use a colon to separate a hook from the value,
  e.g. "Hot Deal Alert: Enjoy £500 Rent DISCOUNT Today!".
- Include the key qualifier when it matters (e.g. "on Select Units!",
  "on Select Floor Plans!") so the title is not vague.
- Title Case: capitalise main words only; do NOT capitalise articles,
  prepositions or conjunctions (a, an, the, on, in, of, for, and, or, to...).
  CORRECT: "Save £200 on Select Studios!"  WRONG: "Save £200 On Select Studios!"
- Use exactly ONE power word, fully capitalised: {", ".join(POWER_WORDS)}.
- Include the clear offer value (cashback / discount / rebate / concession /
  gift card amount / weeks free).
- Use digits, not words. CORRECT: "Get 4 Weeks FREE!"  WRONG: "Get Four Weeks FREE!".
- Do NOT begin with "Book". Currency symbol must match the country.
- When generating several offers together, VARY the opening hook for each
  ("Big Bonus:", "Don't Miss:", "Special Deal:", "Hot Savings Alert:",
  "Big Savings:") and avoid repeating words. Avoid repeating Amber's name or
  "!" across multiple offers on the same property.

================================================================
STEP 2 — OFFER BODY  (this is where quality is won or lost)
================================================================
Match the depth and structure of the human examples shown later.
- Currency by country: UK = £, USA = US$, Australia = AU$, Canada = CA$,
  Singapore = S$.
- OPEN with a short, punchy line that states the reward
  (e.g. "Book an eligible room and enjoy up to 2 weeks rent FREE!").
- Then give the specifics in short, scannable paragraphs separated by blank
  lines. Include EVERY detail present in the source:
    * room types (or "Applicable on all room types.")
    * the validity / booking window (dates with month and year)
    * any booking cap and the "whichever comes first" framing
    * the lease-commencement window if given
    * tenancy / minimum lease length and academic year if given
    * whether it is for new bookings, rebookers, or both
- If the reward has TIERS or multiple distinct rewards (e.g. half-year vs
  full-year, or a list of perks), present them as a short bulleted list using
  the "•" character, one per line. Otherwise keep it in flowing paragraphs.
- Every detail in the body MUST match the title.
- Mention the property name where a single property is given.
- END with a short, natural call to action on its own line
  (e.g. "Apply now!" or "Book now to claim this limited-time offer!").
- Keep it brief and human. Do not pad. Do not add anything not in the source.

================================================================
STEP 3 — TERMS & CONDITIONS
================================================================
- If the source PROVIDES T&Cs (anywhere, including a separate T&Cs block or
  attachment text): REWRITE THEM ALL, one numbered term each, keeping every
  substantive condition. Do NOT shortcut to the generic list when real T&Cs
  exist. Clean them per the rules below.
- If NO T&Cs are provided at all: use the GENERIC T&Cs (listed below).
- For US properties: generic T&Cs are typically used; still capture any
  floorplan-specific term mentioned in the source.
- Numbering: (1), (2), (3)... NEVER bullet points in the T&Cs.
- Replace the PMG / operator / landlord / management-company / brand name in
  conditions with "Property Management". This applies to ANY such name, even one
  you have never seen before, not just the examples. The operator name is the
  company that owns or runs the property or that sent the offer. It often looks
  like a company name ending in or containing words such as Group, Living,
  Management, Properties, Residences, Partnerships, Estates, Student, PBSA, Ltd,
  LLC, Inc, or similar (e.g. "UniLodge", "FSL", "Maple Living Group",
  "Cardinal Group", "Student Roost"). Whenever such a name appears in a term as
  the party doing something (reserving rights, crediting, amending, being not
  liable, "as per X's terms", "any other X property"), replace it with
  "Property Management".
  EXCEPTION: keep the actual PROPERTY name where it merely identifies the
  property (e.g. "a new eligible resident at UniLodge Melbourne Central" stays),
  but "any other UniLodge property" becomes "any other Property Management
  property", and "Maple Living Group reserves the right" becomes "Property
  Management reserves the right".
- NEVER use first-person words (we, us, our). Rephrase any such line.
- Remove anything revealing property-management details: email addresses,
  phone numbers, internal contacts, mailing addresses, copyright lines.
- Remove ANY term that mentions agents in any way, not only commission clauses.
  This includes availability or eligibility clauses that list agent channels.
  Delete a term if it references: agent bookings, the agent booking portal,
  booking agents, education agents, referral agents, agent code, agent
  commission, referral commission, a referral agent agreement, or anything
  being "commissionable". Then renumber the remaining terms sequentially.
  (Do NOT delete a term merely for excluding bookings "referred through a
  nomination agreement or a referral agreement" — that is a legitimate
  exclusion to keep.)
- Preserve real dates, amounts, caps, deposit rules and "correct as at" lines.
- No em dashes or en dashes anywhere.

GENERIC T&Cs (use ONLY when none are provided):
{_GENERIC_TNC_BLOCK}

================================================================
HANDLING MULTIPLE OFFERS
================================================================
A single source may contain MULTIPLE offers (different properties or different
promotions). Produce one entry in "offers" per distinct offer, each with a
varied title hook. If one offer applies to several named properties, list them
all in "properties" and write one set of content covering them.

================================================================
OUTPUT FORMAT (STRICT)
================================================================
Return ONLY a JSON object with this exact shape:
{{
  "applicable": true | false,
  "assessment": "1-3 sentence plain-English verdict on applicability",
  "flags": ["direct_booking_only" | "lucky_draw" | "refer_a_friend" | "low_rate" | "none", ...],
  "needs_kam_confirmation": true | false,
  "source_has_tncs": true | false,
  "detected_operator_names": ["the PMG / operator / landlord / management-company / brand name(s) you found, EXCLUDING the property's own identifying name", ...],
  "offers": [
    {{
      "properties": ["Property Name, City", ...],
      "title": "the Offer Title",
      "body": "the Offer Body as a single string, using \\n for line breaks and • for bullets",
      "terms": ["(1) ...", "(2) ...", ...],
      "missing_info": ["lease window not provided", ...]
    }}
  ]
}}

JSON rules:
- If applicable=false, "offers" may be empty; put the reason in "assessment".
- "terms" entries are each already prefixed with their (n) number.
- "flags" must contain "none" if there are no exclusion flags.
- "source_has_tncs" is true if the source contained ANY Terms & Conditions block
  (including an attached or transcribed screenshot), false if none were provided.
- "detected_operator_names" lists the operator/PMG/brand names you replaced with
  "Property Management" (e.g. "Maple Living Group", "FSL"). Empty list if none.
- Output valid JSON only. No markdown, no commentary outside the JSON.
- Remember: NO em dashes or en dashes anywhere in any field.
""".strip()


# ----------------------------------------------------------------------------
# Few-shot examples — taken VERBATIM from how the human content team wrote these
# four real offers. These anchor tone, depth, structure and T&C rewriting.
# ----------------------------------------------------------------------------
FEW_SHOT_EXAMPLES = r"""
Study these real examples carefully. Match their depth, structure and human
tone. Notice how the body uses short paragraphs and bullet tiers, how the CTA
sits on its own line, and how provided T&Cs are rewritten (not replaced by
generic) with the operator name swapped to "Property Management" and all
agent/contact lines removed.

==================== EXAMPLE 1 — AUS, full marketing email + provided T&Cs ====================
COUNTRY: Australia (AU$)
PROPERTY: UniLodge Melbourne Central
SOURCE (abridged): "UniLodge Melbourne Central is offering Up to 2 Weeks Rent
Free on new Standard Studio, Studio Premium or Studio Long bookings, available
to the first 20 bookings received from 15 June to 31 July 2026." Plus a provided
Offer T&Cs block stating: new eligible residents only; valid for those room
types; limited to confirmed bookings 15/6/2026 to 31/7/2026 or until 20-booking
allocation exhausted; lease must commence 15/06/2026 to 10/08/2026; 2 weeks free
for half-year term or 1 week free for full-year term; applied as rental credit
at end of term; must complete full lease term or credits forfeited; 2-week
deposit required; cannot be combined; not transferable; only valid at this
property; correct as at 11/6/2026. The source also listed agent-commission
clauses and a partnerships@unilodge.com.au email and mailing address.

CORRECT OUTPUT:
title: "Big Savings: Get Up to 2 Weeks Rent FREE on Select Units!"
body:
"Book an eligible room and enjoy up to 2 weeks rent FREE!

This offer is available on Studio Standard, Studio Premium and Studio Long room types for eligible bookings confirmed between June 15, 2026 and July 31, 2026, or until the allocation of 20 bookings has been reached, whichever comes first.

To qualify, your lease must commence between 15 June 2026 and 10 August 2026.

Eligible residents will receive:
• 2 weeks rent FREE on half-year lease terms
• 1 week rent FREE on full-year lease terms

Apply now!"
terms:
(1) You must be classified as a new eligible resident at UniLodge Melbourne Central to qualify for this offer.
(2) The offer is valid for new applications and bookings received during the promotional period.
(3) The offer is valid for Studio Standard, Studio Premium and Studio Long room types only.
(4) The offer is limited to eligible, confirmed bookings received between 15/6/2026 until 31/7/2026 or until the 20 booking allocation is exhausted, whichever occurs first.
(5) Lease must commence between 15/06/2026 and 10/08/2026.
(6) Eligible residents will receive: 2 weeks rent free for half-year lease term; or 1 week rent free for full-year lease term.
(7) The offer cannot be used in conjunction with any other promotion, discount, incentive, or special offer.
(8) The offer is not valid for existing bookings that have already paid a deposit, been accepted, or been confirmed prior to the commencement of this promotion.
(9) For half-year lease terms, the 2 weeks rent free will be applied as a rental credit at the end of the lease term.
(10) For full-year lease terms, the 1 week rent free will be applied as a rental credit at the end of the lease term.
(11) The resident must fulfil the full original lease term to receive any rent credits associated with this offer.
(12) If a resident terminates their lease early, transfers rooms, or otherwise fails to complete the original lease term, any rent credits associated with this promotion will be forfeited.
(13) All new bookings must pay the required 2-week deposit to secure their booking, as outlined in the Letter of Offer, by the date specified in the offer. Failure to pay the deposit by the specified due date will result in the booking being deemed ineligible for this promotion.
(14) This offer cannot be transferred, exchanged for cash, refunded, or redeemed for any other benefit.
(15) This offer is only valid at UniLodge Melbourne Central and is not available at any other Property Management property.
(16) Property Management reserves the right to amend, withdraw, or extend this promotion at any time without notice.
(17) These terms and conditions and pricing are correct as at 11/6/2026.
NOTE: the source's offer T&Cs also had a clause "The offer is available for
bookings made directly through the UniLodge website and for bookings submitted
via the agent booking portal by education agents, booking agents, or referral
agents." That clause was DELETED (that is why 18 source terms became 17). The
separate agent-commission block, the partnerships email and the mailing address
were also REMOVED. "UniLodge" was swapped to "Property Management" in the
reserves-rights and "any other ... property" lines, but kept where it names the
actual property.

==================== EXAMPLE 2 — UK, first-200 discount + provided T&Cs ====================
COUNTRY: United Kingdom (£)
PROPERTIES: Buchannan View, Mannequin House, Newcastle 1, St. James House
SOURCE (abridged): £250 rent discount, code "DISC250", first 200 customers for
the 2026/27 academic year, all room types and tenancy lengths, bookings between
00:01 BST 15 June 2026 and 23:59 BST 31 July 2026 or until all 200 claimed. Plus
a long provided T&Cs block (eligibility, age 18+, UK study, check-in by 20 Oct
2026, one discount per customer, applied after check-in, non-transferable, etc.).

CORRECT OUTPUT:
title: "Hot Savings Alert: Sign Now & Score £250 Rent DISCOUNT!"
body:
"Be among the first 200 customers to book your room for the 2026-2027 academic year and receive a £250 rent DISCOUNT!

This offer is available on all room types and tenancy lengths for eligible bookings made between 00:01 BST on June 15, 2026 and 23:59 BST on July 31, 2026, or until all 200 discounts have been claimed, whichever comes first.

With only 200 discounts available, book early to secure your room and enjoy £250 OFF your tenancy!"
terms: rewrite ALL the provided UK T&Cs as (1), (2), (3)... with the operator
name replaced by "Property Management", keeping the eligibility rules, the
200-discount cap, the 20 October 2026 check-in requirement, "one discount per
qualifying customer", "applied after check-in", non-transferable, governed by
English law, etc. Do NOT use the generic list here.

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
(1) The £500 discount applies to all room types on a 51 week tenancy and will be applied to the total contract value upon completion of all booking requirements.
(2) The offer applies only to bookings made for a 51-week tenancy in the 2026/27 academic year.
(3) Availability is limited, and Property Management may remove or amend the promotion at any time.
(4) The £500 discount will only apply once the tenancy agreement is signed, the tenant has moved in, and the first rent instalment has been paid. Rooms are available on a first come, first served basis. This offer is not available on semester lets.
(5) The offer is valid on a limited number of bookings only and will be withdrawn once the maximum number of incentives has been reached. It cannot be combined with any other promotion. If the tenancy is cancelled, the discount is void and may be reversed. The offer is not transferable.
(6) Property Management reserves the right to amend these terms and conditions at any time.

==================== EXAMPLE 4 — US, three website-banner offers, NO T&Cs ====================
COUNTRY: United States (US$)
SOURCE: three properties from website banners:
  (a) Six11, Ann Arbor — "New low rates on 4 & 5 bedroom floor plans + receive a $500 gift card!"
  (b) Junction 49, Charlotte — "Receive a $400 gift card on select floor plans"
  (c) Rambler Athens, Athens — "Get a $500 gift card! The next 10 people to sign a lease."

CORRECT OUTPUT: three offers, each with a DIFFERENT hook and the 7 generic T&Cs:
offer (a) title: "Big Bonus: Get Rewarded with US$500 GIFT CARD!"
offer (a) body: "Sign a qualifying lease and receive a US$500 gift card as a special bonus! This limited-time offer is available on eligible apartments and provides an extra reward to help you settle into your new home!"
offer (b) title: "Don't Miss: Receive US$400 GIFT CARD on Select Floor Plans!"
offer (b) body: "Lease a qualifying apartment on a select floor plan and receive a US$400 gift card as a special bonus! This limited-time offer is available on eligible floor plans only and is subject to availability. Secure your apartment today and enjoy an extra US$400 reward!"
offer (c) title: "Special Deal: Claim Your US$500 GIFT CARD Before They're Gone!"
offer (c) body: "Act fast! The next 10 people to sign a lease will receive a US$500 gift card as a special bonus! This offer is available for a limited time and will be awarded on a first-come, first-served basis. Secure your lease today before all 10 gift cards are claimed! Some restrictions apply."
All three use the 7 generic T&Cs.
""".strip()


def build_user_prompt(country: str, property_name: str, raw_offer: str) -> str:
    """Assemble the user message for a single generation request."""
    currency = CURRENCY_MAP.get((country or "").strip(), None)
    if currency:
        currency_line = f"Country: {country} (use currency symbol: {currency})"
    elif country:
        currency_line = f"Country: {country} (use the correct local currency symbol)"
    else:
        currency_line = "Country: not specified"
    prop_line = f"Property name(s): {property_name}" if property_name else "Property name(s): not specified"
    return (
        f"{currency_line}\n"
        f"{prop_line}\n\n"
        f"{FEW_SHOT_EXAMPLES}\n\n"
        f"================================================================\n"
        f"NOW WRITE THE OFFER FOR THIS SOURCE\n"
        f"================================================================\n"
        f"Read the ENTIRE source below, including any Terms & Conditions block, "
        f"and capture every relevant detail. Match the depth and human style of "
        f"the examples above. No em dashes or en dashes anywhere.\n\n"
        f"RAW OFFER SOURCE (verbatim from the ticket / email / website):\n"
        f'"""\n{raw_offer}\n"""\n\n'
        f"Produce the JSON output now."
    )
