# Phase 7 — PyQt5 Workspace Shell

Version 0.7.0 adds a professional two-pane workspace over the promoted Phase 6 facade. It adds no Python syntax, rules, lowering, representation semantics, helpers, compilation, execution, debugging, terminal, or toolchain behavior.

The controller accepts source revisions, computes a stable workspace-source fingerprint, submits conversions only through `PythonToCConverter`, and publishes a completed result only when its request sequence and source fingerprint still match the current editor revision. Previous complete C may remain visible after rejection or cancellation, but stale output is explicitly marked and cannot be saved as current output.

The generated-C viewer is permanently read-only. Decision trace and telemetry panels consume immutable completed snapshots. Python and generated C saves use the shared `AtomicWriter`.

## Phase 10 opening-checkpoint refinement

The Python editor now occupies the complete authoring area by default. Generated C and the diagnostics/summary/trace/telemetry tabs begin hidden and have independent keyboard-accessible toolbar toggles. Revealing or hiding either surface changes presentation only: it does not discard output, mutate artifacts, alter mappings, or bypass current-source save eligibility.

Convert remains asynchronous and Cancel remains cooperative. A status-bar progress indicator appears only when conversion lasts beyond a short anti-flicker delay. It begins indeterminate, then reports completed pipeline-stage units and the active stage label. These units are structural milestones rather than estimates of elapsed work.

The controller accepts immutable progress events only for the current request sequence and source fingerprint. Late progress from a superseded conversion is ignored by the same identity gate used for final results. The progress callback is best effort and excluded from semantic products.

Rollback condition: any requirement to modify Phase 6 conversion rules, planning, lowering, C IR, rendering, or supported syntax terminates Phase 7 work and restores the promoted Phase 6 baseline.
