# Phase 14B Entry Criteria

Status: satisfied for the Phase 14B feasibility and opening checkpoint on
2026-07-22. Implementation, vertical validation, promotion, and release are not
claimed by this packet.

## Predecessor authentication

- The sealed `pycforge_phase_14_v0_14_0.tar.gz` archive is 1,016,512 bytes and
  has SHA-256
  `d4fe065d168241b4371901e19eda346c38835c1d2ac07e3870f27abb5a7b3917`.
- Independent safe archive inspection reproduced the promoted canonical
  release-tree SHA-256
  `6eb034b63d4f08b8ea6de08fd38e507d12d4fc2436f0d3a68443624fc4c05d76`
  recorded by `transition/phase_14/release_fingerprint.json`.
- The archived `pycforge/converter` subtree independently hashes to
  `ccb92a82741202569e4639342e6ae711c246e2122a689f7831715ee182596c2d`.
- The sealed wheel is `pycforge-0.14.0-py3-none-any.whl`, 252,934 bytes, with
  SHA-256
  `8de55533728eae00caa6381c4eb0af402ed479e4068047f5e14402cf668c0822`.
- The promoted predecessor records 365 discovered tests: 355 passing, 10
  expected PyQt5-unavailable skips, and zero failures. Architecture, rules,
  helpers, containers, modules, records, numeric, determinism, and transition
  audits passed.
- No compiler, linker, loader, or generated-C executor was invoked while
  authenticating or opening Phase 14B.

## Authority

- The exact user direction is: “Our previous momento excluded the dangerous
  ones. Doesn’t need to be covered conversion territory for PyCForge currently.
  Continue strongly with the mini-phases so PyCForge may thrive ahead
  greatly.”
- Architecture Revision 3.1 and the Revision 3.2 addendum match SHA-256
  `d05963984105466ae7df4c0e25941865fb0e55181059e3c95e3fde42556fd8e3`
  and
  `93b228528a10895fdbdce7b6934d422e7eddd1a79b409bdbc15ea6677e5ab8c6`.
- Phase 14A is sealed and promoted. Phase 14B is a separate bounded decision;
  it does not reopen 14A helpers or authorize Phase 14C, another dangerous
  construct, or Phase 15.
- The Phase 14B debt register retains an owner and containment boundary for all
  14 High or Extreme items. Only
  `DEBT-SHORT-CIRCUIT-CALL-TEMP` becomes active inside this opening.
- `conditional_temporary_regions_decision.md` and
  `breadth_and_change_budgets.md` close the semantic and change boundary before
  implementation is eligible.

## Architecture readiness

- Existing expression lowering already separates prerequisite statements from
  one typed result expression. Existing C IR already represents variable
  declarations, assignments, Boolean expressions, blocks, and `if` statements.
- Therefore conditional placement is feasible without a new C IR node,
  renderer syntax, runtime, helper, allocation, ownership, cleanup, or failure
  channel.
- The cumulative lowerer is already at its 1,000-line structural ceiling
  boundary. Phase 14B entry requires an isolated conditional-evaluation
  analysis/lowering component and extraction rather than growth of that
  hotspot.
- Flat sibling guards avoid synthesizing operand-count-deep C block nesting.
  Existing source-byte, line, token, AST-node, and nesting limits remain the
  resource boundary; no unrelated 64-operand limit is authorized.

## Authorized opening

Implementation may begin only for:

1. existing Boolean-represented `and`/`or` expressions whose already-supported
   scalar operand prerequisites need region placement; and
2. existing type-compatible `int`, `float`, or `bool` chained comparisons whose
   later already-supported scalar operands must remain conditional.

Every primitive in an admitted operand must already be supported by the sealed
cumulative subset. Phase 14B changes placement only. Unsupported calls,
keywords, defaults, dynamic behavior, new arithmetic, mutation, exceptions,
cleanup-sensitive behavior, closures, generators, async syntax, and all other
unopened families remain rejected.

Windows 11 testing remains future user feedback and is not claimed by this
opening. Workspace stale-output protection, generated-C immutability, atomic
save, closed SourceBundle resolution, cancellation, observer isolation, and
the no-toolchain boundary remain mandatory.
