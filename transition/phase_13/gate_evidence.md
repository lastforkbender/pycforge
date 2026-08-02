# Phase 13 Gate Evidence

Status: promoted on 2026-07-22; evidence sealed.

## Opening evidence

- The sealed PyCForge 0.12.2 archive, release tree, and frozen converter subtree
  matched the authenticated SHA-256 identities recorded in
  `baseline_fingerprint.json`.
- The static-record semantic boundary was approved before implementation in
  `record_representation_decisions.md`.
- Phase 13 has distinct rule, renderer, module, record-policy, fact, plan, C IR,
  generated-C, summary, and trace identities. Exact Phase 12 identities remain
  named and read-compatible.
- Result serialization stays at `0.5`: its stable outer key set does not change,
  while the changed nested conversion summary and decision trace carry their
  own `0.13` schema identities.

## Promotion evidence

- The clean reseeded candidate ran 335 discovered tests: 325 passed, 10 were
  expected skips because PyQt5 is unavailable, and none failed.
- Architecture, rules, helpers, containers, modules, records, determinism, and
  Phase 9–13 transition audits passed. Record audit determinism SHA-256 is
  `d322b5c7e5f53f8daebe1210b7d06ccf6fe099768be2d0bb464d8dbd25967e00`.
- Positive and negative record fixtures close PYC3601–PYC3607 and cross-module
  PYC3610. Binding identity, read-after-construction, hidden rebinding forms,
  exact argument categories/order, companion attribution, cancellation, C IR
  const/type/provenance, and serialized-fact tampering have regressions.
- Class-free active Phase 13 generated-C bytes and output fingerprints match an
  explicit historical Phase 12 request for the same supported source.
- Two fixed-epoch wheel builds were byte-identical. The 236,052-byte wheel has
  SHA-256
  `90691b4534388e76e6bdcb83766435b3ad53f424802b0e7624af5d89bb2c1fb0`,
  contains no native binary, and passed ZIP/RECORD/metadata inspection.
- The wheel installed without dependencies into a fresh virtual environment.
  Installed SourceBundle record conversion, installed `audit records`, and an
  installed workspace linked-C atomic save passed.
- Two normalized full source-archive builds were byte-identical. Their SHA-256
  is recorded externally because an archive cannot contain its own digest.
- The authenticated release-tree value is recorded in
  `release_fingerprint.json`; the fingerprint file is excluded from its own
  hash domain.

## Toolchain custody

The first working candidate was abandoned after an adversarial reviewer used
the host compiler in compile-only mode on temporary C outputs. Three accepted
units compiled to temporary object files; one hand-mutated invalid C IR output
failed compilation. Nothing was linked, loaded, or executed. This activated
the declared rollback condition and is preserved in `candidate_reseed.md`.

The promoted candidate was reseeded from a newly authenticated 0.12.2
extraction. Its test, audit, validator, packaging, and installed-wheel gates
invoke no C compiler, linker, loader, or generated-code execution. PyCForge
exposes no such surface.

Windows 11 laptop testing is planned downstream user feedback after all phases,
not evidence available to this release. The portable C11 contract remains the
only target claim; no Windows-specific toolchain or execution path is opened.

Phase 14 is not started and must not open automatically after this gate.
