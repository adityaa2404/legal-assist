"""Live smoke evaluation for Codiv/OpenJev query-intent classification.

Run from backend/ with TYPESAFE_API_KEY set:
    python scripts/evaluate_jev_intent.py

Each sample makes one live Codiv request. This is a smoke test, not a production
benchmark; keep a separate held-out dataset for measuring generalization.
"""
import asyncio
import os
import sys
from collections import Counter

from app.services.jev_client import classify_query_intent


SAMPLES = [
    # Exhaustive: comprehensive coverage
    ("List every termination clause and all notice periods in this agreement.", "exhaustive"),
    ("Identify all indemnity obligations and every exception to them.", "exhaustive"),
    ("Give me a complete list of the parties' payment obligations.", "exhaustive"),
    ("Find all clauses that mention renewal, extension, or automatic renewal.", "exhaustive"),
    ("Summarize every deadline and notice requirement in the contract.", "exhaustive"),
    ("What are all the circumstances where either party can terminate?", "exhaustive"),
    # Comparative: explicit comparison
    ("Compare the liability caps for the supplier and the customer.", "comparative"),
    ("How do the confidentiality obligations differ between the two parties?", "comparative"),
    ("Compare the termination rights in sections 8 and 12.", "comparative"),
    ("Which of these two clauses gives the tenant stronger protection?", "comparative"),
    ("Contrast the indemnity obligations of the buyer and seller.", "comparative"),
    ("What is the difference between termination for cause and without cause?", "comparative"),
    # Targeted: one specific question
    ("What is the notice period for termination without cause?", "targeted"),
    ("Who must pay the late fee under clause 4?", "targeted"),
    ("Does this agreement require written consent for assignment?", "targeted"),
    ("When is the security deposit due?", "targeted"),
    ("What governing law is specified in the agreement?", "targeted"),
    ("Can the landlord increase rent during the current lease term?", "targeted"),
]


async def main() -> int:
    api_key = os.getenv("TYPESAFE_API_KEY")
    if not api_key:
        print("TYPESAFE_API_KEY is not set; live evaluation was not run.", file=sys.stderr)
        return 2

    print(f"Running {len(SAMPLES)} live Codiv samples.")
    correct_by_class = Counter()
    total_by_class = Counter()
    failures = []

    for query, expected in SAMPLES:
        predicted = await classify_query_intent(query, api_key)
        total_by_class[expected] += 1
        passed = predicted == expected
        if passed:
            correct_by_class[expected] += 1
        else:
            failures.append((expected, predicted, query))
        status = "PASS" if passed else "FAIL"
        print(f"{status} expected={expected!r} predicted={predicted!r} query={query!r}")

    total_correct = sum(correct_by_class.values())
    print(f"Overall: {total_correct}/{len(SAMPLES)} ({total_correct / len(SAMPLES):.1%})")
    for label in ("targeted", "comparative", "exhaustive"):
        correct = correct_by_class[label]
        total = total_by_class[label]
        print(f"{label}: {correct}/{total} ({correct / total:.1%})")

    if failures:
        print(f"\nMismatches: {len(failures)}")
        for expected, predicted, query in failures:
            print(f"  expected={expected!r}, predicted={predicted!r}: {query}")

    print(
        "\nSmoke-test result only. Review mismatches and run the held-out benchmark "
        "before enabling this integration in production."
    )
    return 0 if total_correct == len(SAMPLES) else 1


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))
