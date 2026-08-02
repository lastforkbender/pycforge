# Phase 14B Gate Evidence

Scope status: Phase 14B promoted and sealed for PyCForge 0.14.1.  
Evidence status: complete.

## Opening evidence

- The sealed 1,016,512-byte PyCForge 0.14.0 archive matched SHA-256
  `d4fe065d168241b4371901e19eda346c38835c1d2ac07e3870f27abb5a7b3917`.
  Safe archive inspection independently reproduced canonical release-tree
  SHA-256
  `6eb034b63d4f08b8ea6de08fd38e507d12d4fc2436f0d3a68443624fc4c05d76`
  and converter-subtree SHA-256
  `ccb92a82741202569e4639342e6ae711c246e2122a689f7831715ee182596c2d`.
- Those identities match the promoted Phase 14A release fingerprint. The
  predecessor wheel is the 252,934-byte
  `pycforge-0.14.0-py3-none-any.whl`, SHA-256
  `8de55533728eae00caa6381c4eb0af402ed479e4068047f5e14402cf668c0822`.
- Revision 3.1, its Revision 3.2 addendum, the frozen Phase 10 helper registry,
  and every sealed `transition/phase_14` release record retained their exact
  authenticated identities.
- The conditional-temporary-region decision, exact opening specification,
  breadth budget, rollback conditions, and conversion-debt register admitted
  only `DEBT-SHORT-CIRCUIT-CALL-TEMP`. Dangerous runtime and object-model
  families remained excluded.

## Vertical-slice evidence

- Phase 14B adds one isolated `conditional-region-facts` family under
  `fact-table/0.14.1` and exactly two region rules:
  `phase14.conditional.boolean_region@0.14.1` and
  `phase14.conditional.comparison_region@0.14.1`.
- Boolean `and`/`or` regions evaluate the first Boolean operand
  unconditionally and place each later operand's complete prerequisite closure
  in a flat sibling guard with the exact true/false polarity.
- Chained comparisons evaluate the first two compatible scalar operands in
  order, initialize the result and rolling middle value, and place each later
  operand in a flat `if (result)` guard. Every reached middle value is
  materialized once and reused for its adjacent comparisons.
- Conditional placement accepts only the cumulative 0.14.0 scalar-expression
  closure. It adds no Python primitive, call shape, category, representation,
  helper, runtime failure channel, allocation, ownership, cleanup, or C IR node
  kind.
- Analysis, independent reconstruction, and lowering use persistent ownership
  and prerequisite indexes and remain linear. Cancellation checks cover
  discovery, fact reconstruction, plan publication, validation, and
  per-operand lowering.
- Structured validation proves exact region coverage, guard polarity,
  prerequisite containment, left-to-right once-only evaluation, initialized
  accumulators, rolling-middle reuse, mappings, summaries, traces, and
  serialization. Rejection, cancellation, or validation failure publishes no
  partial generated-C successor.
- The isolated conditional component leaves the cumulative central lowerer at
  957 lines, below its 1,000-line architecture ceiling.
- The conditional audit reconstructed 3 exact facts and plans, 5 expected and
  actual flat guards, and 177 unique C IR identifiers. Its witness generated-C
  SHA-256 is
  `cf9ccd348c69bbf51f8642b06e0b6cac3f82d585f4a334a103c9c3e914f610a5`.
- Under the active 0.14.1 configuration, sources selecting no conditional
  region retain exact predecessor generated-C bytes and output fingerprints.
  Explicit Phase 14A requests retain exact 0.14.0 request, payload, summary,
  trace, generated-C, and diagnostic behavior.

## Promotion evidence

- The final suite discovered 413 tests: 403 passed, 10 had the expected
  PyQt5-unavailable skip, and none failed.
- Architecture, rules, helpers, containers, modules, records, numeric,
  conditional, determinism, and applicable transition audits passed. The
  cumulative determinism SHA-256 is
  `f547f60b5405ff91df47e594418ceccbbfe1af0dc0323abb7c0f8d32ef5b0a97`.
- Two fixed-epoch wheel builds were byte-identical. The final wheel is
  `pycforge-0.14.1-py3-none-any.whl`, size 278,494 bytes, SHA-256
  `255cba6d45b6f7f2c8347f4764d37ad9858d9616f84cc93b65b07e205785a70d`.
  Its 120 RECORD members include 17 SVG assets and no native binary.
- A clean isolated wheel installation passed installed SourceBundle
  conditional-region conversion, the conditional audit, and workspace
  linked-C atomic save.
- Two normalized source-archive builds were byte-identical. The final archive
  is `pycforge_phase_14b_v0_14_1.tar.gz`; its size and SHA-256 are recorded
  externally to avoid embedding an archive identity inside itself.
- The canonical release-tree SHA-256 is authenticated by
  `release_fingerprint.json`, which alone carries the value and is excluded
  from its own hash domain.

## Toolchain and platform custody

Phase 14B validation uses Python IR, immutable facts and plans, structured C
IR, independent conformance checks, and deterministic rendering evidence. No C
compiler or linker was invoked. Generated C was never compiled, linked, loaded,
or executed. PyCForge exposes no compilation, linking, loading, execution,
debugging, terminal, package-discovery, or host import-resolution surface.

PyQt5 was unavailable in the release environment, so the 10 existing GUI tests
retain their expected skips and the sealed offscreen-widget evidence remains in
custody. Windows 11 laptop testing remains downstream user feedback; no Windows
11 execution or validation claim is made for 0.14.1.

Phase 14B is the sealed mini-phase boundary. Phase 14C has not started and must
not open automatically. Phase 15 has not started.
