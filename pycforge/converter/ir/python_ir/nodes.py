from __future__ import annotations
from dataclasses import dataclass
from typing import Any

JsonValue = None|bool|int|float|str|tuple["JsonValue",...]|tuple[tuple[str,"JsonValue"],...]

_SCALAR_FIELD_NAMES={"id","name","arg","attr","asname","module","level","kind","kwd_attrs","rest","tag","type_comment","conversion","is_async","simple","lineno"}


def python_ir_reference_ids(kind:str,field_name:str,value:Any,known_ids:object|None=None)->tuple[str,...]:
    """Return stable child IDs from a declared Python 3.11 AST child slot."""
    if field_name in _SCALAR_FIELD_NAMES:
        return ()
    if field_name == "names" and kind in {"Global","Nonlocal"}:
        return ()
    if field_name == "value" and kind in {"Constant","MatchSingleton"}:
        return ()
    if isinstance(value,str) and value.startswith(("py-","syn-")):
        return (value,) if known_ids is None or value in known_ids else ()
    if isinstance(value,(tuple,list)):
        return tuple(reference for item in value for reference in python_ir_reference_ids(kind,field_name,item,known_ids))
    if isinstance(value,dict):
        return tuple(reference for item in value.values() for reference in python_ir_reference_ids(kind,field_name,item,known_ids))
    return ()

@dataclass(frozen=True, slots=True)
class Provenance:
    origin_kind: str
    source_span: dict[str,Any]|None
    origin_node_ids: tuple[str,...]=()
    def to_dict(self)->dict[str,Any]: return {"origin_kind":self.origin_kind,"source_span":self.source_span,"origin_node_ids":list(self.origin_node_ids)}

@dataclass(frozen=True, slots=True)
class PythonIRNode:
    node_id: str
    kind: str
    fields: tuple[tuple[str,JsonValue],...]
    provenance: Provenance
    def to_dict(self)->dict[str,Any]:
        def thaw(v:JsonValue)->Any:
            if isinstance(v,tuple):
                if v and all(isinstance(x,tuple) and len(x)==2 and isinstance(x[0],str) for x in v): return {k:thaw(x) for k,x in v}
                return [thaw(x) for x in v]
            return v
        return {"node_id":self.node_id,"kind":self.kind,"fields":{k:thaw(v) for k,v in self.fields},"provenance":self.provenance.to_dict()}

@dataclass(frozen=True, slots=True)
class PythonIRModule:
    schema_version: str
    document_id: str
    root_node_id: str
    nodes: tuple[PythonIRNode,...]
    def to_dict(self)->dict[str,Any]: return {"schema_version":self.schema_version,"document_id":self.document_id,"root_node_id":self.root_node_id,"nodes":[n.to_dict() for n in self.nodes]}


@dataclass(frozen=True, slots=True)
class PythonIRBundleDocument:
    module_id: str
    logical_name: str
    bundle_ordinal: int
    is_primary: bool
    module: PythonIRModule

    def to_dict(self) -> dict[str, Any]:
        return {
            "module_id": self.module_id,
            "logical_name": self.logical_name,
            "bundle_ordinal": self.bundle_ordinal,
            "is_primary": self.is_primary,
            "document_id": self.module.document_id,
            "python_ir": self.module.to_dict(),
        }


@dataclass(frozen=True, slots=True)
class PythonIRBundle:
    schema_version: str
    primary_module_id: str
    documents: tuple[PythonIRBundleDocument, ...]

    def to_dict(self) -> dict[str, Any]:
        return {
            "schema_version": self.schema_version,
            "primary_module_id": self.primary_module_id,
            "documents": [document.to_dict() for document in self.documents],
        }
