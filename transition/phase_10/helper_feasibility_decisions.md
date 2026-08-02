# Phase 10 Helper Feasibility Decisions

Status: accepted for Phase 10 infrastructure on 2026-07-22  
Authority: Architecture Revision 3.1 and Revision 3.2 addendum  
Promotion effect: infrastructure and fixtures only

These decisions clear the separate two-requirement entry gate. Acceptance does
not promote floor division, modulo, a broader integer model, or any other Python
feature. Current promoted RulePlans continue to declare no helper requirements.

## Decision H10-01 — bounded integer floor division

- Exact requirement: `pycf.i64.floor_div@1.0.0`.
- Prospective consumer: a future bounded-`int64_t` Python floor-division
  RulePlan, admitted only by its own numeric-semantics mini-phase no earlier than
  Phase 14.
- Semantic obligation: C signed division truncates toward zero; Python `//`
  rounds toward negative infinity. Mixed-sign non-exact results therefore need a
  deterministic quotient correction.
- Interface and target: `pycforge-helper/1`, portable ISO C11 under
  `c11-portable-fixed-v1`, two `int64_t` values in and one `int64_t` value out.
- Ownership and lifetime: scalars pass and return by value; no allocation,
  transfer, retained reference, cleanup, or lifetime extension occurs.
- Failure contract: caller-proved nonzero divisor and exclusion of
  `INT64_MIN / -1`. A future RulePlan that cannot prove those preconditions must
  reject or select a separately approved checked-failure contract. The helper
  has no concealed runtime failure channel.
- Why not inline: the quotient/remainder/sign correction is semantic machinery,
  not presentation. Repeating it at every use would duplicate the most delicate
  part of Python division semantics and enlarge generated functions.
- Dependencies: none. Resolution and C IR factory work are bounded and observe
  cancellation before publication.

## Decision H10-02 — bounded integer modulo

- Exact requirement: `pycf.i64.floor_mod@1.0.0`.
- Prospective consumer: a future bounded-`int64_t` Python modulo RulePlan,
  admitted only by its own numeric-semantics mini-phase no earlier than Phase 14.
- Semantic obligation: C remainder follows the dividend sign; Python modulo
  follows the divisor sign. Mixed-sign nonzero remainders therefore need a
  deterministic correction.
- Interface and target: `pycforge-helper/1`, portable ISO C11 under
  `c11-portable-fixed-v1`, two `int64_t` values in and one `int64_t` value out.
- Ownership and lifetime: scalars pass and return by value; no allocation,
  transfer, retained reference, cleanup, or lifetime extension occurs.
- Failure contract: the same caller-proved divisor and overflow-boundary
  preconditions as H10-01. Unproved preconditions make a future rule ineligible.
- Why not inline: the sign correction is a reusable Python semantic obligation.
  Centralizing it prevents rule-by-rule drift and duplicated helper-like blocks.
- Dependencies: none. Resolution and C IR factory work are bounded and observe
  cancellation before publication.

## Boundary retained

The two assets are trusted project code expressed as structured C IR. Python
input cannot name a template, path, include, source fragment, or registry item.
No current source construct selects either asset. Phase 10 does not compile or
execute them and does not claim behavioral verification.
