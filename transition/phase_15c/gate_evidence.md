# Phase 15C Gate Evidence

Status: promotion gate satisfied; Phase 15C promoted and sealed  
Release milestone: PyCForge `0.15.2`  
Workspace contract: `pycforge-workspace/0.5`  
Converter contract: `0.14.3`  
Worker protocol: `pycforge.worker-protocol/0.1`  
Action registry: `pycforge.action-registry/0.2`  
Visual system: `pycforge.visual-system/0.2`  
Presentation settings: schema `1`

## Scope of this record

Phase 15C is the bounded IDE-grade authoring, navigation, search, action
discovery, and inspection milestone. Evidence establishes headless contracts,
static Qt integration, current-release real offscreen widget behavior,
semantic preservation, release custody, and the canonical Phase 15C promotion
gate. The validation report and release fingerprint are assigned, and the
milestone is promoted and sealed.

The offscreen run is real `QApplication` and widget evidence. It is not visible
Windows 11, visible Linux, physical display-scaling, or assistive-technology
evidence.

## Predecessor custody

Phase 15C began from the authenticated Phase 15B release:

- source archive: `pycforge_phase_15b_v0_15_1.tar.gz`;
- archive root: `pycforge_phase_15b_v0_15_1`;
- source archive size: 1,544,352 bytes;
- source archive SHA-256:
  `aefaebbacb12b458bcadd9aa25ac9f2678a374b51901bcc51aab3698049cd827`;
- release-tree fingerprint:
  `d90225e2e75842dfd2ca581c08b844a3e640988e385cfc70a68dba8f27db9b36`;
- converter-subtree SHA-256:
  `a45bc2c31b954f9856c8eab36e95f68b086d5fdd682d2cf47ba2186887743124`;
- package: `0.15.1`;
- workspace: `pycforge-workspace/0.4`;
- action registry: `pycforge.action-registry/0.1`; and
- visual system: `pycforge.visual-system/0.1`.

## Identity evidence

Static identity checks establish the Phase 15C successor values:

- package `0.15.2`;
- workspace `pycforge-workspace/0.5`;
- action registry `pycforge.action-registry/0.2`;
- visual system `pycforge.visual-system/0.2`;
- unchanged converter `0.14.3`;
- unchanged worker protocol `pycforge.worker-protocol/0.1`; and
- unchanged presentation settings schema `1`.

Historical Phase 15B validators retain their literal predecessor identities and
reject the successor cleanly. The 92-file converter subtree retains the exact
authenticated predecessor digest.

## Authoring and session evidence

Headless contracts cover identifier-only tab state, a maximum of two editor
panes, deterministic reconciliation when documents close, and exact
controller-owned document order.

Source-editing evidence covers line duplication, movement, indentation,
outdentation, comment toggle, go-to-line, selection clamping, LF/CRLF
preservation, and immutable operation results. Qt source contracts require
source mutation to enter the active Python editor's undo stack and reject
disabled or read-only targets.

Whitespace, folding, current-line, line-number, bracket, syntax, and bounded
overview behavior remain presentation projections. Generated C stays an
immutable inspection surface.

## Navigation and search evidence

Normalized outline records are parent-linked and breadcrumb-ready. Structure
analysis is bounded to 64 documents, 4,096 symbols, depth 64, 256-character
names, and 256 KiB source text per projection. Invalid syntax is inert.
Cancellable service publication is latest-generation and workspace-key
authenticated.

Bundle search accepts one to 64 immutable, path-free, already-open documents.
It performs literal ordered matching, returns explicit Python and UTF-16
positions, caps previews at 512 characters, and stops after the first omitted
match beyond the global 5,000-result cap. Search service callbacks suppress
stale generations and survive observer failure.

## Action-discovery and history evidence

The command palette projects enabled, visible static actions only, caps one
projection at 50 results, caps its query at 256 characters, and retains no
handler or arbitrary command text.

Session transpilation history is capped at 64 immutable records. It records only
accepted current terminal outcomes and carries no source, generated C,
diagnostics, mappings, facts, summaries, traces, telemetry, or worker envelope.

## Action and visual evidence

