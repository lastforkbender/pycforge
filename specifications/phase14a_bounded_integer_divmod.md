# Phase 14A Bounded Integer Floor Division and Modulo

Status: sealed active contract for PyCForge 0.14.0.

Rule set: `phase14-bounded-numeric-v0.14`  
Numeric policy: `phase14-proved-floor-arithmetic-v0.14`

## Purpose

Phase 14A adds exactly one advanced-source mini-phase: Python integer `//` and
`%` under statically closed helper preconditions. It activates two frozen Phase
10 support templates without adding a Python runtime, exception channel, heap,
cleanup, or dynamic divisor path.

## Exact admitted grammar

An operator occurrence has normalized Python IR shape `BinOp(left, op, right)`,
where `op` is `FloorDiv` or `Mod`.

`left` must be an expression already accepted in an existing scalar integer
expression position and must have the exact integer-like category. If `left`
contains another Phase 14A occurrence, that nested occurrence must independently
pass this complete contract.

`right` must be one of these normalized shapes, with `n` an integer `Constant`
whose runtime type is exactly `int`, never `bool`:

- `Constant(n)` for `1 <= n <= 9223372036854775807`;
- `UnaryOp(UAdd, Constant(n))` for the same positive range;
- `UnaryOp(USub, Constant(n))` for
  `2 <= n <= 9223372036854775807`.

Parentheses disappear during parsing and do not affect eligibility. Decimal,
binary, octal, hexadecimal, and underscore spellings that normalize to the same
integer have the same meaning. No constant folding is performed for eligibility.

Consequently, `0`, `+0`, `-0`, `-1`, and `-9223372036854775808` reject. Nested
signs such as `--2`, bitwise constructions such as `~0`, names, attributes,
subscripts, calls, and arithmetic expressions on the right reject even if their
runtime value would be constant and safe.

## Representation domain

Both operands and the result use the existing signed `int64_t` conversion
domain. This remains a bounded source contract, not Python arbitrary-precision
equivalence. `bool` is not admitted through Python's subclass relationship with
`int`; no coercion or numeric tower behavior is inferred.

The left value must be within `INT64_MIN..INT64_MAX` whenever the source
operation executes. The admitted right-value set is
`[-9223372036854775807, -2]` plus `[1, 9223372036854775807]`. For every such
literal, the floor quotient and modulo result are representable for every
signed-64 left value and the corresponding C11 division/remainder operations
avoid their zero and `INT64_MIN / -1` undefined cases.

## Helper selection and meaning

Each accepted occurrence owns exactly one requirement:

| Python operator | Frozen helper | Result |
| --- | --- | --- |
| `//` | `pycf.i64.floor_div@1.0.0` | signed-64 quotient rounded toward negative infinity |
| `%` | `pycf.i64.floor_mod@1.0.0` | signed-64 remainder with the divisor's sign |

The registry is `phase10-support-templates-v0.10`, fingerprint
`fcb719f07984f3b79e17262e90f93823a9a0139a60529f8486ab09f6c3663d98`.
The floor-division and modulo asset fingerprints respectively remain
`23fa88ff57ffe15bc20845c6a7359f6d35648ecffd3a30ea23fe43f24e1dd869`
and
`cc2e29f5823a119009df78ed20dc410c6eef4d72c57ada115790bd1120dc663e`.

Helper selection is the deterministic union owned by validated RulePlans.
Repeated occurrences emit each required helper once through the existing
registry assembly. User source cannot name, select, replace, configure, or
provide a helper.

## Evaluation and lowering

Python evaluates the left operand before the right operand. Lowering stages the
left value exactly once, then the canonical literal right value, then the helper
result in three deterministic signed-64 temporaries. The selected helper call
receives those left and right temporaries in that order. This uniform shape
makes evaluation and mapping evidence explicit even though the proved divisor
has no effects.

The minimum signed divisor is not repaired during lowering. Its normalized
positive magnitude exceeds the predecessor literal domain, so analysis rejects
it before planning. No out-of-range literal, unsigned wrap, implementation-
defined cast, macro-text injection, special structured expression, or new C IR
node is allowed to broaden the admitted grammar.

The helper definition and prototype precede source definitions in the existing
deterministic helper/source order. Includes remain the registered union. The
renderer performs presentation only and cannot reconstruct numeric proofs.

## Facts, rules, and independent validation

For every candidate occurrence, numeric analysis must publish or reject an
immutable fact containing at least:

- source document, module, enclosing function, node, and provenance identity;
- operator kind and exact left/right node identities;
- both value categories and representation decisions;
- recognized literal shape and mathematical signed-64 value;
- admitted-literal-domain, nonzero, negative-one, and minimum-signed exclusion
  decisions;
- exact helper reference and evaluation dependency order;
- support state and one stable primary rejection cause when unsupported.

Every accepted fact receives exactly one closed RulePlan. Its obligations cover
the signed-64 domain, literal proof, helper preconditions, Python result
semantics, once-only evaluation, exact helper identity, scalar ownership,
absence of cleanup/failure, provenance, cancellation, and target contract.

An independent validator must cross-check facts against Python IR, enclosing
module/function facts, categories, occurrence coverage, RulePlans, helper
requirements, and deterministic order. Lowering is forbidden from recognizing
literal eligibility or repairing missing analysis evidence.

## Stable rejection diagnostics

The mini-phase uses two primary diagnostic codes:

- `PYC3701` — an operand is not in the exact integer-like category, the
  occurrence is in an unsupported scalar context, or its numeric occurrence
  evidence cannot be anchored to the accepted expression;
- `PYC3702` — the divisor is not a direct admitted signed integer literal, is
  zero, negative one, `INT64_MIN`, out of range, calculated/dynamic, or lacks a
  complete safe-divisor proof.

`PYC1018` rejects an unknown numeric-policy identity during request
canonicalization.

Rejection selects no helper and publishes no generated C. Diagnostics identify
the operator or divisor provenance without exposing host paths or unstable AST
representations.

## Required semantic fixtures

Promotion evidence must cover exact and non-exact results in all operand-sign
quadrants; dividends `INT64_MIN`, `-1`, `0`, `1`, and `INT64_MAX`; divisors
`-INT64_MAX`, negative values below `-1`, `1`, and `INT64_MAX`; the identity
`a == (a // b) * b + (a % b)` in mathematical fixture calculations; repeated
helper deduplication; nested-left occurrences; stable rejection of the
`INT64_MIN` divisor spelling; and every other rejection class.

Fixtures and validators inspect structured facts, RulePlans, C IR, helper
manifests, rendered text, mappings, summaries, and traces. They do not compile,
link, load, or execute generated C.

## Explicitly unchanged boundary

No other integer operator, float behavior, failure model, call shape,
container/record rule, module rule, source grammar, GUI behavior, save policy,
host-discovery surface, or Phase 14 feature is promoted. Unsupported cases
remain deterministic clean rejections under the empty approximation allowlist.
