from __future__ import annotations

from copy import deepcopy
import unittest
from unittest.mock import patch

from pycforge import ConversionRequest, PythonToCConverter, ResultStatus
from pycforge.converter.analysis.symbols import SymbolScopeAnalyzer
from pycforge.converter.core.cancellation import CancellationToken
from pycforge.converter.frontend.normalizer import PythonNormalizer
from pycforge.converter.frontend.parser import Python311ParserAdapter
from pycforge.converter.frontend.source_document import SourceDocument
from pycforge.converter.records import (
    MAX_RECORD_FIELDS,
    RecordAnalysisCanceled,
    RecordAnalysisError,
    StaticRecordAnalyzer,
)


RECORD = (
    "class Point:\n"
    "    x: int\n"
    "    y: int\n"
    "    def __init__(self, x: int, y: int) -> None:\n"
    "        self.x = x\n"
    "        self.y = y\n"
)


def normalized(source: str) -> dict:
    document = SourceDocument.create("app.py", source)
    tree = Python311ParserAdapter().parse(document, "3.11")
    return PythonNormalizer().normalize(tree, document).to_dict()


def analyzed(source: str, **options: object):
    module = normalized(source)
    _, bindings, _ = SymbolScopeAnalyzer().analyze(module, allow_records=True)
    return StaticRecordAnalyzer(
        module,
        bindings=tuple(item.to_dict() for item in bindings),
        default_module_id="app",
        default_logical_name="app.py",
        **options,
    ).analyze()


def rejection(source: str, **options: object) -> RecordAnalysisError:
    with unittest.TestCase().assertRaises(RecordAnalysisError) as caught:
        analyzed(source, **options)
    return caught.exception


