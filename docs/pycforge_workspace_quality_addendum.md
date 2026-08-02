# PyCForge Workspace Quality Addendum

Status: accepted at Checkpoint E; Phase 15A implemented in PyCForge 0.15.0  
Applies to: the optional PyQt desktop application after Checkpoint E  
Semantic authority: Architecture Revision 3.1, its Revision 3.2 addendum, and
the sealed Phase 14D contracts remain unchanged

## Product identity

The front-facing application is **PyCForge**. Its windows, menus, dialogs,
accessible names, package metadata, screenshots, and user documentation must
present that name consistently.

No alternate theme-derived product, subsystem, component, mode, workspace,
schema, or user-facing name is retained in the current source tree. Original
pre-migration files and identifiers remain authoritative in the authenticated
Phase 15A archive.

## Product role

The application is an IDE-grade workspace for a deterministic Python-to-C
source transpiler. Python is the authored source. Generated C is an immutable,
inspectable, and explicitly savable transpilation result. The application
orchestrates an exact `ConversionRequest` and presents its result; it does not
select, infer, broaden, or approximate converter semantics.

The professional workspace may provide:

- multi-document Python editing over the explicit closed `SourceBundle`;
- tabs, a bounded Source Bundle navigator, outline and breadcrumb views derived
  only from already-open source, and go-to-line or go-to-symbol navigation;
- undo/redo, indentation operations, comment toggling, code folding, bracket
  matching, whitespace display, and bundle-wide literal search;
- a command palette over declared application actions;
- diagnostics, mappings, conversion summary, decision trace, telemetry, and
  immutable generated-C inspection; and
- schema-versioned presentation preferences and recoverable session layout.

These are workspace features, not new transpiler features.

## Explicit exclusions

Checkpoint E and the bounded Phase 15 workspace track do not authorize:

- running Python or generated C;
- compiling, assembling, linking, loading, packaging, deploying, or debugging;
- a terminal, console, REPL, debugger, build system, task runner, or toolchain
  discovery/configuration surface;
- plugins, extensions, arbitrary scripts, macros, or external command hooks;
- a project/directory explorer, recursive file scan, import discovery, package
  discovery, environment discovery, or installed-module inspection;
- editing generated C; or
- LSP, formatter, refactoring, or completion behavior that consults the host,
  changes conversion eligibility, or silently edits source.

The Source Bundle navigator is not a project explorer. It shows only documents
that the user explicitly opened or added to the closed request.

## Workspace architecture

The Phase 15 quality target requires three separated responsibilities:

1. the PyQt presentation process owns widgets, commands, document interaction,
   accessibility, and lightweight view models;
2. the workspace model owns immutable revisions, dirty state, request
   generations, stale-result custody, and atomic-save eligibility; and
3. a process-isolated conversion worker owns one invocation of the unchanged
   `PythonToCConverter`.

The conversion worker must not share the GUI interpreter or event loop. Its
protocol carries a versioned, bounded request and result. The GUI accepts a
result only when both request generation and bundle fingerprint match the
current immutable workspace revision. One active request and at most one
latest-wins pending request are permitted; superseded pending work is removed
rather than accumulated.

Cancellation begins cooperatively and has a bounded hard-stop path at the
process boundary. A converter defect, non-cooperative stage, worker crash, or
worker out-of-memory condition must not freeze the GUI, block window closure,
publish partial C, replace last-known-good C, or starve a newer request.

## Responsive projection

Background conversion alone is insufficient. Installing generated C,
highlighting, computing source/C positions, creating marker selections,
projecting traces, filtering search results, hashing watched files, and
processing file-system changes must also obey the GUI-thread budgets in
`transition/checkpoint_e/performance_budgets.md`.

Large outputs and observer records use revision keys, cached line/UTF-16
indexes, bounded viewport projections, virtualized models, and lazy detail
construction. Full-document `toPlainText()` copies, whole-bundle fingerprints,
whole-file hashes, recursive tree construction, or one-selection-per-marker
rebuilds are not permitted on each keystroke, cursor move, scroll event, or
progress update.

## Visual system and menus

PyCForge receives a cohesive next-generation visual system built from custom,
professional SVG iconography and restrained graphite, blue, violet, and warm
accent gradients. Decoration must remain subordinate to code readability and
state clarity.

The main menu and context menus are custom PyQt surfaces using the same
gradient, icon, typography, spacing, focus, separator, shortcut, checked,
danger, disabled, hover, and pressed language. Context menus are required for
the Python editor, generated-C inspector, document tabs/Source Bundle
navigator, diagnostics, mappings, and inspector trees. Menu implementation must
retain keyboard traversal, mnemonics, shortcut text, screen-edge placement,
high-DPI rendering, assistive-technology names, and native dismissal/focus
semantics. No menu action may expose an excluded product capability.

## Accessibility and platform evidence

Quality is proved with a real `QApplication` and real PyQt widgets. Source-code
string searches and import-only tests are supporting evidence, not release
evidence. Offscreen tests remain useful but cannot replace visible platform
tests.

Every control has a stable accessible name and, where useful, a description.
Focus is always visible; state is never conveyed by color alone; keyboard order
matches the visual workflow; icon-only actions have tooltips; reduced-motion
and high-contrast behavior remain usable; and menus, editors, panes, dialogs,
toasts, progress, and error recovery are keyboard complete.

Windows 11 is a mandatory real-platform gate. At least one supported Linux
desktop Qt platform is also exercised visibly. Any additional platform is
claimed only after the same gate passes there. Display scaling, multiple
screen geometries, and both keyboard-only and assistive-technology inspection
are part of the evidence.

## Maximum-input quality gate

The active resource-policy ceilings define the stress envelope:

- 1,000,000 UTF-8 source bytes;
- 100,000 source lines;
- 250,000 tokens; and
- 100,000 AST nodes.

Separate fixtures approach each independent ceiling, plus a combined valid
fixture within all ceilings. Cleanly rejected over-limit inputs are also
tested. The application must remain interactive while such requests convert,
cancel, fail, complete, become stale, or are replaced.

## Staged promotion rule

Checkpoint E accepted and froze this architecture and its evidence obligations
without changing the sealed 0.14.3 converter policy identities, generated-C
bytes, fingerprints, diagnostic meanings, or historical files.

Phase 15A promotes only the responsiveness-and-isolation slice: spawned worker
supervision, bounded latest-wins scheduling, cooperative and hard cancellation,
immutable revision/index services, bounded background file and search work, and
headless maximum-envelope/failure evidence. It makes no visible PyQt,
accessibility, Windows 11, or visible Linux claim.

Phase 15B owns the visual/action/menu slice, Phase 15C the broader IDE-grade
workspace slice, and Phase 15D reproducible distribution plus the mandatory
visible Windows 11 and Linux platform gate. The complete Phase 15 workspace
claim exists only after every independently authorized slice passes.
