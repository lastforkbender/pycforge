# Phase 15C Workspace-Completeness Decision

Status: accepted for the authorized Phase 15C scope  
Distribution candidate: PyCForge `0.15.2`  
Workspace contract: `pycforge-workspace/0.5`

## Decision

Phase 15C completes the bounded IDE-grade workspace slice assigned by the
Revision 3.3 addendum and the Checkpoint E feature boundary. Completion means
that every authorized workspace family has one closed, testable implementation
without opening host discovery, external execution, or new converter
semantics.

The accepted feature families are:

1. identifier-only Python document tabs and at most two synchronized panes;
2. undoable duplicate, move, indent, outdent, and comment-toggle source
   operations plus existing undo, redo, select, and literal find/replace;
3. go-to-line, whitespace display, bounded folding, line treatment, syntax,
   bracket, line-number, and overview foundations;
4. cancellable latest-wins outline and breadcrumb projection from already-open
   normalized Python source;
5. cancellable latest-wins literal bundle search over already-open documents;
6. diagnostics, mappings, summary, decision trace, telemetry, and payload-free
   current-session transpilation history;
7. a bounded command palette over enabled, visible, declared actions;
8. immutable generated-C inspection, source/C navigation, copy, select, find,
   and exact atomic Save C;
9. bounded recoverable presentation and layout state; and
10. declared main and context surfaces with shared PyCForge vector and
    stylesheet authority.

## Bounded architecture

Tab and split state retains document identifiers only. Python source remains in
controller-owned document buffers, and two views of one document share a
bounded buffer adapter rather than duplicating semantic authority.

Source-editing helpers are deterministic, selection-aware, and line-ending
preserving. Mutation commands are widget-scoped, require an enabled writable
Python surface, and participate in the editor undo stack. Generated C has no
mutation route.

Outline and breadcrumb analysis receives immutable already-open text and
publishes only the latest matching workspace generation. Bundle search is
literal, path-free, globally capped, and ordered by bundle and source
position. Neither service reads files or discovers host state.

The command palette projects registry metadata and current action state. It
does not own handlers and cannot execute arbitrary text. History records are
immutable, payload-free, and limited to accepted current terminal results.

## Exact declarative inventory

- action registry: `pycforge.action-registry/0.2`;
- action specifications: 48;
- static actions: 47;
- bounded dynamic action templates: 1;
- total declared surfaces: 18;
- persistent main menus: 5;
- context surfaces: 11;
- visual system: `pycforge.visual-system/0.2`; and
- packaged SVG icons: 55.

The main menus are File, Edit, View, Navigate, and Transpile. The generated-C
context remains exactly Copy, Select All, and Find.

## Checkpoint E debt disposition

`CE-IDE-WORKSPACE-COMPLETENESS` is retired for the authorized Phase 15C
workspace scope. The disposition is supported by complete bounded feature
slices, headless contracts, static Qt integration checks, semantic-preservation
guards, and explicit responsiveness bounds.

This retirement does not retire or satisfy the separate real-platform debt.
Real or offscreen PyQt widget runs have not yet been performed for this
candidate. Visible Windows 11, visible Linux, display-scaling,
assistive-technology, clean-install, dependency/license, and reproducible
distribution evidence remains owned by Phase 15D.

## Semantic and product boundary

The decision changes no converter file, supported Python construct, diagnostic,
fact, RulePlan, C IR shape, helper, mapping, summary, trace, telemetry record,
serialized result, generated-C byte, or converter fingerprint.

Phase 15C adds no language server, formatter, semantic completion, refactoring,
quick-fix mutation, source-control integration, remote files, collaboration,
cloud synchronization, arbitrary project configuration, plugin API, external
command, terminal, build, run, debug, or generated-C editor.
