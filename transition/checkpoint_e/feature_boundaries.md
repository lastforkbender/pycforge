# Phase 15 Workspace Feature Boundaries Frozen at Checkpoint E

Status: closed Checkpoint E decision; Phase 15 implementation not opened

## Authorized IDE-grade workspace features

The later Phase 15 workspace track may implement the following as presentation
or source-editing features over the explicit closed SourceBundle:

- multi-document tabs and split Python editor views;
- a Source Bundle navigator with explicit add, open, remove, reorder,
  make-primary, save, dirty, and linked-path state;
- undo/redo, select all, duplicate/move line, indentation, outdent, comment
  toggle, case-preserving literal find/replace, and go to line;
- code folding, whitespace display, current-line treatment, line numbers,
  bracket matching, syntax highlighting, and a bounded overview rail;
- bundle-wide literal search over already-open documents;
- an outline and breadcrumbs derived only from already-open normalized syntax;
- diagnostics/problems, mappings, conversion summary, decision trace,
  telemetry, and conversion history for the current application session;
- command palette and discoverable keyboard shortcuts over the same declared
  action registry used by menus and toolbars;
- read-only generated-C tabs, source/C navigation, copy, select, find, and
  atomic Save C;
- recoverable layout/session presentation preferences that do not persist
  unsaved source or semantic artifacts; and
- custom PyQt main and context menus using professional SVG icons, gradients,
  text labels, shortcuts, and complete keyboard/accessibility behavior.

Outline and breadcrumb data are observers. They do not become converter facts,
RulePlans, eligibility evidence, imports, or host discovery.

## Forbidden product surfaces

The application must not expose:

- Run, Execute, Build, Compile, Assemble, Link, Load, Deploy, Test, Debug, or
  Profile commands;
- terminal, shell, console, REPL, debugger, breakpoint, watch-expression,
  process, task, or build-output panes;
- compiler, linker, SDK, make, CMake, Meson, package manager, interpreter,
  virtual-environment, or toolchain selection/discovery;
- plugins, extensions, arbitrary user scripts, macros, command hooks, or
  extension marketplaces;
- project explorer, folder tree, workspace scan, recursive search outside the
  explicit bundle, automatic import resolution, installed-package inspection,
  or environment indexing;
- editing, formatting, refactoring, or applying patches to generated C; or
- automatic execution or saving as a side effect of conversion.

Labels, disabled placeholders, hidden actions, command-palette entries, context
menu entries, settings, telemetry fields, and documentation are all part of
this prohibition.

## Deferred pending separate specification

The following are not opened merely by calling the application IDE-grade:

- language-server integration;
- semantic completion, rename, refactoring, quick-fix source mutation, or
  formatter integration;
- source-control hosting, issue tracking, remote files, collaborative editing,
  or cloud synchronization;
- arbitrary project configuration or directory-based workspaces; and
- a plugin or extension API.

They require independent privacy, determinism, host-discovery, responsiveness,
failure, and semantic-boundary decisions.

## Generated-C custody

Generated C is always read-only. Copy, search, navigation, reveal/hide, and
explicit atomic save are authorized. Undo, redo, paste, cut, replace, format,
code action, quick fix, and direct document modification are unavailable in
that surface.

The last-known-good generated C may remain visible after a source edit, failed
conversion, cancellation, worker crash, or rejection, but it is visibly stale
and cannot be saved as current.

## Menu boundary

The main menu and every context menu derive from the authorized action
registry. Context determines availability; it cannot introduce an action that
does not exist in the declared boundary. Generated-C menus omit mutating
actions. Menu styling never replaces labels with ambiguous icons and never
suppresses native focus, dismissal, mnemonic, assistive, or shortcut behavior.

## Naming custody

New user-facing and active internal architecture records call the application
PyCForge. Current module paths, specifications, tests, and artifacts use that
identity exclusively. Original pre-migration bytes remain authoritative in the
authenticated Phase 15A archive.
