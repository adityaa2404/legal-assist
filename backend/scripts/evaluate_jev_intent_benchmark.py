"""Expanded live benchmark for Codiv/OpenJev query-intent classification.

Run from backend/ with TYPESAFE_API_KEY set:
    python -m scripts.evaluate_jev_intent_benchmark

This is a small manually labeled evaluation set, not an independent gold-standard
dataset. Review every mismatch and validate on real, representative product queries
before production use. Each scored sample makes one live Codiv request.
"""
import asyncio
import os
import sys
from collections import Counter, defaultdict

from app.services.jev_client import classify_query_intent


# Deliberately different from the 18 smoke-test phrases.
SAMPLES = [
    # targeted: one answer or one specific obligation/fact
    ("Is the tenant allowed to sublet without written approval?", "targeted"),
    ("What date does this contract expire?", "targeted"),
    ("Who owns the intellectual property created under this agreement?", "targeted"),
    ("Does the supplier have to maintain insurance?", "targeted"),
    ("What is the maximum late-payment interest rate?", "targeted"),
    ("Can either party assign this contract to an affiliate?", "targeted"),
    ("How much notice is required before a price increase?", "targeted"),
    ("Which law governs disputes under the agreement?", "targeted"),
    ("Is there a cap on indirect damages?", "targeted"),
    ("When must the deposit be returned?", "targeted"),

    # comparative: asks to compare, contrast, rank, or identify a difference
    ("Compare the renewal mechanics in the master agreement and the addendum.", "comparative"),
    ("Which party bears more risk if confidential information leaks?", "comparative"),
    ("How does the cure period differ for payment defaults versus other breaches?", "comparative"),
    ("Contrast the warranties given by the buyer with those given by the seller.", "comparative"),
    ("Are the indemnity caps higher in clause 10 or clause 14?", "comparative"),
    ("Explain the differences between the old and revised termination language.", "comparative"),
    ("Which version gives the customer a broader audit right?", "comparative"),
    ("Compare the notice methods permitted for the landlord and tenant.", "comparative"),
    ("What changed between the original limitation-of-liability clause and the amendment?", "comparative"),
    ("Do both parties have equivalent rights to terminate for convenience?", "comparative"),

    # exhaustive: broad or complete coverage across multiple items
    ("List every representation and warranty made by either party.", "exhaustive"),
    ("Find all provisions that impose a deadline on the customer.", "exhaustive"),
    ("Give me a full inventory of fees, charges, and reimbursable expenses.", "exhaustive"),
    ("Identify every exception to the confidentiality obligations.", "exhaustive"),
    ("Extract all obligations that survive termination.", "exhaustive"),
    ("List each event of default and the remedy associated with it.", "exhaustive"),
    ("Find every reference to personal data, processing, or security incidents.", "exhaustive"),
    ("Give a complete list of required notices, including recipient and delivery method.", "exhaustive"),
    ("What are all the conditions that must be met before payment is due?", "exhaustive"),
    ("Identify every clause that limits, excludes, or caps liability.", "exhaustive"),
]

# These are intentionally unscored: the API only offers three intent classes,
# so it cannot represent "off-topic" or "unclear". Inspect outputs to understand
# how it behaves at the boundary; do not count a forced label as correct.
BOUNDARY_PROBES = [
    "hello",
    "What is the weather tomorrow?",
    "Can you explain this contract and compare all risks with the previous draft?",
    "termination?",
]


async def evaluate_group(samples, api_key, label):
    correct_by_class = Counter()
    total_by_class = Counter()
    failures = []
    confusion = defaultdict(Counter)

    print(f"\nRunning {len(samples)} {label} samples.")
    for query, expected in samples:
        predicted = await classify_query_intent(query, api_key)
        total_by_class[expected] += 1
        confusion[expected][predicted or "fallback/invalid"] += 1
        if predicted == expected:
            correct_by_class[expected] += 1
        else:
            failures.append((expected, predicted, query))
        status = "PASS" if predicted == expected else "FAIL"
        print(f"{status} expected={expected!r} predicted={predicted!r} query={query!r}")

    total_correct = sum(correct_by_class.values())
    total = len(samples)
    print(f"{label} overall: {total_correct}/{total} ({total_correct / total:.1%})")
    for intent in ("targeted", "comparative", "exhaustive"):
        n = total_by_class[intent]
        if n:
            print(f"{intent}: {correct_by_class[intent]}/{n} ({correct_by_class[intent] / n:.1%})")

    print("Confusion matrix (expected -> predicted counts):")
    for expected in ("targeted", "comparative", "exhaustive"):
        if total_by_class[expected]:
            print(f"  {expected}: {dict(confusion[expected])}")

    if failures:
        print(f"Mismatches: {len(failures)}")
        for expected, predicted, query in failures:
            print(f"  expected={expected!r}, predicted={predicted!r}: {query}")

    return total_correct, total


async def main() -> int:
    api_key = os.getenv("TYPESAFE_API_KEY")
    if not api_key:
        print("TYPESAFE_API_KEY is not set; live benchmark was not run.", file=sys.stderr)
        return 2

    correct, total = await evaluate_group(SAMPLES, api_key, "Benchmark")
    print("\nUnscored boundary probes (three-class schema has no off-topic/unclear label):")
    for query in BOUNDARY_PROBES:
        predicted = await classify_query_intent(query, api_key)
        print(f"  predicted={predicted!r} query={query!r}")

    print(
        "\nInterpretation: this is a manually labeled 30-query check, not proof of "
        "production accuracy. Review mismatches and test on a representative held-out "
        "set from real usage before enabling in production."
    )
    return 0 if correct == total else 1


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))
