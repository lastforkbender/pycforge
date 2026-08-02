# Checkpoint E Opening Evidence

Status: documentation and architecture opening complete; implementation and
release gates remain open

## Sealed predecessor custody

- `CURRENT_STATE.md` identifies PyCForge 0.14.3 / Phase 14D as promoted and
  sealed.
- `evidence/phase_14d/release_report.json` records 539 discovered tests, 524
  passes, 15 expected skips, zero failures, and a 65/65 focused Phase 14D gate.
- The same report records the promoted converter-subtree SHA-256 as
  `74b32c25e40af3398dd46288941812ce7ad87f0d4b72fec3d3bd786cc1b8f3a8`.
- The promoted wheel is recorded as 340,054 bytes with SHA-256
  `c0dd0c0ed79131daa5af815a8a9bb096b9f955c9c617ec0b8eb6a10c69d27b7f`.
- Phase 15 is recorded as not started. This opening does not alter that fact.

## Current correctness foundations

Source inspection confirms:

- `WorkspaceController` uses an immutable snapshot model, monotonically
  advancing sequence, cancellation token, and bundle fingerprint;
- semantic edits retire the active request, including A→B→A edits;
- result and progress publication reject obsolete generations and mismatched
  bundle fingerprints;
- the GUI requests conversion asynchronously and bridges worker snapshots to
  the Qt thread with signals;
- generated C is read-only, freshness-gated, and atomically saved only after a
  current publishable result; and
- window close requests non-waiting controller shutdown.

Existing controller tests cover stale late results from a converter that
ignores cancellation, A→B→A retirement, worker/submit failures, recovery, and
last-known-good C custody.

## Opening risks found by source audit

The present application is not claimed to meet Checkpoint E responsiveness:

1. conversion uses `ThreadPoolExecutor(max_workers=1)` in the GUI process; a
   non-cooperative request can monopolize the worker and delay replacement or
   interpreter exit;
2. Cancel only sets a cooperative token and has no process-level hard stop;
3. canonicalization, source-document construction, tokenization, `ast.parse`,
   and several whole-document transforms contain intervals that cannot be
   interrupted externally;
4. each source edit copies full editor text and synchronously recomputes source
   and bundle fingerprints;
5. each snapshot compares full source/output text and rehashes every linked
   source for file-watcher state;
6. result publication installs the complete generated-C document and its
   syntax highlighting on the GUI thread;
7. mapping position projection repeatedly splits and prefix-encodes generated
   output per mapping rather than using one revision index;
8. cursor and edit updates can rebuild thousands of extra selections, while
   bracket matching may scan a whole document;
9. live Find can rescan a whole document and materialize every match without a
   result/marker bound; and
10. inspector trees are eagerly and recursively materialized when visible.

These are owned opening debt, not statements that the converter is
semantically incorrect.

## Evidence gap

The sealed 0.14.3 release environment did not have PyQt5 available. Ten Qt
tests were expected skips, and the release report explicitly states that
Windows 11 execution was future feedback. Historical offscreen screenshots and
tests remain useful custody, but there is no current real-platform,
maximum-input event-loop, custom-menu accessibility, or process-isolation
evidence.

## Accepted decisions

The opening packet now records:

- the exclusive PyCForge product and workspace identity;
- an IDE-grade transpiler-workspace feature boundary;
- explicit no-run/build/debug/terminal/toolchain/plugin/project-explorer and
  immutable-generated-C boundaries;
- a process-isolated future conversion worker with latest-wins scheduling;
- maximum-input responsiveness budgets based on 1,000,000 bytes, 100,000
  lines, 250,000 tokens, and 100,000 AST nodes;
- custom gradient/icon main and context-menu requirements;
- accessibility and real visible PyQt/platform gates;
- bounded implementation/change authority; and
- fail-closed rollback conditions.

## Opening non-claims

This packet creates no Python implementation, test, validator, schema,
manifest, release fingerprint, package artifact, version change, UI screenshot,
platform pass, performance pass, or release promotion. It invokes no compiler,
linker, loader, debugger, generated-C executor, or external toolchain.

Checkpoint E validation is eligible to begin. The recorded implementation
slices belong to Phase 15, remain unopened, and must preserve direct-converter
equivalence and all sealed historical custody when separately authorized.
