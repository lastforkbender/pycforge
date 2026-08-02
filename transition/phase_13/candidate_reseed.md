# Phase 13 Candidate Reseed Record

Date: 2026-07-22

The first Phase 13 working candidate was abandoned before promotion because an
independent adversarial reviewer invoked the host C compiler on temporary C
output. Three accepted generated-C translation units were compiled to
temporary object files, and one hand-mutated const-member C IR rendering was
submitted to a compile-only command and rejected by the compiler. Nothing was
linked, loaded, or executed. PyCForge itself exposed or invoked no toolchain.

That event activated the explicit rollback condition in
`rollback_conditions.md`; it is not being waived or rewritten. The abandoned
tree is excluded from every release artifact and release fingerprint.

The release candidate was reseeded from a new extraction of the sealed 0.12.2
predecessor. Before any Phase 13 source was overlaid, the extraction was
authenticated as:

- archive SHA-256:
  `6a603684001f2cb2e9365d7e9b318f1a95dbe95b2cb36cf8821c30403c1754d0`;
- canonical predecessor tree SHA-256:
  `434981decfd2b2fc2b344f5b9a3b37377396376c2e0a8c8ed00bb9fa9077d765`;
- predecessor converter-subtree SHA-256:
  `4d7676a46105652efd13efb699d00e7a39a4b1bfd7ae7daad32c22702fd41b51`.

Only the reviewed source, contract, documentation, and test changes were then
copied into this clean candidate. Its release gate is structural and textual;
no C compiler, linker, loader, or generated-code execution may be used.

Release reporting must retain both facts: the abandoned development candidate
had compile-only review activity, while this reseeded release candidate and its
validator use no C toolchain. Phase 14 remains unopened.
