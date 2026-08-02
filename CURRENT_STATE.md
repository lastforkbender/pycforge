# PyCForge Current Contract Index

Current release: `0.15.2` / Phase 15C IDE-Grade Transpiler Workspace  
Release state: promoted, sealed, and release-custody validated  
Converter boundary: sealed Phase 14D contracts at `0.14.3`  
Workspace boundary: `pycforge-workspace/0.5`  
Worker protocol: `pycforge.worker-protocol/0.1`  
Action registry: `pycforge.action-registry/0.2`  
Visual system: `pycforge.visual-system/0.2`  
Presentation settings: schema `1`  
Immediate rollback: authenticated Phase 15B `0.15.1` release  
Roadmap authority: Revision 3.1 plus Revision 3.2 and Revision 3.3 addenda

PyCForge is a deterministic Python-to-C source transpiler. Its terminal
artifact is independently validated C11 source. It never imports or executes
user Python and exposes no compiler, assembler, linker, loader, runner,
debugger, terminal, toolchain, plugin, project explorer, external-command
surface, or generated-C editor. Generated C remains read-only and
explicit-save-only.

Phase 15C is a non-semantic workspace release. The complete converter
subtree, supported Python subset, diagnostics, facts, RulePlans, summaries,
traces, telemetry, mappings, result serialization, generated-C bytes, and
converter fingerprints remain governed by `0.14.3`.

## Promotion and release custody

The Phase 15C feature scope is implemented, validated, promoted, and sealed.
Its canonical validation report is assigned and promotion eligible. The
release fingerprint is assigned, and the Phase 15C source archive, pure-Python
wheel, handoff, package report, validation report, and checksum records are
built and validated under the milestone release workflow.

The public distribution amendment makes PyQt5 a mandatory runtime dependency,
adds standard wheel and source-distribution checks, and requires a clean
ordinary installation to import and construct the real offscreen Qt workspace.
No `workspace` extra is needed or provided. This custody statement still does
not claim the wider Phase 15D visible-platform gate: physical Windows 11/Linux
rendering, display scaling, and assistive-technology certification remain
unopened.

No validation or release step invokes a C toolchain or compiles, links, loads,
or executes generated C.

## Active identities

| Surface | Active identity | Authority |
|---|---|---|
| package | `0.15.2` | `pyproject.toml` |
| converter contract | `0.14.3` | `pycforge/converter/contracts/versions.py` |
| workspace | `pycforge-workspace/0.5` | `specifications/pycforge_workspace.md` |
| worker IPC | `pycforge.worker-protocol/0.1` | `pycforge/ide/worker_protocol.py` |
| action registry | `pycforge.action-registry/0.2` | `pycforge/ide/action_contract.py` |
| visual system | `pycforge.visual-system/0.2` | `pycforge/ide/visual_tokens.py` |
| settings | schema `1` | `pycforge/ide/qt_contract.py` |
| source bundle | `source-bundle/0.2` | `specifications/source_bundle.md` |
| Python grammar IR | `python-ir/0.4` | `specifications/python_ir_schema.md` |
| conversion plan | `conversion-plan/0.14.3` | `specifications/analysis_and_planning.md` |
| C IR | `c-ir/0.14.3` | `specifications/c_ir_schema.md` |
| generated artifact | `generated-c/0.14.3` | `specifications/result_and_fingerprints.md` |
| decision trace | `pycforge.decision-trace/0.14.3` | `schemas/decision_trace.schema.json` |
| conversion summary | `pycforge.conversion-summary/0.14.3` | `specifications/result_and_fingerprints.md` |
| result serialization | `0.5` | `pycforge/converter/contracts/versions.py` |
| target/semantics | `c11-portable-fixed-v1` / `strict-source-v1` | active converter specifications |

## Authenticated rollback

Phase 15C began from the promoted and sealed Phase 15B release:

- source archive: `pycforge_phase_15b_v0_15_1.tar.gz`;
- archive root: `pycforge_phase_15b_v0_15_1`;
- size: 1,544,352 bytes;
- SHA-256:
  `aefaebbacb12b458bcadd9aa25ac9f2678a374b51901bcc51aab3698049cd827`;
- release-tree fingerprint:
  `d90225e2e75842dfd2ca581c08b844a3e640988e385cfc70a68dba8f27db9b36`;
- converter-subtree SHA-256:
  `a45bc2c31b954f9856c8eab36e95f68b086d5fdd682d2cf47ba2186887743124`.

That authenticated archive and its `0.15.1` wheel are the immediate rollback.

## Phase 15C implementation

### Documents, panes, and authoring

Workspace session state stores bounded document identifiers only. The Python
source workspace has document tabs and at most two synchronized panes. It does
not duplicate semantic source authority or admit an unbounded editor grid.

Python authoring includes undoable duplicate, move, indent, outdent, and
comment-toggle operations. Go-to-line uses document blocks instead of copying
complete source. Whitespace display and folding are presentation state.
Existing line numbers, current-line treatment, syntax, bracket, overview,
undo/redo, select, and literal find/replace foundations remain intact.

