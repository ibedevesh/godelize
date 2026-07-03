"""
A deny-by-default action gate — the shape of "gödelize your AI agent".

An LLM agent gathers an applicant's facts and *proposes* to approve a loan. This gate
decides whether that action is allowed, and ships a guardrail the approval can never break:
no one below a 650 credit score is ever approved — proved for every possible input.
"""
from godelization import Rulebook, all_of

rb = Rulebook("loan")
cibil = rb.fact("cibil")
income = rb.fact("income")
loan = rb.fact("loan")
balance = rb.fact("balance")

# The decision the agent proposes — approve only if ALL conditions hold.
approve = rb.define("approve", all_of(
    cibil >= 700,
    loan <= 10 * income,
    100 * balance >= 2 * loan,
))

# The guardrail: whenever `approve` is true, the score is at least 650. Always.
rb.guardrail("never_subprime", ensures=(cibil >= 650), when=approve)
