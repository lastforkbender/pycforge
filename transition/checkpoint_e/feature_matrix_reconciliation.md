# Checkpoint E Feature-Matrix Reconciliation

Status: promotion gate reconciled; semantic matrix remains frozen

`specifications/feature_matrix.json` is the sealed PyCForge 0.14.3 semantic
matrix. It contains exactly 69 entries under
`pycforge.feature-matrix/0.14.3`, with rule set
`phase14-required-keyword-only-calls-v0.14.3` and renderer
`c-renderer-v0.14.3`.

Checkpoint E does not edit, reseed, reorder, expand, or reinterpret that JSON.
IDE-grade workspace features are presentation and source-authoring facilities;
they do not create new supported Python constructs or contexts.

The existing supported entries remain supported only in their exact recorded
contexts. Every recorded unsupported or deferred entry remains explicitly
unsupported or deferred, including defaults and variadics outside the exact
required-keyword-only profile, dynamic/indirect calls, comprehensions,
container mutation or escape, plain/dynamic imports, executable module state,
general classes and methods, record mutation/escape, lambdas, async constructs,
and pattern matching. The default policy remains: every unlisted Python 3.11
node or context is unsupported.

No Phase 14E is opened. Checkpoint E is a hardening and workspace-quality
checkpoint after sealed Phase 14D, not another semantic mini-phase. Any future
semantic expansion requires its own explicit feasibility decision, feature
matrix change, contract identities, diagnostics, fixtures, cumulative
eligibility proof, and atomic promotion.

Checkpoint E now supplies an explicit ordered witness for every exact
`(construct, context)` entry and one unlisted `Try` default witness. All 37
supported rows convert through the public converter and pass independent
generated-C text conformance. All 31 unsupported rows, the one deferred row,
and the unlisted default reject without C under their declared boundary and
diagnostic precedence. The executable report contains zero matrix-contract
mismatches and zero witness errors.

The 80-case promotion corpus also matches the authenticated Phase 14D
predecessor byte-for-byte under full `result_to_json` serialization. This
proves direct-converter preservation for status, diagnostics, artifacts,
facts, RulePlans, generated-C bytes, mappings, summaries, traces, telemetry,
request fingerprints, and output fingerprints.

Application-level request equivalence belongs to Phase 15 because it depends
on the future process worker and application request protocol. Checkpoint E
does not claim or simulate that unopened surface. The unchanged JSON identity
is evidence of semantic preservation, not a file to update for visual or
performance work.