The import-safe registry contains 48 action specifications: 47 static actions
and one bounded recent-file dynamic template. Eighteen declared surfaces
contain five persistent main menus, one bounded submenu, one toolbar, and
eleven contexts. File, Edit, View, Navigate, and Transpile are the main menus.

The generated-C context is exactly Copy, Select All, and Find. Persistent
`QAction` construction remains singly owned by `qt_actions.py`.

The vector catalogue contains 55 self-contained SVG assets. Static checks
require logical view boxes, token colors, no raster payloads, no external or
embedded references, no scripts, no text glyphs, and no fixed physical
dimensions. Phase 15C styling covers tabs, split panes, breadcrumbs, outline,
bundle search, history, and the command palette.

## Responsiveness and isolation evidence

Phase 15A process isolation remains binding. Conversion stays in a spawned
child process under one-active/one-latest scheduling, byte-only bounded
transport, cooperative cancellation, bounded termination, immutable revision
authentication, and stale-result suppression.

Phase 15C services perform no host scan or conversion. Bundle search and source
structure analysis are cancellable, latest-wins background services. Routine
go-to-line uses document blocks instead of complete-source copies. Tab, pane,
palette, and history state have absolute bounds.

## Real offscreen Qt evidence

The promoted Phase 15C release was exercised with:

- Python `3.12.13`;
- PyQt `5.15.11`;
- Qt build `5.15.14` and runtime `5.15.19`;
- the `offscreen` QPA backend;
- one real `QApplication`;
- 18 focused workspace cases with zero failures, errors, or skips; and
- zero new PyCForge threads after close and zero worker leaks.

The large-source fixture contains 250,113 characters. Window construction took
0.054 seconds against an 8-second bound. The first event-loop turn took 0.0103
seconds against a 1-second bound. A 0.01-second timer delivered 110 ticks during
1.201 seconds of isolated transpilation, below the 30-second bound.

Large-file mode was active, its syntax highlighter was detached, and the shared
editor buffer remained authoritative. A small end-to-end workspace conversion
completed in 0.408 seconds as supporting evidence. The 18-case widget record is
the canonical Phase 15C runtime evidence.

## Workspace-completeness disposition

`CE-IDE-WORKSPACE-COMPLETENESS` is retired for the authorized Phase 15C scope:
all bounded authoring, navigation, action-discovery, observer, and generated-C
inspection families in the Checkpoint E boundary now have explicit
implementations and fail-closed contracts.

The separate visible-platform and wider distribution obligations are not
retired. Phase 15D remains unopened and retains visible Windows 11/Linux,
physical display-scaling, assistive-technology, dependency/license, and broad
clean-install/first-use gates.

## Validation and promotion boundary

The canonical `evidence/phase_15c/validation_report.json` authenticates the
exact validation subject and records Phase 15C promotion eligibility. The
assigned `transition/phase_15c/release_fingerprint.json` authenticates the
sealed release tree.

The Phase 15C milestone source archive, pure-Python wheel, handoff, package
report, validation report, and checksum records are built and validated. This
release custody does not claim the Phase 15D visible-platform and broader
distribution gate.

Supporting test families are:

```text
python -m unittest tests.test_phase12_2_qt
python -m unittest tests.test_phase15c_action_contract
python -m unittest tests.test_phase15c_command_palette
python -m unittest tests.test_phase15c_source_editing
python -m unittest tests.test_phase15c_source_structure
python -m unittest tests.test_phase15c_workspace_search
python -m unittest tests.test_phase15c_workspace_session
python -m unittest tests.test_phase15c_session_history
python -m unittest tests.test_phase15c_visual_system
python -m unittest tests.test_phase15c_qt_command_contract
python -m unittest tests.test_phase15c_qt_panels_contract
python -m unittest tests.test_phase15c_qt_position_reverse
python -m unittest tests.test_phase15c_qt_workspace_integration
python -m unittest tests.test_phase15c_release_contract
python -m unittest tests.test_validate_phase15c
python -m unittest tests.test_phase15c_release_packaging
python tools/validate_phase15c.py --mode promotion
```

No promotion or release step invokes a C toolchain or executes generated C.
