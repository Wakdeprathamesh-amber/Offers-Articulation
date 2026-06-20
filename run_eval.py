"""
Live SOP-compliance evaluation runner.

Runs every scenario in tests/scenarios.py through the real model and grades each
output with sop_checker. Prints a per-scenario report and a final summary.

Usage:
    python run_eval.py            # run all scenarios
    python run_eval.py --quiet    # only show failures + summary

Requires OPENAI_API_KEY (read from env / .env).
"""

import sys

import app
from sop_checker import check_compliance, summarize

sys.path.insert(0, "tests")
from scenarios import SCENARIOS  # noqa: E402


def main():
    quiet = "--quiet" in sys.argv
    total_errors = 0
    total_warns = 0
    failed = []

    for sc in SCENARIOS:
        try:
            result = app.generate_offer(sc["country"], sc["property_name"], sc["raw"])
        except Exception as exc:
            print(f"\n❌ {sc['id']}: GENERATION CRASHED: {exc}")
            failed.append(sc["id"])
            total_errors += 1
            continue

        violations = check_compliance(result, sc["ctx"])
        s = summarize(violations)
        total_errors += len(s["errors"])
        total_warns += len(s["warnings"])

        status = "✅" if s["ok"] else "❌"
        if not s["ok"]:
            failed.append(sc["id"])

        if quiet and s["ok"]:
            continue

        print(f"\n{status} {sc['id']}  (applicable={result.get('applicable')}, "
              f"offers={len(result.get('offers') or [])})")
        for o in result.get("offers") or []:
            print(f"     title: {o.get('title')}")
        for e in s["errors"]:
            print(f"     ERROR [{e['rule']}] {e['message']}")
        for w in s["warnings"]:
            print(f"     warn  [{w['rule']}] {w['message']}")

    print("\n" + "=" * 70)
    print(f"SUMMARY: {len(SCENARIOS)} scenarios | "
          f"{total_errors} errors | {total_warns} warnings | "
          f"{len(failed)} scenarios with errors")
    if failed:
        print("Scenarios with errors: " + ", ".join(failed))
    print("=" * 70)
    return 1 if total_errors else 0


if __name__ == "__main__":
    raise SystemExit(main())
