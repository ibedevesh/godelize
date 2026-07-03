"""
godel — write a rulebook once; get a kernel-proved, Z3-disproved, certificate-emitting gate.

    from godelization import Rulebook, ite, gmin, all_of
    from godelization import prove, disprove, decide

Pipeline:
    prove(rb)      -> Lean kernel certifies each guardrail (or reports it open)
    disprove(rb)   -> Z3 finds a counterexample, or proves none exists (unsat)
    decide(rb, ..) -> run the gate on real facts, get a certificate
"""
from .core import (
    Rulebook, Guardrail, Expr, Var, Lit,
    ite, gmin, gmax, all_of, evaluate,
)
from .lean import prove, build as build_lean, emit as emit_lean, Proof
from .smt import disprove, build as build_smt, emit as emit_smt, Disproof
from .certify import decide
from .autoformalize import autoformalize, Result

__all__ = [
    "Rulebook", "Guardrail", "Expr", "Var", "Lit",
    "ite", "gmin", "gmax", "all_of", "evaluate",
    "prove", "build_lean", "emit_lean", "Proof",
    "disprove", "build_smt", "emit_smt", "Disproof",
    "decide",
    "autoformalize", "Result",
]
