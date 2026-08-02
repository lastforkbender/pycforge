# Python-to-C Converter Architecture — Revision 3.2 Addendum

Status: Phase 10 entry clarification  
Base authority: Revision 3.1  
Base document SHA-256: `d05963984105466ae7df4c0e25941865fb0e55181059e3c95e3fde42556fd8e3`

This addendum supplements Revision 3.1. It does not rewrite the promoted
Phase 9 semantic boundary or alter the sealed PyCForge v0.9.0 release.

## Roadmap custody

Every future full-project handoff archive shall contain the authoritative base
roadmap and each active addendum. Transition evidence records their identities
and hashes. A phase handoff may summarize the roadmap, but a summary is not a
substitute for the authoritative documents.

## Phase 10 entry gate

Support-template infrastructure must not be justified with unused or invented
helpers. Before helper-registry implementation begins, at least two concrete
helper requirements must be owned by promoted RulePlans or accepted feasibility
decisions. Each accepted decision records:

- the prospective consumer and exact semantic obligation;
- interface, target-contract, ownership, lifetime, and failure requirements;
- why structured inline C IR is insufficient or undesirable;
- dependency and cancellation expectations;
- the phase in which the consumer may become eligible.

An accepted feasibility decision authorizes infrastructure requirements and
fixtures only. It does not silently promote the prospective Python feature.
If two honest requirements cannot be demonstrated, Phase 10 remains at its
entry checkpoint.

## Python-first workspace

The Python source editor is the primary workspace and receives the full editor
area by default. Generated C remains immutable presentation output and is hidden
until the user explicitly reveals it. A visible, keyboard-accessible Show/Hide C
control governs the view without changing conversion state, output eligibility,
or atomic-save policy. Hiding generated C never discards it. Stale or rejected
output remains unsavable as current output.

Diagnostics, conversion summary, decision trace, and telemetry remain
inspection surfaces rather than source-authoring controls.

## Conversion progress

Conversion progress is non-modal and observer-only. Pressing Convert immediately
publishes a converting state and leaves Cancel available. A short-delay inline
indicator avoids flicker for fast conversions. Before the first stage event it
is indeterminate; afterward it reports completed pipeline stages and the active
stage name. Stage counts describe pipeline milestones, not elapsed-time
percentages.

Progress callbacks are best effort. Their absence, latency, or failure cannot
change diagnostics, status, generated C, mappings, artifacts, semantic or output
fingerprints, decision traces, or telemetry. No conversion-progress popup is
required.

## Historical validators

A promotion-time whole-tree fingerprint validates that historical release tree,
not an arbitrary later cumulative tree. Later candidates prove compatibility by
running the complete historical test suite, validating the preserved predecessor
archive, and passing their current-phase validator. Historical fingerprints are
never rewritten merely to make a later tree match.

## Opening-checkpoint exit criteria

The Phase 10 opening checkpoint passes when:

- Revision 3.1 and this addendum are packaged and hash-verified;
- the Python editor opens full-width with generated C hidden;
- generated C has an explicit Show/Hide control and remains read-only;
- conversion progress is delayed, inline, cancel-compatible, and stage-aware;
- progress-observer failure is proved semantically inert;
- stale-result and atomic-save guarantees remain passing;
- the complete Phase 0–9 regression suite remains passing.

Helper-registry implementation follows only after the separate two-requirement
entry decision is approved.
