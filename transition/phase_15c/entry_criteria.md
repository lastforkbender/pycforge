# Phase 15C Entry and Predecessor Authentication

Status: satisfied  
Authorized stage: Phase 15C IDE-grade transpiler workspace  
Opened: 2026-07-26

## Authority

Architecture Revision 3.1 and its accepted Revision 3.2 and Revision 3.3
addenda remain the roadmap authority. The user separately authorized Phase 15C
after the promoted and sealed Phase 15B milestone.

Phase 15C is limited to bounded authoring, navigation, search, action discovery,
and inspection over the explicit closed `SourceBundle`. It may complete:

- multi-document Python tabs and at most two synchronized source panes;
- bounded, undoable Python source-editing commands;
- go-to-line, whitespace display, folding, outline, and breadcrumbs;
- literal search across already-open bundle documents;
- a command palette over the declared action registry;
- payload-free current-session transpilation history;
- diagnostics, mappings, summary, trace, telemetry, and read-only generated-C
  inspection; and
- the Phase 15C action, context-menu, icon, and workspace-style additions.

Phase 15C does not open Phase 15D distribution or visible-platform gates.

## Authenticated predecessor

Work began from the canonical Phase 15B release:

- filename: `pycforge_phase_15b_v0_15_1.tar.gz`;
- archive root: `pycforge_phase_15b_v0_15_1`;
- size: 1,544,352 bytes;
- SHA-256:
  `aefaebbacb12b458bcadd9aa25ac9f2678a374b51901bcc51aab3698049cd827`;
- release-tree fingerprint:
  `d90225e2e75842dfd2ca581c08b844a3e640988e385cfc70a68dba8f27db9b36`;
- converter-subtree custody SHA-256:
  `a45bc2c31b954f9856c8eab36e95f68b086d5fdd682d2cf47ba2186887743124`;
- package: `0.15.1`;
- workspace contract: `pycforge-workspace/0.4`;
- action registry: `pycforge.action-registry/0.1`;
- visual system: `pycforge.visual-system/0.1`;
- worker protocol: `pycforge.worker-protocol/0.1`; and
- presentation settings: schema `1`.

The predecessor archive remains the authoritative rollback and custody copy.
Phase 15C receives a distinct release fingerprint only after canonical
validation; it never rewrites the authenticated predecessor artifact.

## Entry invariants

- PyCForge remains a deterministic Python-to-C source transpiler.
- The converter contract remains `0.14.3`.
- The 92-file converter subtree remains byte-identical to Phase 15B.
- Process isolation, one-active/one-latest scheduling, bounded cancellation,
  revision authentication, stale-result suppression, and exact Save C
  authority remain unchanged.
- Generated C remains read-only and explicit-save-only.
- The one-to-64-document `SourceBundle` remains the entire source universe.
- Source structure and bundle search observe already-open source only.
- Routine GUI interaction cannot invoke conversion, scan the host, or perform
  unbounded work.
- No compiler, linker, loader, runner, debugger, terminal, toolchain, plugin,
  project explorer, host discovery, or generated-C editing surface is allowed.

## Evidence boundary at entry

Entry authentication does not prove the Phase 15C candidate. Real,
offscreen-widget, visible Windows 11, visible Linux, display-scaling, and
assistive-technology runs have not yet been performed for this candidate.
Canonical Phase 15C validation and release fingerprint assignment remain
mandatory before promotion.
