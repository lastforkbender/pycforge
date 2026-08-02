# PyCForge Workspace — `pycforge-workspace/0.5`

Status: active Phase 15C workspace contract in PyCForge `0.15.2`  
Scope: installed PyQt5 desktop application only  
Semantic authority: sealed Phase 14D converter contracts at `0.14.3`  
Worker protocol: `pycforge.worker-protocol/0.1`  
Action registry: `pycforge.action-registry/0.2`  
Visual system: `pycforge.visual-system/0.2`  
Presentation settings: schema `1`

## Product identity

The front-facing application and workspace identity is **PyCForge**. The
current source, distribution, window titles, accessible application name,
organization and application settings identity, menus, toolbars, dialogs,
screenshots, and user documentation use that identity exclusively.

Phase 15C retains the closed PyCForge-only presentation namespace established
in Phase 15B. The application reads and writes only recognized schema-1
presentation settings in the active PyCForge namespace. Earlier presentation
bytes remain authoritative only in their authenticated historical archive.

## Transpiler boundary

PyCForge is a deterministic Python-to-C **source transpiler** for a deliberately
bounded Python subset. The workspace submits explicit `ConversionRequest`
values through the same public `PythonToCConverter` facade used by the API and
headless CLI.

The workspace does not select, approximate, or reinterpret conversion
semantics. Given the same canonical request and observation options, direct
API, CLI, and workspace use preserve the same status, diagnostics, artifacts,
facts, RulePlans, generated-C bytes, mappings, summaries, decision traces,
telemetry, and fingerprints.

PyCForge stops after producing and independently validating deterministic C11
source. It has no compile, assemble, link, load, run, execute, test, debug,
profile, terminal, REPL, toolchain, build-system, deployment, or generated-code
runtime surface. It never imports or executes user Python.

## Closed SourceBundle workspace

The application projects the same explicit one-to-64-document `SourceBundle`
accepted by the sealed converter:

- exactly one primary document;
- canonical module IDs and relative logical source names;
- explicit add, open, remove, select, reorder, make-primary, and save actions;
- one optional linked host path and dirty state per Python document; and
- transactional rejection of duplicate, invalid, or over-capacity changes.

Only an explicit Open action or explicit recent-file selection reads a host
file. PyCForge does not scan folders, watch projects, discover packages,
resolve imports from the host environment, index unrelated files, or reopen
source automatically.

Every semantic document, identity, primary, or ordering change advances the
workspace generation, requests cancellation of obsolete conversion work, and
makes the previous result stale. A late or mismatched result is never
republished even if later edits restore byte-identical source.

## Editors and immutable generated C

Python is the only editable code surface. Generated C is an immutable
inspection surface. Replace, paste, cut, formatting, code actions, and direct
mutation are unavailable for generated C.

Diagnostics, source-to-C mappings, Conversion Summary, Decision Trace, and
Telemetry are observer surfaces. Search, selection, layout, visual style,
visibility, geometry, recent-file, and scroll state never enter request or
artifact fingerprints.

Generated C remains hidden until explicitly shown. Hiding it does not discard a
valid result. Last-known-good C may remain visible after an edit, rejection,
cancellation, or failure, but it is marked stale and cannot be saved as
current.

Python Save and Save As validate the complete candidate workspace before
writing. Dirty-source removal, replacement, and close require an explicit
Save, Discard, or Cancel decision.

Save C is enabled only for a complete publishable result whose exact
SourceBundle fingerprint matches the committed current workspace. Conversion
never writes C automatically. Linked-C writes use the shared atomic writer;
rejection, cancellation, stale state, invalid paths, or interrupted replacement
leaves the preceding destination unchanged.

## Phase 15C authoring and inspection

Document tabs and split-pane state store bounded document identifiers only.
They never retain source text, paths, conversion results, or observer payloads.
The workspace may expose one or two synchronized Python source panes; it cannot
open an unbounded editor grid.

