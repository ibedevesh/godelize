"""
godel.certify — the runtime gate.

`decide(rb, name, facts)` evaluates a named decision on concrete facts and returns a
certificate: the value, plus confirmation that every guardrail holds for these facts.
The certificate is what you log / return to a caller as evidence of the decision.
"""
from __future__ import annotations

from .core import Rulebook, evaluate


def decide(rb: Rulebook, name: str, facts: dict[str, int]) -> dict:
    missing = set(rb.facts) - set(facts)
    if missing:
        raise ValueError(f"missing facts: {sorted(missing)}")
    defs = dict(rb._def_index)
    value = evaluate(defs[name], facts, defs, rb.facts) if name in defs else None
    guardrails = []
    for g in rb.guardrails:
        triggered = g.when is None or bool(evaluate(g.when, facts, defs, rb.facts))
        holds = (not triggered) or bool(evaluate(g.ensures, facts, defs, rb.facts))
        guardrails.append({"name": g.name, "triggered": triggered, "holds": holds})
    return {
        "rulebook": rb.name,
        "facts": dict(facts),
        "decision": name,
        "value": value,
        "guardrails": guardrails,
        "all_guardrails_hold": all(g["holds"] for g in guardrails),
    }
