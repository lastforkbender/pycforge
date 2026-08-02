# Python-to-C Converter Architecture — Revision 3.3 Workspace Addendum

Status: accepted by Hardening Checkpoint E  
Base authority: Revision 3.1  
Revision 3.1 SHA-256:
`d05963984105466ae7df4c0e25941865fb0e55181059e3c95e3fde42556fd8e3`  
Revision 3.2 SHA-256:
`93b228528a10895fdbdce7b6934d422e7eddd1a79b409bdbc15ea6677e5ab8c6`  
Normative workspace-quality addendum SHA-256:
`cd71d6678e926878129e62a0838e240f7f20f61f078f41831b32e20b7bae31cd`

This addendum supplements, and does not rewrite, Architecture Revision 3.1 or
its Revision 3.2 addendum. It records the workspace direction accepted during
the roadmap's post-Phase-14 Hardening Checkpoint E.

## Product correction

The front-facing desktop application and workspace identity is **PyCForge**.
No alternate theme-derived product, subsystem, component, workspace, mode,
schema, window, menu, or settings name is retained in the current source tree.
Original pre-migration text remains authoritative in the authenticated Phase
15A archive.

PyCForge remains a Python-to-C source transpiler. Its successful terminal
artifact is deterministic C11 source. The product does not compile, assemble,
link, load, execute, test, debug, profile, benchmark, or deploy generated C and
does not expose a terminal, toolchain, or build system.

## Checkpoint E responsibility

Checkpoint E:

- freezes the supported Python subset at sealed Phase 14D;
- performs the full-subset architecture review;
- runs deterministic full-supported-subset fuzz and metamorphic validation;
- reconciles documentation with the 69-entry semantic feature matrix;
- records current workspace performance and architecture debt;
- fixes active PyCForge identity without rewriting historical custody; and
- establishes measurable Phase 15 workspace and distribution gates.

Checkpoint E does not open Phase 14E or Phase 15. It does not claim completion
of the future visual, responsiveness, accessibility, or platform work.

## Phase 15 staged delivery

When separately authorized, Phase 15 shall be implemented as bounded,
independently reviewable stages:

1. **Phase 15A — responsiveness and isolation:** a process-isolated converter
   supervisor, one-active/one-latest-pending scheduling, bounded cooperative and
   hard cancellation, revision/index services, and no-freeze maximum-input
   evidence.
2. **Phase 15B — application shell and visual system:** one action registry,
   custom gradient/icon main and context menus, cohesive PyCForge graphics,
   keyboard behavior, high-DPI rendering, and accessibility.
3. **Phase 15C — IDE-grade transpiler workspace:** bounded source-authoring,
   navigation, search, diagnostics, mappings, trace, telemetry, and virtualized
   read-only generated-C inspection over the explicit closed `SourceBundle`.
4. **Phase 15D — distribution and platform gate:** reproducible headless and
   desktop artifacts, dependency/license custody, schema compatibility,
   clean-install/first-use tests, and visible Windows 11 plus Linux PyQt
   evidence.

Each stage preserves exact direct-converter equivalence. No stage may add run,
build, debug, terminal, toolchain, plugin, host-discovery, project-explorer, or
generated-C editing behavior.

## Normative detail

The complete architecture, resource envelope, latency budgets, worker
supervision, projection rules, visual/menu requirements, accessibility gates,
and platform evidence are normative in
[`pycforge_workspace_quality_addendum.md`](pycforge_workspace_quality_addendum.md)
and the Checkpoint E transition packet.
