from __future__ import annotations
from pycforge.converter.ir.python_ir.nodes import (
    PythonIRBundle,
    PythonIRModule,
    python_ir_reference_ids,
)

def validate_python_ir(
    module: PythonIRModule,
    *,
    allowed_document_ids: frozenset[str] | None = None,
)->tuple[bool,str]:
    if module.schema_version not in {"python-ir/0.3", "python-ir/0.4"}: return False,"unsupported Python IR schema"
    permitted_documents = allowed_document_ids or frozenset((module.document_id,))
    ids=[n.node_id for n in module.nodes]
    if len(ids)!=len(set(ids)): return False,"duplicate Python IR node IDs"
    id_set=set(ids)
    if module.root_node_id not in id_set: return False,"missing Python IR root"
    for node in module.nodes:
        if not node.node_id.startswith(("py-","syn-")): return False,"invalid Python IR node identity domain"
        if node.provenance.origin_kind not in {"source","synthetic"}: return False,"invalid Python IR provenance kind"
        if node.provenance.origin_kind == "synthetic" and any(
            origin_node_id not in id_set for origin_node_id in node.provenance.origin_node_ids
        ):
            return False,"synthetic Python IR provenance contains a dangling origin node"
        if node.provenance.origin_kind == "source":
            span=node.provenance.source_span
            if span is not None:
                if not isinstance(span,dict) or span.get("document_id") not in permitted_documents:return False,"source node has an invalid document span"
                start,end=span.get("start",{}),span.get("end",{})
                if any(not isinstance(pos.get(key),int) or pos.get(key)<0 for pos in (start,end) for key in ("line","column","offset")):
                    return False,"source node span contains invalid positions"
                if end["offset"] < start["offset"]:
                    return False,"source node span is reversed"
        field_names={name for name,_ in node.fields}
        if field_names & {"generated_c","c_ir","c_type","target_representation"}:
            return False,"normalized Python IR contains target-owned fields"
        for field_name,value in node.fields:
            if _contains_c_text(value): return False,"normalized Python IR contains generated C text"
            for reference in python_ir_reference_ids(node.kind,field_name,value):
                if reference not in id_set: return False,"normalized Python IR contains a dangling node reference"
    return True,""


def validate_python_ir_bundle(bundle: PythonIRBundle) -> tuple[bool, str]:
    if bundle.schema_version != "python-ir-bundle/0.4":
        return False, "unsupported Python IR bundle schema"
    if not bundle.documents or not 1 <= len(bundle.documents) <= 64:
        return False, "Python IR bundle document count is outside the closed bound"
    module_ids = [item.module_id for item in bundle.documents]
    document_ids = [item.module.document_id for item in bundle.documents]
    ordinals = [item.bundle_ordinal for item in bundle.documents]
    if len(module_ids) != len(set(module_ids)):
        return False, "duplicate module ID in Python IR bundle"
    if len(document_ids) != len(set(document_ids)):
        return False, "duplicate document ID in Python IR bundle"
    if ordinals != list(range(len(bundle.documents))):
        return False, "Python IR bundle ordinals are not contiguous source order"
    if bundle.primary_module_id != bundle.documents[0].module_id or not bundle.documents[0].is_primary:
        return False, "Python IR bundle primary identity is inconsistent"
    if any(item.is_primary != (item.bundle_ordinal == 0) for item in bundle.documents):
        return False, "Python IR bundle contains an invalid primary role"
    all_node_ids: list[str] = []
    for item in bundle.documents:
        valid, message = validate_python_ir(item.module)
        if not valid:
            return False, message
        all_node_ids.extend(node.node_id for node in item.module.nodes)
    if len(all_node_ids) != len(set(all_node_ids)):
        return False, "Python IR bundle contains duplicate cross-document node IDs"
    return True, ""

def _contains_c_text(value:object)->bool:
    # Structural guard against accidental target payload fields, not source strings.
    if isinstance(value,tuple): return any(_contains_c_text(v) for v in value)
    return False
