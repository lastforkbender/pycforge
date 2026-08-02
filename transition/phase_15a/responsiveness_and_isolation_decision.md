# Phase 15A Responsiveness and Isolation Decision

Status: accepted  
Distribution: PyCForge `0.15.0`  
Converter boundary: sealed `0.14.3`

## Process boundary

The workspace uses `spawn` exclusively. One child process receives one bounded
canonical request, invokes the unchanged `PythonToCConverter`, returns bounded
canonical progress/terminal frames, and exits. Only
`pycforge/ide/process_worker.py` imports converter-facade authority inside the
IDE package.

`pycforge.worker-protocol/0.1` uses `send_bytes` and `recv_bytes`; it does not
use pickle or arbitrary Python-object IPC. Request, control, progress, result,
artifact, mapping, diagnostic, and failure envelopes are type-, size-, depth-,
identity-, and fingerprint-checked. Malformed, duplicate-terminal, oversized,
broken, or incomplete transport fails closed.

## Scheduling and cancellation

The supervisor admits one active and one replaceable latest pending request.
Submitting a newer request removes any older pending request and requests
cancellation of the active request. The cooperative grace is 750 ms. Hard
termination begins after grace and resource reclamation is bounded by two
seconds. A pending request begins within 250 ms after prior process exit.
Window close does not wait for converter cooperation.

## Revision and publication

Every semantic edit advances an immutable workspace revision. Proportional
canonicalization, fingerprints, UTF-8 indexes, line starts, and UTF-16 line
starts run on a one-active/one-latest-pending daemon service. Convert and Save C
remain unavailable until the latest revision authenticates.

A result publishes only if request sequence, revision generation, bundle
fingerprint, request fingerprint, and transport fingerprint are all current.
The A-to-B-to-A edit case cannot revive a late A result. Canceled, stale,
superseded, failed, crashed, malformed, partial, or mismatched work retains no
publication authority.

Generated-C line/UTF-16 indexes are deferred to a latest-wins background
service after terminal status publication. Mapping projection waits for that
exact index, avoiding whole-output scans on the GUI thread.

## GUI-thread containment

Linked-file reads, UTF-8 decoding/hashing, external-change observation, and
guarded atomic writes run on bounded daemon workers. An exact revision guard is
rechecked immediately before linked-C replacement.

Source synchronization is coalesced for 120 ms; an edit immediately disables
Save C and cancels active conversion, while full editor text is copied only
when the coalesced revision flushes or a semantic command requires it.

Literal search is debounced 150 ms and latest-wins. It stores at most 5,000
UTF-16 ranges and preserves the exact count. Large-file syntax highlighting,
bracket scans, stored markers, viewport selections, and overview rails are
bounded. Generated C installs in 32 KiB event-loop slices and hidden output or
detail panes remain deferred.

## Exact non-semantic boundary

Direct and isolated `result_to_json` bytes must match for the same request and
observation options. The converter subtree is frozen. No Phase 15A code selects
new semantics, rewrites C, invokes a C toolchain, or executes generated C.

