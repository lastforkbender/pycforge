# Phase 15B Entry and Predecessor Authentication

Status: satisfied  
Authorized stage: Phase 15B application shell and visual system  
Opened: 2026-07-26

## Authority

Architecture Revision 3.1 and its accepted Revision 3.2 and Revision 3.3
addenda remain the roadmap authority. The user separately authorized Phase 15B
after promotion of Phase 15A.

Phase 15B is limited to:

- one declarative application-action authority;
- custom PyCForge main and context menus derived from that authority;
- professional SVG iconography and a cohesive semantic visual system;
- keyboard, mnemonic, focus, dismissal, checked, disabled, and danger states;
- logical high-DPI sizing and accessibility metadata; and
- complete removal of the retired pre-PyCForge theme vocabulary from the
  current source and distribution.

Phase 15B does not open Phase 15C or Phase 15D.

## Authenticated predecessor

Work began from the canonical Phase 15A release:

- filename: `pycforge_phase_15a_v0_15_0.tar.gz`;
- size: 1,480,105 bytes;
- SHA-256:
  `da33821ef82d948a9204af76baa5495ae2ff5df4500b12f4a67c12663cd95a06`;
- release-tree fingerprint:
  `52014b9bd92912fe25b5d2faf42a388e98e828be66a3b371277d552666cf172a`;
- converter-subtree custody SHA-256:
  `a45bc2c31b954f9856c8eab36e95f68b086d5fdd682d2cf47ba2186887743124`;
- package: `0.15.0`;
- workspace contract: `pycforge-workspace/0.3`; and
- worker protocol: `pycforge.worker-protocol/0.1`.

The predecessor archive remains the authoritative custody copy of all
pre-migration historical bytes. Phase 15B receives a new release fingerprint;
it never rewrites the authenticated predecessor artifact.

## Entry invariants

- PyCForge remains a deterministic Python-to-C source transpiler.
- The converter contract remains `0.14.3`.
- The converter subtree remains byte-identical to Phase 15A.
- Process isolation, cancellation, revision authentication, bounded
  projections, stale-result suppression, and exact Save C authority remain
  unchanged.
- Generated C remains read-only and explicit-save-only.
- The closed one-to-64-document `SourceBundle` remains the entire source
  universe.
- No compiler, linker, loader, runner, debugger, terminal, toolchain, plugin,
  project explorer, host discovery, or generated-C editing surface is allowed.

