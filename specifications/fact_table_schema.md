# Fact Tables — cumulative through `fact-table/0.14.3`

Every table declares schema version, stable ID, producer, key domain,
completeness, invalidation dependencies, and deterministically sorted unique
records. Every record contains an immutable value and source-node/document
provenance. Published tables recursively freeze nested mappings and sequences.

The cumulative tables cover scopes, bindings, value categories, function
signatures, call targets, returns, locals, the bundle-wide call graph, and Phase
11 container shapes/bindings/accesses/iterations. Phase 12 adds six immutable
`fact-table/0.12` publications:

- `module-identity-facts`, keyed by exact module ID, records module/document/
  logical-source identity, bundle ordinal and primary role, plus the synthetic
  document-plan node and owned import/function node IDs;
- `module-import-facts`, keyed by stable import-item ID, records the import and
  alias nodes, importer and exact target module, imported and local spellings,
  direct target function node, normalized source ordinal, and support state;
- `module-function-facts`, keyed by function node ID, records module/document,
  original and flattened names, bundle function ordinal, external linkage, and
  whether reserved module-generated name mode applies;
- `module-initialization-facts`, containing exactly one aggregate record keyed by
  its synthetic node ID, with dependency-first `module_order`, exact dependency
  edges, `reject-all-cycles`, and `runtime_initialization: none`;
- `module-namespace-facts`, keyed by module ID, records owned local functions,
  immutable imported-function bindings and their direct targets, and generated
  source function names;
- `module-source-facts`, keyed by module ID, records source-document ID, logical
  source name, bundle ordinal/role, content fingerprint, and eligibility state.

Every module document, direct function, and normalized import item has exactly
one complete corresponding record, and the initialization graph has one closed
aggregate record. Records sort by their declared stable keys; ordered syntax and
dependency-first function order are explicit value fields rather than inferred
from map iteration.

Validators reject missing cumulative tables, duplicate or unsorted keys,
malformed or dangling document/module/binding references, missing provenance,
inconsistent import/namespace/edge facts, invalid aggregate topological order,
module/linkage collisions, invalid supported-plan relationships, and unresolved
obligations. Re-analysis publishes new tables and fingerprints; consumers never
mutate an earlier publication.

Phase 13 adds six complete `fact-table/0.13` publications:

- `record-definition-facts`, keyed by `record_id`, records the exact class and
  class binding, module/document, flattened name, ordered fields, structural
  initializer, immutable automatic storage, unique ownership, non-nullability,
  and no-cleanup model;
- `record-field-facts`, keyed by `field_id`, records the declaration, target and
  annotation nodes, source name, zero-based ordinal, exact scalar category,
  module/document, and immutable state;
- `record-initializer-facts`, keyed by `initializer_id`, records the function,
  arguments, `self`, ordered parameters and assignments, complete field list,
  direct receiver model, and once-only declaration-order initialization;
- `record-instance-facts`, keyed by `instance_id`, records the exact class,
  owner function, construction and assignment, target/binding, ordered
  arguments, module/document, automatic lifetime, no allocation, no alias, no
  cleanup, and immutable state;
- `record-binding-facts`, keyed by the local `binding_id`, records its one
  declaration, all occurrences, exact approved field-access nodes, owner
  function, unique assignment, no-alias proof, and no-escape proof; and
- `record-access-facts`, keyed by `access_node_id`, records the exact instance,
  binding, record and field, owner function/module/document, direct read mode,
  and resulting scalar category.

Every retained Phase 13 `ClassDef`, record field, structural `__init__`, record
construction, local owner, and direct field read has exactly one matching
record fact. Validators close all cross-table IDs, field ordering and arity,
field categories, declaration provenance, module/document equality,
initializer coverage, ownership/lifetime constants, and supported RulePlan
relationships. A class-free Phase 13 plan still publishes all six tables as
complete empty publications. Historical 0.12 module facts are not repurposed.

Phase 14A adds one complete `fact-table/0.14` publication:

- `numeric-operation-facts`, keyed by `binop_node_id` in the
  `binop-node-id` domain and carrying a deterministic `operation_id`, records the
  exact `BinOp`, operator, left, right, enclosing function, document, module, and
  logical-source identities; floor-divide or floor-modulo kind; exact integer
  categories and `int64_t` representations; direct signed-literal shape, node
  chain, and mathematical divisor value; admitted-domain, nonzero,
  negative-one, and minimum-signed exclusion proofs; exact helper requirement;
  left-before-right once-only evaluation; scalar ownership; no allocation,
  cleanup, or runtime failure; and the target contract.

Every retained active Phase 14A `FloorDiv` or `Mod` occurrence has exactly one
matching supported numeric fact. Validators re-anchor facts to Python IR,
module/function facts, categories, RulePlans, helper requirements, provenance,
and deterministic ordering. Missing, duplicate, unsorted, dangling,
wrong-owner, malformed-literal, unsafe-divisor, wrong-helper, or tampered
numeric evidence rejects before lowering. Historical fact tables retain their
exact schemas and shapes.

Phase 14B adds one complete `fact-table/0.14.1` publication:

- `conditional-region-facts`, keyed by the region source node ID in the
  `conditional-region-node-id` domain, records its deterministic region ID,
  Boolean-short-circuit or chained-comparison kind, exact function/module/
  document/logical-source owner, ordered operator and operand nodes and kinds,
  exact operand categories, unconditional prefix, per-operand evaluation mode
  and guard polarity, branch-local prerequisite closure, guarded operands,
  once-only source order, `bool` result, `flat-guarded-assignment-v1` shape,
  absent allocation/cleanup, unchanged failure channel, and exact target.

