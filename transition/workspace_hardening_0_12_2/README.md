# Workspace hardening 0.12.2 transition

This corrective release closes only PyCForge workspace defects discovered by
the first real-PyQt5 v0.12.1 review. It does not open Phase 13 and does not
change converter rules, accepted syntax, schemas, diagnostics, lowering,
helpers, generated-C bytes, or the source-only product boundary.

The immutable predecessor is `pycforge_phase_12_1_v0_12_1.tar.gz`, SHA-256
`5fd2231024a57c9ca736991e2ca90f645357c1d4cca69dfcf3bd53d1860d507e`.
Its canonical tree is
`aed47ffbf4e17aebccfe571d506856dc9cf497308e1769f7db7597089a873efb`.
The frozen converter subtree must remain
`4d7676a46105652efd13efb699d00e7a39a4b1bfd7ae7daad32c22702fd41b51`.

Promotion evidence includes the complete headless suite, actual offscreen PyQt5 tests,
the v0.12.2 widget smoke at normal and scaled display factors, authenticated
predecessor validation, every cumulative audit, deterministic source and wheel
builds, and isolated installed-artifact checks. Generated C remains textual
evidence only and is never compiled, linked, loaded, or executed.

Run the candidate gate from the release root:

```text
python -m unittest discover -s tests
python tools/validate_pycforge_workspace_0_12_2.py --run-tests
python tools/smoke_pycforge_workspace_0_12_2.py
```

Pass `--predecessor-archive pycforge_phase_12_1_v0_12_1.tar.gz
--require-predecessor` to authenticate immediate predecessor custody.
