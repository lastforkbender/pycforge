# Checkpoint E Architecture and Workspace Decision

Decision: accepted at Checkpoint E for future Phase 15 implementation  
Scope: PyCForge desktop application only  
Converter semantics: frozen at the sealed 0.14.3 boundary

## Decision

PyCForge will use a process-isolated conversion service and a revision-driven,
IDE-grade PyQt workspace. The GUI process never executes conversion work and
the worker process never owns widgets.

```text
PyCForge widgets
    -> immutable workspace revision
        -> bounded worker supervisor
            -> isolated PythonToCConverter process
        <- versioned result envelope
    <- guarded, lazy view projections
```

The child process invokes the same public converter facade with the same exact
request identities as direct API use. Transport, supervision, menus, editor
features, and presentation preferences are observers and do not enter semantic
or output fingerprints.

## Worker supervisor

The supervisor owns:

- a monotonically increasing request generation;
- the exact bundle and request fingerprint expected by the GUI;
- one active worker request and at most one replaceable pending request;
- cooperative cancellation followed by a bounded terminate/kill escalation;
- crash, timeout, malformed-envelope, and resource-failure classification; and
- guaranteed cleanup on window close and application shutdown.

A newer request replaces the pending request. It never waits behind an
unbounded queue of obsolete conversions. A late, malformed, mismatched,
partial, or superseded result is discarded without touching displayed
last-known-good C.

The IPC envelope is explicitly versioned, size bounded, and fail closed. It
contains plain serializable values and authenticated request/result identities.
It does not expose arbitrary object deserialization, command execution,
environment discovery, or a toolchain.

## Workspace revisions

Edits update an in-memory document revision cheaply. Expensive bundle
fingerprints, UTF-8 hashes, line indexes, and search indexes are debounced,
incremental, cached, or computed outside the GUI event loop. Conversion takes
an immutable snapshot of the latest committed revision.

The GUI uses stable revision and projection keys. A progress-only snapshot does
not reread both full editors, rehash every linked file, rebuild the document
navigator, or recreate diagnostics and mappings.

## Editors and projections

- Python uses a writable IDE-grade editor.
- Generated C uses a read-only inspector that may be populated incrementally
  or viewport-first.
- Line/column and UTF-16 conversions use one cached index per text revision.
- Syntax highlighting supports a measured large-file mode and never blocks the
  event loop with a whole-document rehighlight.
- Diagnostics, mappings, traces, telemetry, and summaries use virtualized
  models with bounded visible rows and lazy children.
- Search is debounced and cancelable. Visible markers are capped or
  viewport-projected even when the total match count is large.
- File reads, hashes, existence checks on potentially slow paths, and external
  file-change assessment are moved off the GUI thread.

## Application shell

The front-facing shell, title, About surface, settings namespace, main menu,
context menus, accessible application name, and new documentation use
`PyCForge`. Custom gradient/icon menus share one action registry so menu bar,
context menu, toolbar, command palette, shortcuts, enabled state, tooltips, and
accessible names cannot drift.

The Source Bundle navigator remains bounded to explicitly opened documents. It
must not become a project explorer.

## Rejected alternatives

- **Keep the current conversion thread:** rejected because a Python thread
  cannot hard-stop a non-cooperative or stuck conversion and shares the GUI
  interpreter’s GIL.
- **Use more conversion threads:** rejected because it permits obsolete CPU
  work and does not provide crash, hang, or shutdown isolation.
- **Silently fall back from the process worker to the old thread:** rejected;
  failure must be visible and recoverable rather than weakening the liveness
  contract.
- **Put converter logic in widgets:** rejected because it would duplicate or
  alter semantic authority.
- **Build a browser/Electron shell:** not authorized by this checkpoint; the
  required gate is real PyQt.

## Preservation

No decision here authorizes a converter feature, policy/schema bump,
generated-C change, historical-file rewrite, or C toolchain action.
