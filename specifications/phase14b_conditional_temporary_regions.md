# Phase 14B Conditional Temporary Regions — sealed contract

Status: implemented, validated, promoted, and sealed in PyCForge 0.14.1.

## Purpose

Phase 14B closes one existing evaluation-order debt. PyCForge 0.14.0 can lower
an already-supported scalar expression to a sequence of prerequisite C IR
statements followed by one scalar C IR expression. Those prerequisites are
normally emitted before the consuming expression. That is not valid when the
source operand is conditional under Python `and`, `or`, or a chained
comparison.

Phase 14B may place that already-understood prerequisite sequence inside an
explicit guarded C IR region. It adds no Python syntax, scalar operation,
function-call shape, representation, runtime behavior, helper, allocation,
cleanup, or C IR node kind.

## Exact source boundary

An eligible operand is an expression composed only from the cumulative
PyCForge 0.14.0 scalar subset. Every primitive occurrence in the operand must
already have complete bindings, categories, representation evidence, facts,
RulePlans, helper requirements where applicable, and a closed failure policy.
Phase 14B removes only the placement rejections represented by `PYC2950` and
`PYC2951`; it cannot make an otherwise unsupported expression eligible.

This compositional boundary includes existing direct understood positional
source-function calls, their already-supported argument expressions, ordinary
supported scalar arithmetic and unary expressions, simple comparisons,
proved container or record scalar reads, and promoted Phase 14A floor
arithmetic. It does not authorize keywords, defaults, unpacking, dynamic call
targets, recursion, mutation, dynamic indexing, new numeric forms, or another
source feature.

Two region forms are eligible:

1. A Boolean `BoolOp` using `And` or `Or`, with at least two operands, where
   every operand has the exact existing Boolean representation and one or more
   operands requires prerequisite statements. The first operand is
   unconditional. Each later operand remains conditional on the accumulated
   Boolean result.
2. A chained `Compare` with at least two comparison operators, where all
   operands have one exact compatible existing scalar category from `int`,
   `float`, or `bool`, and at least one operand after the first comparison
   requires conditional placement. A later expression may be admitted even
   when its final C expression is pure: its materialization must still occur
   only after the preceding comparison succeeds.

Nested occurrences are decided independently. A child region may be composed
inside an eligible operand only when its own complete fact and RulePlan prove
that all child prerequisites remain inside the parent operand's guard. No
prerequisite may be hoisted merely because the child expression is otherwise
supported.

The existing SourceBundle, top-level function, module, record, container,
numeric, and call-graph boundaries remain exact. In particular, Python
operand-returning `and` and `or` semantics are not generalized: every admitted
Boolean operand and the result remain exactly Boolean-represented.

## Required analysis fact

Every accepted region must have one immutable record in a complete
`conditional-region-facts` table under `fact-table/0.14.1`. A record anchors at
least:

- region, root node, enclosing function, module, document, and logical-source
  identities;
- region kind and exact `And`, `Or`, or ordered comparison operators;
- ordered operand node IDs, categories, representations, and conditional
  ordinals;
- the complete prerequisite closure for every operand, including understood
  source-call and promoted numeric-operation facts;
- exact guard polarity for every conditional operand;
- once-only and source-order decisions;
- Boolean result and, for a chain, rolling-middle temporary strategies;
- scalar automatic lifetime, no new allocation or cleanup, no new runtime
  failure channel, and the exact target contract;
- provenance, cancellation, and resource dependencies.

The exact lowering-shape value is `flat-guarded-assignment-v1`. It describes
placement through existing declarations, assignments, blocks, and sibling
guards; it is not a new C IR node or renderer construct.

The table must exactly cover every source occurrence that selects either 14B
region rule. Independent validation reconstructs the region from Python IR,
value categories, call facts, numeric facts, ownership facts, and parent/child
relationships. Lowering cannot rediscover, widen, or repair the source
eligibility decision.

## RulePlans and obligations

At most two new rule families are permitted:

- `phase14.conditional.boolean_region`;
- `phase14.conditional.comparison_region`.

Each accepted region has exactly one of those plans, versioned `0.14.1`, with
an empty helper-requirement set of its own. Existing nested operations retain
their existing plans and helper ownership. The region plan must close these
obligations as applicable:

- exact existing scalar eligibility and representation compatibility;
- complete prerequisite closure and deterministic source order;
- unconditional-prefix evaluation exactly once;
- conditional operands evaluated at most once and only when their Python gate
  is open;
- no call, helper call, argument temporary, or other prerequisite hoisted
  across a short-circuit boundary;
- `And` true-gate and `Or` false-gate polarity preserved;
- chained middle operands materialized once and reused for the adjacent
  comparisons;