Source-authoring commands cover duplicate line or selection, move lines,
indent, outdent, and Python comment toggle. Each command is deterministic,
selection-aware, line-ending preserving, and undoable through the active Python
editor. Go-to-line uses document blocks without copying the complete source.
Whitespace display and code-fold state are presentation-only.

The source outline and breadcrumbs derive from normalized already-open Python
text. Analysis runs outside the GUI thread, is cancellable and latest-wins, and
is bounded by source size, symbol count, hierarchy depth, and label length.
Invalid syntax produces an inert projection and cannot retire valid structure
for another open document.

Find in Source Bundle searches literal text captured from the explicit open
documents. It performs no file-system access, project discovery, or import
resolution. Requests are immutable and path-free; results are in bundle and
source order, include Python and UTF-16 positions, and stop after the first
omitted match beyond the 5,000-result projection cap.

The command palette projects enabled, visible, static registry actions only.
It owns no handlers and provides no free-form execution path. Session
transpilation history stores at most 64 immutable, payload-free terminal
records; it cannot retain Python or generated-C text, diagnostics, mappings,
facts, traces, telemetry, or worker envelopes.

## Declarative action authority

The import-safe action registry declares exactly 48 stable action
specifications, including the bounded recent-file dynamic template. A stable
identifier owns:

- visible label and mnemonic;
- SVG icon identifier;
- shortcut;
- tooltip and status explanation;
- accessible name;
- checkability and default checked state;
- semantic tone; and
- allowed menu, toolbar, context, and dynamic surfaces.

The optional Qt adapter creates and binds each persistent `QAction` once.
Menus, toolbars, context surfaces, and bounded recent-file entries consume the
registry. No persistent action is created ad hoc by an individual widget.

The registry is presentation authority, not semantic authority. Enablement,
checked state, and visibility project the exact current controller snapshot.
They never replace request generation, immutable revision, bundle fingerprint,
result freshness, or the final Save C recheck.

## Main-menu contract

The persistent main menus are:

- File;
- Edit;
- View;
- Navigate; and
- Transpile.

They use custom PyCForge menu presentation over native `QMenu` and `QAction`
interaction mechanics. Menu styling preserves:

- keyboard traversal and focus;
- mnemonics and native shortcut columns;
- checked and disabled state;
- submenu indication;
- Escape and outside-click dismissal;
- focus return;
- assistive-technology exposure; and
- screen-edge placement.

Custom rendering may add graphite gradients, bounded corner radii, icons,
selection rails, and danger treatment. It may not replace native action
semantics, obscure labels, remove shortcut text, or suppress focus indicators.

## Context-menu contract

Context surfaces are declared for:

- the editable Python source editor;
- the read-only generated-C inspector;
- the closed Source Bundle navigator;
- document tabs;
- diagnostics;
- source-to-C mappings;
- bundle-search results;
- session transpilation history;
- structured inspectors used by Conversion Summary, Decision Trace, and
  Telemetry;
- writable text input; and
- generic read-only text.

Every item is either a registered action, a separator, a declared submenu, or a
bounded dynamic entry whose command family is declared by the registry.

The generated-C surface uses a closed read-only allowlist. It may expose
inspection, selection, copying, view toggles, and source/mapping navigation. It
must not expose Undo, Cut, Paste, Replace, formatting, refactoring, code
generation, or another mutating command.

## Visual system

`pycforge.visual-system/0.2` defines semantic rather than widget-specific
tokens for:

- canvas, raised, panel, menu, inset, hover, pressed, selected, and disabled
  surfaces;
- primary, soft, muted, disabled, inverse, and accent text;
- focus, selection, transpilation, success, warning, error, and danger states;
- border, separator, rail, and shadow treatment; and
- logical spacing, radii, and icon dimensions.

The visual language uses graphite surfaces, layered gradients, high-contrast
text, blue and violet focus and selection accents, and a restrained warm
transpilation accent. Important states use text, shape, check state, rails, and
contrast in addition to color.

Self-contained SVG icons:

