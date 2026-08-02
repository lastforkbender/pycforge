# PyCForge Workspace — `pycforge-workspace/0.1`

Status: active and unchanged in PyCForge 0.14.3
Scope: optional PyQt5 desktop workspace only

## Converter boundary

Version 0.12.2 was the corrective desktop-safety release over the sealed 0.12.1
workspace. Phases 13, 14A, 14B, 14C, and 14D change converter contracts to bounded
records, bounded integer floor arithmetic, proved conditional temporary
regions, exact direct keyword calls, and exact required keyword-only calls but
do not broaden this workspace contract. The workspace always
submits an explicit request and presents the resulting active identities,
diagnostics, facts, mappings, summary, trace, and generated source without
selecting or approximating conversion semantics itself.

Given the same canonical request, the workspace and direct converter API must
produce identical semantic results and generated-C bytes. Theme, geometry,
font, panel, search, selection, recent-file, and scroll state are observers;
none may enter request or artifact fingerprints. The workspace exposes no
compile, link, load, run, debug, terminal, package discovery, or source-import
discovery action.

PyQt5 remains an optional dependency. Workspace support modules must import
safely in a headless installation, while attempting to instantiate a Qt-only
widget fails clearly. The headless controller remains fully testable without
an event loop.

## Explicit bundle workspace

The navigator projects the same closed `SourceBundle` retained by Phase 14D:

- one through 64 documents, with exactly one explicit primary document;
- immutable workspace document IDs and editable canonical module IDs and
  relative logical source names;
- one source path and dirty indicator per opened or saved Python document;
- explicit add, remove, select, reorder, and make-primary operations; and
- duplicate, invalid, or over-capacity changes rejected transactionally.

Only an explicit Open action or selection from the bounded recent-file list
may read a host source file. The navigator does not scan directories, resolve
imports, inspect installed packages, or reopen recent files automatically.
Removing, replacing, or closing dirty source requires an explicit Save,
Discard, or Cancel decision.

Any semantic document, identity, primary, or ordering change advances the
workspace request generation, cancels an active conversion, and makes an older
result stale. A late result from an older generation is discarded and never
republished, even when subsequent edits restore byte-identical source and the
same bundle fingerprint.

## Editors and quantum visibility rail

Python source and generated C use dedicated fixed-width code editors. The
Python editor is writable; generated C is always read-only. Both provide line
numbers, current-line treatment, matching-bracket feedback, and deterministic
Python or C syntax highlighting. Highlighting is presentation only and never
parses, imports, evaluates, or modifies source.

The right-side **quantum visibility rail** is a compressed document map. It
shows the visible viewport plus normalized search, diagnostic, and source/C
mapping markers across the entire document. Marker roles remain distinguishable
by hue and rail treatment against the dark surface. Activating a marker moves
to its exact range; activating empty rail space scrolls proportionally. The
rail is keyboard-focusable: arrow keys traverse markers, Enter activates the
selected marker, and Page Up/Page Down scroll the editor. It mirrors scrollbar
state and performs no semantic analysis of its own.

Find and replace is an inline editor panel, not a modal dialog. It supports
literal text, case sensitivity, whole-word matching, next/previous movement,
replace current, and replace all. `Ctrl+F`, `Ctrl+H`, `F3`, `Shift+F3`, and
`Escape` provide the conventional keyboard path. Replace actions are disabled
for the generated-C editor.

## Diagnostics and inspection

Diagnostics are presented as a filterable structured list containing severity,
code, message, module, and line, with explanation and remediation detail when
published. Activating a located diagnostic selects the owning document and
navigates to its source range. Search hits, diagnostics, and available
source-to-output mappings are also projected on the quantum rail.

Conversion Summary, Decision Trace, and Telemetry use searchable trees rather
than raw editable JSON. Generated C and details remain independently
showable. Progress is delayed, inline, stage-aware, cancellable, and non-modal;
observer or rendering failure cannot alter conversion custody. Action enabled
states derive from the immutable workspace snapshot.

## Linked generated-C save

The primary Python document establishes the default linked C path by replacing
its suffix with `.c`. A user may explicitly choose a different link, which is
retained until changed. The link names a save destination only: it does not
create a second conversion artifact or affect generated text.

Save C is permitted only when all of the following hold:

1. generated C exists and its result state is publishable;
2. its recorded bundle fingerprint exactly matches the current workspace; and
3. a linked destination exists or the user explicitly chooses one.

Before freshness is evaluated or a write is attempted, visible pending module
IDs and logical source names are committed and validated as one semantic
workspace change. Python Save As similarly validates the complete candidate
bundle, including destination-derived identity, before its atomic writer is
invoked. A rejected identity or duplicate path therefore cannot modify either
the source destination or the last-known-good linked C file.

Writes use the shared atomic writer. Conversion itself never writes the linked
file. Cancellation, rejection, stale output, invalid paths, or interrupted
replacement therefore leaves any last-known-good C file intact. Linking or
saving C does not compile, link, load, or execute it.

## PyCForge visual and accessibility contract

PyCForge uses graphite-to-dark gradients with restrained cyan and violet
focus rails. Text and primary controls retain accessible contrast; hover,
focus, pressed, selected, disabled, error, warning, and success states are
visibly distinct. Icons are self-contained SVG line art—no bitmap, remote, or
embedded raster assets are permitted.

Every icon-only action has an accessible name and tooltip. Major editors,
navigators, filters, diagnostic lists, progress, and status surfaces expose
descriptive accessible names. Focus remains visible, keyboard order follows
the visual workflow, and important states are communicated with text or shape
in addition to color.

Presentation persistence uses schema version `1`, recorded at
`settings/schema_version`, and is failure-tolerant. It may retain UI
window geometry/state, splitter positions, view toggles, font size, word-wrap
choice, the last file-dialog directory, and bounded recent-file references.
Recent references are reopened only after explicit user action. Settings must
not persist unsaved Python contents, generated C, diagnostics, conversion
artifacts, helper content, or credentials. Invalid or unavailable settings fall
back to safe defaults and never prevent the converter from starting. Malformed
known values or an incompatible schema clear only recognized presentation keys;
unrelated application settings remain untouched.