Generated C is immutable. Its exact context allowlist is Copy, Select All, and
Find. Save C requires a complete current result whose authenticated bundle
fingerprint matches the committed workspace.

### Structure, navigation, and search

Outline and breadcrumb data derives only from immutable already-open normalized
Python source. Analysis is cancellable and latest-wins, and it is bounded to:

- 64 documents;
- 4,096 outline symbols;
- depth 64;
- 256 characters per symbol name; and
- 256 KiB source text per projection.

Invalid syntax is inert and cannot retire valid structure for another open
document.

Find in Source Bundle searches immutable path-free snapshots of one to 64
already-open documents. It performs no file I/O, project discovery, import
resolution, or host scan. Results carry Python and UTF-16 positions, bounded
previews, deterministic bundle/source order, and a global 5,000-match
projection cap.

### Action discovery and observers

The command palette searches enabled, visible static registry actions. It owns
no handlers, provides no free-form command path, caps queries at 256
characters, and projects at most 50 results.

Session transpilation history stores at most 64 immutable payload-free terminal
records. It does not retain source, generated C, diagnostics, mappings, facts,
summaries, traces, telemetry, or worker envelopes.

Diagnostics, mappings, Conversion Summary, Decision Trace, Telemetry, outline,
bundle-search results, and history use bounded observer panels. Generated C
remains a read-only incremental inspection surface.

### Action and visual inventories

The import-safe action registry contains:

- 48 action specifications;
- 47 static actions;
- one bounded recent-file dynamic template;
- 18 declared surfaces;
- five persistent main menus; and
- eleven context surfaces.

The main menus are File, Edit, View, Navigate, and Transpile. Persistent
`QAction` construction remains singly owned by `pycforge/ide/qt_actions.py`.

The visual catalogue contains 55 safe self-contained SVG icons. Phase 15C
extends the shared semantic stylesheet to document tabs, split panes,
breadcrumbs, outline, bundle search, history, and the command palette.

## Real offscreen Qt evidence

Phase 15C records current-release runtime evidence, not inherited historical
evidence:

- Python `3.12.13`;
- PyQt `5.15.11`;
- Qt build `5.15.14` and runtime `5.15.19`;
- QPA platform `offscreen`;
- exactly one real `QApplication`;
- 18 focused workspace cases with zero failures, errors, or skips;
- a 250,113-character source fixture;
- window construction in 0.054 seconds, below the 8-second bound;
- first event-loop turn in 0.0103 seconds, below the 1-second bound;
- a 0.01-second timer producing 110 ticks during 1.201 seconds of isolated
  transpilation, below the 30-second bound;
- large-file mode active with the syntax highlighter detached;
- shared editor-buffer authority preserved; and
- zero new PyCForge threads after close and zero worker leaks.

A small end-to-end workspace conversion completed in 0.408 seconds as
supporting evidence. The 18-case widget record is the canonical Phase 15C
runtime evidence.

These checks use real PyQt widgets on the offscreen QPA backend. They do not
constitute visible desktop, physical-screen, display-scaling, or
assistive-technology evidence.

## Preserved responsiveness and safety

Phase 15A process isolation and Phase 15B command/visual custody remain binding:

- conversion runs in a spawned child process;
- exactly one active and one replaceable latest pending request is admitted;
- cooperative cancellation has bounded hard-termination fallback;
- exact generation, revision, bundle, request, and transport guards control
  publication;
- stale, failed, canceled, partial, malformed, oversized, or superseded work
  cannot publish or save C;
- file I/O, hashing, revision/index construction, literal search,
  source-structure analysis, and guarded atomic writes remain outside the GUI
  thread; and
- large-file projections and generated-C population remain bounded or
  incremental.

Routine tab, pane, palette, history, go-to-line, and observer updates do not
invoke the transpiler, scan the host, hash the complete bundle, or recursively
build unbounded view state.

The one-to-64-document `SourceBundle` remains the entire source universe.
Python is the only editable code surface.

## Checkpoint E debt disposition

`CE-IDE-WORKSPACE-COMPLETENESS` is retired for the authorized Phase 15C scope.
Every bounded authoring, navigation, action-discovery, observer, and immutable
generated-C inspection family in the Checkpoint E boundary has an explicit
implementation, fail-closed contract, and supporting real offscreen runtime
evidence.

The separate visible-platform and Phase 15D distribution debt remains open.
Retiring the Phase 15C completeness item does not claim the complete Phase 15
workspace.

## Roadmap boundary

Phase 15C adds no project explorer, recursive host scan, language server,
formatter, semantic completion, refactoring engine, quick-fix mutation,
source-control hosting, remote-file system, collaboration, cloud
synchronization, arbitrary project configuration, plugin system, macro,
external command, build/run/debug action, terminal, toolchain integration, or
generated-C editing.

Phase 15D, the wider distribution and real visible Windows 11/Linux PyQt gate,
remains unopened.

## Supporting gates

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

Detailed Phase 15C scope and evidence are recorded under
`transition/phase_15c` and `evidence/phase_15c`.
