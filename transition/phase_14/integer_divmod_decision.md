# Phase 14A Integer Floor-Division and Modulo Decision

Status: feasibility accepted for implementation on 2026-07-22; not implemented
or promoted by this decision.

Authority: Architecture Revision 3.1, Revision 3.2 addendum, the authenticated
PyCForge 0.13.0 predecessor, and explicit user approval.

## Decision D14A-01 — admit one static-precondition profile

Phase 14A may implement the two Python operators `//` and `%` only when all of
the following are proved before RulePlan publication:

1. Both operands have the exact existing integer-like representation category;
   `bool`, `float`, unknown, record, container, and coercion-dependent operands
   do not qualify.
2. The left operand is an otherwise supported scalar expression and its value
   is inside the declared signed-64 conversion domain whenever evaluated.
3. The right operand is a directly recognized signed-64 integer literal under
   the grammar fixed by `specifications/phase14a_bounded_integer_divmod.md`.
4. The literal's mathematical value is in `[-9223372036854775807, -2]` or
   `[1, 9223372036854775807]`. Zero, negative one, and the minimum signed-64
   value are outside the admitted grammar.
5. The left operand is evaluated exactly once. No optimizer, renderer, helper,
   mapping, trace, or observer may duplicate or reorder it.
6. The exact registered helper requirement is selected: floor division selects
   `pycf.i64.floor_div@1.0.0`; modulo selects
   `pycf.i64.floor_mod@1.0.0`.

This profile closes the helper failure preconditions without adding a runtime
failure channel. A zero divisor is rejected statically. A divisor of `-1` is
also rejected statically, even when a particular dividend could prove safe, so
`INT64_MIN / -1` can never reach C division or remainder. Every admitted
literal divisor makes both operations defined for every signed-64 dividend.

## Semantic result

For eligible mathematical operands `a` and `b`, the selected helpers must
produce exactly Python's integer results:

- `a // b` is the quotient rounded toward negative infinity;
- `a % b` has the divisor's sign, satisfies `abs(a % b) < abs(b)` when
  nonzero, and satisfies `a == (a // b) * b + (a % b)` mathematically.

The frozen helpers achieve this by correcting C11's truncation-toward-zero
quotient and dividend-sign remainder. Their scalar-by-value ownership, no
allocation, no cleanup, no dependency, and no runtime failure contracts remain
unchanged. Helper source, structured C IR factories, semantic versions, asset
fingerprints, and registry fingerprint are frozen inputs to 14A, not editable
implementation space.

## Minimum signed-literal boundary

The mathematical divisor `-9223372036854775808` is deliberately ineligible.
Python normalizes it as `UnaryOp(USub, Constant(9223372036854775808))`, whose
positive magnitude lies outside the predecessor literal-lowering domain.
Phase 14A does not repair that gap with special lowering, unsigned conversion,
text injection, or a new C IR form. It assigns a stable out-of-domain rejection
and leaves any broader signed-literal representation change to a separately
approved decision.

## Explicit rejections

The following remain ineligible and must select no helper:

- a dynamic, named, called, indexed, attributed, calculated, folded, or
  otherwise nonliteral divisor;
- literal `0`, signed zero, literal `-1`, literal `INT64_MIN`, a Boolean literal,
  or a mathematical integer outside the admitted divisor set;
- mixed numeric categories, implicit Boolean-as-integer behavior, or a result
  dependent on Python arbitrary precision;
- checked failure, `ZeroDivisionError`, overflow emulation, or any exception
  surface;
- promotion of `/`, `divmod`, `pow`, bit operations, or another advanced
  construct.

## Proof and publication obligations

Analysis must publish an immutable fact for every candidate occurrence,
including exact operand categories, normalized literal value and shape,
precondition decisions, helper reference, evaluation dependencies, source and
binding provenance, and rejection cause. Validation must independently anchor
those facts to Python IR and the selected RulePlan. Lowering may consume only
validated facts and must request the exact helper through the existing registry
assembly path.

Cancellation before atomic publication yields no successor facts, plan, helper
manifest, C IR, mappings, trace, summary, or generated C. Unsupported or
incomplete evidence rejects deterministically; it is never repaired by
renderer inference or runtime checks.

Decision outcome: feasible and approved for a bounded 14A implementation.
Promotion requires the full vertical gate in the draft manifest.
