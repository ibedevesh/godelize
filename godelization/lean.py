"""
godel.lean — emit the rulebook to Lean and get the kernel to prove the guardrails.

`prove(rb)` writes a self-contained Lean file (definitions + one theorem per guardrail),
compiles it, and for each guardrail searches a small ladder of tactics for one that closes
the goal with a proof the kernel accepts and that rests only on standard sound axioms.
No `sorry`, no `native_decide` is ever accepted.
"""
from __future__ import annotations

import re
import subprocess
import tempfile
from dataclasses import dataclass
from pathlib import Path

from .core import Bin, Call, Cmp, Expr, Fn, Ite, Lit, Rulebook, Var, _Bool

STD_AXIOMS = {"propext", "Quot.sound", "Classical.choice"}
CHEATS = ("sorryAx", "native", "ofReduceBool", "ofReduceNat")
_ERR = re.compile(r":\d+:\d+:\s*error", re.IGNORECASE)

# Tactic ladder: tried in order; first one that certifies wins.
TACTICS = [
    "omega",
    "simp only [Int.min_def, Int.max_def]; omega",
    "grind",
    "simp only [Int.min_def, Int.max_def]; grind",
    "decide",
]


# -- expression -> Lean --------------------------------------------------- #
def _args(rb: Rulebook) -> str:
    return " ".join(rb.facts)


def lean_int(e: Expr, defs: set[str], args: str) -> str:
    """Emit an Int-valued expression."""
    if isinstance(e, Lit):
        return str(e.val)
    if isinstance(e, Var):
        return f"({e.name} {args})" if e.name in defs else e.name
    if isinstance(e, Call):
        inner = " ".join(lean_int(a, defs, args) for a in e.args)
        return f"({e.name} {inner})"
    if isinstance(e, Bin):
        return f"({lean_int(e.a, defs, args)} {e.op} {lean_int(e.b, defs, args)})"
    if isinstance(e, Fn):
        return f"({e.name} {lean_int(e.a, defs, args)} {lean_int(e.b, defs, args)})"
    if isinstance(e, Ite):
        return (f"(if {lean_prop(e.cond, defs, args)} then {lean_int(e.a, defs, args)} "
                f"else {lean_int(e.b, defs, args)})")
    raise TypeError(f"not an Int expr: {e!r}")


def lean_prop(e: Expr, defs: set[str], args: str) -> str:
    """Emit a Prop-valued (logical) expression, for theorem goals/hypotheses."""
    if isinstance(e, Var) and e.name in defs:      # a Bool-valued definition used as a proposition
        return f"(({e.name} {args}) = true)"
    if isinstance(e, Call):
        return f"(({e.name} " + " ".join(lean_int(a, defs, args) for a in e.args) + ") = true)"
    if isinstance(e, Cmp):
        op = {">=": "≥", "<=": "≤", ">": ">", "<": "<", "=": "="}[e.op]
        return f"({lean_int(e.a, defs, args)} {op} {lean_int(e.b, defs, args)})"
    if isinstance(e, _Bool):
        if e.op == "not":
            return f"(¬ {lean_prop(e.args[0], defs, args)})"
        j = " ∧ " if e.op == "and" else " ∨ "
        return "(" + j.join(lean_prop(a, defs, args) for a in e.args) + ")"
    raise TypeError(f"not a Prop expr: {e!r}")


def lean_bool(e: Expr, defs: set[str], args: str) -> str:
    """Emit a Bool-valued expression (for a `: Bool` definition like a decision gate)."""
    if isinstance(e, Var) and e.name in defs:
        return f"({e.name} {args})"
    if isinstance(e, Cmp):
        return f"(decide {lean_prop(e, defs, args)})"
    if isinstance(e, _Bool):
        if e.op == "not":
            return f"(! {lean_bool(e.args[0], defs, args)})"
        j = " && " if e.op == "and" else " || "
        return "(" + j.join(lean_bool(a, defs, args) for a in e.args) + ")"
    raise TypeError(f"not a Bool expr: {e!r}")


def _is_bool(e: Expr) -> bool:
    return isinstance(e, Cmp) or (isinstance(e, _Bool))


def _def_line(name: str, e: Expr, defs: set[str], args: str, facts: list[str]) -> str:
    sig = " ".join(f"({f} : Int)" for f in facts)
    if _is_bool(e):
        return f"def {name} {sig} : Bool := {lean_bool(e, defs, args)}"
    return f"def {name} {sig} : Int := {lean_int(e, defs, args)}"


def _names_in(e: Expr) -> set[str]:
    """Definition names referenced directly in an expression."""
    if isinstance(e, (Var, Call)):
        base = {e.name}
        if isinstance(e, Call):
            for a in e.args:
                base |= _names_in(a)
        return base
    if isinstance(e, (Bin, Cmp, Fn)):
        return _names_in(e.a) | _names_in(e.b)
    if isinstance(e, Ite):
        return _names_in(e.cond) | _names_in(e.a) | _names_in(e.b)
    if isinstance(e, _Bool):
        out: set[str] = set()
        for a in e.args:
            out |= _names_in(a)
        return out
    return set()


