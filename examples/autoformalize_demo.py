"""
Hand messy English rules + a few trusted examples to the AI; get back a VERIFIED rulebook.

Run:  ANTHROPIC_API_KEY=... python3 examples/autoformalize_demo.py
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from godelization import autoformalize  # noqa: E402

# What a user actually has: rules in prose, and a handful of cases they know the answer to.
RULES = """
A loan-approval gate. Approve a loan only when ALL of these hold:
  - the applicant's credit score (cibil) is at least 700,
  - the loan amount is at most 10 times their annual income,
  - their average balance is at least 2% of the loan amount.
Define a boolean `approve`.
Hard safety rule that must NEVER be violated: nobody with a credit score below 650
may ever be approved.
"""

TESTS = [
    {"facts": {"cibil": 720, "income": 100000, "loan": 500000, "balance": 20000},
     "decision": "approve", "expect": True},
    {"facts": {"cibil": 640, "income": 100000, "loan": 500000, "balance": 20000},
     "decision": "approve", "expect": False},
    {"facts": {"cibil": 800, "income": 100000, "loan": 9000000, "balance": 200000},
     "decision": "approve", "expect": False},  # loan > 10x income
]


def main() -> int:
    try:
        from dotenv import load_dotenv
        load_dotenv(Path(__file__).resolve().parent.parent / ".env")
    except ImportError:
        pass
    res = autoformalize(RULES, TESTS, max_rounds=5)
    print("=== loop log ===")
    for line in res.log:
        print(" ", line)
    print(f"\n=== converged: {res.ok} (in {res.rounds} round(s)) ===\n")
    print("=== the verified rulebook the AI produced ===")
    print(res.code)
    return 0 if res.ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
