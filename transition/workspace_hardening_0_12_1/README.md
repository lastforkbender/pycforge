# Workspace hardening 0.12.1 transition

This transition records the GUI-only PyCForge hardening release layered over
the sealed PyCForge 0.12.0 / Phase 12 converter. It does not open Phase 13 and
does not revise any converter schema, configuration identity, diagnostic,
RulePlan, helper, C IR node, lowering rule, or generated-C contract.

The immutable predecessor identities are recorded in `manifest.json`. The
release validator authenticates the complete `pycforge/converter` subtree
against the sealed 0.12.0 archive and checks fixed singleton and module-bundle
generated-C fixtures. The existing `transition/phase_12` and
`evidence/phase_12` records remain sealed and are not restated here.

The new contract is `pycforge-workspace/0.1`, specified by
`specifications/pycforge_workspace_legacy_0_1.md`. Its scope is bounded bundle editing,
professional read/write source presentation, structured inspection,
presentation-only persistence, and safe atomic Python/C saves. It adds no
compilation, linking, loading, execution, debugging, terminal, toolchain, or
host import-discovery surface.

The manifest intentionally contains no self-referential hash of the promoted
0.12.1 tree. Final archive custody is recorded externally with the release
artifact and in `evidence/pycforge_workspace_0_12_1/release_report.json`; this does not
rewrite the transition's predecessor facts.

Run the deterministic gate from the release root:

```text
python tools/validate_pycforge_workspace_0_12_1.py --run-tests
```

Pass `--predecessor-archive` or `--require-predecessor` when authentication of
the sealed Phase 12 source archive is required by the release environment.
