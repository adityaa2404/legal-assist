"""Live smoke evaluation for Jev's bounded Legal Assist query-intent labels.

Run from backend/ with JEV_API_KEY set:
    python scripts/evaluate_jev_intent.py

Each successful sample uses one Jev API credit. This is a small smoke set, not a
representative benchmark; review mismatches before enabling the integration in prod.
"""
import asyncio
import os
import sys

from app.services.jev_client import classify_query_intent


SAMPLES = [
    ("List every termination clause and all notice periods in this agreement.", "exhaustive"),
    ("Identify all indemnity obligations and every exception to them.", "exhaustive"),
    ("Give me a complete list of the parties' payment obligations.", "exhaustive"),
    ("Compare the liability caps for the supplier and the customer.", "comparative"),
    ("How do the confidentiality obligations differ between the two parties?", "comparative"),
    ("Compare the termination rights in sections 8 and 12.", "comparative"),
    ("What is the notice period for termination without cause?", "targeted"),
    ("Who must pay the late fee under clause 4?", "targeted"),
    ("Does this agreement require written consent for assignment?", "targeted"),
]


async def main() -> int:
    api_key = os.getenv("JEV_API_KEY")
    if not api_key:
        print("JEV_API_KEY is not set; live evaluation was not run.", file=sys.stderr)
        return 2

    print(f"Running {len(SAMPLES)} live samples (up to {len(SAMPLES)} credits).")
    correct = 0
    results = []
    for query, expected in SAMPLES:
        predicted = await classify_query_intent(query, api_key)
        passed = predicted == expected
        correct += int(passed)
        results.append((expected, predicted, passed, query))

    for expected, predicted, passed, query in results:
        status = "PASS" if passed else "FAIL"
        print(f"{status} expected={expected!r} predicted={predicted!r} query={query!r}")

    accuracy = correct / len(SAMPLES)
    print(f"Accuracy: {correct}/{len(SAMPLES)} ({accuracy:.1%})")
    print("Note: this small hand-labelled smoke set is not sufficient for production validation.")
    return 0 if accuracy == 1.0 else 1


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))
