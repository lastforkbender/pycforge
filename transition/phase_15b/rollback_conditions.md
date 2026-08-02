# Phase 15B Rollback Conditions

Status: mandatory

The immediate rollback is the authenticated Phase 15A `0.15.0` source archive
and wheel. Rollback never mutates unsaved Python or overwrites last-known-good
linked C.

Rollback is mandatory if the Phase 15B candidate:

- changes any converter file, semantic contract, generated-C byte, diagnostic,
  fact, RulePlan, mapping, summary, trace, telemetry, or converter fingerprint;
- weakens spawned-process isolation, cancellation, revision authentication,
  stale-result suppression, bounded projection, or atomic Save C custody;
- contains the retired-theme lexeme in any current path, source byte, package
  member name, source-archive member, wheel member, test identifier, report, or
  diagnostic;
- creates persistent application actions outside the declared registry;
- creates main or context menu commands outside declared surface layouts;
- exposes a generated-C mutation action;
- presents an icon-only menu command or an icon-only control without a tooltip
  and accessible name;
- loses native keyboard traversal, mnemonic, shortcut, focus-return, Escape
  dismissal, checked-state, or screen-edge menu behavior;
- contains an unsafe, rasterized, remotely referenced, text-bearing, or
  physically sized icon asset;
- exposes compilation, linking, execution, debugging, terminal, toolchain,
  plugin, project-explorer, host-discovery, or another forbidden capability;
- claims visible Windows 11, visible Linux, assistive-technology, or display
  scaling evidence that was not executed; or
- opens Phase 15C or Phase 15D without separate authorization.

One rollback trigger stops promotion and packaging.
