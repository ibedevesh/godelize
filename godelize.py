#!/usr/bin/env python3
"""
godelize — run a rulebook through the whole pipeline and report.

    python3 godelize.py examples/loan.py
    python3 godelize.py examples/income_tax.py

For every guardrail it prints: the Lean kernel verdict (certified + which tactic + axioms)
and the Z3 disprover verdict (no counterexample, or the exact one it found). Exits non-zero
if any guardrail is not kernel-certified — so it doubles as a CI trust anchor.
"""
import importlib.util
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT))
from godelization import build_lean, build_smt, disprove  # noqa: E402


def load_rulebook(path: str):
    spec = importlib.util.spec_from_file_location("rulebook_module", path)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    if not hasattr(mod, "rb"):
        raise SystemExit(f"{path} must define a module-level `rb = Rulebook(...)`")
    return mod.rb


def main(argv: list[str]) -> int:
    if len(argv) != 2:
        raise SystemExit("usage: python3 godelize.py <path-to-rulebook.py>")
    rb = load_rulebook(argv[1])
    # godel WRITES the Lean and SMT — nobody hand-writes them. They land in generated/.
    lean_path = ROOT / "generated" / f"{rb.name}.lean"
    smt_path = ROOT / "generated" / f"{rb.name}.smt2"
    proofs = {p.guardrail: p for p in build_lean(rb, lean_path)}
    build_smt(rb, smt_path)
    disproofs = {d.guardrail: d for d in disprove(rb)}

    print(f"rulebook: {rb.name}   ({len(rb.facts)} facts, {len(rb.defs)} defs, "
          f"{len(rb.guardrails)} guardrails)")
    print(f"godel wrote: {lean_path.relative_to(ROOT)}  and  {smt_path.relative_to(ROOT)}\n")
    print(f"{'guardrail':<20} | {'kernel':<8} | {'tactic':<12} | {'z3 disprover':<14} | axioms")
    print("-" * 88)
    all_ok = True
    for g in rb.guardrails:
        p, d = proofs[g.name], disproofs[g.name]
        all_ok = all_ok and p.certified
        kernel = "CERT" if p.certified else "OPEN"
        z3 = "no bypass" if d.safe else "BYPASS!"
        ax = "" if p.axioms is None else ("∅" if not p.axioms else ",".join(sorted(p.axioms)))
        print(f"{g.name:<20} | {kernel:<8} | {str(p.tactic or '-'):<12} | {z3:<14} | {ax}")
        if not d.safe and d.counterexample:
            print(f"{'':<20}   counterexample: {d.counterexample}")
    print("-" * 88)
    if all_ok:
        print("OK — every guardrail is kernel-certified.")
        return 0
    print("OPEN — a guardrail is not yet kernel-certified (see README open obligations).")
    return 1


if __name__ == "__main__":
    sys.exit(main(sys.argv))
