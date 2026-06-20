"""A broad library of diverse offer scenarios for SOP-compliance evaluation.

Each scenario is a realistic raw offer (many for properties the model has never
seen) plus the context the SOP checker needs. Used by:
  * tests/test_sop_compliance_live.py  (asserts zero SOP errors on live output)
  * run_eval.py                        (prints a human-readable compliance report)
"""

SCENARIOS = [
    {
        "id": "uk_discount_provided_tncs",
        "country": "United Kingdom",
        "property_name": "Crown Place, Leeds",
        "raw": (
            "Crown Place Leeds is offering a £400 rent discount for the 2026-2027 academic year — "
            "book now! Applicable on all room types for the first 100 bookings.\n"
            "Terms:\n"
            "1. We will apply the £400 discount to the resident's account after check-in.\n"
            "2. Valid for the first 100 confirmed bookings only.\n"
            "3. Commission is payable to booking agents via our agent portal using an agent code.\n"
            "4. Vita Student reserves the right to withdraw this offer at any time.\n"
            "5. Email bookings@vitastudent.com for queries."
        ),
        "ctx": {
            "country": "United Kingdom",
            "property_names": ["Crown Place, Leeds"],
            "source_has_tncs": True,
            "operator_names": ["Vita Student"],
            "expect_applicable": True,
        },
    },
    {
        "id": "us_giftcard_no_tncs",
        "country": "United States",
        "property_name": "The Standard, Austin",
        "raw": (
            "The Standard Austin: New residents receive a $1,000 gift card when they sign a lease "
            "for select floor plans. Limited time only."
        ),
        "ctx": {
            "country": "United States",
            "property_names": ["The Standard, Austin"],
            "source_has_tncs": False,
            "operator_names": [],
            "expect_applicable": True,
        },
    },
    {
        "id": "aus_rentfree_agent_tncs",
        "country": "Australia",
        "property_name": "Scape Swanston, Melbourne",
        "raw": (
            "Scape Swanston is offering up to 3 weeks rent free on studio bookings, first 30 bookings "
            "from 1 July to 31 August 2026.\n"
            "T&Cs:\n"
            "1. New eligible residents at Scape Swanston only.\n"
            "2. 3 weeks rent free for full-year leases; 1 week for half-year leases.\n"
            "3. Available via the agent booking portal by education agents and booking agents.\n"
            "4. Scape reserves the right to amend this promotion.\n"
            "5. Not available at any other Scape property.\n"
            "Contact partnerships@scape.com.au."
        ),
        "ctx": {
            "country": "Australia",
            "property_names": ["Scape Swanston, Melbourne"],
            "source_has_tncs": True,
            # 'Scape' is part of the property name, so we can't flag the bare word;
            # rely on agent/email/dash/operator-pattern checks instead.
            "operator_names": [],
            "expect_applicable": True,
        },
    },
    {
        "id": "canada_cashback_fee_waived",
        "country": "Canada",
        "property_name": "Maple Heights Residences, Toronto",
        "raw": (
            "Maple Heights Residences in Toronto — book for 2026-2027 and get CA$750 cashback plus "
            "your application fee waived! Use code MAPLE750. Premium Ensuite and Two-Bed only, "
            "first 50 bookings 1 September to 30 November 2026.\n"
            "Terms:\n"
            "1. We will credit the CA$750 cashback after move-in and the first instalment.\n"
            "2. The application fee waiver applies to new bookings only.\n"
            "3. Commission only payable to booking agents via our agent portal using their agent code.\n"
            "4. Maple Living Group reserves the right to amend or withdraw this offer.\n"
            "5. Not available at any other Maple Living Group property.\n"
            "Email leasing@maplelivinggroup.ca."
        ),
        "ctx": {
            "country": "Canada",
            "property_names": ["Maple Heights Residences, Toronto"],
            "source_has_tncs": True,
            "operator_names": ["Maple Living Group"],
            "expect_applicable": True,
        },
    },
    {
        "id": "singapore_discount",
        "country": "Singapore",
        "property_name": "Coliwoo Orchard, Singapore",
        "raw": (
            "Coliwoo Orchard is offering S$500 off the first month's rent for new bookings on "
            "all room types, valid until 31 December 2026."
        ),
        "ctx": {
            "country": "Singapore",
            "property_names": ["Coliwoo Orchard, Singapore"],
            "source_has_tncs": False,
            "operator_names": [],
            "expect_applicable": True,
        },
    },
    {
        "id": "exclusion_direct_booking_only",
        "country": "United States",
        "property_name": "Hub Tucson",
        "raw": "Book directly with us and save $300 on your first month. Direct bookings only.",
        "ctx": {
            "country": "United States",
            "property_names": ["Hub Tucson"],
            "source_has_tncs": False,
            "operator_names": [],
            "expect_applicable": False,
        },
    },
    {
        "id": "exclusion_lucky_draw",
        "country": "United Kingdom",
        "property_name": "iQ Shoreditch, London",
        "raw": "Book your room and get a chance to win a £1,000 Amazon voucher in our prize draw!",
        "ctx": {
            "country": "United Kingdom",
            "property_names": ["iQ Shoreditch, London"],
            "source_has_tncs": False,
            "operator_names": [],
            "expect_applicable": False,
        },
    },
    {
        "id": "exclusion_refer_a_friend",
        "country": "Australia",
        "property_name": "Yugo Melbourne",
        "raw": "Refer a friend and you both get AU$200 cashback when they sign a lease!",
        "ctx": {
            "country": "Australia",
            "property_names": ["Yugo Melbourne"],
            "source_has_tncs": False,
            "operator_names": [],
            "expect_applicable": False,
        },
    },
    {
        "id": "spelled_number_weeks",
        "country": "United Kingdom",
        "property_name": "Chapter Spitalfields, London",
        "raw": "Chapter Spitalfields: Book now and get Four Weeks Free rent on all studios for 2026-2027!",
        "ctx": {
            "country": "United Kingdom",
            "property_names": ["Chapter Spitalfields, London"],
            "source_has_tncs": False,
            "operator_names": [],
            "expect_applicable": True,
        },
    },
    {
        "id": "multi_offer_us",
        "country": "United States",
        "property_name": "Lark Austin; The Forum; Villas on Sycamore",
        "raw": (
            "1. Lark Austin: Receive a $500 gift card on 4-bedroom floor plans.\n"
            "2. The Forum, Denton: Get $300 off your first month on select units.\n"
            "3. Villas on Sycamore: Sign today and receive a $250 Visa gift card."
        ),
        "ctx": {
            "country": "United States",
            "property_names": None,  # multiple, skip single-property body check
            "source_has_tncs": False,
            "operator_names": [],
            "expect_applicable": True,
        },
    },
    {
        "id": "low_rate_only",
        "country": "United States",
        "property_name": "River House, Tempe",
        "raw": "River House Tempe: New lower rates from just $799/month on select studios. No incentive, just great value.",
        "ctx": {
            "country": "United States",
            "property_names": ["River House, Tempe"],
            "source_has_tncs": False,
            "operator_names": [],
            "expect_applicable": False,  # pure low-rate -> should be flagged/KAM
        },
    },
    {
        "id": "long_title_stress",
        "country": "United Kingdom",
        "property_name": "The Old Fire Station Student Accommodation, Birmingham",
        "raw": (
            "The Old Fire Station Student Accommodation in Birmingham is offering £1,250 cashback "
            "on premium en-suite studio apartments for the 2026-2027 academic year for the first "
            "25 bookings."
        ),
        "ctx": {
            "country": "United Kingdom",
            "property_names": ["The Old Fire Station Student Accommodation, Birmingham"],
            "source_has_tncs": False,
            "operator_names": [],
            "expect_applicable": True,
        },
    },
    # ------------------------------ expanded coverage ------------------------
    {
        "id": "ireland_euro_discount",
        "country": "Ireland",
        "property_name": "Uninest Dublin",
        "raw": (
            "Uninest Dublin is offering €500 off the total rent for the 2026-2027 academic year "
            "on all room types, valid until 31 December 2026."
        ),
        "ctx": {
            "country": "Ireland",
            "property_names": ["Uninest Dublin"],
            "source_has_tncs": False,
            "operator_names": [],
            "expect_applicable": True,
        },
    },
    {
        "id": "newzealand_giftcard",
        "country": "New Zealand",
        "property_name": "UniLodge Auckland City",
        "raw": "UniLodge Auckland City: New residents receive a NZ$400 gift card when they book a studio for 2026.",
        "ctx": {
            "country": "New Zealand",
            "property_names": ["UniLodge Auckland City"],
            "source_has_tncs": False,
            "operator_names": [],
            "expect_applicable": True,
        },
    },
    {
        "id": "rebooker_only",
        "country": "United Kingdom",
        "property_name": "Mannequin House, London",
        "raw": (
            "Mannequin House: Returning students who rebook for the 2026-2027 academic year receive "
            "£300 off their rent. Rebookers only, all room types."
        ),
        "ctx": {
            "country": "United Kingdom",
            "property_names": ["Mannequin House, London"],
            "source_has_tncs": False,
            "operator_names": [],
            "expect_applicable": True,
        },
    },
    {
        "id": "partial_tncs_operator_email",
        "country": "United States",
        "property_name": "The Hub Minneapolis",
        "raw": (
            "The Hub Minneapolis: Sign a lease and get a $600 gift card. Select floor plans.\n"
            "Terms:\n"
            "1. Gift card issued after move-in.\n"
            "2. Campus Advantage reserves the right to modify or end this promotion.\n"
            "Questions? Email leasing@campusadvantage.com."
        ),
        "ctx": {
            "country": "United States",
            "property_names": ["The Hub Minneapolis"],
            "source_has_tncs": True,
            "operator_names": ["Campus Advantage"],
            "expect_applicable": True,
        },
    },
    {
        "id": "mixed_valid_and_lucky_draw",
        "country": "United States",
        "property_name": "Stadium View; Tower Lofts",
        "raw": (
            "1. Stadium View, Columbus: Sign a lease and receive a $400 gift card on select units.\n"
            "2. Tower Lofts, Columbus: Book now for a chance to win a free year of rent in our prize draw!"
        ),
        "ctx": {
            "country": "United States",
            "property_names": None,
            "source_has_tncs": False,
            "operator_names": [],
            "expect_applicable": True,  # at least the valid one applies
        },
    },
    {
        "id": "missing_validity_date",
        "country": "United Kingdom",
        "property_name": "Canto Court, London",
        "raw": "Canto Court London: Book now and get £200 cashback on all studios for 2026-2027.",
        "ctx": {
            "country": "United Kingdom",
            "property_names": ["Canto Court, London"],
            "source_has_tncs": False,
            "operator_names": [],
            "expect_applicable": True,
            "expect_missing_info": True,  # no validity end date in source
        },
    },
    {
        "id": "contact_heavy_tncs",
        "country": "Australia",
        "property_name": "Journal Student Living, Sydney",
        "raw": (
            "Journal Student Living Sydney: AU$1,000 cashback on new bookings for full-year leases, "
            "first 15 bookings.\n"
            "Terms & Conditions:\n"
            "1. Cashback paid after move-in and first rent payment.\n"
            "2. Valid for full-year leases only.\n"
            "3. Journal Student Living reserves the right to amend this offer.\n"
            "4. Not available at any other Journal Student Living property.\n"
            "Contact: bookings@journalstudent.com.au or call +61 3 9000 0000. "
            "Mailing address: Level 5, 100 Collins Street, Melbourne VIC 3000, Australia."
        ),
        "ctx": {
            "country": "Australia",
            "property_names": ["Journal Student Living, Sydney"],
            "source_has_tncs": True,
            # operator brand is also in the property name, so rely on contact/dash
            # checks and the operator-pattern safety net rather than the bare name.
            "operator_names": [],
            "expect_applicable": True,
        },
    },
    {
        "id": "tiered_rewards",
        "country": "United Kingdom",
        "property_name": "Buchannan View, Glasgow",
        "raw": (
            "Buchannan View Glasgow: Get £500 cashback on 51-week leases or £250 cashback on "
            "44-week leases, for the 2026-2027 academic year, all room types."
        ),
        "ctx": {
            "country": "United Kingdom",
            "property_names": ["Buchannan View, Glasgow"],
            "source_has_tncs": False,
            "operator_names": [],
            "expect_applicable": True,
        },
    },
    {
        "id": "direct_and_agents_allowed",
        "country": "United States",
        "property_name": "Lark on 42nd, Austin",
        "raw": (
            "Lark on 42nd: Receive a $500 gift card on select floor plans. Available for direct "
            "bookings and for bookings made through booking agents."
        ),
        "ctx": {
            "country": "United States",
            "property_names": ["Lark on 42nd, Austin"],
            "source_has_tncs": False,
            "operator_names": [],
            "expect_applicable": True,  # agent path explicitly allowed
        },
    },
    {
        "id": "germany_euro_cashback",
        "country": "Germany",
        "property_name": "The Fizz Berlin",
        "raw": "The Fizz Berlin: New residents get €750 cashback on apartment bookings for 2026, all room types.",
        "ctx": {
            "country": "Germany",
            "property_names": ["The Fizz Berlin"],
            "source_has_tncs": False,
            "operator_names": [],
            "expect_applicable": True,
        },
    },
    {
        "id": "low_rate_with_incentive",
        "country": "United Kingdom",
        "property_name": "Newcastle 1, Newcastle",
        "raw": (
            "Newcastle 1: Lower rates from just £160 per week PLUS £100 cashback on all studios "
            "for the 2026-2027 academic year."
        ),
        "ctx": {
            "country": "United Kingdom",
            "property_names": ["Newcastle 1, Newcastle"],
            "source_has_tncs": False,
            "operator_names": [],
            "expect_applicable": True,  # has a real incentive (cashback) -> applicable
        },
    },
]
