# Phase 14B Conditional Temporary Regions Decision

Status: feasibility accepted for bounded implementation on 2026-07-22. No
implementation or promotion is claimed by this decision.

Authority: Architecture Revision 3.1, Revision 3.2 addendum, the authenticated
and promoted PyCForge 0.14.0 predecessor, and explicit user approval to continue
the bounded Phase 14 mini-phases while retaining the dangerous-feature
exclusions.

Recorded approval: “Our previous momento excluded the dangerous ones. Doesn’t
need to be covered conversion territory for PyCForge currently. Continue
strongly with the mini-phases so PyCForge may thrive ahead greatly.”

## Decision D14B-01 — admit the existing scalar-expression closure

Phase 14B may conditionally place only scalar expressions already understood
by the cumulative 0.14.0 converter. Eligibility is compositional rather than
restricted to a direct whole-call operand: wrappers and combinations do not
add primitive semantics when every contained occurrence already has complete
facts, plans, representations, and failure obligations.

The sole newly resolved question is where an already-planned prerequisite
statement executes. A prerequisite closure may include direct understood
positional source calls, their ordered argument temporaries, promoted Phase 14A
helper-backed operations, and other existing scalar subexpressions. It may not
contain a primitive that would otherwise reject.

For a Boolean region, the root must be `And` or `Or`, all operands and the
result must be exactly Boolean-represented, and at least one operand must have a
prerequisite requiring explicit placement. For a comparison region, the root
must be a chain, all operands must share one compatible existing `int`,
`float`, or `bool` representation, and at least one operand after the first
comparison must require conditional materialization.

Nested region occurrences are accepted only through independent facts and
plans. A child prerequisite closure remains lexically inside its parent's open
guard. This is composition of the same decision, not permission to infer a new
source feature.

## Decision D14B-02 — lower to flat guarded statements

Boolean regions use one initialized automatic `bool` accumulator. Operand zero
is evaluated once unconditionally. Each later operand receives one sibling
`if` guard in source order: `result` for `And`, `!result` for `Or`. The
operand's complete prerequisite sequence and the accumulator assignment occur
inside that guard.

Chained-comparison regions evaluate and materialize the first two operands in
source order, initialize one Boolean result from the first comparison, and
retain the second operand in an initialized rolling `previous` temporary. Each
later operand receives one sibling `if (result)` guard. Inside it, PyCForge
emits the operand prerequisites, materializes `current`, assigns the next
comparison to `result`, and updates `previous = current`.

These shapes preserve:

- Python left-to-right order;
- exactly-once evaluation of every reached operand;
- no evaluation of a skipped operand;
- once-only reuse of every chained middle operand;
- definite initialization before every result or rolling-middle read;
- flat per-region control depth rather than operand-count-deep nested blocks.

Only existing structured C IR nodes may represent the declarations,
assignments, guards, blocks, and expressions. Raw C text, a conditional
expression, statement expression, `goto`, a new C IR node kind, and renderer
semantic inference are forbidden.

## Decision D14B-03 — require complete region facts and exact plans

Analysis must publish one immutable `fact-table/0.14.1`
`conditional-region-facts` record for every selected region. It records exact
ownership and source identity, root kind and operators, ordered operands,
categories and C types, prerequisite closure, conditional ordinals, guard
polarity, call and numeric fact references, result/rolling strategy, lifetime,
resource, cancellation, failure, and target decisions.

The fact's lowering shape is exactly `flat-guarded-assignment-v1`. The exact
region-plan obligations are the identifiers fixed in the opening
specification, not merely equivalent prose.

Independent validation must reconstruct the region directly from Python IR and
the already-published cumulative facts. It must require exact coverage and
exact RulePlan fact, obligation, explanation, and helper-requirement sets. It
must also verify from structured C IR that no prerequisite call or helper call
was hoisted outside its declared guard.

At most two RulePlan families may be added:

- `phase14.conditional.boolean_region@0.14.1`;
- `phase14.conditional.comparison_region@0.14.1`.

The region rules own no helpers. Existing nested operations keep their existing
helper requirements, and helper assembly remains the exact union of
operation-owned plans.

## Decision D14B-04 — preserve existing policies and roots causes

No new public policy field is justified. The active rule-set identity, facts,
plan, C IR envelope, generated-C envelope, summary, trace, and renderer may
advance to 0.14.1. `strict-source-v1`, the Phase 14A numeric policy, result
serialization 0.5, SourceBundle, Python IR, helper, container, module, record,
target, and workspace contracts remain unchanged.

`PYC2950` and `PYC2951` remain the placement-boundary diagnostics for forms
that do not close this proof. Existing target, arity, representation,
recursion, numeric, container, or record diagnostics retain precedence when
they are the actual root cause.

## Explicitly rejected neighboring behavior

This decision does not authorize:

- non-Boolean operand-returning `and` or `or` semantics;
- strings, records, containers, unknown values, or coercion-dependent values as
  comparison-chain operands;
- keyword/default/variadic/unpacked or indirect calls;
- recursion, exceptions, failure propagation, mutation, global state,
  allocation, cleanup, arbitrary-precision repair, or a new runtime;
- a new scalar operation, statement, binding form, grammar form, helper, C IR
  node, renderer shortcut, or host/toolchain surface;
- Phase 14C, another deferred construct family, or Phase 15.

## Resource decision

No 64-operand ceiling is introduced. That number belongs to unrelated document,
container, and record policies and is not evidence for an expression limit.
The existing aggregate source and AST ceilings bound the source, while flat
guards keep generated control depth independent of region width. Analysis,
validation, and lowering must remain linear. If implementation evidence shows
that an additional expression-specific ceiling is genuinely required, 14B
pauses for a new reviewed resource decision rather than inventing one during
coding.

Decision outcome: feasible and approved for bounded implementation. Promotion
requires a later manifest, complete vertical evidence, hardening, packaging,
and an explicit promoted release record; none is supplied here.