- result and rolling-middle temporaries initialized before every read;
- skipped operands produce no evaluation;
- automatic scalar lifetime with no new ownership, allocation, cleanup, or
  runtime failure channel;
- complete synthetic provenance and source/output mappings;
- bounded linear analysis/lowering and cancellation-safe publication;
- exact `c11-portable-fixed-v1` target behavior.

The exact obligation identifiers are:

- `scalar-operand-representations-proved`;
- `unconditional-prefix-proved`;
- `guard-polarity-proved`;
- `short-circuit-order-preserved`;
- `operands-evaluated-left-to-right-once`;
- `prerequisite-statements-branch-contained`;
- `intermediate-values-reused-without-reevaluation`;
- `structured-c-ir-only`;
- `result-materialized-once`;
- `allocation-and-cleanup-absent`;
- `runtime-failure-channel-unchanged`;
- `source-provenance-anchored`;
- `cancellation-safe-points-honored`; and
- `target-contract-exact`.

The plan facts, obligations, explanation tokens, and empty region-owned helper
set are exact independently validated sets, not descriptive hints.

## Structured C IR lowering

Lowering uses only existing `CVariableDeclaration`, `CAssignmentStatement`,
`CIfStatement`, `CBlock`, Boolean/unary/binary expression, call, and identifier
reference nodes. It may not use raw C text, a C conditional expression,
statement expressions, `goto`, a new C IR node, or renderer inference.

For `a and b and c`, the required shape is semantically:

```text
evaluate prerequisites for a
bool result = a
if (result) {
    evaluate prerequisites for b
    result = b
}
if (result) {
    evaluate prerequisites for c
    result = c
}
```

For `or`, each later sibling guard is `!result`. These are flat sibling guard
statements; the source operand count does not create a linearly nested C block
chain.

For `a < b < c < d`, the required shape is semantically:

```text
evaluate prerequisites for a, then b
T left = a
T previous = b
bool result = left < previous
if (result) {
    evaluate prerequisites for c
    T current = c
    result = previous < current
    previous = current
}
if (result) {
    evaluate prerequisites for d
    T current = d
    result = previous < current
    previous = current
}
```

The rolling `previous` value is already initialized, has the one proved chain
type, and is updated only after the current operand has been evaluated once.
Each guard is a flat sibling. If an operand contains its own independently
proved region, that child's complete prelude remains lexically within the
parent guard.

## Resources and cancellation

Phase 14B adds no arbitrary 64-operand limit. The sealed aggregate source-byte,
line, token, AST-node, and maximum-nesting ceilings already bound the input.
Flat guarded lowering avoids synthesizing operand-count-deep control nesting.
Analysis, independent validation, and lowering must be linear in normalized
nodes, operand edges, and prerequisite references; a whole-subtree rescan for
each region or operand is forbidden.

Cancellation checks are required during fact construction, validation, plan
publication, and per-operand lowering. Cancellation or rejection publishes no
partial successor fact table, plan, C IR, mapping, summary, trace, telemetry
semantics, or generated C.

## Stable rejection boundary

`PYC2950` remains the Boolean-region primary diagnostic when an operand would
require unsafe eager placement but cannot satisfy this profile. `PYC2951`
remains the chained-comparison primary diagnostic for an unproved conditional
operand. An existing, more specific root cause such as unresolved target,
arity, representation mismatch, recursion, invalid numeric proof, or invalid
container/record access must retain diagnostic precedence and must not be
masked by a placement diagnostic.

Malformed or adversarial published facts are internal validation failures; they
do not become broader source acceptance. No generated C is published for an
unsupported or internally inconsistent region.

## Contract identities if implemented

- rule set: `phase14-conditional-regions-v0.14.1`;
- renderer: `c-renderer-v0.14.1`;
- conditional facts: `fact-table/0.14.1`;
- conversion plan: `conversion-plan/0.14.1`;
- C IR envelope: `c-ir/0.14.1` with no new node kind;
- generated C: `generated-c/0.14.1`;
- conversion summary: `pycforge.conversion-summary/0.14.1`;
- decision trace: `pycforge.decision-trace/0.14.1`;
- result serialization: unchanged at `0.5`.

No new public policy field is introduced. `strict-source-v1`, the Phase 14A
numeric policy, and the sealed module, record, container, helper, target, and
workspace policies remain unchanged. Explicit 0.14.0 configuration remains a
historical read-compatible surface and must preserve its exact semantic shape.

## Explicit non-goals

Phase 14B does not open keyword arguments, defaults, variadics, unpacking,
assignment expressions, exceptions, recursion, dynamic calls, new strings,
new containers, general classes, mutation, comprehensions, context managers,
closures, generators, async behavior, compilation, linking, loading, or
execution. It does not start Phase 15.
