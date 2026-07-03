"""
godelization.autoformalize — hand it messy rules; get back a verified rulebook.

The loop:  AI drafts a rulebook  ->  the kernel proves the guardrails, Z3 hunts for a
bypass, and your test cases check the numbers  ->  every failure is fed back to the AI
->  repeat until it holds.

The AI is never trusted: nothing it writes is accepted until the kernel certifies the
guardrails, Z3 finds no counterexample, and every test case passes. The AI does the
tedious drafting; the deterministic tools relentlessly correct it.

Honest note: the test cases are YOUR ground truth — they are what catch the AI misreading
the source. The loop makes the rulebook provably guardrail-safe and consistent with the
tests you gave; it cannot prove the rules match a statute's true intent (that is your call).
"""
from __future__ import annotations

import re
from dataclasses import dataclass

from . import core
from .certify import decide
from .core import Rulebook
from .lean import prove
from .smt import disprove

DSL = """You are writing a `godelization` rulebook in Python. Use ONLY this API:

    rb = Rulebook("name")
    x = rb.fact("x")                 # declare an integer input fact
    rb.assume(x >= 0)                # domain assumptions the inputs always satisfy
    d = rb.define("d", <expr>)       # a named definition (a function of the facts)
    rb.guardrail("g", ensures=<bool-expr>, when=<bool-expr or None>)
        # "whenever `when` holds, `ensures` must hold" — proved for EVERY possible input.
        # omit `when` for an unconditional property of a computed value.

Expressions use ordinary Python operators on facts/defs:
    + - *            arithmetic
    //               integer (truncating) division      e.g.  30 * x // 100
    >= <= > < ==     comparisons  ->  boolean
    & | ~            and / or / not   (use these, NOT python's and/or/not)
    ite(cond, a, b)  if-then-else            gmin(a, b) / gmax(a, b)   min / max
    all_of(e1, e2, ...)                      a defined name applied at a point: d(expr)

Rules: all values are integers. Reference a prior def by the variable it returned.
Output ONLY the Python code, defining a module-level `rb`. No prose, no markdown fences."""


@dataclass
class Result:
    rulebook: Rulebook | None
    code: str
    rounds: int
    ok: bool
    log: list[str]


_DSL_NS = {
    "Rulebook": core.Rulebook, "ite": core.ite, "gmin": core.gmin,
    "gmax": core.gmax, "all_of": core.all_of,
}


def _exec_rulebook(code: str) -> Rulebook:
    ns = dict(_DSL_NS)
    ns["__builtins__"] = {"range": range, "len": len, "enumerate": enumerate,
                          "list": list, "int": int, "True": True, "False": False}
    exec(code, ns)   # noqa: S102 - executing the DSL the AI drafted, in a restricted namespace
    if "rb" not in ns or not isinstance(ns["rb"], Rulebook):
        raise ValueError("code must define a module-level `rb = Rulebook(...)`")
    return ns["rb"]


def _check(rb: Rulebook, tests: list[dict]) -> tuple[list[str], bool]:
    """Return (failure messages, all_ok)."""
    fails: list[str] = []
    for t in tests:
        got = decide(rb, t["decision"], t["facts"])["value"]
        if got != t["expect"]:
            fails.append(f"test {t['facts']} -> `{t['decision']}` gave {got}, expected {t['expect']}")
    for p in prove(rb):
        if not p.certified:
            fails.append(f"guardrail `{p.guardrail}` could not be kernel-certified "
                         f"(it may not follow from your rules)")
    for d in disprove(rb):
        if not d.safe:
            fails.append(f"guardrail `{d.guardrail}` can be VIOLATED — Z3 counterexample: "
                         f"{d.counterexample}")
    return fails, not fails


def _strip_fences(text: str) -> str:
    m = re.search(r"```(?:python)?\n(.*?)```", text, re.DOTALL)
    return m.group(1) if m else text


def autoformalize(rules_text: str, tests: list[dict], *, max_rounds: int = 5,
                  model: str = "claude-opus-4-8") -> Result:
    """Draft-and-verify loop. `tests` is a list of
    {"facts": {...}, "decision": "<def name>", "expect": <value>}."""
    import anthropic
    client = anthropic.Anthropic()
    log: list[str] = []
    feedback = ""
    code = ""
    for rnd in range(1, max_rounds + 1):
        user = f"Rules to formalize:\n{rules_text}\n\nTest cases the rulebook must satisfy:\n"
        for t in tests:
            user += f"  {t['facts']} -> {t['decision']} = {t['expect']}\n"
        if feedback:
            user += f"\nYour previous attempt failed:\n{feedback}\nFix it and output the full rulebook again."
        resp = client.messages.create(
            model=model, max_tokens=4096, system=DSL,
            messages=[{"role": "user", "content": user}])
        code = _strip_fences("".join(b.text for b in resp.content if b.type == "text")).strip()
        try:
            rb = _exec_rulebook(code)
        except Exception as e:
            feedback = f"Your code did not run: {type(e).__name__}: {e}"
            log.append(f"round {rnd}: code error — {e}")
            continue
        fails, ok = _check(rb, tests)
        if ok:
            log.append(f"round {rnd}: all guardrails certified, Z3 clean, tests pass")
            return Result(rb, code, rnd, True, log)
        feedback = "\n".join(f"- {f}" for f in fails)
        log.append(f"round {rnd}: {len(fails)} issue(s)")
    return Result(None, code, max_rounds, False, log)
