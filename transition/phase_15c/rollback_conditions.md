# Phase 15C Rollback Conditions

Status: mandatory

The immediate rollback is the authenticated Phase 15B `0.15.1` source archive
and wheel. The source archive is
`pycforge_phase_15b_v0_15_1.tar.gz`, 1,544,352 bytes, with SHA-256
`aefaebbacb12b458bcadd9aa25ac9f2678a374b51901bcc51aab3698049cd827`.
Rollback never mutates unsaved Python or overwrites last-known-good linked C.

Rollback is mandatory if the Phase 15C candidate:

- changes any converter file, semantic contract, generated-C byte, diagnostic,
  fact, RulePlan, mapping, summary, trace, telemetry, or converter fingerprint;
- weakens spawned-process isolation, one-active/one-latest scheduling, bounded
  cancellation, revision authentication, stale-result suppression, or atomic
  Save C custody;
- retains source text, generated C, diagnostics, mappings, traces, telemetry,
  or worker payloads in tab, split-pane, command-palette, or history state;
- allows more than two source panes, more than 64 bundle documents, more than
  5,000 projected bundle-search matches, more than 64 history records, or more
  than the declared structure and palette bounds;
- allows stale source structure, search, conversion, or history results to
  publish as current;
- performs source-structure or bundle-search file I/O, host discovery,
  recursive scanning, import resolution, or environment inspection;
- creates a free-form command-execution route or bypasses declared action
  enablement;
- differs from 48 action specifications, 47 static actions, 18 declared
  surfaces, 11 context surfaces, five main menus, or 55 packaged SVG icons;
- creates persistent actions outside the registry or context commands outside
  declared surfaces;
- exposes generated-C mutation;
- makes routine GUI interaction invoke conversion, whole-bundle hashing,
  recursive projection, or another unbounded operation;
- exposes compilation, linking, execution, debugging, terminal, toolchain,
  plugin, project-explorer, host-discovery, or external-command behavior;
- claims real or offscreen PyQt, visible platform, display-scaling,
  assistive-technology, clean-install, reproducible distribution, or packaging
  evidence that was not executed;
- assigns a release fingerprint or promotion state before canonical validation
  passes; or
- opens Phase 15D without separate authorization.

One rollback trigger stops promotion, fingerprint assignment, and packaging.
