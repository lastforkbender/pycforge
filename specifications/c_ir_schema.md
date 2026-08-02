# Structured C IR — cumulative through `c-ir/0.14.3` — StableInternal

C IR is the sole structured boundary between lowering and rendering. Rules and
analysis never emit final C strings. The cumulative syntax vocabulary through
0.11 remains intact, including prototypes/calls, helper linkage, fixed arrays,
initializer lists, and subscripts.

Phase 12 adds translation-unit module metadata, not a second C unit or a new C
syntax family. The single `CTranslationUnit` records an ordered immutable module
manifest and initialization order. Every source prototype/definition records
its owner logical module and source-document identity. Every source call binding
resolves to one declared owned function, including when reached through an
imported alias. Import aliases are analysis bindings only and never become C
declarations.

The validator requires:

- one exact known owner module/document for every source function;
- exactly one matching prototype and definition per source binding;
- external linkage for every source function and internal `static` linkage for
  registered helpers;
- unique collision-free `pycm_` names in multi-document units and legacy names
  only for the singleton/no-import compatibility form;
- dependency-first module order with module-ID tie breaking and source function
  order within each module;
- all helper prototypes, then all source prototypes, then any allowed source
  external declarations, then helper definitions, then source definitions under
  the established assembly categories;
- every call target declared with exact signature before use;
- provenance document IDs belonging to the manifest and source-symbol mapping
  targets resolving to valid C binding/node identities;
- no module initializer, import-state global, source-controlled include, second
  translation unit, or unresolved module placeholder.

The general validator continues to enforce node/binding uniqueness, reserved
identifiers, registered headers, type/literal/operator compatibility, control
placement, declaration scope, container constraints, and helper contracts.
Every node is frozen and provenance-bearing; the builder seals after one build.

Historical C IR 0.8–0.14.1 serialization remains byte-stable and does not acquire
later-phase fields. C IR inspection contains no Python AST object, mutable fact
table, final C text, GUI state, compiler/linker option, executable, host path,
or discovery instruction.

Phase 13 adds three closed record constructs to `c-ir/0.13`:

- `CRecordDefinition` with one binding-backed type identifier and 1–64 ordered
  `CRecordField` members of exact `int64_t`, `double`, or `bool` type;
- `CRecordInitializer` with the exact unqualified record type and one compatible
  scalar element per member in declaration order; and
- `CMemberAccessExpr` with an exact receiver, field binding, result type, and
  explicit direct (`.`) or pointer (`->`) mode. The Phase 13 source profile
  produces direct mode only.

A source record instance is a `CVariableDeclaration` whose type is the
corresponding named record with object-level `const`, whose storage is automatic,
and whose initializer is the exact `CRecordInitializer`. Argument staging uses
ordinary typed local declarations before that aggregate. The structural Python
`__init__` has no C function node.

The cumulative validator requires record type and field bindings to be unique and
collision-free; field count/order/types to match every initializer; member
accesses to reference a declared compatible field; const qualification to be
legal; includes to cover member types; and record definitions to precede all
prototypes and executable definitions. It rejects record nodes in historical C
IR schemas. Record nodes contain no heap, address, null, destructor, method,
runtime type, or helper instruction.

Phase 14A versions the source unit as `c-ir/0.14` without adding a syntax node
kind. Each validated numeric occurrence lowers through existing `int64_t`
variable declarations and direct-call expressions: one deterministic left
temporary, one right temporary containing the proved signed literal, and one
result temporary calling the exact registered floor-division or modulo helper.
The operation mapping and helper provenance remain attached to the existing
nodes.

The 0.14 validator requires the numeric policy and plan/fact evidence to agree,
the selected helper prototype and definition to have exact registered identity
and internal linkage, each call to target that declaration with two `int64_t`
arguments and result, and helper requirements/manifests to equal the RulePlan-
owned union. It rejects numeric staging or active numeric helpers in historical
C IR schemas. The renderer cannot infer literal safety or replace a helper.

Phase 14B versions its retained envelope as `c-ir/0.14.1` and adds no C IR node
kind. A proved Boolean region uses one initialized `bool` accumulator followed
by flat sibling `CIfStatement` blocks. `And` guards on the accumulator and `Or`
guards on its logical negation. A proved comparison region initializes the
first two typed operands and Boolean result, then uses flat true-guarded blocks
whose complete operand prerequisites, assignment, and adjacent comparison stay
inside the branch. Every reached middle value is materialized once and reused.

The validator requires one exact `conditional-region-facts` record and matching
0.14.1 RulePlan for every such region; exact accumulator/operand bindings;
initialized-before-read values; branch-contained prerequisite nodes; unique
provenance-bearing C IR node IDs; and no region-owned helper, allocation,
cleanup, raw-text, conditional-expression, statement-expression, or `goto`
node. Conditional lowering is rejected under historical `c-ir/0.14`, where
`PYC2950` and `PYC2951` retain the Phase 14A placement boundary.

Phase 14C versions its retained envelope as `c-ir/0.14.2` and adds no C IR node
kind. Every selected keyword call uses existing typed automatic variable
declarations to stage all actual values exactly once in source order. The
existing `CCallExpr` then contains one pure `CIdentifierRef` per formal ordinal,
referencing the temporary of the actual statically bound to that formal.

The validator requires one exact `keyword-call-binding-facts` record and
matching `phase14.keyword_call.exact_binding@0.14.2` RulePlan for every selected
call; declaration-before-reference; exact source-order temporary provenance;
the proved formal-order reference permutation; exact target signature and
result type; and no unstaged source expression, name lookup, helper owned by the
binding rule, runtime binder, allocation, cleanup, raw C, or new node kind.
Unsupported negative records remain analysis evidence only and cannot own a
RulePlan or publish any C IR node.
Explicit historical `c-ir/0.14.1` remains the Phase 14B envelope and rejects
keyword-call plans.

Phase 14D versions the active envelope as `c-ir/0.14.3` and adds no C IR node,
type, storage mode, linkage rule, or syntax kind. An admitted required
keyword-only formal is an existing `CParameter` in full Python formal order
after positional-only and positional-or-keyword formals. C has no
keyword-only marker; the source calling-mode obligation remains in validated
normalized signature evidence, affected existing `FunctionDef` RulePlans,
`keyword-only-call-binding-facts`, and the matching call RulePlan.

Every selected Phase 14D call stages explicit actual values through existing
typed automatic declarations in Python source order. Its existing `CCallExpr`
contains one pure `CIdentifierRef` per full formal ordinal, including required
keyword-only ordinals. The reference names the temporary of the one actual
statically bound to that formal under lowering shape
`source-order-actual-temporaries-formal-order-references-v1`.

The validator requires exact eligible function-signature facts, the affected
existing `FunctionDef` RulePlan evidence, and C parameter order for every
admitted declaration, plus one exact call-keyed
`keyword-only-call-binding-facts` record and matching
`phase14.keyword_only_call.exact_binding@0.14.3` RulePlan for every selected
call. It checks parameter kinds and coverage, declaration-before-reference,
source-order temporary provenance, full formal-order reference identity, exact
target signature/result, and absence of defaults, variadics, unpacking, runtime
binding, rule-owned helpers, allocation, cleanup, raw C, or new nodes.
Unsupported call facts remain analysis evidence only and publish no C IR.

Explicit historical `c-ir/0.14.2` remains the Phase 14C envelope, retains its
exact positional/explicit-keyword profile and generated structures, and rejects
required keyword-only declarations.