class Phase13RecordAnalysisTests(unittest.TestCase):
    def test_cancellation_is_not_reported_as_a_record_rejection(self):
        module = normalized(RECORD + "\ndef run() -> int:\n    point = Point(1, 2)\n    return point.x\n")
        token = CancellationToken()
        token.cancel()
        with self.assertRaises(RecordAnalysisCanceled):
            StaticRecordAnalyzer(module, cancellation=token).analyze()

    def test_both_analysis_passes_cancel_without_publishing_a_partial_plan(self):
        source = RECORD + "\ndef run() -> int:\n    point = Point(1, 2)\n    return point.x\n"
        from pycforge.converter.analysis import stage as analysis_stage

        real_analyzer = analysis_stage.StaticRecordAnalyzer
        for cancel_on_pass in (1, 2):
            with self.subTest(cancel_on_pass=cancel_on_pass):
                class CancelOnPass(real_analyzer):
                    calls = 0

                    def __init__(self, *args, **kwargs):
                        type(self).calls += 1
                        if type(self).calls == cancel_on_pass:
                            kwargs["cancellation"].cancel()
                        super().__init__(*args, **kwargs)

                token = CancellationToken()
                with patch.object(analysis_stage, "StaticRecordAnalyzer", CancelOnPass):
                    result = PythonToCConverter().convert(
                        ConversionRequest.from_source(source),
                        cancellation=token,
                    )
                self.assertEqual(result.status, ResultStatus.CANCELED)
                self.assertEqual(CancelOnPass.calls, cancel_on_pass)
                self.assertIsNone(result.generated_c)
                self.assertEqual(result.stage_artifact.kind, "python_ir")
                self.assertFalse(
                    any(item.code.startswith("PYC36") for item in result.diagnostics)
                )
                self.assertEqual({item.code for item in result.diagnostics}, {"PYC1901"})

    def test_accepts_exact_record_and_publishes_closed_facts(self):
        source = RECORD + (
            "\n"
            "def run() -> int:\n"
            "    point = Point(10, 20)\n"
            "    return point.x + point.y\n"
        )
        first = analyzed(source)
        second = analyzed(source)
        self.assertEqual(first.to_dict(), second.to_dict())
        self.assertEqual(len(first.definitions), 1)
        self.assertEqual([item.source_name for item in first.fields], ["x", "y"])
        self.assertEqual([item.field_name for item in first.accesses], ["x", "y"])
        definition = first.definitions[0]
        instance = first.instances[0]
        binding = first.bindings[0]
        self.assertEqual(definition.module_id, "app")
        self.assertEqual(definition.logical_name, "app.py")
        self.assertEqual(definition.ownership_model, "unique-lexical-owner")
        self.assertEqual(definition.lifetime_model, "enclosing-function-activation")
        self.assertEqual(definition.aliasing_model, "forbidden")
        self.assertEqual(definition.cleanup_model, "none")
        self.assertEqual(definition.nullability_model, "non-null-by-construction")
        self.assertFalse(definition.mutable)
        self.assertEqual(instance.storage_model, "automatic-inline-record")
        self.assertEqual(instance.allocation_model, "none")
        self.assertEqual(instance.ownership_model, "unique-lexical-owner")
        self.assertFalse(instance.mutable)
        self.assertTrue(binding.single_assignment)
        self.assertTrue(binding.noalias)
        self.assertFalse(binding.escapes)
        self.assertTrue(all(item.statically_bound for item in first.accesses))

    def test_accepts_all_approved_field_categories_and_parameter_arguments(self):
        source = (
            "class Sample:\n"
            "    count: int\n"
            "    ratio: float\n"
            "    enabled: bool\n"
            "    def __init__(self, count: int, ratio: float, enabled: bool) -> None:\n"
            "        self.count = count\n"
            "        self.ratio = ratio\n"
            "        self.enabled = enabled\n"
            "\n"
            "def run(count: int, ratio: float, enabled: bool) -> float:\n"
            "    sample = Sample(count, ratio, enabled)\n"
            "    return sample.ratio\n"
        )
        result = analyzed(source)
        self.assertEqual(
            [item.category.value for item in result.fields],
            ["integer-like", "floating-like", "boolean-like"],
        )
        self.assertEqual(result.accesses[0].field_category.value, "floating-like")

    def test_accepts_prior_record_field_read_as_scalar_constructor_argument(self):
        source = RECORD + (
            "\ndef run() -> int:\n"
            "    first = Point(1, 2)\n"
            "    second = Point(first.x, first.y)\n"
            "    return second.x\n"
        )
        result = analyzed(source)
        self.assertEqual(len(result.instances), 2)
        self.assertEqual(sorted(item.field_name for item in result.accesses), ["x", "x", "y"])

    def test_module_qualified_names_resolve_without_losing_source_name(self):
        source = RECORD + "\ndef run() -> int:\n    point = Point(1, 2)\n    return point.x\n"
        module = normalized(source)
        class_node = next(item for item in module["nodes"] if item["kind"] == "ClassDef")
        function_node = next(
            item
            for item in module["nodes"]
            if item["kind"] == "FunctionDef" and item["fields"]["name"] == "run"
        )
        qualified = "pycm_app_Point"
        rewritten = deepcopy(module)
        rewritten_class = next(
            item for item in rewritten["nodes"] if item["node_id"] == class_node["node_id"]
        )
        rewritten_class["fields"]["name"] = qualified
        for item in rewritten["nodes"]:
            if item["kind"] == "Name" and item["fields"].get("id") == "Point":
                item["fields"]["id"] = qualified
        _, bindings, _ = SymbolScopeAnalyzer().analyze(rewritten, allow_records=True)
        result = StaticRecordAnalyzer(
            rewritten,
            module_records={
                class_node["node_id"]: {
                    "source_name": "Point",
                    "flattened_name": qualified,
                    "module_id": "app",
                    "document_id": rewritten_class["provenance"]["source_span"]["document_id"],
                    "logical_name": "app.py",
                }
            },
            function_records={
                function_node["node_id"]: {
                    "module_id": "app",
                    "document_id": function_node["provenance"]["source_span"]["document_id"],
                    "logical_name": "app.py",
                }
            },
            bindings=tuple(item.to_dict() for item in bindings),
        ).analyze()
        self.assertEqual(result.definitions[0].source_name, "Point")
        self.assertEqual(result.definitions[0].flattened_name, qualified)
        self.assertEqual(len(result.instances), 1)

    def test_rejects_class_object_model_features_and_nested_classes(self):
        cases = {
            "class Point(Base):\n    x: int\n    def __init__(self, x: int) -> None:\n        self.x = x\n": "PYC3601",
            "@decorate\nclass Point:\n    x: int\n    def __init__(self, x: int) -> None:\n        self.x = x\n": "PYC3601",
            "def outer() -> int:\n    class Point:\n        x: int\n        def __init__(self, x: int) -> None:\n            self.x = x\n    return 1\n": "PYC3601",
        }
        for source, code in cases.items():
            with self.subTest(code=code):
                self.assertEqual(rejection(source).code, code)

    def test_rejects_invalid_field_shapes_types_duplicates_and_capacity(self):
        too_many = "\n".join(f"    f{index}: int" for index in range(MAX_RECORD_FIELDS + 1))
        params = ", ".join(f"f{index}: int" for index in range(MAX_RECORD_FIELDS + 1))
        copies = "\n".join(f"        self.f{index} = f{index}" for index in range(MAX_RECORD_FIELDS + 1))
        cases = (
            "class Point:\n    x: int = 1\n    def __init__(self, x: int) -> None:\n        self.x = x\n",
            "class Point:\n    x: str\n    def __init__(self, x: str) -> None:\n        self.x = x\n",
            "class Point:\n    x: int\n    x: int\n    def __init__(self, x: int, x2: int) -> None:\n        self.x = x\n        self.x = x2\n",
            f"class Huge:\n{too_many}\n    def __init__(self, {params}) -> None:\n{copies}\n",
        )
        for source in cases:
            with self.subTest(source=source[:30]):
                self.assertEqual(rejection(source).code, "PYC3602")

    def test_rejects_non_exact_initializers(self):
        cases = (
            RECORD.replace("-> None", "-> int"),
            RECORD.replace("self.x = x\n        self.y = y", "self.y = y\n        self.x = x"),
            RECORD.replace("self.y = y", "self.y = x"),
            RECORD.replace("        self.y = y\n", "        self.y = y\n        x = 1\n"),
            RECORD.replace("x: int, y: int", "y: int, x: int"),
        )
        for source in cases:
            with self.subTest(source=source[-50:]):
                self.assertEqual(rejection(source).code, "PYC3603")

    def test_rejects_additional_methods_with_stable_code(self):
        source = RECORD + "    def total(self) -> int:\n        return self.x + self.y\n"
        error = rejection(source)
        self.assertEqual(error.code, "PYC3604")
        self.assertIn("other methods", error.message)

    def test_rejects_non_direct_and_mismatched_construction(self):
        cases = {
            RECORD + "\ndef run(flag: bool) -> int:\n    if flag:\n        point = Point(1, 2)\n    return 1\n": "PYC3605",
            RECORD + "\ndef run() -> int:\n    point = Point(x=1, y=2)\n    return point.x\n": "PYC3605",
            RECORD + "\ndef run() -> int:\n    point = Point(1.0, 2)\n    return point.x\n": "PYC3605",
            RECORD + "\ndef run() -> int:\n    return Point(1, 2).x\n": "PYC3605",
        }
        for source, code in cases.items():
            with self.subTest(source=source[-60:]):
                self.assertEqual(rejection(source).code, code)

    def test_rejects_alias_rebind_escape_container_truth_and_identity_uses(self):
        suffixes = (
            "    alias = point\n    return point.x\n",
            "    point = Point(3, 4)\n    return point.x\n",
            "    return point\n",
            "    sink(point)\n    return 1\n",
            "    values = [point]\n    return 1\n",
            "    if point:\n        return 1\n    return 0\n",
            "    return 1 if point is point else 0\n",
        )
        for suffix in suffixes:
            source = RECORD + "\ndef run() -> int:\n    point = Point(1, 2)\n" + suffix
            with self.subTest(suffix=suffix.strip()):
                self.assertEqual(rejection(source).code, "PYC3606")

    def test_rejects_object_annotations_and_indirect_constructor_values(self):
        annotation = RECORD + "\ndef inspect(point: Point) -> int:\n    return 1\n"
        forward = RECORD + "\ndef inspect(point: \"Point\") -> int:\n    return 1\n"
        returned = RECORD + "\ndef inspect() -> Point:\n    return Point(1, 2)\n"
        indirect = RECORD + "\ndef run() -> int:\n    factory = Point\n    return 1\n"
        self.assertEqual(rejection(annotation).code, "PYC3606")
        self.assertEqual(rejection(forward).code, "PYC3606")
        self.assertEqual(rejection(returned).code, "PYC3606")
        self.assertEqual(rejection(indirect).code, "PYC3606")

    def test_rejects_nested_scope_capture(self):
        source = RECORD + (
            "\ndef run() -> int:\n"
            "    point = Point(1, 2)\n"
            "    def nested() -> int:\n"
            "        return point.x\n"
            "    return 1\n"
        )
        self.assertEqual(rejection(source).code, "PYC3606")

    def test_rejects_lambda_and_comprehension_capture(self):
        suffixes = (
            "    callback = lambda: point.x\n    return 1\n",
            "    values = [point.x for _ in [1]]\n    return 1\n",
            "    values = (point.x for _ in [1])\n    return 1\n",
        )
        for suffix in suffixes:
            source = RECORD + "\ndef run() -> int:\n    point = Point(1, 2)\n" + suffix
            with self.subTest(suffix=suffix.strip()):
                self.assertEqual(rejection(source).code, "PYC3606")

    def test_rejects_field_mutation_unknown_and_dynamic_access(self):
        suffixes = (
            "    point.x = 3\n    return point.x\n",
            "    del point.x\n    return 1\n",
            "    return point.missing\n",
            "    return getattr(point, \"x\")\n",
            "    return point.x.real\n",
        )
        for suffix in suffixes:
            source = RECORD + "\ndef run() -> int:\n    point = Point(1, 2)\n" + suffix
            with self.subTest(suffix=suffix.strip()):
                self.assertEqual(rejection(source).code, "PYC3607")

    def test_rejects_field_read_before_construction(self):
        source = RECORD + (
            "\ndef run() -> int:\n"
            "    value = point.x\n"
            "    point = Point(1, 2)\n"
            "    return value\n"
        )
        error = rejection(source)
        self.assertEqual(error.code, "PYC3606")
        self.assertIn("before construction", error.message)

    def test_constructor_resolution_uses_the_class_binding_not_spelling(self):
        cases = (
            RECORD
            + "\ndef run(Point: int) -> int:\n"
            + "    point = Point(1, 2)\n"
            + "    return point.x\n",
            RECORD
            + "\ndef run() -> int:\n"
            + "    def Point(x: int, y: int) -> int:\n"
            + "        return x + y\n"
            + "    point = Point(1, 2)\n"
            + "    return point.x\n",
        )
        for source in cases:
            with self.subTest(source=source[-90:]):
                error = rejection(source)
                self.assertEqual(error.code, "PYC3606")
                self.assertIn("lexical class binding", error.message)

    def test_rejects_every_owner_scope_rebinding_surface(self):
        suffixes = (
            "    global point\n"
            "    point = Point(1, 2)\n"
            "    return point.x\n",
            "    point = Point(1, 2)\n"
            "    try:\n"
            "        value = 1\n"
            "    except Exception as point:\n"
            "        value = 2\n"
            "    return value\n",
            "    point = Point(1, 2)\n"
            "    def point() -> int:\n"
            "        return 1\n"
            "    return 1\n",
            "    point = Point(1, 2)\n"
            "    match 1:\n"
            "        case point:\n"
            "            value = 1\n"
            "    return value\n",
            "    point = Point(1, 2)\n"
            "    import support as point\n"
            "    return 1\n",
        )
        for suffix in suffixes:
            source = RECORD + "\ndef run() -> int:\n" + suffix
            with self.subTest(suffix=suffix):
                self.assertEqual(rejection(source).code, "PYC3606")

    def test_rejects_context_manager_field_store_and_constructor_type_comment(self):
        field_store = RECORD + (
            "\ndef run() -> int:\n"
            "    point = Point(1, 2)\n"
            "    with manager() as point.x:\n"
            "        return 1\n"
        )
        typed_constructor = RECORD + (
            "\ndef run() -> int:\n"
            "    point = Point(1, 2)  # type: Point\n"
            "    return point.x\n"
        )
        self.assertEqual(rejection(field_store).code, "PYC3607")
        self.assertEqual(rejection(typed_constructor).code, "PYC3605")

    def test_class_spelling_is_legal_for_a_scalar_field_and_parameter(self):
        source = (
            "class Alpha:\n"
            "    Alpha: int\n"
            "    def __init__(self, Alpha: int) -> None:\n"
            "        self.Alpha = Alpha\n"
            "\n"
            "def run() -> int:\n"
            "    value = Alpha(7)\n"
            "    return value.Alpha\n"
        )
        result = analyzed(source)
        self.assertEqual([item.source_name for item in result.fields], ["Alpha"])
        self.assertEqual([item.field_name for item in result.accesses], ["Alpha"])

    def test_rejects_python_dunder_descriptor_field_names(self):
        for name in ("__class__", "__dict__", "__weakref__", "__custom__"):
            source = (
                "class Unsafe:\n"
                f"    {name}: int\n"
                f"    def __init__(self, {name}: int) -> None:\n"
                f"        self.{name} = {name}\n"
            )
            with self.subTest(name=name):
                self.assertEqual(rejection(source).code, "PYC3602")

    def test_rejects_record_names_that_shadow_annotation_builtins(self):
        for name in ("int", "float", "bool", "str"):
            source = (
                f"class {name}:\n"
                "    value: int\n"
                "    def __init__(self, value: int) -> None:\n"
                "        self.value = value\n"
            )
            with self.subTest(name=name):
                self.assertEqual(rejection(source).code, "PYC3601")

    def test_rejects_cross_module_construction(self):
        source = RECORD + "\ndef run() -> int:\n    point = Point(1, 2)\n    return point.x\n"
        module = normalized(source)
        class_node = next(item for item in module["nodes"] if item["kind"] == "ClassDef")
        function_node = next(
            item
            for item in module["nodes"]
            if item["kind"] == "FunctionDef" and item["fields"]["name"] == "run"
        )
        analyzer = StaticRecordAnalyzer(
            module,
            module_records={
                class_node["node_id"]: {
                    "source_name": "Point",
                    "flattened_name": "Point",
                    "module_id": "records",
                    "document_id": class_node["provenance"]["source_span"]["document_id"],
                    "logical_name": "records.py",
                }
            },
            function_records={
                function_node["node_id"]: {
                    "module_id": "app",
                    "document_id": function_node["provenance"]["source_span"]["document_id"],
                    "logical_name": "app.py",
                }
            },
        )
        with self.assertRaises(RecordAnalysisError) as caught:
            analyzer.analyze()
        self.assertEqual(caught.exception.code, "PYC3608")

    def test_typed_rejection_carries_source_and_module_identity(self):
        error = rejection(
            "class Point:\n    x: str\n    def __init__(self, x: str) -> None:\n        self.x = x\n"
        )
        payload = error.to_dict()
        self.assertEqual(payload["code"], "PYC3602")
        self.assertEqual(payload["module_id"], "app")
        self.assertEqual(payload["logical_name"], "app.py")
        self.assertTrue(payload["document_id"].startswith("src-"))
        self.assertIsNotNone(payload["source_span"])
        self.assertTrue(payload["node_id"].startswith("py-"))


if __name__ == "__main__":
    unittest.main()
