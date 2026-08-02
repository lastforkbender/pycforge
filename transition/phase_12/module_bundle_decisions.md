# Phase 12 Explicit-Module-Bundle Decisions

Status: accepted before Phase 12 implementation on 2026-07-22  
Authority: Architecture Revision 3.1 and Revision 3.2 addendum  
Target: `c11-portable-fixed-v1` under `strict-source-v1`

These decisions authorize only a bounded closed-world SourceBundle. They do not
authorize Python import-system equivalence, packages, discovery, executable
module initialization, multiple C outputs, compilation, linking, or execution.

## M12-01 — explicit identities and capacity

- `source-bundle/0.2` contains one primary and zero or more companions, 1–64
  documents total; every member is part of the conversion unit.
- Each document explicitly supplies logical module ID, logical source name, and
  decoded UTF-8-compatible text. No module ID is inferred from a path.
- A module ID has 1–16 dot-separated `[a-z][a-z0-9_]{0,62}` segments and at most
  255 UTF-8 bytes. Exact IDs and logical source names are separately unique.
- Comparison is exact. There is no case/Unicode/path/package normalization or
  prefix resolution. At most 4,096 normalized import items are admitted.
- Host/display paths are not request fields and cannot enter semantic/output
  fingerprints.

## M12-02 — accepted import form

- Each document has zero or more absolute `ImportFrom` preamble statements,
  followed by one or more supported top-level synchronous functions.
- `level == 0`, the module spelling equals one supplied module ID, no star is
  present, and every ordered item names a directly defined eligible function.
- Optional aliases and multiple/parenthesized ordered names are supported.
- An alias is one immutable module-scope imported-function binding that reuses
  the target binding/signature and creates no callable value or C declaration.
- Calls remain direct `Name` calls. No implicit cross-document name search or
  re-export is permitted.

## M12-03 — dependency, cycle, and initialization policy

- Resolved imports create exact `importer -> imported` edges. Self-edges and
  nontrivial SCCs reject, even when an import is unused.
- Acyclic modules use dependency-first stable topological order. Exact logical
  module ID UTF-8 order breaks ready-set ties; functions retain source order.
- Namespace construction is compile-time only. No module object, import cache,
  initializer function, global guard/state, or runtime import-failure path exists.
- The bundle-wide function call graph includes cross-module edges; existing
  `PYC2920` recursion policy remains in force.

## M12-04 — SourceBundle-only resolution and exclusions

- Resolution consumes only the immutable exact-ID map built from request
  members. It never consults a path, filesystem, working directory, environment,
  network, import hook/cache, package index, or installed distribution.
- Plain, relative, star, late, local, conditional, and dynamic imports reject.
  Module values/aliases, attributes, re-export, implicit parents, package
  initializers/namespaces, `from pkg import submodule`, and fallback resolution
  reject.
- An error in any member rejects the entire bundle and publishes no partial C
  IR, helper output, mapping set, or generated C.

## M12-05 — C names, linkage, and singleton compatibility

- Every source function retains external linkage. Helpers retain registered
  `pycf_` names and internal `static` linkage.
- A multi-document source function uses
  `pycm_<binding-sha256>__<module-escape>__<legacy-token>`. The complete
  lowercase SHA-256 of fully qualified stable binding identity immediately
  follows `pycm_`, so collision entropy is inside C11's guaranteed significant
  external-identifier prefix. Module escape maps `_` to `_u` and `.` to `_d`;
  `pycm_` is converter-reserved.
- Imported aliases receive no C identifier and call the target binding.
- A one-document/no-import request selects the legacy name/declaration plan and
  must preserve Phase 11 generated C bytes exactly.

## M12-06 — one translation unit and mappings

- Exactly one C translation unit is generated. Category order is registered
  includes, helper prototypes, source prototypes, permitted source externals,
  helper definitions, then source definitions. Source items use approved
  module/function order; every prototype precedes every definition.
- No module header/include, second C source, object, link/build instruction, or
  module initializer is emitted.
- Every diagnostic/mapping identifies logical module, logical source,
  source-document revision, and span. Import aliases map to target
  binding/prototype/definition; call occurrences map from importer provenance to
  the target C binding. No explanatory comment is fabricated for imports.

## M12-07 — stable primary diagnostics

- `PYC3501`: malformed/noncanonical document or logical identity
- `PYC3502`: duplicate/ambiguous module or logical source identity
- `PYC3503`: exact imported module absent from SourceBundle
- `PYC3504`: unsupported import form
- `PYC3505`: missing/ineligible directly defined imported member
- `PYC3506`: alias/namespace collision, rebind, foreign implicit reference,
  module value, or re-export
- `PYC3507`: self or multi-module dependency cycle
- `PYC3508`: package/import-system, implicit parent/prefix/fallback behavior
- `PYC3509`: executable module initialization/general top-level state
- `PYC3510`: document/import/aggregate resource ceiling

Call arity/type and function recursion retain `PYC2904`, `PYC2905`, and
`PYC2920`. Every PYC35xx code requires an independent negative fixture.
