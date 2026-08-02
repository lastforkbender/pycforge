# Phase 9 Entry Criteria

Entry was evaluated against the unmodified promoted Phase 8 archive.

- Phase 8 archive SHA-256 verified: `c30bb745aa0c471683c8056ca017aa501366ecdb4e3c4c4c16d905658015cbc6`.
- Phase 8 tree fingerprint verified: `fcf5161c71e194072c97b5abcf8f690e3172da29c2c65e1ccf81490b050c26e8`.
- All 92 Phase 0–8 tests passed before Phase 9 edits.
- Phase 8 validator, architecture audit, rule audit, determinism audit, transition audit, Checkpoint C, GUI/facade isolation, cancellation, observers, mappings, and stale-result protections were reviewed.
- The Phase 8 archive and extracted baseline were preserved unchanged; work occurred in a separate Phase 9 tree.
- Revision 3.1’s complete Phase 9 section and the correct PyCForge handoff were reviewed. The uploaded `HM(3).txt` was identified as a Cecil+ handoff and was not treated as PyCForge authority.
- Constraint/value categories, representation/ownership, C definitions/returns, source mappings, trace snapshots, target resolution, and exact annotation evidence were frozen before call lowering.
- The inherited stale README and review defects were assigned to the new candidate, not backported into the promoted archive.

Selected scope: top-level exact-annotated functions, positional parameters, stable locals, direct understood-target calls, compatible explicit returns, prototypes, and explicit rejection of dynamic neighboring behavior.
