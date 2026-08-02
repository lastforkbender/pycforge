# Phase 14A Gate Evidence

Scope status: Phase 14A promoted and sealed for PyCForge 0.14.0.  
Evidence status: complete.

## Opening evidence

- The sealed PyCForge 0.13.0 archive, release tree, converter subtree, and
  wheel matched the authenticated SHA-256 identities recorded in
  `baseline_fingerprint.json`.
- The bounded integer floor-arithmetic boundary was accepted before
  implementation in `integer_divmod_decision.md` and
  `specifications/phase14a_bounded_integer_divmod.md`.
- The Phase 14 conversion-debt register has an explicit owner, disposition,
  risk, and containment boundary for every item. It authorizes no silent
  approximation.
- Breadth and change budgets admit only `BinOp.FloorDiv`, `BinOp.Mod`, one
  numeric fact family, one RulePlan family, and the two frozen Phase 10 helper
  references. No new Python IR or C IR syntax node kind is authorized.
- The helper registry and floor-division/modulo assets retain their sealed
  fingerprints. Phase 14A selects them; it does not alter them.

## Vertical-slice evidence

- Numeric analysis and numeric lowering reside in a separate feature package.
  Analysis publishes source/document/module/function-anchored immutable
  `fact-table/0.14` records; lowering consumes validated facts and RulePlans.
- Each accepted `//` or `%` occurrence owns exactly one
  `phase14.numeric.floor_arithmetic` RulePlan and the exact corresponding
  helper requirement.
- The admitted direct-literal divisor set excludes `0`, `-1`, and
  `INT64_MIN`, closing both C11 undefined division cases without a runtime
  failure or exception channel.
- Signed-64 left, right, and result temporaries preserve left-to-right,
  exactly-once evaluation. Repeated requirements are deterministically
  deduplicated in the frozen helper registry.
- Independent validation cross-checks numeric facts, RulePlans, helper
  requirements, C IR, rendered helper definitions/calls, mappings, summaries,
  traces, and serialization. Unsupported or incomplete evidence publishes no
  generated C.
- Mathematical reference fixtures cover exact and non-exact results, every
  sign quadrant, signed-64 boundary dividends, extreme admitted divisors, and
  `a == (a // b) * b + (a % b)`.
- Stable negative fixtures cover mixed/Boolean categories, zero, negative one,
  `INT64_MIN`, out-of-range, dynamic, and calculated divisors. Primary numeric
  diagnostics are `PYC3701` and `PYC3702`.
- An explicit historical Phase 13 request retains exact predecessor generated-C
  bytes and fingerprints and contains no Phase 14 numeric-policy field.

## Promotion evidence

- The final suite discovered 365 tests: 355 passed, 10 had the expected
  PyQt5-unavailable skip, and none failed.
- Architecture, rules, helpers, containers, modules, records, numeric,
  determinism, and Phase 9–14 transition audits passed. The cumulative
  determinism SHA-256 is
  `67e309271328db2031659953645769987f6654770a4395dc73261d10bee97ef0`;
  the numeric audit witness-C SHA-256 is
  `3b57b1466fc4f75506301c3393456d09d38328680befe82ee7986bd9949d6812`.
- Two fixed-epoch wheel builds were byte-identical. The 252,934-byte wheel has
  SHA-256
  `8de55533728eae00caa6381c4eb0af402ed479e4068047f5e14402cf668c0822`,
  contains 115 validated RECORD members and no native binary, and carries the
  `py3-none-any` tag.
- A clean isolated wheel installation passed installed SourceBundle numeric
  conversion, the numeric audit, and workspace linked-C atomic save.
- Two normalized source-archive builds were byte-identical. The archive digest
  is recorded externally to avoid embedding an archive's identity inside
  itself.
- The canonical release-tree SHA-256 is authenticated by
  `release_fingerprint.json`, which is excluded from its own hash domain.

## Toolchain and platform custody

Phase 14A validation uses structured C IR, independent text conformance, and a
mathematical reference model. The release candidate invokes no C compiler,
linker, loader, or generated-code executor. PyCForge exposes no such surface.

Windows 11 laptop testing remains downstream user feedback, not evidence
claimed by 0.14.0. The portable C11 source contract remains the only target
claim, and no platform-specific execution or discovery path is opened.

Phase 14A is the sealed mini-phase boundary. Broader Phase 14 remains closed
pending an independent decision and explicit approval. Phase 15 has not
started.
