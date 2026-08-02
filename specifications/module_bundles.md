# Explicit Module Bundles — Phase 12 base retained through Phase 14C

Active policy identity: `phase13-explicit-record-modules-v0.13`  
Historical policy identity: `phase12-explicit-sourcebundle-modules-v0.12`  
Bundle schema: `source-bundle/0.2`  
Target: `c11-portable-fixed-v1` under `strict-source-v1`

Phase 12 is a closed-world source-bundle profile. It introduces neither
Python's import system nor package behavior. Only documents explicitly present
in `SourceBundle` can participate.

## Accepted source form

Every document contains zero or more absolute `from` imports, then zero or more
approved module-local record declarations, followed by one or more otherwise
eligible top-level synchronous function definitions:

```python
from exact.module_id import function_name
from exact.module_id import function_name as local_name
from exact.module.id import first, second as local_second

def use(value: int) -> int:
    return local_second(first(value))
```

An accepted `ImportFrom` has `level == 0`, a nonempty module spelling equal to
one canonical logical module ID, no star, and one or more ordered aliases.
Parenthesized and multiline spellings normalize to the same ordered alias
items. All imports form the module preamble and must precede the first record or
function. Every imported member is a directly defined, eligible top-level
function in the exact target document. `as` creates an immutable module-scope
`imported-function` binding. The alias and the target reuse one target C binding
and signature; an alias does not create a prototype, definition, callable
value, or ownership boundary.

Each module has an isolated namespace. Same-spelled functions in different
modules are distinct. Calls remain direct `Name` calls and resolve only to an
eligible same-module function, an explicitly imported-function binding, or the
existing narrowly recognized `range` built-in. No unique-name search across
other documents is allowed. Imports are not re-exported.

Under the active Phase 13 policy, approved record declarations enter only their
defining module's namespace. A record class is not an eligible imported member;
attempting to import one rejects with `PYC3610`. Record construction and all
field reads must remain in that exact module. No cross-module record type or
value identity is created.

## Dependency and initialization policy

Each resolved import contributes an `importer -> imported` dependency edge.
Repeated members from one target retain individual import facts but the graph
uses one exact module edge. A self-edge or a strongly connected component with
more than one module rejects with `PYC3507`, including when the import is
otherwise unused. Related cycle edges are ordered by importer module ID,
source ordinal, and imported module ID.

For an acyclic graph, module order is a dependency-first stable topological
order. Among simultaneously eligible modules, exact logical module ID UTF-8
byte order is the tie breaker. Functions within a module remain in source
order. This order governs source prototypes, source definitions, module facts,
summaries, and deterministic trace events.

Initialization is compile-time namespace construction only. Phase 12 emits no
module object, import cache, initialization function, guard, external variable,
global state, or runtime failure path. Executable top-level statements and
general globals reject with `PYC3509`. The existing bundle-wide function call
graph includes cross-module calls; direct or mutual function recursion still
rejects with `PYC2920`.

## C namespace, linkage, and name policy

All source functions retain the Target C Source Contract's external linkage.
Helpers retain registered `pycf_` spellings and internal `static` linkage.
In a multi-document bundle, a source function receives:

```text
pycm_<binding-sha256>__<module-escape>__<legacy-function-token>
```

`binding-sha256` is the complete lowercase SHA-256 of the UTF-8 spelling
`<module-id>.<source-function-name>` and immediately follows `pycm_`, placing
collision entropy within C11's guaranteed significant external-identifier
prefix. The module escape preserves lowercase ASCII letters and digits, maps
`_` to `_u`, and maps `.` to `_d`. The legacy function token uses the central
predecessor allocator's reserved-name escape policy.
`pycm_` is a reserved
converter-managed source-function namespace distinct from helper-owned
`pycf_`. The central allocator and C IR validator still reject every target,
normalization, or linkage collision.

A one-document bundle with no import items uses the historical source-function
name plan and must render generated C byte-identically to the Phase 11 scalar
or container path for the same canonical request.

## Single-translation-unit representation

The active Phase 14C profile emits exactly one `CTranslationUnit`. It contains,
in order:

1. registered includes under the existing include-order policy;
2. all record type definitions in module/declaration order;
3. helper prototypes in resolved helper-plan order;
4. all source prototypes in module/function order;
5. any existing validated source external declarations;
6. helper definitions in resolved helper-plan order;
7. all source definitions in the same module/function order.

Every function has exactly one matching prototype before every definition.
Imported aliases lower to target binding references and add no C declaration.
No source-controlled include, header, second `.c` file, object, linker input,
build instruction, or module initializer is produced.

## Mappings and diagnostics

Every diagnostic and source mapping identifies logical module ID, logical
source name, source-document ID, revision, and span. Cross-document diagnostic
order is bundle ordinal, source offset, stage rank, severity rank, code, then
decision identity. Request-level identity failures precede source diagnostics.

An imported alias has a deterministic source-symbol relationship to the target
function binding, prototype, and definition. A call maps its callee occurrence
in the importing document to the target C binding. An unused import maps to the
target declaration through this relationship; the renderer does not fabricate
a C comment merely to create an output range.

## Explicit exclusions

Rejected forms include plain `import`, relative or star import, an import after
the first function, any local or conditional import, module aliases/objects,
attribute calls, record imports, re-export, package initializer or
namespace-package behavior,
implicit parents, `from pkg import submodule`, `__import__`, `importlib`-style
dynamic loading, source-controlled discovery, installed dependency resolution,
multiple translation units, compilation, linking, loading, and execution.

Every rejection publishes no partial C IR, helper output, mapping set, or
generated C.