def _reachable(rb: Rulebook, exprs: list[Expr]) -> set[str]:
    """All definition names reachable (transitively) from `exprs`."""
    defidx = dict(rb.defs)
    seen: set[str] = set()
    stack = [n for e in exprs for n in _names_in(e)]
    while stack:
        n = stack.pop()
        if n in defidx and n not in seen:
            seen.add(n)
            stack += list(_names_in(defidx[n]))
    return seen


def emit(rb: Rulebook, tactic: str = "omega", tactics: dict[str, str] | None = None) -> str:
    """Full Lean source: definitions + one theorem per guardrail.
    `tactics` optionally maps a guardrail name to the tactic to use for it (from `prove`);
    guardrails not in the map fall back to `tactic`."""
    args = _args(rb)
    defnames: set[str] = set()
    lines = [f"-- generated by godel from rulebook `{rb.name}` — do not edit by hand", ""]
    for name, e in rb.defs:
        lines.append(_def_line(name, e, defnames, args, rb.facts))
        defnames.add(name)
    lines.append("")

    sig = " ".join(f"({f} : Int)" for f in rb.facts)
    SIMP = ("simp only [Bool.and_eq_true, Bool.or_eq_true, Bool.not_eq_true',"
            " decide_eq_true_eq]")
    bool_defs = {n for n, e in rb.defs if _is_bool(e)}

    def _order(names: set[str]) -> str:      # outermost-first
        return " ".join(n for n, _ in reversed(rb.defs) if n in names)

    for g in rb.guardrails:
        hyps = ""
        for i, a in enumerate(rb.assumptions):
            hyps += f" (a{i} : {lean_prop(a, defnames, args)})"
        body = ""
        # A def can appear in the hypothesis (`when`) and/or the goal (`ensures`);
        # unfold + simplify it wherever it actually is.
        if g.when is not None:
            hyps += f" (h : {lean_bool(g.when, defnames, args)} = true)"
            when_defs = _order(_reachable(rb, [g.when]))
            if when_defs:
                body += f"  unfold {when_defs} at h\n"
            body += f"  {SIMP} at h\n"
        ens_defs = _order(_reachable(rb, [g.ensures]))
        if ens_defs:
            body += f"  unfold {ens_defs}\n"
            if _names_in(g.ensures) & bool_defs:   # goal has Bool structure to normalize
                body += f"  {SIMP}\n"
        goal = lean_prop(g.ensures, defnames, args)
        tac = (tactics or {}).get(g.name, tactic)
        lines.append(f"theorem {g.name} {sig}{hyps} : {goal} := by")
        lines.append(body + f"  {tac}")
        lines.append(f"#print axioms {g.name}")
    return "\n".join(lines) + "\n"


# -- run + parse ---------------------------------------------------------- #
def _run(src: str) -> tuple[int, str]:
    with tempfile.NamedTemporaryFile("w", suffix=".lean", delete=False) as f:
        f.write(src); path = f.name
    try:
        p = subprocess.run(["lean", path], capture_output=True, text=True)
    finally:
        Path(path).unlink(missing_ok=True)
    return p.returncode, "\n".join(l for l in (p.stdout + p.stderr).splitlines()
                                   if "canonicalize" not in l)


def _axioms(out: str, name: str) -> set[str] | None:
    if f"'{name}' does not depend on any axioms" in out:
        return set()
    line = next((l for l in out.splitlines() if f"'{name}' depends on axioms:" in l), None)
    if line is None:
        return None
    return set(re.findall(r"[A-Za-z_][\w.]*", line.split("axioms:", 1)[1]))


@dataclass
class Proof:
    guardrail: str
    certified: bool
    tactic: str | None
    axioms: set[str] | None


def prove(rb: Rulebook) -> list[Proof]:
    """Prove every guardrail. Each is attempted with each tactic until one certifies."""
    results: list[Proof] = []
    for g in rb.guardrails:
        won: Proof | None = None
        for tac in TACTICS:
            # Emit a single-guardrail file to isolate this attempt.
            one = Rulebook(rb.name, rb.facts, rb.assumptions, rb.defs, [g], rb._def_index)
            rc, out = _run(emit(one, tac))
            if rc != 0 or _ERR.search(out):
                continue
            ax = _axioms(out, g.name)
            if ax is None:
                continue
            if ax <= STD_AXIOMS and not any(c in a for a in ax for c in CHEATS):
                won = Proof(g.name, True, tac, ax)
                break
        results.append(won or Proof(g.name, False, None, None))
    return results


def build(rb: Rulebook, out_lean: str | Path) -> list[Proof]:
    """Prove the guardrails, then WRITE the generated Lean file to disk using each
    guardrail's winning tactic — the auditable artifact godel produced. Returns the proofs.
    Open (uncertified) guardrails are written as a commented obligation, never as `sorry`."""
    proofs = prove(rb)
    certified = {p.guardrail: p.tactic for p in proofs if p.certified}
    open_ones = [p.guardrail for p in proofs if not p.certified]
    proven_rb = Rulebook(rb.name, rb.facts, rb.assumptions, rb.defs,
                         [g for g in rb.guardrails if g.name in certified], rb._def_index)
    src = emit(proven_rb, tactics=certified)
    if open_ones:
        src += "\n-- OPEN proof obligations (not yet kernel-certified): " + ", ".join(open_ones) + "\n"
    path = Path(out_lean)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(src)
    return proofs
