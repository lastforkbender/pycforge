from __future__ import annotations
from dataclasses import dataclass
from pycforge.converter.ir.c_ir.model import *
from pycforge.converter.ir.c_ir.validation import validate_translation_unit

_PRECEDENCE={CBinaryOp.LOGICAL_OR:3,CBinaryOp.LOGICAL_AND:4,CBinaryOp.BIT_OR:5,CBinaryOp.BIT_XOR:6,CBinaryOp.BIT_AND:7,CBinaryOp.EQUAL:8,CBinaryOp.NOT_EQUAL:8,CBinaryOp.LESS:9,CBinaryOp.LESS_EQUAL:9,CBinaryOp.GREATER:9,CBinaryOp.GREATER_EQUAL:9,CBinaryOp.SHIFT_LEFT:10,CBinaryOp.SHIFT_RIGHT:10,CBinaryOp.ADD:11,CBinaryOp.SUBTRACT:11,CBinaryOp.MULTIPLY:12,CBinaryOp.DIVIDE:12,CBinaryOp.REMAINDER:12}
@dataclass(frozen=True,slots=True)
class SourceOutputMapping:
    c_node_id:str; origin_kind:str; source_document_id:str|None; source_node_ids:tuple[str,...]; rule_plan_id:str|None; start_byte:int; end_byte:int; start_line:int; start_column:int; end_line:int; end_column:int
@dataclass(frozen=True,slots=True)
class RenderedC:
    text:str; mappings:tuple[SourceOutputMapping,...]

