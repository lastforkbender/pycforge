from __future__ import annotations

import re
import unittest

from pycforge import (
    ConversionRequest,
    PythonToCConverter,
    ResultStatus,
    SourceBundle,
    SourceDocumentInput,
)
from pycforge.converter.c_output import validate_c_text
from pycforge.converter.contracts.configuration import (
    PHASE12_MODULE_POLICY,
    PHASE12_RENDERER,
    PHASE12_RULE_SET,
)


SCALAR_RECORD = (
    "class Sample:\n"
    "    count: int\n"
    "    ratio: float\n"
    "    enabled: bool\n"
    "    def __init__(self, count: int, ratio: float, enabled: bool) -> None:\n"
    "        self.count = count\n"
    "        self.ratio = ratio\n"
    "        self.enabled = enabled\n"
)

POINT_RECORD = (
    "class Point:\n"
    "    x: int\n"
    "    def __init__(self, x: int) -> None:\n"
    "        self.x = x\n"
)


def convert(source: str):
    return PythonToCConverter().convert(ConversionRequest.from_source(source))


def table(payload: object, table_id: str) -> dict:
    return next(
        item
        for item in payload["fact_tables"]  # type: ignore[index]
        if item["table_id"] == table_id
    )


def kinds(value: object, kind: str) -> list[dict]:
    found: list[dict] = []
    if isinstance(value, dict):
        if value.get("kind") == kind:
            found.append(value)
        for item in value.values():
            found.extend(kinds(item, kind))
    elif isinstance(value, (list, tuple)):
        for item in value:
            found.extend(kinds(item, kind))
    return found


