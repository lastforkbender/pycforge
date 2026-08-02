# Checkpoint E Breadth and Change Budgets

Status: opening budget; implementation must remain independently reviewable

## Documentation-only opening budget

This opening may add only:

- the workspace-quality addendum;
- `transition/checkpoint_e` opening decisions; and
- `evidence/checkpoint_e` initial reports.

It modifies zero Python files, zero tests, zero tools, zero schemas, zero
existing specifications, zero manifests, zero historical transition files,
zero release records, and zero package/version files.

## Phase 15 implementation boundary

A separately authorized Phase 15 implementation candidate may change the active desktop
application, its UI-specific headless controller/adapters, UI assets, workspace
tests/tools, and current documentation/evidence. It may add a bounded worker
supervisor and IPC adapter that call the unchanged public converter facade.

It may not change:

- `pycforge/converter/**` semantics or active converter identities;
- diagnostic ownership or meanings;
- Python IR, facts, RulePlans, C IR, renderer, helper, policy, request, result,
  trace, telemetry, or serialization contracts;
- generated-C bytes or output fingerprints for any accepted request;
- sealed Phase 0–14D transition/evidence/history files; or
- the no-toolchain boundary.

If the unchanged converter cannot support the worker protocol without a
converter-subtree edit, implementation pauses for a separate architecture
decision rather than spending semantic change budget implicitly.

## Structural budget

The Phase 15 application must be decomposed instead of enlarging the existing
monoliths:

- no new active Python production module exceeds 600 physical lines;
- no active workspace production module exceeds 1,000 physical lines at the
  candidate gate;
- presentation, action registry, worker supervision, revision/index services,
  editors, virtualized models, menus, and platform adaptation have explicit
  ownership boundaries;
- the complete Checkpoint E candidate changes no more than 25 production
  modules and adds no more than 7,000 net production lines, excluding tests,
  documentation, and hand-authored SVG assets; and
- any exception is documented and approved before code is written.

The line budget is a ceiling, not a target. Moving code without improving
ownership does not satisfy decomposition.

## Dependency and asset budget

- PyQt5 remains the declared optional GUI dependency during Phase 15 unless a
  separately approved compatibility decision changes it.
- No Electron, browser runtime, embedded web server, C compiler, debugger,
  terminal emulator, language server, plugin host, or native binary dependency
  is authorized.
- New icons are hand-authored self-contained SVG with no remote reference,
  script, font dependency, bitmap payload, or embedded executable content.
- Fonts and themes use platform/Qt resources or explicitly packaged,
  license-audited assets only.

## Evidence budget

Every implementation slice must add:

- headless unit tests for its state and failure contracts;
- real PyQt widget behavior tests;
- max-envelope latency and event-loop measurements where it affects a hot path;
- keyboard/accessibility assertions for every new action or surface;
- stale-result and generated-C immutability checks;
- process cleanup and failure-injection coverage for worker changes; and
- visible platform evidence before any platform support claim.

No source-string presence test may be the sole evidence for a visual,
accessibility, responsiveness, or process-isolation requirement.

## Slice discipline

Implementation is promoted in bounded vertical slices:

1. PyCForge identity and shared action/menu system;
2. process-isolated worker supervision and latest-wins custody;
3. revision/index services and maximum-input editor/result responsiveness;
4. virtualized inspectors, bundle search, and safe IDE editing features; and
5. accessibility, visible platform, deterministic packaging, and final
   hardening.

These slices belong to Phase 15 and require separate authorization. Each slice
must leave the application usable and preserve the full predecessor test suite.
A partially styled but inaccessible menu, partially isolated worker, or
half-virtualized result path is not a promotable endpoint.
