"""
Income tax, new regime (s.115BAC(1A) + Finance Bill 2026) — the arithmetic example.

Same library, a very different rulebook: instead of a boolean gate, a chain of integer
definitions that compute a number, with guardrails proved for every possible income.
This is the Mode-1 "verdict" shape (the engine computes the answer); loan.py is the
Mode-2 "action gate" shape (the engine vetoes an action).
"""
from godelization import Rulebook, ite, gmin

rb = Rulebook("income_tax")
ti = rb.fact("ti")
rb.assume(ti >= 0)

slab = rb.define("slab",
    ite(ti > 400000,  5  * (gmin(ti, 800000)  - 400000)  // 100, 0)
    + ite(ti > 800000,  10 * (gmin(ti, 1200000) - 800000)  // 100, 0)
    + ite(ti > 1200000, 15 * (gmin(ti, 1600000) - 1200000) // 100, 0)
    + ite(ti > 1600000, 20 * (gmin(ti, 2000000) - 1600000) // 100, 0)
    + ite(ti > 2000000, 25 * (gmin(ti, 2400000) - 2000000) // 100, 0)
    + ite(ti > 2400000, 30 * (ti - 2400000) // 100, 0))

rebated = rb.define("rebated",
    ite(ti <= 1200000, 0, gmin(slab, ti - 1200000)))

surRate = rb.define("surRate",
    ite(ti <= 5000000, 0, ite(ti <= 10000000, 10, ite(ti <= 20000000, 15, 25))))

surRaw = rb.define("surRaw", surRate * rebated // 100)

marginC = rb.define("marginC",
    ite(ti <= 5000000, 0, ite(ti <= 10000000, 5000000,
        ite(ti <= 20000000, 10000000, 20000000))))

taxPlusSur = rb.define("taxPlusSur", rebated + surRaw)

# marginal relief: cap total (tax+surcharge) at  taxPlusSur(threshold) + (income - threshold)
marginCap = rb.define("marginCap",
    ite(marginC == 0, taxPlusSur, taxPlusSur(marginC) + (ti - marginC)))

taxSurRelieved = rb.define("taxSurRelieved", gmin(taxPlusSur, marginCap))
cess = rb.define("cess", 4 * taxSurRelieved // 100)
tax = rb.define("tax", taxSurRelieved + cess)

rb.guardrail("tax_nonneg", ensures=(tax >= 0))
rb.guardrail("tax_le_income", ensures=(tax <= ti))
rb.guardrail("relief_le_raw", ensures=(taxSurRelieved <= taxPlusSur))
rb.guardrail("relief_le_cap", ensures=(taxSurRelieved <= marginCap))
