# Phase 15A Entry and Predecessor Authentication

Status: satisfied  
Authorized stage: Phase 15A responsiveness and isolation only  
Opened: 2026-07-26

## Authority

Architecture Revision 3.1 remains the roadmap authority. Revision 3.2 and the
accepted Revision 3.3 Workspace Addendum supplement it. Phase 15A implements
only the first bounded stage named by Revision 3.3:

- process-isolated converter supervision;
- one active and one latest replaceable pending request;
- bounded cooperative and hard cancellation;
- revision/index services; and
- maximum-envelope no-freeze evidence.

The authorization does not open Phase 15B, 15C, or 15D.

## Authenticated predecessor

Work began from the sealed Checkpoint E source archive:

- filename: `pycforge_checkpoint_e_v0_14_4.tar.gz`;
- root: `pycforge_checkpoint_e_v0_14_4`;
- size: 1,398,824 bytes;
- SHA-256:
  `b609c761748a4caf96a42df7ba99dc2e74416fb6c880a2ac547f181f5313c5c0`;
- sealed tree fingerprint:
  `7bc3959111808fe9ac15ba351798f62e024714e600edc4e6eeecc78a8b14138a`;
- converter-subtree custody SHA-256:
  `a45bc2c31b954f9856c8eab36e95f68b086d5fdd682d2cf47ba2186887743124`;
- predecessor wheel: `pycforge-0.14.4-py3-none-any.whl`, 360,994 bytes;
- predecessor wheel SHA-256:
  `c1bcafe638cb07b2bc87cb869ab2bbf2fbff20c8cc073b5716b189b075e5ccd6`.

The archive was authenticated before extraction. Phase 15A never rewrites the
sealed Checkpoint E archive, historical transition/evidence records, historical
validators/builders, or converter subtree.

## Entry invariants

- PyCForge remains a Python-to-C source transpiler.
- The converter contract remains `0.14.3`.
- Generated C remains read-only, explicit-save-only, and freshness-gated.
- The closed one-to-64-document `SourceBundle` remains the only workspace
  source universe.
- No compiler, linker, loader, runner, debugger, terminal, toolchain, plugin,
  project explorer, host discovery, or generated-C editing surface is allowed.
- PyCForge is the exclusive active application and workspace identity.
