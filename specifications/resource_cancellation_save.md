# Resource, Cancellation, and Atomic Save — v0.9

Default limits are 1,000,000 UTF-8 source bytes, 100,000 source lines, 250,000 tokens, 100,000 AST nodes, nesting depth 128, 1,000 diagnostics, 10,000 trace events, and 10,000 telemetry events. Nesting depth 128 is also the maximum accepted pipeline ceiling, keeping normalization, C IR validation, rendering, and independent text parsing safely below the host stack boundary. Invalid or unsafe limits reject canonicalization.

Resource exhaustion emits a stable diagnostic and publishes no successor from the failing stage. Cancellation is cooperative at stage boundaries and safe points in category analysis and lowering. A token observed after stage work or validation prevents successor publication. Canceled results expose no generated C.

Phase 10 exact dependency-closure and topological-order work checks the same
cancellation token. Cancellation discards the resolver's local closure and
publishes no partial helper plan, manifest, C IR, or generated C.

Phase 14B checks cancellation while constructing persistent prerequisite
closures, materializing published references, independently reconstructing
facts and plans, and lowering each guarded operand. Conditional analysis and
validation are linear in normalized nodes, operand edges, and published
prerequisite references. Cancellation retires the unpublished successor and
cannot expose a partial conditional fact table, plan, branch, mapping, summary,
trace semantics, or generated C.

Phase 14C checks cancellation while visiting calls and actuals, constructing
and independently reconstructing the binding permutation, publishing its fact
and RulePlan, staging source-order temporaries, and assembling formal-order
references. Cancellation retires the whole unpublished successor and cannot
expose a partial keyword table, plan, C IR, mapping, summary, trace, or
generated C.

Interactive progress is a best-effort, observer-only projection of pipeline boundaries. Progress failure is contained, late events are ignored by request/source identity, and no progress event can authorize publication. UI progress uses a short delay and never blocks cancellation with a modal dialog.

Only a complete publishable result for the current source fingerprint may be saved as C. CLI and workspace writes create a same-directory UTF-8 temporary, flush and `fsync` it, then atomically replace the destination. Rejection, cancellation, stale workspace state, observer-only old output, encoding failure, or injected interruption leaves the preceding destination unchanged.
