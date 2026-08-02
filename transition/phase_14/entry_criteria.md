# Phase 14 Entry Criteria

Status: satisfied for the Phase 14A opening checkpoint on 2026-07-22; no
implementation or promotion is claimed.

## Predecessor authentication

- The sealed `pycforge_phase_13_v0_13_0.tar.gz` source archive is 963,912
  bytes and has SHA-256
  `36938f021db7110c590af878c748b5331ccc2d3de2f2144c3eb3b09d76fb998a`.
- Independent archive inspection reproduced the promoted canonical release-tree
  SHA-256
  `483743b12fdd682b4b2ad488279ef243f00f0b055332096e5af09b0b01ab00a2`
  recorded by `transition/phase_13/release_fingerprint.json`.
- The archived `pycforge/converter` subtree independently hashes to
  `16d780e9eb5861f20ef3a1132928c32353aae97f99a3da526bc42386a0871dc6`.
  The candidate subtree matched that identity before any Phase 14 entry
  artifact was added.
- The v0.13.0 wheel identity remains SHA-256
  `90691b4534388e76e6bdcb83766435b3ad53f424802b0e7624af5d89bb2c1fb0`.
- The authenticated v0.13.0 handoff records 335 discovered tests: 325 passing
  and 10 expected PyQt5-dependent skips, with cumulative audits passing.
- The prior compile-only custody incident remains historical evidence of the
  abandoned first Phase 13 candidate. It is not erased or reclassified. No C
  compiler, linker, loader, or generated-code executor was invoked while
  authenticating or opening Phase 14A.

## Authority and opening conditions

- The user explicitly approved the recommended individually sealed Phase 14
  course and authorized Phase 14 to proceed.
- Architecture Revision 3.1 and its Revision 3.2 addendum match their sealed
  SHA-256 identities. Phase 14 therefore remains a sequence of independent
  mini-phases; approval of 14A does not approve any neighboring construct.
- The refreshed Phase 14 conversion-debt register assigns an explicit owner,
  risk, disposition, and containment boundary to every item. It contains no
  unowned High or Extreme entry and authorizes no approximation.
- `integer_divmod_decision.md` accepts only the exact 14A feasibility decision.
  `breadth_and_change_budgets.md` closes its allowed expansion before code work.
- The two prospective helpers and the complete Phase 10 registry have been
  identity-checked. Phase 14A may select only
  `pycf.i64.floor_div@1.0.0` and `pycf.i64.floor_mod@1.0.0`; it may not modify
  or replace them.

## Authorized opening

The opening gate authorizes implementation work only for exact integer `//`
and `%` occurrences whose right operand is a directly proved existing-lowerable
signed-64 literal in `[-9223372036854775807, -2]` or
`[1, 9223372036854775807]`, under the focused specification. It does not
authorize dynamic divisors, exception emulation, arbitrary-precision integers,
checked arithmetic, a general numeric runtime, or any other Phase 14 family.

Windows 11 testing remains future user feedback. It is neither claimed here nor
an entry requirement. The workspace, no-host-discovery, generated-C
immutability, atomic-save, cancellation, observer-isolation, and no-toolchain
boundaries remain mandatory predecessor obligations.
