# godelize

**Gödelize the rule-following parts of your AI system.** Write the rules once — or hand over
messy ones and let an AI draft them — and get a decision gate that the Lean **kernel proves**,
**Z3 tries to break**, and that ships a **certificate for every decision**.

![license](https://img.shields.io/badge/license-MIT-blue)
![proof](https://img.shields.io/badge/proof-Lean%204-orange)
![solver](https://img.shields.io/badge/solver-Z3-4c1)

---

Modern agents converge on one pattern: **the LLM proposes, deterministic code decides.** The
model reads messy input and picks actions; plain code owns the consequential calls — *can this
checkout proceed? is this refund within policy? is this loan approvable? what tax is owed?*
That code is the trust boundary, and today it's guarded — at best — by a handful of unit tests.

**godelize replaces _"we tested some cases"_ with _"we proved no case slips through."_** You
write the rulebook once; it emits a Lean engine, gets the kernel to prove your guardrails for
**every possible input**, has Z3 hunt for a counterexample, and returns a runtime gate that
attaches a certificate to each decision. The LLM never enters the trust path — godelize doesn't
make the model reliable, it makes the model *unnecessary* for the decision.

```
   YOU WRITE                    godelize DOES (deterministic — no AI)
 ┌─────────────┐      ┌───────────────────────────────────────────────┐
 │ rulebook.py │  ──▶ │  → Lean engine   → kernel PROVES guardrails    │
 │ facts       │      │  → SMT           → Z3 tries to BREAK them       │
 │ + guardrails│      │  → runtime gate  → CERTIFICATE per decision     │
 └─────────────┘      └───────────────────────────────────────────────┘
```

---

## The problem, measured

Hand a frontier model the exact tax rules **in the prompt** (a computation test, not a memory
test) and ask it to compute tax for 27 real Indian-income cases, scored against the certified
engine:

| | result |
|---|---|
| **Claude Opus 4.8** (rules in context) | **3 / 27 correct (11%)** |
| Largest single error | **₹31,93,320** |
| **godelize engine** | **exact on all — kernel-certified** |

The model is right only on the trivial zero-tax cases and wrong on nearly everything requiring
arithmetic. **A language model can't be trusted for rule-following, even holding the rules** —
so take it out of that job.

> Reproduce: `python3 eval.py` (needs `ANTHROPIC_API_KEY`).

---

## Quickstart

```bash
# requires: lean 4 (via elan) and z3 on PATH.  no Mathlib.
git clone https://github.com/ibedevesh/godelize && cd godelize

python3 godelize.py examples/loan.py          # a deny-by-default action gate
python3 godelize.py examples/income_tax.py    # an arithmetic verdict engine
python3 -m pytest tests/                       # the trust anchor must bite
```

```
rulebook: loan   (4 facts, 1 defs, 1 guardrails)
godelize wrote: generated/loan.lean  and  generated/loan.smt2

guardrail        | kernel | tactic | z3 disprover | axioms
never_subprime   | CERT   | omega  | no bypass    | Quot.sound,propext
OK — every guardrail is kernel-certified.
```

The generated `.lean` compiles **standalone** — a reviewer can re-check the proofs with
`lean generated/loan.lean`, trusting only the kernel, not godelize.

---

## Write a rulebook

```python
from godelization import Rulebook, all_of

rb      = Rulebook("loan")
cibil   = rb.fact("cibil")
income  = rb.fact("income")
loan    = rb.fact("loan")
balance = rb.fact("balance")

# The action an LLM agent proposes: approve only if all conditions hold.
approve = rb.define("approve", all_of(
    cibil >= 700, loan <= 10 * income, 100 * balance >= 2 * loan))

# The line it can NEVER cross — proved for every possible input.
rb.guardrail("never_subprime", ensures=(cibil >= 650), when=approve)
```

- `prove(rb)` → kernel-certified (rejects any `sorry` / `native_decide`)
- `disprove(rb)` → Z3 finds no bypass, or hands you the exact counterexample
- `decide(rb, "approve", {...})` → runs the gate, returns the decision **+ a certificate**

Two shapes ship as examples: an **action gate** (`loan` — veto an action) and a **verdict
engine** (`income_tax` — compute a number). Same library.

> The package imports as `godelization`; the repo/command is `godelize`.

---

## Or: hand over messy rules, an AI drafts them

For people who don't write Python (or Lean), `autoformalize()` closes the loop:

> **messy rules / a PDF + a few trusted examples → an AI drafts the rulebook → the kernel
> proves the guardrails, Z3 hunts a bypass, your test cases check the numbers → every failure
> is fed back → repeat until it holds.**

```python
from godelization import autoformalize

result = autoformalize(rules_text, tests=[
    {"facts": {"cibil": 720, "income": 100000, "loan": 500000, "balance": 20000},
     "decision": "approve", "expect": True},
    # ...
])
# result.rulebook is verified: kernel-certified, Z3-clean, matches every test.
```

**The AI is never trusted.** Nothing it writes is accepted until the kernel certifies the
guardrails, Z3 finds no counterexample, and every test passes. The AI does the tedious
drafting; the deterministic tools relentlessly correct it. `examples/autoformalize_demo.py`
re-derives the loan gate from an English description — it converges in one round.

---

## The honest ceiling — why it's named for Gödel

godelize proves your engine **obeys the rules you wrote** — *not* that your rules capture the
real world. Translating a statute or policy into a rulebook is a human judgment the kernel
can't check; it secures everything *below* that translation. So the honest claim is:

> *"provably never crosses the lines you named"* — **not** *"provably safe."*

Your **test cases are the ground truth** that catches an AI misreading the source. Keep
rulebook constants cited to their statute so the one unverifiable step stays small and
checkable. Not everything is formalizable — pretending otherwise is the failure mode.

*(Building the tax example, stating a "no-cliff" guardrail exposed a real bug: an early engine
applied surcharge with no marginal relief, over-charging ₹1,12,320 for one extra rupee at
₹50 L — the same mistake the LLM makes. The proof discipline surfaced it. Verification is
load-bearing, not decoration.)*

---

## Project layout

| path | what |
|---|---|
| `godelization/` | the library — `core` (rulebook + evaluator), `lean` (prove), `smt` (disprove), `certify` (runtime + certificate), `autoformalize` (AI draft + verify loop) |
| `examples/` | `loan.py` (action gate), `income_tax.py` (verdict engine), `autoformalize_demo.py` |
| `generated/` | the Lean + SMT written from a rulebook — the auditable proof artifacts |
| `godelize.py` | run any rulebook → write generated files + prove + disprove; the CI trust anchor |
| `eval.py` | the measured head-to-head: LLM vs the certified engine |
| `tests/` | proves the anchor bites — a false guardrail must fail to certify |

---

## Open work

- **Two-point / temporal guardrails** (universal "no cliff", `∀x. f(x+1) ≤ f(x)+1`). `omega`
  and `grind` close single-input guardrails but not comparisons across two inputs with
  truncating division — these need a compositional proof. The ladder reports them **OPEN**
  rather than faking them.
- **Fact extraction.** The gate is only as true as the facts fed in; making document
  extraction auditable (provenance to the source) is where the remaining trust sits.
- More fact types (currently integer scalars) and multi-argument function application.

---

**Requires** Lean 4 (via `elan`) and `z3` on PATH — no Mathlib. The core
(prove / disprove / certify) needs no Python packages; `eval.py` and `autoformalize.py` need
`anthropic` (`pip install -r requirements.txt`). MIT licensed.