Its producer is `analysis.plan`, completeness is `complete`, and its exact
invalidation dependencies are `value-category-facts`,
`evaluation-order-facts`, `call-target-facts`, `container-access-facts`,
`record-access-facts`, and `numeric-operation-facts`. Records are unique and
sorted by region node ID. Provenance includes the region, owner function,
operators, operands, and complete prerequisite identities with the six fixed
conditional-region evidence tokens.

Independent validation reconstructs the eligible set from normalized Python
IR and cumulative facts. It rejects missing or extra regions, changed operand
or operator order, wrong guard or prefix, incomplete prerequisites/provenance,
wrong source ownership, helper ownership, or a nonmatching 0.14.1 RulePlan.
Historical `fact-table/0.14` numeric facts keep their exact Phase 14A schema;
they are dependencies of, not replacements for, the new table.

Phase 14C adds one complete `fact-table/0.14.2` publication:

- `keyword-call-binding-facts`, keyed by the call source node ID in the
  `keyword-call-node-id` domain, records its deterministic binding ID; call,
  callee, target function and target binding; exact target name; positional-
  only count; ordered parameter nodes/names/categories; ordered positional and
  keyword nodes/names/value nodes; one source-order binding entry per actual;
  source-to-formal and formal-to-source vectors; formal-order argument nodes;
  exact evaluation order; complete-coverage and once-only proofs;
  `source-order-temporaries-formal-order-references-v1` lowering shape; absent
  allocation/cleanup; statically absent runtime binding failure; support state;
  and exact diagnostic/rejection evidence when unsupported.

The table is complete over keyword-bearing direct-source-function candidates
whose existing declaration signature reaches the static binder, not only over
accepted calls. A rejected candidate has `supported: false`, an exact diagnostic,
nonempty reason and rejection node, and no 14C RulePlan or C IR. A rule-selected
call has exactly one supported record, and every selected 14C RulePlan references
exactly one supported record.

Its producer is `analysis.plan`, completeness is `complete`, and its exact
invalidation dependencies are `binding-facts`, `function-signature-facts`,
`value-category-facts`, `call-target-facts`, and `evaluation-order-facts`.
Records are unique and sorted by call node ID. Provenance anchors the call,
callee, target function, formals, positional actuals, keyword nodes, and keyword
values with the fixed keyword-call evidence tokens.

Independent validation reconstructs the complete candidate set, support or
rejection state, association vectors, and exact supported-plan correspondence
from normalized Python IR and predecessor facts. It rejects missing or extra
calls, changed keyword spelling or order, wrong target/signature/category,
incomplete coverage, inconsistent forward/inverse vectors, wrong provenance,
call-target disagreement, or a nonmatching 0.14.2 RulePlan. Historical
`fact-table/0.14.1` conditional facts retain their exact Phase 14B schema and
are never repurposed as keyword-binding evidence.

Phase 14D adds one complete call-keyed `fact-table/0.14.3` publication:

- `keyword-only-call-binding-facts`, keyed by call source node ID in the
  `keyword-only-call-node-id` domain, records its deterministic binding ID;
  call, callee, target function and binding; ordered formal node IDs, names,
  categories, and kinds; positional-capable and required-keyword-only ordinal
  partitions; ordered positional and keyword nodes/names/value nodes; one
  source-order entry per actual; source-to-formal and formal-to-source vectors;
  complete exact-once coverage; actual/formal category agreement;
  `source-order-actual-temporaries-formal-order-references-v1`; absent
  defaults, variadics, unpacking, allocation, cleanup, and runtime binding
  failure; support state; and exact diagnostic/rejection evidence when
  unsupported.

The table is complete over resolved direct-call candidates whose target
signature contains at least one required keyword-only formal and reaches the
Phase 14D binder. It is not keyed by declarations and contains no declaration
record. Required-keyword-only declaration evidence remains in existing
`function-signature-facts` without changing the serialized `ParameterFact`
shape. The admitted kind remains `keyword-only`; required status is separately
reconstructed from the corresponding null `kw_defaults` entry in normalized
Python IR.

A rejected call candidate has `supported: false`, one exact diagnostic,
nonempty reason and rejection node, and no Phase 14D call RulePlan or C IR.
Every selected Phase 14D call has exactly one supported record, and every
selected `phase14.keyword_only_call.exact_binding@0.14.3` RulePlan references
exactly one supported record.

The producer is `analysis.plan`, completeness is `complete`, and invalidation
dependencies are existing `binding-facts`, `function-signature-facts`,
`value-category-facts`, `call-target-facts`, and `evaluation-order-facts`.
Records are unique and sorted by call node ID. Provenance anchors the call,
callee, target function, all formals, positional actuals, keyword nodes, and
keyword values.

Independent validation reconstructs every call candidate, declaration
eligibility, formal kind/order, support or rejection, association vectors, and
supported-plan correspondence from Python IR and existing facts. It separately
validates admitted uncalled required-keyword-only functions through their
existing signature facts and FunctionDef RulePlans. Missing, extra, reordered,
wrong-kind, defaulted, variadic, unpacked, wrong-category, malformed-provenance,
or mismatched evidence rejects before lowering.

Historical `fact-table/0.14.2` keyword-call facts retain their exact call-keyed
Phase 14C shape and cannot acquire keyword-only formal kinds or 0.14.3 plans.
