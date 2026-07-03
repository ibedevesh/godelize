#!/usr/bin/env python3
"""
eval.py — why this exists, measured.

Hands a frontier LLM the EXACT tax rules in the prompt (a computation test, not a memory
test) and compares its answers to the godel engine. Ground truth comes from the same
rulebook the kernel certified (`examples/income_tax.py`) — there is no second oracle.

Usage:  ANTHROPIC_API_KEY=... python3 eval.py
Requires: `pip install anthropic`.
"""
import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from godelization import decide                       # noqa: E402
from examples.income_tax import rb             # noqa: E402

MODEL = "claude-opus-4-8"
SCENARIOS = [
    300000, 500000, 900000, 1500000, 1800000, 2200000, 2800000, 4000000,
    1201000, 1205000, 1210000, 1250000,
    4990000, 5000000, 5010000, 5050000, 5200000,
    9990000, 10000000, 10100000, 10300000,
    19900000, 20000000, 20100000, 20500000, 30000000, 55000000,
]

RULES = """You are computing Indian income tax under the NEW regime (section 115BAC(1A)) \
for a resident individual under 60. Use EXACTLY these rules.

SLABS: up to 4,00,000 nil; 4-8L 5%; 8-12L 10%; 12-16L 15%; 16-20L 20%; 20-24L 25%; above 24L 30%.
87A REBATE: if total income <= 12,00,000 tax is nil; just above 12L, total tax must not
  exceed the income earned above 12,00,000.
SURCHARGE (capped 25%): >50L 10%; >1Cr 15%; >2Cr 25%. Marginal relief (To = Ro + So):
  crossing threshold T, total (tax+surcharge) <= (tax+surcharge at income=T, lower rate) + (income-T).
CESS: 4% on (tax + surcharge after relief).
Compute FINAL TAX PAYABLE including cess. Think step by step, then report the number."""

TOOL = {
    "name": "report_tax", "description": "Report final tax payable including cess.",
    "input_schema": {"type": "object",
                     "properties": {"final_tax_payable": {"type": "number"}},
                     "required": ["final_tax_payable"]},
}


def ask(client, income):
    r = client.messages.create(
        model=MODEL, max_tokens=2048, system=RULES, tools=[TOOL],
        tool_choice={"type": "tool", "name": "report_tax"},
        messages=[{"role": "user", "content": f"Total income = Rs {income:,}. Final tax payable?"}])
    for b in r.content:
        if b.type == "tool_use":
            return float(b.input["final_tax_payable"])
    return None


def main():
    try:
        import anthropic
        from dotenv import load_dotenv
        load_dotenv(Path(__file__).resolve().parent / ".env")
    except ImportError:
        print("pip install anthropic python-dotenv"); return 1
    if not os.environ.get("ANTHROPIC_API_KEY"):
        print("set ANTHROPIC_API_KEY (or put it in godel/.env)"); return 1

    client = anthropic.Anthropic()
    correct, worst = 0, (0, 0)
    print(f"{'income':>12} | {'engine (certified)':>18} | {'claude':>14} | {'diff':>12}")
    print("-" * 68)
    for inc in SCENARIOS:
        t = decide(rb, "tax", {"ti": inc})["value"]
        c = ask(client, inc)
        diff = None if c is None else c - t
        ok = c is not None and abs(diff) < 1.0
        correct += ok
        if diff is not None and abs(diff) > abs(worst[1]):
            worst = (inc, diff)
        print(f"{inc:>12,} | {t:>18,} | {(f'{c:,.0f}' if c is not None else 'None'):>14} | "
              f"{(f'{diff:,.0f}' if diff is not None else '-'):>12}  {'' if ok else 'WRONG'}")
    n = len(SCENARIOS)
    print("-" * 68)
    print(f"\nClaude correct: {correct}/{n} ({100*correct//n}%). "
          f"Largest error: Rs {abs(worst[1]):,.0f} at income Rs {worst[0]:,}.")
    print("Engine: exact on all, kernel-certified (run: python3 godelize.py examples/income_tax.py).")
    return 0


if __name__ == "__main__":
    sys.exit(main())
