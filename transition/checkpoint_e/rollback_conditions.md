# Checkpoint E Rollback Conditions

Status: mandatory for every implementation slice

## Rollback authority

The immediate safe rollback is the authenticated sealed PyCForge 0.14.3
application and converter boundary. Rollback concerns the active workspace
candidate only. It must not rewrite Phase 14D history, regenerate historical
fingerprints, mutate user Python, or overwrite a last-known-good linked C file.

## Immediate rollback triggers

Rollback is mandatory if a candidate:

- changes direct-converter diagnostics, status, artifacts, generated-C bytes,
  mappings, summaries, traces, telemetry, request fingerprints, or output
  fingerprints for an otherwise identical request;
- modifies any sealed historical transition, evidence, handoff, release
  fingerprint, or predecessor artifact;
- runs conversion on the GUI thread or silently falls back to an in-process
  conversion thread;
- permits more than one active plus one latest pending conversion;
- publishes a late, mismatched, partial, canceled, malformed, crashed, or
  superseded worker result;
- cannot cancel/terminate a non-cooperative worker or leaves an orphan process
  after Cancel, close, or crash;
- misses any maximum-input event-loop, interaction, result-publication, or
  shutdown budget;
- edits generated C or saves stale/failed/canceled generated C as current;
- exposes run, build, debug, terminal, toolchain, plugin, project-explorer,
  host-discovery, or another forbidden feature;
- presents an alternate theme-derived product or component name;
- introduces custom menus that fail keyboard, mnemonic, screen-edge,
  high-DPI, focus, dismissal, or accessible-name behavior;
- claims a platform without a passing real visible PyQt gate there;
- persists unsaved source, generated C, credentials, semantic artifacts, or an
  unsafe worker payload in presentation settings; or
- broadens dependency or asset custody beyond the approved budget.

## Failure containment

Before promotion, the candidate must prove that rollback leaves:

- every user Python document either saved by explicit choice or still
  recoverable through the candidate’s declared recovery mechanism;
- the last-known-good linked C bytes unchanged;
- no worker process, pipe, temporary output, lock, or incomplete settings
  migration;
- presentation settings either readable by the predecessor or safely ignored;
  and
- the sealed 0.14.3 package/install path usable.

## Settings migration

Any settings schema change is versioned and transactional. The previous
settings blob is retained until the new schema has opened and closed
successfully. Invalid values fall back per field. Rollback never interprets a
new opaque worker envelope as settings and never requires deleting unrelated
application preferences.

## Recovery behavior

Worker startup failure, crash, timeout, out-of-memory, malformed IPC, or forced
termination produces a clear PyCForge error state with Retry and safe close.
There is no automatic downgrade to weaker isolation. The current source remains
editable and last-known-good generated C remains visible but unsavable as
current.

## Promotion stop

One rollback trigger stops packaging and release promotion. The issue is fixed
in the bounded slice or the slice is reverted in full; recorded thresholds,
fixtures, or expected outcomes are not weakened to convert a failure into a
pass.
