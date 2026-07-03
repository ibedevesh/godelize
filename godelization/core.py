"""
godel.core — the single source you write your rules in.

You build an expression tree with ordinary Python operators (`+ - * // min max`,
`>= <= > < ==`, `& | ~`). That one tree is emitted to Lean (for kernel proof) and to
SMT-LIB (for the Z3 disprover), and evaluated directly in Python (for the runtime gate).
Because all three come from the same tree, they cannot drift.
"""
from __future__ import annotations

from dataclasses import dataclass, field


# --------------------------------------------------------------------------- #
#  Expression tree                                                            #
# --------------------------------------------------------------------------- #
class Expr:
    """A node in the rule expression tree. Operators build more nodes."""

    def __add__(self, o): return Bin("+", self, lift(o))
    def __radd__(self, o): return Bin("+", lift(o), self)
    def __sub__(self, o): return Bin("-", self, lift(o))
    def __rsub__(self, o): return Bin("-", lift(o), self)
    def __mul__(self, o): return Bin("*", self, lift(o))
    def __rmul__(self, o): return Bin("*", lift(o), self)
    def __floordiv__(self, o): return Bin("/", self, lift(o))  # integer (truncating) division

    def __ge__(self, o): return Cmp(">=", self, lift(o))
    def __le__(self, o): return Cmp("<=", self, lift(o))
    def __gt__(self, o): return Cmp(">", self, lift(o))
    def __lt__(self, o): return Cmp("<", self, lift(o))
    def __eq__(self, o): return Cmp("=", self, lift(o))  # type: ignore[override]

    def __and__(self, o): return Bool("and", self, o)
    def __or__(self, o): return Bool("or", self, o)
    def __invert__(self): return Bool("not", self)


@dataclass(eq=False)
class Var(Expr):
    name: str

    def __call__(self, *args) -> "Call":
        """Apply a defined function at explicit arguments, e.g. `taxPlusSur(threshold)`."""
        return Call(self.name, tuple(lift(a) for a in args))


@dataclass(eq=False)
class Call(Expr):
    name: str
    args: tuple


@dataclass(eq=False)
class Lit(Expr):
    val: int


@dataclass(eq=False)
class Bin(Expr):          # arithmetic: + - * /
    op: str
    a: Expr
    b: Expr


@dataclass(eq=False)
class Cmp(Expr):          # comparison -> boolean
    op: str
    a: Expr
    b: Expr


@dataclass(eq=False)
class _Bool(Expr):        # and / or / not
    op: str
    args: tuple


def Bool(op, *args) -> "_Bool":   # constructor used by &, |, ~
    return _Bool(op, tuple(lift(a) for a in args))


@dataclass(eq=False)
class Ite(Expr):          # if cond then a else b
    cond: Expr
    a: Expr
    b: Expr


@dataclass(eq=False)
class Fn(Expr):           # min / max (and room for more)
    name: str
    a: Expr
    b: Expr


def lift(x) -> Expr:
    if isinstance(x, Expr):
        return x
    if isinstance(x, bool):
        raise TypeError("use godel comparisons, not python bool literals")
    if isinstance(x, int):
        return Lit(x)
    raise TypeError(f"cannot lift {x!r} into an Expr")


# Ergonomic builders ------------------------------------------------------- #
def ite(cond: Expr, a, b) -> Expr: return Ite(cond, lift(a), lift(b))
def gmin(a, b) -> Expr: return Fn("min", lift(a), lift(b))
def gmax(a, b) -> Expr: return Fn("max", lift(a), lift(b))
def all_of(*xs: Expr) -> Expr:
    out = xs[0]
    for x in xs[1:]:
        out = out & x
    return out


# --------------------------------------------------------------------------- #
#  Rulebook                                                                    #
# --------------------------------------------------------------------------- #
@dataclass
class Guardrail:
    name: str
    ensures: Expr            # the property that must always hold
    when: Expr | None = None  # ...whenever this holds (e.g. the decision). None = unconditional.


@dataclass
class Rulebook:
    """What you write once. Facts in, named definitions, a decision, and guardrails
    that must hold for every possible input."""
    name: str
    facts: list[str] = field(default_factory=list)
    assumptions: list[Expr] = field(default_factory=list)   # domain facts, e.g. income >= 0
    defs: list[tuple[str, Expr]] = field(default_factory=list)
    guardrails: list[Guardrail] = field(default_factory=list)
    _def_index: dict[str, Expr] = field(default_factory=dict)

    def fact(self, name: str) -> Var:
        self.facts.append(name)
        return Var(name)

    def assume(self, e: Expr) -> None:
        self.assumptions.append(e)

    def define(self, name: str, e: Expr) -> Var:
        """A named function of the facts. Later defs (and guardrails) may reference it."""
        self.defs.append((name, e))
        self._def_index[name] = e
        return Var(name)   # referencing the name later emits a call `name <facts>`

    def guardrail(self, name: str, ensures: Expr, when: Expr | None = None) -> None:
        self.guardrails.append(Guardrail(name, ensures, when))


# --------------------------------------------------------------------------- #
#  Python evaluator — the runtime gate                                         #
# --------------------------------------------------------------------------- #
def _trunc_div(a: int, b: int) -> int:
    """Truncating integer division, matching Lean's Int `/` on the domains we use."""
    q = abs(a) // abs(b)
    return q if (a >= 0) == (b >= 0) else -q


def evaluate(e: Expr, env: dict[str, int], defs: dict[str, Expr], facts: list[str]):
    """Evaluate an expression to an int or a bool over concrete fact values.
    `defs` inlines referenced definitions; `facts` names the parameters a definition
    binds when it is applied to explicit arguments via `Call`."""
    ev = lambda x: evaluate(x, env, defs, facts)  # noqa: E731
    if isinstance(e, Lit):
        return e.val
    if isinstance(e, Var):
        if e.name in env:
            return env[e.name]
        if e.name in defs:
            return ev(defs[e.name])
        raise KeyError(f"unknown name {e.name}")
    if isinstance(e, Call):
        callee = evaluate(e.args[0], env, defs, facts)  # single-parameter defs (our case)
        inner = dict(env, **{facts[0]: callee})
        return evaluate(defs[e.name], inner, defs, facts)
    if isinstance(e, Bin):
        a, b = ev(e.a), ev(e.b)
        if e.op == "+": return a + b
        if e.op == "-": return a - b
        if e.op == "*": return a * b
        return _trunc_div(a, b)   # "/"
    if isinstance(e, Cmp):
        a, b = ev(e.a), ev(e.b)
        return {">=": a >= b, "<=": a <= b, ">": a > b, "<": a < b, "=": a == b}[e.op]
    if isinstance(e, _Bool):
        vs = [ev(x) for x in e.args]
        if e.op == "and": return all(vs)
        if e.op == "or": return any(vs)
        return not vs[0]
    if isinstance(e, Ite):
        return ev(e.a) if ev(e.cond) else ev(e.b)
    if isinstance(e, Fn):
        a, b = ev(e.a), ev(e.b)
        return min(a, b) if e.name == "min" else max(a, b)
    raise TypeError(f"cannot evaluate {e!r}")
