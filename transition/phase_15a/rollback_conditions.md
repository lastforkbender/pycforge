# Phase 15A Rollback Conditions

Status: mandatory

The immediate rollback is the authenticated sealed Checkpoint E `0.14.4`
source archive and wheel. Rollback must not rewrite historical custody, mutate
unsaved Python, or overwrite last-known-good linked C.

Rollback is mandatory if the Phase 15A candidate:

- changes any converter file, contract identity, serialized result, generated-C
  byte, diagnostic, fact, RulePlan, mapping, summary, trace, telemetry, or
  fingerprint for an otherwise identical request;
- invokes conversion in the GUI interpreter or silently falls back to an
  in-process thread;
- admits more than one active plus one latest pending conversion;
- cannot reclaim a non-cooperative worker within two seconds;
- leaves an orphan process, obsolete pending request, pipe, or incomplete
  temporary output after Cancel or close;
- publishes canceled, stale, superseded, failed, crashed, malformed, partial,
  oversized, or identity-mismatched output;
- blocks the GUI thread on revision/index work, full-file I/O or hashing,
  literal search, proportional progress work, or eager large-output projection;
- saves generated C without exact current-revision authority;
- makes generated C editable;
- presents an alternate theme-derived product or component name;
- exposes compilation, linking, execution, debugging, terminal, toolchain,
  plugin, project-explorer, host-discovery, or another forbidden surface;
- claims visible PyQt, accessibility, Windows 11, or visible Linux evidence
  that was not executed; or
- opens Phase 15B, 15C, or 15D without separate authorization.

Worker failure never triggers a weaker isolation fallback. The workspace
remains editable; last-known-good C may remain visible but is unsavable as
current. One rollback trigger stops promotion and packaging.