- use a `0 0 24 24` view box and logical sizing;
- contain no raster element or embedded raster payload;
- contain no remote, file, or data reference;
- contain no script, foreign object, or font-glyph dependency;
- contain no fixed physical width or height; and
- remain understandable beside visible text labels.

The packaged catalogue contains exactly 55 SVG icons. Phase 15C extends the
shared stylesheet to document tabs, split panes, breadcrumbs, outline and
result trees, bundle search, session history, and the command palette.

The interface has no animation. Reduced-motion behavior is therefore inherent.

## High-DPI and accessibility foundations

Qt high-DPI scaling and high-DPI pixmaps are enabled before application
construction. Menus, toolbars, navigator controls, and window branding use
logical icon dimensions.

Every icon-only control has a visible tooltip and accessible name. Menus and
context surfaces have stable accessible names. Focus, hover, pressed, checked,
selected, disabled, warning, error, and danger states remain distinguishable.
Menus preserve visible text labels and native keyboard interaction.

These are source and behavior foundations. They do not constitute visible
Windows 11 or Linux certification, assistive-technology certification, or a
real display-scaling matrix.

## Phase 15A isolation and responsiveness

Each conversion executes in a spawned child process. The GUI interpreter and
event loop never invoke `PythonToCConverter`; the workspace import and
invocation of that facade belongs to the child entry point. Transport uses
bounded canonical JSON frames over byte-only process connections under
`pycforge.worker-protocol/0.1`.

The supervisor admits exactly one active conversion and one replaceable latest
pending request. A newer request retires an older pending request and asks the
active request to cancel. Cooperative cancellation retains bounded hard
termination and reaping. Close acceptance does not wait for converter
cooperation.

A result publishes only when its request generation, source-bundle
fingerprint, transport fingerprint, and authenticated workspace revision all
match current immutable state. Cancellation, supersession, startup failure,
broken transport, malformed or oversized IPC, abrupt exit, and resource
exhaustion cannot publish partial C or replace last-known-good C.

File reads, hashes, external-change observation, revision/index construction,
literal search, source-structure analysis, and atomic writes run outside the
GUI thread. Editor marker, search, syntax, bracket, overview, generated-C, and
hidden-detail projections remain capped, viewport-focused, deferred, or
incremental.

Structured Summary, Decision Trace, and Telemetry inspection is iterative and
cycle-safe. One projection admits at most 1,024 nodes, 16 levels, 256 children
per container, and 2,048 characters per displayed value. Pending document
identity edits immediately mark generated output stale and disable Save C.
Diagnostics are not presented as current while cancellation is pending.

Action enablement and menu refresh are bounded projections. They do not invoke
the transpiler, read source files, hash complete documents, scan directories,
discover packages, or rebuild result details.

## Presentation settings

Presentation settings use schema version `1` at
`settings/schema_version`. Recognized values are bounded and failure-tolerant:
window geometry and state, splitter positions, view toggles, last dialog
directory, and a bounded recent-file list. Recent references open only after
explicit user action.

Settings never persist unsaved Python, generated C, diagnostics, mappings,
artifacts, helper content, worker envelopes, or credentials. Invalid or
incompatible known values fall back safely and clear only recognized
presentation keys; unrelated preferences remain untouched.

## Evidence boundary

Phase 15C changes workspace authoring, navigation, inspection, and
presentation contracts only. It does not change the supported Python subset,
converter code, converter identities, generated-C bytes, result serialization,
diagnostics, facts, RulePlans, summaries, traces, telemetry, mappings, or
fingerprints.

Phase 15C evidence includes source inspection, static contracts, headless
behavior, registry and icon checks, and real PyQt5 widget execution using the
offscreen QPA backend. It makes no physical display-scaling,
assistive-technology, Windows 11, or visible Linux claim.

Visible Windows 11/Linux PyQt, display-scaling, and assistive-technology gates
remain mandatory in Phase 15D. Validation invokes no C toolchain and never
executes generated C.

Phase 15D remains unopened.
