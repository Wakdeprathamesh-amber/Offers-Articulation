# Test suite — amber Offer Content Automation

Regression tests for the offer-content generator. The default suite is **fully
deterministic and offline** (OpenAI is mocked), so it is safe and free to run on
every change. A separate **optional live suite** exercises the real model.

## Run

```bash
cd "offer content automation"
source venv/bin/activate
pip install -r tests/requirements-test.txt   # pytest (+ reportlab for one PDF test)

pytest                # run the full offline suite
pytest -v             # verbose
pytest tests/test_sanitizers.py   # a single file
```

### Optional live quality tests (cost money, need network + key)

```bash
RUN_LIVE_TESTS=1 OPENAI_API_KEY=sk-... pytest tests/test_live_examples.py -v
```

## What is covered

| File | Area | Key cases |
|------|------|-----------|
| `test_prompts.py` | Prompt builder + constants | currency injection per country, unknown/empty country, few-shot embedded, 7 generic T&Cs, SOP rules present |
| `test_sanitizers.py` | Dash cleaning + agent-term removal | en/em dash, horizontal bar, leading comma, non-string passthrough; removes all agent/commission clauses but **keeps** "nomination/referral agreement"; renumbering, `1.` vs `(1)` numbering, case-insensitivity |
| `test_normalize.py` | Output-shape contract | missing keys, non-dict input, string→list coercion for flags/properties/terms/missing_info, bad offer entries skipped |
| `test_annotate.py` | Title length status | 60 target / 72 hard cap boundaries, missing/None title, unicode currency char count |
| `test_postprocess.py` | Full pipeline + `generate_offer` (mocked OpenAI) | combined clean+normalize+renumber, idempotency, bad-JSON propagation |
| `test_routes.py` | Flask endpoints | `/` loads; `/generate` empty/no-key/happy/exception/non-JSON/bad-model-JSON; `/extract-pdf` no-file/wrong-ext/real-image-PDF warning/extraction-error/happy |
| `test_pdf.py` | PDF extraction | real example PDFs have no text layer; generated text PDF extracts; corrupt PDF raises |
| `test_live_examples.py` | Live quality (opt-in) | UK £500, US multi-offer varied hooks, AUS T&C agent-clause removal, direct-booking/lucky-draw flagging |

## Adding tests for new features

1. Put pure-logic tests next to the matching file above.
2. For anything that calls OpenAI, mock it with `make_fake_openai(...)` from
   `conftest.py` (returns a fake client yielding a canned JSON string).
3. Keep the offline suite green before shipping; run the live suite before a
   release to sanity-check output quality.
