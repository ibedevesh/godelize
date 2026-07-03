"""
The trust anchor must BITE: a rulebook whose guardrail is actually false must fail to
certify, and Z3 must hand back a real counterexample. If these ever pass, the whole
premise is broken. Run: python3 -m pytest tests/  (or: python3 tests/test_trust_anchor.py)
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from godelization import Rulebook, all_of, prove, disprove, decide


def _good():
    rb = Rulebook("loan_ok")
    cibil = rb.fact("cibil"); income = rb.fact("income")
    loan = rb.fact("loan"); balance = rb.fact("balance")
    approve = rb.define("approve", all_of(
        cibil >= 700, loan <= 10 * income, 100 * balance >= 2 * loan))
    rb.guardrail("never_subprime", ensures=(cibil >= 650), when=approve)
    return rb


def _buggy():
    # Same rule but the credit-score condition is REMOVED — subprime approvals slip through.
    rb = Rulebook("loan_buggy")
    cibil = rb.fact("cibil"); income = rb.fact("income")
    loan = rb.fact("loan"); balance = rb.fact("balance")
    approve = rb.define("approve", all_of(
        loan <= 10 * income, 100 * balance >= 2 * loan))
    rb.guardrail("never_subprime", ensures=(cibil >= 650), when=approve)
    return rb


def test_good_rulebook_certifies():
    rb = _good()
    assert all(p.certified for p in prove(rb)), "honest guardrail must be kernel-certified"
    assert all(d.safe for d in disprove(rb)), "Z3 must find no bypass"


def test_buggy_rulebook_is_rejected():
    rb = _buggy()
    assert not any(p.certified for p in prove(rb)), "a false guardrail must NOT certify"
    bad = disprove(rb)
    assert any(not d.safe and d.counterexample for d in bad), "Z3 must produce a counterexample"


def test_certificate_reflects_the_decision():
    rb = _good()
    approved = decide(rb, "approve", {"cibil": 720, "income": 100000, "loan": 500000, "balance": 20000})
    assert approved["value"] is True and approved["all_guardrails_hold"]
    denied = decide(rb, "approve", {"cibil": 600, "income": 100000, "loan": 500000, "balance": 20000})
    assert denied["value"] is False and denied["all_guardrails_hold"]


if __name__ == "__main__":
    test_good_rulebook_certifies()
    test_buggy_rulebook_is_rejected()
    test_certificate_reflects_the_decision()
    print("all trust-anchor tests passed")
