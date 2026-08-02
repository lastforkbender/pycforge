# Phase 14B Breadth and Change Budgets

Status: binding opening budget. Crossing a limit pauses implementation and
requires a new reviewed decision. Limits are not implementation targets.

## Breadth budget

| Dimension | Maximum authorized breadth |
| --- | --- |
| New semantic family | One: conditional placement of existing scalar prerequisites |
| Python root node kinds | Existing `BoolOp` using `And`/`Or`, and existing chained `Compare` |
| New Python syntax or primitive operations | Zero |
| Boolean categories | Exact existing Boolean representation only |
| Comparison categories | One compatible existing category per chain: `int`, `float`, or `bool` |
| Operand closure | Only expressions whose primitive occurrences are already supported by the cumulative 0.14.0 subset |
| New statement or binding forms | Zero |
| Conditional fact-table families | At most one complete family |
| New RulePlan families | At most two |
| New helper requirements or assets | Zero |
| New runtime failure channels | Zero |
| Allocation, ownership, or cleanup changes | Zero |
| New C IR node kinds | Zero |
| Other Phase 14 evaluations | Zero |

A wrapper or composition is eligible only because all of its primitive
operations already have complete cumulative evidence. Phase 14B may not treat
placement as permission to accept a new call form, numeric operation, dynamic
access, mutation, coercion, or failure behavior.

Nested 14B occurrences consume this same budget independently. Their fact
dependencies must prove that a child prerequisite closure remains within the
parent operand's guard.

## Resource breadth

No new operand-count constant is authorized. In particular, 64 is the sealed
limit for other product dimensions and is not an expression-resource proof.
Phase 14B continues to rely on the existing aggregate source-byte, line, token,
AST-node, and maximum-nesting ceilings.

Flat sibling guards are mandatory for the region's own operand sequence. An
operand count may increase statement count linearly but may not synthesize an
operand-count-deep `if` tree. If measurements demonstrate a need for a new
expression-specific ceiling, implementation stops and records the evidence
before a separate decision.

## Semantic and schema change budget

- At most one immutable `conditional-region-facts` family under
  `fact-table/0.14.1` may be introduced.
- At most two RulePlan definitions may be introduced, one for Boolean regions
  and one for chained-comparison regions.
- The active identities may advance to:
  `phase14-conditional-regions-v0.14.1`, `c-renderer-v0.14.1`,
  `conversion-plan/0.14.1`, `c-ir/0.14.1`, `generated-c/0.14.1`,
  `pycforge.conversion-summary/0.14.1`, and
  `pycforge.decision-trace/0.14.1`.
- Advancing the C IR envelope does not authorize a new C IR dataclass, enum
  member, statement kind, expression kind, type, storage mode, or renderer
  construct.
- SourceBundle 0.2, Python IR 0.4, result serialization 0.5, semantic policy,
  target contract, and helper/container/module/record/numeric/workspace policy
  identities are frozen.
- No new public conditional-evaluation policy field may be added. The rule set
  and exact region facts own this decision.
- Existing `PYC2950` and `PYC2951` may be refined from blanket placement
  rejections into exact profile boundaries. A new primary source diagnostic is
  outside the opening budget unless an independently reviewed ambiguity cannot
  be expressed without one.
- Unsupported nested primitives retain their existing diagnostic precedence;
  a placement diagnostic cannot conceal target, arity, representation,
  recursion, numeric, container, record, or module causes.

## Compatibility budget

- `phase14-bounded-numeric-v0.14` and `c-renderer-v0.14` remain explicit
  historical configuration identities.
- An explicit historical 0.14.0 request must preserve its exact canonical
  request shape, generated-C bytes, generated-output fingerprint, payload,
  summary, and trace schema behavior. No 14B field may leak into that shape.
- Under the new active configuration, sources with no selected conditional
  region must preserve predecessor generated-C bytes and output fingerprints.
  Versioned envelopes may differ only where this opening explicitly permits.
- Phase 14A helper source, interfaces, versions, registry membership, registry
  fingerprint, and generated helper bytes remain exact.
- Existing module closure, record/container ownership, workspace staleness,
  read-only generated C, and linked-save behavior may not change.

## Implementation-location budget

One isolated conditional-evaluation package may own region facts, analysis,
independent validation, and lowering. Integration edits are limited to
contract identities and capability checks, analysis publication, planning,
fact validation, lowering delegation, structured C IR validation, summaries,
traces, diagnostics/feature metadata, audits, tests, and release evidence.

The cumulative `pycforge/converter/lowering.py` file is already 999 lines
against the 1,000-line architecture ceiling. Phase 14B must extract the legacy
Boolean/comparison mechanics behind a narrow service boundary and leave that
hotspot at or below the ceiling; adding the feature inline is forbidden.
Conditional analysis cannot depend on C IR or rendering. Conditional lowering
cannot perform source eligibility analysis or emit final C text.

GUI widgets, workspace state/control, saving, source acquisition, host import
discovery, module resolution, container/record ownership, numeric helper
semantics, the helper registry, and renderer syntax invention are outside the
implementation-location budget.

## Complexity, cancellation, and publication budget

- Build parent, ownership, and prerequisite indexes once. Analysis and
  validation must be linear in normalized nodes, operand edges, and referenced
  cumulative facts; per-region whole-tree or repeated subtree scans are
  forbidden.
- Lowering is linear in reached operands and their already-planned prerequisite
  statements.
- Cancellation checks are required during region discovery, fact
  reconstruction, RulePlan publication, and per-operand lowering.
- Rejection, cancellation, internal validation failure, or interrupted
  replacement publishes no partial successor fact table, plan, C IR, mapping,
  helper manifest, summary, decision trace, semantic telemetry, or generated C.
- Observers remain bounded and semantically inert. Their configuration and
  failure cannot influence region facts, guards, names, mappings, or output
  fingerprints.

## Budget reopening triggers

Stop Phase 14B rather than stretching this budget if implementation appears to
need a new syntax or source primitive, a new C IR node, nested statement
expression, raw C text, runtime flag, helper, allocation, cleanup, exception or
other failure channel, dynamic target/value behavior, operand-returning
non-Boolean `and`/`or`, a new resource ceiling, more than two rule families, or
any neighboring Phase 14 mini-phase.