class Phase13EndToEndTests(unittest.TestCase):
    def assert_converted(self, result) -> dict:
        self.assertEqual(result.status, ResultStatus.CONVERTED, result.diagnostics)
        self.assertEqual(result.diagnostics, ())
        self.assertIsNotNone(result.generated_c)
        self.assertIsNotNone(result.stage_artifact)
        assert result.generated_c is not None
        assert result.stage_artifact is not None
        self.assertTrue(validate_c_text(result.generated_c).accepted)
        self.assertEqual(result.stage_artifact.kind, "generated_c")
        self.assertEqual(result.stage_artifact.schema_version, "0.14.3")
        self.assertEqual(result.stage_artifact.payload["schema_version"], "generated-c/0.14.3")
        self.assertEqual(result.stage_artifact.payload["c_ir_schema"], "c-ir/0.14.3")
        return result.stage_artifact.payload

    def assert_rejected(self, source: str, code: str) -> None:
        result = convert(source)
        self.assertEqual(result.status, ResultStatus.REJECTED)
        self.assertIsNone(result.generated_c)
        self.assertEqual([item.code for item in result.diagnostics], [code])

    def test_scalar_records_are_real_const_automatic_structs(self) -> None:
        source = SCALAR_RECORD + (
            "\n"
            "def read_count() -> int:\n"
            "    sample = Sample(7, 1.5, True)\n"
            "    return sample.count\n"
            "\n"
            "def read_ratio() -> float:\n"
            "    sample = Sample(7, 1.5, True)\n"
            "    return sample.ratio\n"
            "\n"
            "def read_enabled() -> bool:\n"
            "    sample = Sample(7, 1.5, True)\n"
            "    return sample.enabled\n"
        )
        result = convert(source)
        payload = self.assert_converted(result)
        generated = result.generated_c or ""

        self.assertIn("typedef struct Sample {", generated)
        self.assertRegex(generated, r"\bint64_t count(?:_\d+)?;")
        self.assertRegex(generated, r"\bdouble ratio(?:_\d+)?;")
        self.assertRegex(generated, r"\bbool enabled(?:_\d+)?;")
        self.assertEqual(len(re.findall(r"\bconst Sample sample(?:_\d+)? = \{", generated)), 3)
        self.assertEqual(len(re.findall(r"return sample(?:_\d+)?\.count(?:_\d+)?;", generated)), 1)
        self.assertEqual(len(re.findall(r"return sample(?:_\d+)?\.ratio(?:_\d+)?;", generated)), 1)
        self.assertEqual(len(re.findall(r"return sample(?:_\d+)?\.enabled(?:_\d+)?;", generated)), 1)

        c_ir = payload["c_ir"]
        self.assertEqual(c_ir["kind"], "CTranslationUnit")
        self.assertEqual(c_ir["schema_version"], "c-ir/0.14.3")
        self.assertEqual(len(kinds(c_ir, "CRecordDefinition")), 1)
        self.assertEqual(len(kinds(c_ir, "CRecordField")), 3)
        self.assertEqual(len(kinds(c_ir, "CRecordInitializer")), 3)
        accesses = kinds(c_ir, "CMemberAccessExpr")
        self.assertEqual(len(accesses), 3)
        self.assertEqual({item["mode"] for item in accesses}, {"direct"})
        object_declarations = [
            item
            for item in kinds(c_ir, "CVariableDeclaration")
            if item["type_ref"]["base"] == "Sample"
        ]
        self.assertEqual(len(object_declarations), 3)
        self.assertTrue(
            all(item["type_ref"]["qualifiers"] == ["const"] for item in object_declarations)
        )

        definitions = table(payload, "record-definition-facts")["records"]
        fields = table(payload, "record-field-facts")["records"]
        instances = table(payload, "record-instance-facts")["records"]
        bindings = table(payload, "record-binding-facts")["records"]
        self.assertEqual(len(definitions), 1)
        self.assertEqual(
            [item["value"]["category"] for item in fields],
            ["integer-like", "floating-like", "boolean-like"],
        )
        self.assertEqual(len(instances), 3)
        self.assertTrue(all(item["value"]["allocation_model"] == "none" for item in instances))
        self.assertTrue(all(item["value"]["cleanup_model"] == "none" for item in instances))
        self.assertTrue(all(item["value"]["noalias"] for item in bindings))
        self.assertTrue(all(not item["value"]["escapes"] for item in bindings))

        self.assertEqual(payload["helper_requirements"], [])
        self.assertEqual(payload["helper_manifest"], [])
        self.assertEqual(result.conversion_summary["helpers"], [])
        for forbidden in ("malloc", "calloc", "realloc", "free", "NULL", "->"):
            self.assertNotIn(forbidden, generated)

    def test_constructor_arguments_are_staged_left_to_right_exactly_once(self) -> None:
        source = (
            "class Pair:\n"
            "    left: int\n"
            "    right: int\n"
            "    def __init__(self, left: int, right: int) -> None:\n"
            "        self.left = left\n"
            "        self.right = right\n"
            "\n"
            "def first() -> int:\n"
            "    return 1\n"
            "\n"
            "def second() -> int:\n"
            "    return 2\n"
            "\n"
            "def run() -> int:\n"
            "    pair = Pair(first(), second())\n"
            "    return pair.left + pair.right\n"
        )
        result = convert(source)
        payload = self.assert_converted(result)
        generated = result.generated_c or ""

        first_call = generated.index("= first();")
        second_call = generated.index("= second();")
        aggregate = generated.index("const Pair pair = {")
        self.assertLess(first_call, second_call)
        self.assertLess(second_call, aggregate)
        self.assertEqual(generated.count("= first();"), 1)
        self.assertEqual(generated.count("= second();"), 1)
        self.assertEqual(len(re.findall(r"int64_t pycf_record_arg_[a-f0-9]+ =", generated)), 2)

        initializer = table(payload, "record-initializer-facts")["records"][0]["value"]
        instance = table(payload, "record-instance-facts")["records"][0]["value"]
        self.assertEqual(
            initializer["evaluation_order"],
            "field-declaration-order-left-to-right-once",
        )
        self.assertEqual(len(instance["argument_node_ids"]), 2)
        record_initializer = kinds(payload["c_ir"], "CRecordInitializer")[0]
        self.assertEqual(len(record_initializer["elements"]), 2)

    def test_repeated_conversion_is_byte_and_artifact_deterministic(self) -> None:
        source = SCALAR_RECORD + (
            "\ndef run() -> int:\n"
            "    sample = Sample(9, 2.0, False)\n"
            "    return sample.count\n"
        )
        first = convert(source)
        second = convert(source)
        self.assert_converted(first)
        self.assert_converted(second)
        self.assertEqual(first.generated_c, second.generated_c)
        self.assertEqual(first.output_fingerprint, second.output_fingerprint)
        self.assertEqual(
            first.stage_artifact.artifact_fingerprint,
            second.stage_artifact.artifact_fingerprint,
        )
        self.assertEqual(first.stage_artifact.payload["c_ir"], second.stage_artifact.payload["c_ir"])
        self.assertEqual(first.conversion_summary, second.conversion_summary)

    def test_uninstantiated_and_multiple_record_definitions_have_closed_order(self) -> None:
        unused = convert(
            POINT_RECORD
            + "\ndef run() -> int:\n"
            + "    return 1\n"
        )
        unused_payload = self.assert_converted(unused)
        self.assertIn("typedef struct Point {", unused.generated_c or "")
        self.assertEqual(
            table(unused_payload, "record-instance-facts")["records"],
            [],
        )
        self.assertEqual(len(kinds(unused_payload["c_ir"], "CRecordDefinition")), 1)
        self.assertEqual(len(kinds(unused_payload["c_ir"], "CRecordInitializer")), 0)

        source = (
            "class Zed:\n"
            "    z: int\n"
            "    def __init__(self, z: int) -> None:\n"
            "        self.z = z\n"
            "\n"
            "class Alpha:\n"
            "    a: int\n"
            "    def __init__(self, a: int) -> None:\n"
            "        self.a = a\n"
            "\n"
            "def run() -> int:\n"
            "    z = Zed(1)\n"
            "    a = Alpha(2)\n"
            "    return z.z + a.a\n"
        )
        result = convert(source)
        payload = self.assert_converted(result)
        record_facts = table(payload, "record-definition-facts")["records"]
        self.assertEqual([item["key"] for item in record_facts], sorted(item["key"] for item in record_facts))
        declarations = payload["c_ir"]["declarations"]
        record_declarations = [item for item in declarations if item["kind"] == "CRecordDefinition"]
        self.assertEqual(len(record_declarations), 2)
        self.assertEqual(
            [item["identifier"]["binding_id"] for item in record_declarations],
            [item["value"]["class_binding_id"] for item in record_facts],
        )
        first_non_record = next(index for index, item in enumerate(declarations) if item["kind"] != "CRecordDefinition")
        self.assertEqual(first_non_record, 2)
        rendered_order = [
            (result.generated_c or "").index(f"typedef struct {item['identifier']['spelling']} {{")
            for item in record_declarations
        ]
        self.assertEqual(rendered_order, sorted(rendered_order))

    def test_multi_document_records_remain_module_local(self) -> None:
        def document(class_name: str, value: int, function_name: str) -> str:
            return (
                f"class {class_name}:\n"
                "    value: int\n"
                "    def __init__(self, value: int) -> None:\n"
                "        self.value = value\n"
                "\n"
                f"def {function_name}() -> int:\n"
                f"    item = {class_name}({value})\n"
                "    return item.value\n"
            )

        request = ConversionRequest(
            SourceBundle(
                SourceDocumentInput("app.py", document("AppBox", 1, "run"), "app"),
                (SourceDocumentInput("lib.py", document("LibBox", 2, "helper"), "lib"),),
            )
        )
        result = PythonToCConverter().convert(request)
        payload = self.assert_converted(result)
        definitions = [
            item["value"] for item in table(payload, "record-definition-facts")["records"]
        ]
        self.assertEqual(
            {(item["module_id"], item["source_name"]) for item in definitions},
            {("app", "AppBox"), ("lib", "LibBox")},
        )
        self.assertEqual(len({item["class_binding_id"] for item in definitions}), 2)
        self.assertTrue(all(item["flattened_name"].startswith("pycm_") for item in definitions))
        self.assertTrue(all(f"__{item['module_id']}__" in item["flattened_name"] for item in definitions))
        self.assertEqual(payload["c_ir"]["module_order"], ["app", "lib"])
        self.assertEqual(len(kinds(payload["c_ir"], "CRecordDefinition")), 2)
        self.assertEqual(len(kinds(payload["c_ir"], "CRecordInitializer")), 2)

    def test_c_reserved_and_library_names_are_safely_planned(self) -> None:
        source = (
            "class printf:\n"
            "    switch: int\n"
            "    def __init__(self, switch: int) -> None:\n"
            "        self.switch = switch\n"
            "\n"
            "def run() -> int:\n"
            "    value = printf(1)\n"
            "    return value.switch\n"
        )
        result = convert(source)
        payload = self.assert_converted(result)
        generated = result.generated_c or ""
        record = kinds(payload["c_ir"], "CRecordDefinition")[0]
        record_name = record["identifier"]["spelling"]
        field_name = record["fields"][0]["identifier"]["spelling"]

        self.assertNotEqual(record_name, "printf")
        self.assertNotEqual(field_name, "switch")
        self.assertRegex(record_name, r"^[A-Za-z_][A-Za-z0-9_]*$")
        self.assertRegex(field_name, r"^[A-Za-z_][A-Za-z0-9_]*$")
        self.assertIn(f"typedef struct {record_name} {{", generated)
        self.assertIn(f"int64_t {field_name};", generated)
        self.assertIn(f"value.{field_name}", generated)
        self.assertTrue(validate_c_text(generated).accepted)

    def test_each_static_record_boundary_has_a_stable_diagnostic(self) -> None:
        cases = {
            "PYC3601": (
                "class Point(Base):\n"
                "    x: int\n"
                "    def __init__(self, x: int) -> None:\n"
                "        self.x = x\n"
                "\ndef run() -> int:\n"
                "    return 1\n"
            ),
            "PYC3602": (
                "class Point:\n"
                "    x: str\n"
                "    def __init__(self, x: str) -> None:\n"
                "        self.x = x\n"
                "\ndef run() -> int:\n"
                "    return 1\n"
            ),
            "PYC3603": (
                "class Point:\n"
                "    x: int\n"
                "    def __init__(self, x: int) -> int:\n"
                "        self.x = x\n"
                "\ndef run() -> int:\n"
                "    return 1\n"
            ),
            "PYC3604": POINT_RECORD
            + "    def get(self) -> int:\n"
            + "        return self.x\n"
            + "\ndef run() -> int:\n"
            + "    return 1\n",
            "PYC3605": POINT_RECORD
            + "\ndef run() -> int:\n"
            + "    point = Point(x=1)\n"
            + "    return point.x\n",
            "PYC3606": POINT_RECORD
            + "\ndef run() -> int:\n"
            + "    point = Point(1)\n"
            + "    alias = point\n"
            + "    return point.x\n",
            "PYC3607": POINT_RECORD
            + "\ndef run() -> int:\n"
            + "    point = Point(1)\n"
            + "    point.x = 2\n"
            + "    return point.x\n",
        }
        for code, source in cases.items():
            with self.subTest(code=code):
                self.assert_rejected(source, code)

    def test_record_binding_proof_failures_are_user_diagnostics_not_internal_failures(self) -> None:
        before_construction = POINT_RECORD + (
            "\ndef run() -> int:\n"
            "    value = point.x\n"
            "    point = Point(1)\n"
            "    return value\n"
        )
        shadowed_constructor = POINT_RECORD + (
            "\ndef run(Point: int) -> int:\n"
            "    point = Point(1)\n"
            "    return point.x\n"
        )
        for source in (before_construction, shadowed_constructor):
            with self.subTest(source=source[-80:]):
                self.assert_rejected(source, "PYC3606")

    def test_companion_module_record_diagnostics_keep_companion_identity(self) -> None:
        primary = "def run() -> int:\n    return 1\n"
        companion_bad_arity = POINT_RECORD + (
            "\ndef bad() -> int:\n"
            "    point = Point()\n"
            "    return 1\n"
        )
        companion_mutation = POINT_RECORD + (
            "\ndef bad() -> int:\n"
            "    point = Point(1)\n"
            "    point.x = 2\n"
            "    return point.x\n"
        )
        for source, code in (
            (companion_bad_arity, "PYC3605"),
            (companion_mutation, "PYC3607"),
        ):
            result = PythonToCConverter().convert(
                ConversionRequest(
                    SourceBundle(
                        SourceDocumentInput("main.py", primary, "main"),
                        (SourceDocumentInput("companion.py", source, "companion"),),
                    )
                )
            )
            with self.subTest(code=code):
                self.assertEqual(result.status, ResultStatus.REJECTED)
                self.assertEqual([item.code for item in result.diagnostics], [code])
                diagnostic = result.diagnostics[0]
                self.assertEqual(diagnostic.source_module_id, "companion")
                self.assertEqual(diagnostic.source_logical_name, "companion.py")
                self.assertTrue(diagnostic.source_span["document_id"].startswith("src-"))

    def test_cross_module_records_reject_and_phase12_stays_historical(self) -> None:
        app = (
            "from records import Point\n"
            "\ndef run() -> int:\n"
            "    point = Point(1)\n"
            "    return point.x\n"
        )
        records = POINT_RECORD + (
            "\ndef local() -> int:\n"
            "    point = Point(2)\n"
            "    return point.x\n"
        )
        cross_module = PythonToCConverter().convert(
            ConversionRequest(
                SourceBundle(
                    SourceDocumentInput("app.py", app, "app"),
                    (SourceDocumentInput("records.py", records, "records"),),
                )
            )
        )
        self.assertEqual(cross_module.status, ResultStatus.REJECTED)
        self.assertEqual([item.code for item in cross_module.diagnostics], ["PYC3610"])
        self.assertEqual(cross_module.diagnostics[0].stage, "modules.resolve")

        phase12 = dict(
            rule_set_version=PHASE12_RULE_SET,
            renderer_version=PHASE12_RENDERER,
            module_policy_version=PHASE12_MODULE_POLICY,
        )
        historical = PythonToCConverter().convert(
            ConversionRequest.from_source("def run() -> int:\n    return 1\n", **phase12)
        )
        self.assertEqual(historical.status, ResultStatus.CONVERTED)
        self.assertEqual(historical.stage_artifact.schema_version, "0.12")
        self.assertEqual(historical.stage_artifact.payload["schema_version"], "generated-c/0.12")
        self.assertEqual(historical.stage_artifact.payload["c_ir_schema"], "c-ir/0.12")
        self.assertNotIn("record_policy_version", historical.stage_artifact.payload)
        self.assertEqual(
            historical.conversion_summary["schema_version"],
            "pycforge.conversion-summary/0.12",
        )

        historical_class = PythonToCConverter().convert(
            ConversionRequest.from_source(
                POINT_RECORD + "\ndef run() -> int:\n    return 1\n",
                **phase12,
            )
        )
        self.assertEqual(historical_class.status, ResultStatus.REJECTED)
        self.assertIsNone(historical_class.generated_c)
        self.assertEqual([item.code for item in historical_class.diagnostics], ["PYC3509"])
        self.assertNotEqual(historical_class.diagnostics[0].code[:6], "PYC360")


if __name__ == "__main__":
    unittest.main()
