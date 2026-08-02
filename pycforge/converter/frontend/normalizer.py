from __future__ import annotations
import ast, hashlib, json, math
from typing import Any
from .source_document import SourceDocument
from pycforge.converter.ir.python_ir.nodes import Provenance, PythonIRModule, PythonIRNode

# Host runtimes newer than the declared 3.11 grammar expose fields such as
# FunctionDef.type_params even when feature_version=(3, 11) makes them
# syntactically unavailable.  Omit host-only fields so normalized Python IR is
# a projection of the declared grammar rather than the interpreter's AST shape.
_SKIP_FIELDS={"ctx","type_params"}

def _freeze(value:Any)->Any:
    if isinstance(value,list): return tuple(_freeze(v) for v in value)
    if isinstance(value,dict): return tuple((k,_freeze(value[k])) for k in sorted(value))
    return value

class PythonNormalizer:
    schema_version="python-ir/0.3"
    def normalize(self,tree:ast.AST,document:SourceDocument)->PythonIRModule:
        nodes=[]; ids={}; counter=0
        ordered=[]; seen=set()
        for item in ast.walk(tree):
            if isinstance(item,ast.expr_context) or id(item) in seen: continue
            seen.add(id(item)); ordered.append(item)
        for item in ordered:
            if isinstance(item,ast.AST):
                counter+=1
                span=self._span(item,document)
                seed={"document":document.document_id,"index":counter,"kind":type(item).__name__,"span":span}
                ids[id(item)]="py-"+hashlib.sha256(json.dumps(seed,sort_keys=True,separators=(",",":"),ensure_ascii=False).encode()).hexdigest()[:20]
        def convert_value(v:Any)->Any:
            if isinstance(v,ast.AST): return ids[id(v)]
            if isinstance(v,list): return tuple(convert_value(x) for x in v)
            if isinstance(v,float) and not math.isfinite(v):
                return ("unsupported-python-value","float-nonfinite",repr(v))
            if isinstance(v,(str,int,float,bool,type(None))): return v
            # Preserve the fact that bytes, complex, Ellipsis, and any future
            # scalar are not strings.  A plain repr() here would let an
            # unsupported Python literal masquerade as a supported str value.
            return ("unsupported-python-value", type(v).__name__, repr(v))
        for item in ordered:
            if not isinstance(item,ast.AST): continue
            fields=[]
            for name,value in ast.iter_fields(item):
                if name in _SKIP_FIELDS: continue
                fields.append((name,_freeze(convert_value(value))))
            span=self._span(item,document)
            nodes.append(PythonIRNode(ids[id(item)],type(item).__name__,tuple(fields),Provenance("source",span)))
        return PythonIRModule(self.schema_version,document.document_id,ids[id(tree)],tuple(nodes))
    def _span(self,node:ast.AST,document:SourceDocument)->dict[str,Any]|None:
        if not hasattr(node,"lineno"): return None
        return document.span_from_utf8_columns(node.lineno,node.col_offset,getattr(node,"end_lineno",node.lineno),getattr(node,"end_col_offset",node.col_offset)).to_dict()

    def synthetic(self,kind:str,origin_node_ids:tuple[str,...],fields:dict[str,Any]|None=None)->PythonIRNode:
        frozen=tuple((k,_freeze(v)) for k,v in sorted((fields or {}).items()))
        seed={"kind":kind,"origins":origin_node_ids,"fields":frozen}
        nid="syn-"+hashlib.sha256(repr(seed).encode()).hexdigest()[:20]
        return PythonIRNode(nid,kind,frozen,Provenance("synthetic",None,origin_node_ids))
