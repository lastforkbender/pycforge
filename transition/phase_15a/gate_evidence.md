# Phase 15A Gate Evidence

Status: promoted and sealed  
Distribution: PyCForge `0.15.0`  
Converter contract: sealed `0.14.3`  
Workspace contract: `pycforge-workspace/0.3`  
Worker protocol: `pycforge.worker-protocol/0.1`

## Converter custody and equivalence

The Checkpoint E converter-subtree SHA-256 remains
`a45bc2c31b954f9856c8eab36e95f68b086d5fdd682d2cf47ba2186887743124`.
The Phase 15A validator compares exact `result_to_json` bytes between direct
facade conversion and spawned-process conversion for single- and
multi-document requests. No result field is normalized away.

## Supervision and failure containment

The focused gate covers latest-pending replacement, active supersession,
cooperative cancel, forced termination, pending-start latency, abrupt exit,
malformed and duplicate terminal envelopes, oversized frames, broken pipes,
startup failure, stale generation/fingerprint rejection, and non-blocking
close. Every started process is reaped.

The promotion stress executes 100 edit/convert/cancel cycles. Ten cycles wait
for an actual spawned child before cancel; the remaining cycles adversarially
exercise pending and startup races. All 100 finish canceled, with one maximum
simultaneous worker and no active PID or pending generation after the gate.

## Maximum envelope

The validator records separate and combined fixtures approaching:

- 1,000,000 UTF-8 source bytes;
- 100,000 source lines;
- 250,000 tokens; and
- 100,000 AST nodes.

It verifies a 999,999-byte/100,000-line combined valid-syntax revision,
near-250,000-token and near-100,000-AST-node fixtures, the exact byte-ceiling
worker request, and clean rejection at one byte over the protocol source
ceiling. Revision/index construction executes off the caller thread.

Dense 950 KiB literal search submits in bounded time, runs off-thread, returns
an exact total, and retains only 5,000 UTF-16 ranges. Editor storage,
`ExtraSelection`, rail, bracket, and syntax-highlighting gates are capped.
Linked-file tests inject multi-second latency without blocking caller-side
Cancel or close, and stale atomic Save C preserves the preceding destination.

## Platform honesty

The promotion environment is headless Linux and does not provide PyQt5.
Phase 15A therefore makes no real-widget, event-loop-timer, accessibility,
display-scaling, Windows 11, or visible Linux claim. Offscreen/static checks are
supporting evidence only. Phase 15D remains the mandatory visible platform and
distribution gate.

## Safety

Runtime scans confine converter-facade authority to the spawned worker and ban
pickle/object IPC, dynamic execution, subprocess/tool discovery, compiler
tokens, and GUI-side `.convert()` authority. Tests, validation, packaging, and
smokes are Python-to-C-source-only. No compiler, linker, loader, foreign
function, or generated-C executor is invoked.

Exact test counts, fixture measurements, machine data, audit records, and
artifact hashes are recorded in `evidence/phase_15a` and the external Phase 15A
validation/package/checksum reports.

