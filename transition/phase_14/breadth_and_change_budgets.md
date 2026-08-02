# Phase 14A Breadth and Change Budgets

Status: binding opening budget. Crossing a limit pauses implementation and
requires a new decision; limits are not targets.

## Breadth budget

| Dimension | Maximum authorized breadth |
| --- | --- |
| Python operator kinds | Exactly `FloorDiv` and `Mod` on `BinOp` |
| New source-feature families | One: bounded integer division/remainder |
| Operand categories | Exact existing integer-like category only; Boolean is excluded |
| Divisor form | One directly proved signed-64 literal grammar |
| Divisor values | `[-9223372036854775807, -2]` plus `[1, 9223372036854775807]` |
| Expression contexts | Existing scalar-expression contexts only; no new statement or binding form |
| Rule families | At most two, one for `//` and one for `%` |
| Helper requirements | Exactly two frozen references, one per operator |
| Runtime failure channels | Zero |
| Allocation, ownership, or cleanup changes | Zero |
| Other Phase 14 evaluations | Zero |

Nested occurrences are eligible only through the left operand and only when
each occurrence independently satisfies the same profile. The right operand is
always the literal leaf fixed by the specification. Parentheses and integer
literal spelling bases do not enlarge the normalized grammar.

## Semantic and schema change budget

- At most one new immutable numeric-operation fact-table family may be added.
- At most two new RulePlan definition families may be added.
- No Python IR node or grammar schema change is authorized.
- No new structured C IR node kind is authorized. Existing helper-call,
  expression, include, prototype, definition, and manifest structures must be
  used.
- No helper asset, helper interface, helper factory, helper semantic version,
  registry membership, registry fingerprint, target-C contract, or failure
  contract may change.
- Active Phase 14 contract identities may be versioned only where the supported
  source decision is semantically observable: numeric facts, conversion plan,
  generated-C envelope, summary/trace, rule set, and any exact C IR envelope
  required by existing compatibility rules. SourceBundle, Python IR, result
  serialization, module, container, record, helper, target, and workspace
  contracts are outside the budget.
- At most five new primary source diagnostics may be reserved. Companion
  diagnostics must not conceal a broader primary rejection.
- Existing sources containing no eligible `//` or `%` occurrence must preserve
  their generated-C bytes and generated-output fingerprint under an explicit
  historical configuration comparison.

## Implementation-location budget

One isolated numeric-analysis component may be introduced. Integration edits
are limited to contract identities, analysis-stage publication and validation,
planning, lowering through helper requirements, diagnostics/feature metadata,
serialization compatibility, audits, and evidence. GUI, workspace controller,
save, source acquisition, module discovery, container ownership, record
ownership, renderer syntax invention, and host integration are outside scope.

## Resource and cancellation budget

- Analysis and lowering must remain linear in the number of normalized nodes
  plus selected numeric occurrences; no whole-tree rescan per occurrence is
  allowed.
- Every added unbounded-looking loop must have an existing resource ceiling or
  an explicit bounded traversal proof.
- Cancellation checks are required during numeric fact construction,
  independent validation, RulePlan publication, and helper-backed lowering.
- Rejection or cancellation cannot publish a partial helper manifest or
  observer-visible successor artifact.
- Telemetry and traces remain bounded observers and do not enter semantic or
  output fingerprints except through their already declared envelopes.

## Budget reopening triggers

Stop 14A rather than stretching this budget if implementation appears to need
a dynamic divisor, checked runtime failure, a new helper or helper version, a
new C IR node, arbitrary-precision arithmetic, constant folding, an exception
model, special repair for the `INT64_MIN` divisor spelling, new expression
contexts, more than two rule families, or any feature listed separately in the
Phase 14 roadmap. Such a need requires an independent feasibility record and
explicit approval.
