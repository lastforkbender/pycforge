# Phase 14C Rollback Conditions

Before promotion, abandon the Phase 14C candidate and restore the authenticated
PyCForge 0.14.1 release if any condition below occurs.

## Candidate-abandon triggers

- The sealed 0.14.1 source archive, canonical release tree, converter subtree,
  wheel, roadmap, addendum, helper registry, or promoted release evidence
  cannot be reproduced at its recorded identity.
- An actual value, nested call, helper-backed operation, or complete
  prerequisite sequence evaluates in formal order rather than Python source
  order; evaluates more than once; or is omitted after its source position is
  reached.
- The emitted C call receives temporary references in any order other than
  exact formal ordinal order, or a reference does not identify the one actual
  statically bound to that formal.
- A final `CCallExpr` argument contains an unstaged source expression, source
  call, helper call, or other effect whose evaluation order C may choose.
- A positional-only formal is bound by keyword, a required formal is unbound,
  a formal is bound twice, an unknown keyword is accepted, or actual/formal
  category compatibility is inferred rather than proved.
- A default, keyword-only parameter, variadic parameter, starred argument,
  double-star keyword, `range` keyword, record-constructor keyword, method,
  alias-created callable value, indirect target, dynamic target, or recursive
  call publishes C.
- Python runtime argument binding, `TypeError` behavior, an exception channel,
  runtime name table, hashing, string comparison for binding, or dynamic
  dispatch is introduced.
- A keyword actual containing a sealed Phase 14B conditional region has a
  prerequisite hoisted outside its fact-owned guard, or Phase 14C changes the
  region fact or guard semantics.
- Keyword-binding facts fail exact coverage, contain dangling or foreign
  target/signature ownership, disagree with Python IR or sealed lexical,
  module, signature, category, call-graph, or conditional facts, or cannot be
  independently reconstructed without consulting lowering output.
- A binding fact fails to distinguish source evaluation order from formal call
  order, does not publish a complete actual-to-formal bijection, or silently
  repurposes an existing predecessor call-target field.
- The new RulePlan has an unresolved obligation, an inexact fact/explanation
  set, or a nonempty rule-owned helper requirement.
- Lowering resolves keyword names or repairs unsupported binding; rendering
  infers binding or evaluation semantics; or final text bypasses structured C
  IR and validation.
- `PYC2912` is used outside exact static name-binding failures on an otherwise
  eligible direct target (unknown keyword, positional-only keyword, collision,
  or duplicate), or `PYC2910` ceases to own `*`/`**`, null-name unpacking, and
  excluded keyword-shape boundaries.
- A more specific target, signature, arity, category, recursion, module,
  numeric, container, record, or conditional rejection is masked by a generic
  keyword diagnostic.
- The implementation introduces raw C text, a new C IR node kind, renderer
  syntax, a new helper or helper version, runtime state, allocation, ownership
  transfer, cleanup, or a new failure channel.
- The cumulative lowering hotspot exceeds its 1,000-line architecture ceiling,
  or analysis, independent validation, and lowering ordering are not separated.
- Binding, validation, or lowering becomes superlinear through repeated
  signature scans, whole-module rescans per call, or permutation enumeration.
- An explicit 0.14.1 or earlier request changes its canonical shape, facts,
  plans, generated-C bytes, output fingerprint, payload, summary, trace,
  diagnostics, or historical keyword rejection; or a source without a selected
  14C call changes generated-C bytes under the new active rules.
- Phase 14A helper code, helper fingerprints, registry membership or
  fingerprint, numeric semantics, or generated helper output changes.
- Phase 14B conditional facts, lowering shapes, guard placement, generated C
  for predecessor sources, or sealed transition evidence changes.
- Rejection, cancellation, internal failure, resource exhaustion, or observer
  failure publishes a partial or current successor artifact, or permits stale
  C to be saved as fresh.
- Determinism, provenance, source/output mappings, cancellation responsiveness,
  observer isolation, SourceBundle closure, module behavior, record/container
  ownership, workspace safety, package installation, or an earlier test/audit
  regresses.
- A test, audit, validator, evidence collector, review, or packaging gate
  compiles, links, loads, or executes generated C.
- Promotion is attempted without a later manifest, complete vertical evidence,
  adversarial fact/C IR validation, deterministic artifacts, an owned debt
  register, or authenticated predecessor custody.

## Rollback baseline

Rollback source archive: `pycforge_phase_14b_v0_14_1.tar.gz`  
Archive size: 1,088,259 bytes  
Archive SHA-256:
`30737e3a49dc3ed163be071742736f8310c2636a1dc8ac9b9b297aa8c030d2a1`  
Canonical tree SHA-256:
`895329a2723301de66adcb118a32308648a7993068e3ef7b5c9764914b9e2f4f`  
Converter subtree SHA-256:
`5d261abb5f7dbc480050472cac40a6b4a9539945a3d2e3211af552e094f9780d`

Rollback preserves every Phase 14A and Phase 14B release and custody record. It
does not rewrite `transition/phase_14`, rewrite `transition/phase_14b`, erase
failed-candidate evidence, or reclassify an unmet 14C obligation as passing.
