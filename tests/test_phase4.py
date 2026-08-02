from __future__ import annotations
import json,os,subprocess,sys,unittest
from pathlib import Path
from pycforge.converter.c_output import CRenderer,validate_c_text
from pycforge.converter.ir.c_ir import *
ROOT=Path(__file__).resolve().parents[1]

def prov(node="py-source",kind="direct source conversion"):
    return CProvenance(kind,"doc-main",(node,),{"start":{"line":1,"column":0},"end":{"line":1,"column":1}},"plan-test")

def add_unit(left_expr=None,right_expr=None,name="add"):
    p=prov()
    fn=CIdentifier("bind-fn",name,p); a=CIdentifier("bind-a","a",p); b=CIdentifier("bind-b","b",p)
    ar=CIdentifierRef("c-ref-a","bind-a",p); br=CIdentifierRef("c-ref-b","bind-b",p)
    expr=CBinaryExpr("c-add",CBinaryOp.ADD,left_expr or ar,right_expr or br,p)
    body=CBlock("c-block",(CReturnStatement("c-return",expr,p),),p)
    function=CFunctionDefinition("c-fn",fn,CType("int64_t"),(CParameter("c-param-a",a,CType("int64_t"),p),CParameter("c-param-b",b,CType("int64_t"),p)),body,CStorage.NONE,p)
    builder=CTranslationUnitBuilder("c11-portable-fixed-v1",provenance=p)
    builder.add_include(CInclude("c-inc","stdint.h",True,p));builder.add_declaration(function)
    return builder.build()

class Phase4Tests(unittest.TestCase):
    def test_essential_c_ir_validates_and_matches_golden(self):
        unit=add_unit(); validation=validate_translation_unit(unit)
        self.assertTrue(validation.accepted,validation.errors)
        rendered=CRenderer().render(unit)
        self.assertEqual(rendered.text,(ROOT/"fixtures/c_ir/essential_golden.c").read_text())
        self.assertTrue(validate_c_text(rendered.text).accepted)

    def test_serialization_is_deterministic(self):
        a=json.dumps(serialize_translation_unit(add_unit()),sort_keys=True,separators=(",",":"))
        b=json.dumps(serialize_translation_unit(add_unit()),sort_keys=True,separators=(",",":"))
        self.assertEqual(a,b);self.assertIn('"schema_version":"c-ir/0.8"',a)

    def test_precedence_parentheses_are_semantic(self):
        p=prov(); ar=CIdentifierRef("x-a","bind-a",p);br=CIdentifierRef("x-b","bind-b",p)
        nested=CBinaryExpr("x-mul",CBinaryOp.MULTIPLY,CBinaryExpr("x-add",CBinaryOp.ADD,ar,br,p),CIdentifierRef("x-b2","bind-b",p),p)
        text=CRenderer().render(add_unit(left_expr=nested,right_expr=CIdentifierRef("x-a2","bind-a",p))).text
        self.assertIn("return (a + b) * b + a;",text)

    def test_right_nested_non_associative_expression_is_parenthesized(self):
        p=prov(); ar=CIdentifierRef("y-a","bind-a",p);br=CIdentifierRef("y-b","bind-b",p)
        right=CBinaryExpr("y-sub-inner",CBinaryOp.SUBTRACT,CIdentifierRef("y-a2","bind-a",p),br,p)
        outer=CBinaryExpr("y-sub-outer",CBinaryOp.SUBTRACT,ar,right,p)
        text=CRenderer().render(add_unit(left_expr=outer,right_expr=CIdentifierRef("y-b2","bind-b",p))).text
        self.assertIn("return a - (a - b) + b;",text)

    def test_structured_pointer_declarator(self):
        p=prov(); ident=CIdentifier("bind-global","items",p)
        decl=CVariableDeclaration("c-global",ident,CType("int64_t",(CQualifier.CONST,),2),None,CStorage.STATIC,p)
        builder=CTranslationUnitBuilder("c11-portable-fixed-v1",provenance=p);builder.add_include(CInclude("c-global-inc","stdint.h",True,p));builder.add_declaration(decl)
        out=CRenderer().render(builder.build()).text
        self.assertEqual(out,"#include <stdint.h>\n\nstatic const int64_t ** items;\n")

    def test_keywords_and_reserved_names_are_rejected(self):
        for name in ("return","__secret","_System","main","printf","INT64_MAX"):
            result=validate_translation_unit(add_unit(name=name))
            self.assertFalse(result.accepted,name)

    def test_unresolved_binding_is_rejected(self):
        p=prov(); missing=CIdentifierRef("c-missing","bind-missing",p)
        result=validate_translation_unit(add_unit(left_expr=missing))
        self.assertFalse(result.accepted);self.assertTrue(any("unresolved" in e for e in result.errors))

    def test_source_and_synthetic_provenance_survive_rendering(self):
        rendered=CRenderer().render(add_unit())
        mapped={m.c_node_id:m for m in rendered.mappings}
        self.assertEqual(mapped["c-return"].source_document_id,"doc-main")
        self.assertEqual(mapped["c-return"].source_node_ids,("py-source",))
        self.assertGreater(mapped["c-return"].end_byte,mapped["c-return"].start_byte)

    def test_builder_is_single_publication(self):
        b=CTranslationUnitBuilder("c11-portable-fixed-v1");b.build()
        with self.assertRaises(RuntimeError):b.build()
        missing_header=add_unit()
        missing_header=CTranslationUnit(missing_header.schema_version,missing_header.node_id,missing_header.target_contract,(),missing_header.declarations,missing_header.provenance)
        self.assertTrue(any("stdint.h" in item for item in validate_translation_unit(missing_header).errors))
        p=prov(); builder=CTranslationUnitBuilder("c11-portable-fixed-v1",provenance=p)
        builder.add_include(CInclude("bad-include","stdio.h",True,p))
        self.assertTrue(any("unregistered include" in item for item in validate_translation_unit(builder.build()).errors))

    def test_conformance_rejects_malformed_text(self):
        self.assertFalse(validate_c_text("int main(void) {\n").accepted)
        self.assertFalse(validate_c_text("int @bad;\n").accepted)
        self.assertFalse(validate_c_text("int main(void);\n").accepted)
        self.assertFalse(validate_c_text("int printf(void);\n").accepted)
        self.assertFalse(validate_c_text("int _f(void);\n").accepted)
        self.assertFalse(validate_c_text("int64_t f(void);\n").accepted)
        self.assertFalse(validate_c_text("#include <stdio.h>\nint f(void);\n").accepted)
        self.assertTrue(validate_c_text("#include <stdint.h>\nint64_t f(void);\n").accepted)

    def test_renderer_rejects_invalid_ir_instead_of_emitting_text(self):
        with self.assertRaises(ValueError):CRenderer().render(add_unit(name="while"))

    def test_cross_process_renderer_determinism(self):
        code="from tests.test_phase4 import add_unit;from pycforge.converter.c_output import CRenderer;print(CRenderer().render(add_unit()).text,end='')"
        env={**os.environ,"PYTHONPATH":str(ROOT)}
        a=subprocess.check_output([sys.executable,"-c",code],cwd=ROOT,env=env)
        b=subprocess.check_output([sys.executable,"-c",code],cwd=ROOT,env=env)
        self.assertEqual(a,b)

if __name__=="__main__":unittest.main()
