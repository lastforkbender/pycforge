# Normalized Python IR Schema — `python-ir/0.4`

The cumulative frontend first normalizes every explicit SourceBundle document as
an independent `python-ir/0.3` module inside an internal immutable bundle
envelope. Module analysis consumes only that in-memory envelope and publishes
the current `python-ir/0.4` conversion boundary: one flattened synthetic module
whose body retains import nodes for planning, keeps approved record class
declarations before their module's functions, and orders modules
dependency-first while preserving source order within each declaration class.
Per-document raw
module roots remain in the bundle evidence payload; they are not silently
reinterpreted as the flattened root.

The normalized node vocabulary and field-aware reference rules remain those
promoted in `python-ir/0.3`. Each node contains a globally unambiguous stable
`py-` source-node ID or distinct `syn-` synthetic-node ID, normalized kind,
deterministic ordered fields, and provenance with source document/span and
origin-node IDs. Source IDs incorporate document revision identity so equal
local ordinals in different documents cannot collide.

`ImportFrom` retains absolute level, exact dotted module spelling, ordered alias
records, and source spans. Resolution never consults a host path. It rewrites
only validated direct function-call and same-module record-construction
spellings to their unique bundle names and adds three synthetic planning node
kinds:

- one `ModuleDocument` per supplied document;
- one aggregate `ModuleInitialization` containing dependency order and the
  no-runtime-initialization policy;
- one `ModuleBundleAssembly` proving the single-translation-unit obligation.

All synthetic origin references name retained `python-ir/0.4` nodes. The raw
per-document bundle, resolution record, fact tables, and flattened IR are
separate immutable payload members; target C types, helpers, rendered C,
filesystem paths, and discovery state are prohibited from Python IR.

Phase 13 does not add a parallel Python IR schema or erase the normalized class
body. Retained `ClassDef`, field `AnnAssign`, structural `__init__`, constructor
`Call`, and field `Attribute` nodes keep their ordinary 3.11 shape and exact
source provenance. Static-record meaning is published separately as complete
`fact-table/0.13` records and RulePlans; Python IR never stores a C layout,
automatic-storage decision, or rendered member spelling.

Phase 14A retains this exact `python-ir/0.4` boundary. `BinOp` with `FloorDiv`
or `Mod` and direct `Constant`/`UnaryOp` divisor shapes remain ordinary Python
IR nodes; safe-divisor meaning is published only in `fact-table/0.14`. Python
IR performs no constant folding, helper selection, signed-literal repair, or C
temporary construction.

Phase 14B retains the same `python-ir/0.4` boundary. `BoolOp` and `Compare`
remain ordinary normalized nodes with ordered operands/operators; calls and
other prerequisite-producing children are not rewritten into a new region
node. Guard polarity, prerequisite closure, and placement are published only
in `conditional-region-facts` under `fact-table/0.14.1`.

Phase 14C also retains `python-ir/0.4`. A `Call` keeps its ordered ordinary
`args` references and ordered `keyword` node references; each `keyword` keeps
its exact normalized source `arg` spelling or null unpacking marker and value
reference. Python IR does not bind names to formals, permute values into formal
order, create argument temporaries, or encode C parameter spellings. Exact
binding and the two order vectors are published only in
`keyword-call-binding-facts` under `fact-table/0.14.2`.

Phase 14D retains the same `python-ir/0.4` boundary. An `arguments` node keeps
ordered `posonlyargs`, `args`, and `kwonlyargs`; ordered `defaults` and
`kw_defaults`; and exact `vararg`/`kwarg` presence. A null `kw_defaults` entry
is retained as grammar evidence that its corresponding keyword-only formal is
required. Existing `arg` nodes keep their exact name, annotation, span, and
binding provenance.

Python IR does not classify an eligible Phase 14D signature, add a parameter
kind field, change the serialized `ParameterFact` shape, erase the
keyword-only/default distinction, or encode a C calling convention. Existing
function-signature facts and FunctionDef RulePlans prove declarations;
call-keyed `keyword-only-call-binding-facts` under `fact-table/0.14.3` prove
selected and rejected direct-call bindings.

Parser-only host AST objects and fields outside the declared Python 3.11 grammar
are omitted. Re-normalizing and resolving the same canonical SourceBundle must
produce byte-equivalent IR. Historical `python-ir/0.3` remains the
single-document schema and is not silently repurposed.