class CRenderer:
    def __init__(self)->None:self._parts=[];self._maps=[];self._line=1;self._column=0;self._byte=0
    def _render_external(self,d:CExternalDeclaration)->None:
        self._mapped(d.node_id,d.provenance,lambda:self._render_external_inner(d))
    def _render_external_inner(self,d):
        if isinstance(d,CRecordDefinition):
            self._render_record_definition(d)
        elif isinstance(d,CFunctionPrototype):
            self._render_function_signature(d); self._write(";\n")
        elif isinstance(d,CFunctionDefinition):
            self._render_function_signature(d); self._write("\n"); self._render_block(d.body)
        elif isinstance(d,CVariableDeclaration):self._render_var(d,0)
        else:raise TypeError(type(d).__name__)
    def _render_record_definition(self,d:CRecordDefinition)->None:
        self._write("typedef struct "+d.identifier.spelling+" {\n")
        for field in d.fields:
            self._mapped(
                field.node_id,
                field.provenance,
                lambda field=field:self._write(
                    "    "+self._declarator(field.type_ref,field.identifier.spelling)+";\n"
                ),
            )
        self._write("} "+d.identifier.spelling+";\n")
    def _render_function_signature(self,d):
        prefix="" if d.storage is CStorage.NONE else d.storage.value+" "
        self._write(prefix+self._type(d.return_type)+" "+d.identifier.spelling+"(")
        if not d.parameters:self._write("void")
        for index,p in enumerate(d.parameters):
            if index:self._write(", ")
            self._mapped(p.node_id,p.provenance,lambda p=p:self._write(self._declarator(p.type_ref,p.identifier.spelling)))
        self._write(")")
    def _render_block(self,b:CBlock)->None:
        self._mapped(b.node_id,b.provenance,lambda:self._render_block_inner(b))
    def _render_block_inner(self,b):
        self._write("{\n")
        for s in b.statements:self._render_statement(s,1)
        self._write("}\n")
    def _render_statement(self,s:CStatement,indent:int)->None:
        def inner():
            self._write("    "*indent)
            if isinstance(s,CVariableDeclaration):self._render_var(s,indent,leading=False)
            elif isinstance(s,CExpressionStatement):
                self._render_expr(s.expression); self._write(";\n")
            elif isinstance(s,CReturnStatement):
                self._write("return")
                if s.expression is not None:
                    self._write(" "); self._render_expr(s.expression)
                self._write(";\n")
            elif isinstance(s,CAssignmentStatement):
                self._render_expr(s.target); self._write(" = "); self._render_expr(s.value); self._write(";\n")
            elif isinstance(s,CIfStatement):
                self._write("if ("); self._render_expr(s.condition); self._write(")\n"); self._render_block_at(s.then_block,indent)
                if s.else_block is not None:
                    self._write("    "*indent+"else\n"); self._render_block_at(s.else_block,indent)
            elif isinstance(s,CWhileStatement):
                self._write("while ("); self._render_expr(s.condition); self._write(")\n"); self._render_block_at(s.body,indent)
            elif isinstance(s,CForStatement):
                d=s.initializer
                self._write("for (")
                self._mapped(d.node_id,d.provenance,lambda:self._render_for_initializer(d))
                self._write("; ")
                self._render_expr(s.condition); self._write("; ")
                self._mapped(s.update.node_id,s.update.provenance,lambda:self._render_assignment_fragment(s.update))
                self._write(")\n")
                self._render_block_at(s.body,indent)
            elif isinstance(s,CBreakStatement): self._write("break;\n")
            elif isinstance(s,CContinueStatement): self._write("continue;\n")
            else:raise TypeError(type(s).__name__)
        self._mapped(s.node_id,s.provenance,inner)
    def _render_block_at(self,b:CBlock,indent:int)->None:
        self._mapped(b.node_id,b.provenance,lambda:self._render_block_at_inner(b,indent))
    def _render_block_at_inner(self,b,indent):
        self._write("    "*indent+"{\n")
        for st in b.statements:self._render_statement(st,indent+1)
        self._write("    "*indent+"}\n")
    def _render_var(self,d,indent,leading=True):
        prefix="" if d.storage is CStorage.NONE else d.storage.value+" "
        self._write(prefix+self._declarator(d.type_ref,d.identifier.spelling))
        if d.initializer is not None:
            self._write(" = "); self._render_expr(d.initializer)
        self._write(";\n")
    def _render_for_initializer(self,d:CVariableDeclaration)->None:
        self._write(self._declarator(d.type_ref,d.identifier.spelling)+" = ")
        self._render_expr(d.initializer)
    def _render_assignment_fragment(self,s:CAssignmentStatement)->None:
        self._render_expr(s.target); self._write(" = "); self._render_expr(s.value)
    def _type(self,t:CType)->str:
        q=" ".join(x.value for x in t.qualifiers)
        base=(q+" " if q else "")+t.base
        return base+(" " + "*"*t.pointer_depth if t.pointer_depth else "")
    def _declarator(self,t:CType,name:str)->str:
        suffix="".join(f"[{extent}]" for extent in t.array_extents)
        rendered_type=self._type(t)
        if t.object_const:
            if t.pointer_depth:
                return rendered_type+" const "+name+suffix
            return "const "+rendered_type+" "+name+suffix
        return rendered_type+" "+name+suffix
    def _precedence(self,e:CExpression)->int:
        if isinstance(e,(CIntegerLiteral,CFloatLiteral,CBooleanLiteral,CStringLiteral,CIdentifierRef,CInitializerList,CRecordInitializer)): return 15
        if isinstance(e,(CCallExpr,CSubscriptExpr,CMemberAccessExpr)): return 14
        if isinstance(e,CUnaryExpr): return 13
        if isinstance(e,CBinaryExpr): return _PRECEDENCE[e.op]
        raise TypeError(type(e).__name__)
    def _render_expr(self,e:CExpression,parent:int=0,right_child:bool=False)->None:
        prec=self._precedence(e)
        paren=prec<parent or (right_child and prec==parent and isinstance(e,CBinaryExpr))
        def inner():
            if paren:self._write("(")
            if isinstance(e,CIntegerLiteral):self._write(str(e.value)+e.suffix)
            elif isinstance(e,CFloatLiteral):self._write(repr(e.value))
            elif isinstance(e,CBooleanLiteral):self._write("true" if e.value else "false")
            elif isinstance(e,CStringLiteral):self._write('"'+self._escape_string(e.value)+'"')
            elif isinstance(e,CIdentifierRef):self._write(self._binding_spelling(e.binding_id))
            elif isinstance(e,(CInitializerList,CRecordInitializer)):
                self._write("{")
                for i,item in enumerate(e.elements):
                    if i:self._write(", ")
                    self._render_expr(item)
                self._write("}")
            elif isinstance(e,CCallExpr):
                self._render_expr(e.callee,14);self._write("(")
                for i,a in enumerate(e.arguments):
                    if i:self._write(", ")
                    self._render_expr(a)
                self._write(")")
            elif isinstance(e,CSubscriptExpr):
                self._render_expr(e.container,14);self._write("[");self._render_expr(e.index);self._write("]")
            elif isinstance(e,CMemberAccessExpr):
                self._render_expr(e.receiver,14)
                self._write("." if e.mode is CMemberAccessMode.DIRECT else "->")
                self._write(self._binding_spelling(e.field_binding_id))
            elif isinstance(e,CUnaryExpr):
                # Parenthesize a nested unary expression so two adjacent '-'
                # tokens cannot be re-lexed by C as pre-decrement.
                self._write(e.op.value);self._render_expr(e.operand,prec+1)
            elif isinstance(e,CBinaryExpr):
                self._render_expr(e.left,prec);self._write(f" {e.op.value} ");self._render_expr(e.right,prec,True)
            else:raise TypeError(type(e).__name__)
            if paren:self._write(")")
        self._mapped(e.node_id,e.provenance,inner)
    @staticmethod
    def _escape_string(value:str)->str:
        out=[]
        for index,ch in enumerate(value):
            code=ord(ch)
            if ch=='\\': out.append('\\\\')
            elif ch=='"': out.append('\\"')
            # C11 performs trigraph replacement before tokenization. Escaping
            # every question mark prevents text such as ??/ from becoming a
            # backslash during translation phase 1.
            elif ch=='?': out.append('\\?')
            elif ch=='\n': out.append('\\n')
            elif ch=='\r': out.append('\\r')
            elif ch=='\t': out.append('\\t')
            elif 32 <= code < 127: out.append(ch)
            else:
                encoded=ch.encode('utf-8')
                next_is_hex=index+1<len(value) and value[index+1] in '0123456789abcdefABCDEF'
                for byte_index,b in enumerate(encoded):
                    # C hexadecimal escapes consume an unbounded run of hex
                    # digits.  Use a fixed-width octal escape for the final
                    # byte when the following source character is hexadecimal.
                    out.append(f"\\{b:03o}" if next_is_hex and byte_index+1==len(encoded) else f"\\x{b:02x}")
        return ''.join(out)
    def _binding_spelling(self,binding_id:str)->str:
        # populated from validated declarations before expression rendering
        return self._bindings[binding_id]
    def _mapped(self,node_id,prov,fn):
        start=(self._byte,self._line,self._column);fn();end=(self._byte,self._line,self._column)
        self._maps.append(SourceOutputMapping(node_id,prov.origin_kind,prov.source_document_id,prov.source_node_ids,prov.rule_plan_id,start[0],end[0],start[1],start[2],end[1],end[2]))
    def _write(self,text:str)->None:
        self._parts.append(text);self._byte+=len(text.encode("utf-8"))
        lines=text.split("\n")
        if len(lines)>1:self._line+=len(lines)-1;self._column=len(lines[-1])
        else:self._column+=len(text)
    def render(self,unit:CTranslationUnit)->RenderedC:
        valid=validate_translation_unit(unit)
        if not valid.accepted:raise ValueError("invalid C IR: "+"; ".join(valid.errors))
        self._bindings={}
        for d in unit.declarations:
            if isinstance(d,CRecordDefinition):
                for field in d.fields:
                    self._bindings[field.identifier.binding_id]=field.identifier.spelling
            elif isinstance(d,(CFunctionPrototype,CFunctionDefinition)):
                self._bindings[d.identifier.binding_id]=d.identifier.spelling
                for p in d.parameters:self._bindings[p.identifier.binding_id]=p.identifier.spelling
                def collect(st):
                    if isinstance(st,CVariableDeclaration): self._bindings[st.identifier.binding_id]=st.identifier.spelling
                    elif isinstance(st,CIfStatement):
                        for x in st.then_block.statements: collect(x)
                        if st.else_block:
                            for x in st.else_block.statements: collect(x)
                    elif isinstance(st,(CWhileStatement,CForStatement)):
                        if isinstance(st,CForStatement): self._bindings[st.initializer.identifier.binding_id]=st.initializer.identifier.spelling
                        for x in st.body.statements: collect(x)
                if isinstance(d,CFunctionDefinition):
                    for st in d.body.statements: collect(st)
            elif isinstance(d,CVariableDeclaration):self._bindings[d.identifier.binding_id]=d.identifier.spelling
        self._parts=[];self._maps=[];self._line=1;self._column=0;self._byte=0
        for inc in unit.includes:self._mapped(inc.node_id,inc.provenance,lambda inc=inc:self._write(f"#include <{inc.header}>\n" if inc.system else f'#include "{inc.header}"\n'))
        if unit.includes and unit.declarations:self._write("\n")
        for index,decl in enumerate(unit.declarations):
            self._render_external(decl)
            if index+1<len(unit.declarations):self._write("\n")
        return RenderedC("".join(self._parts),tuple(self._maps))
