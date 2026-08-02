from __future__ import annotations

from collections.abc import Mapping
import json
import os
import socket
import subprocess
import sys
import unittest
from dataclasses import replace
from pathlib import Path
from unittest.mock import patch

from pycforge import (
    ConversionRequest,
    PythonToCConverter,
    ResultStatus,
    SourceBundle,
    SourceDocumentInput,
)
from pycforge.converter.c_output import validate_c_text
from pycforge.converter.analysis.validation import validate_analysis_payload
from pycforge.converter.contracts.configuration import PHASE11_RULE_SET
from pycforge.converter.contracts.versions import (
    C_IR_SCHEMA,
    CONVERSION_PLAN_SCHEMA,
    CONVERSION_SUMMARY_SCHEMA,
    DECISION_TRACE_SCHEMA,
    GENERATED_C_SCHEMA,
    MODULE_FACT_SCHEMA,
    PYTHON_IR_BUNDLE_SCHEMA,
    RESULT_SCHEMA_VERSION,
    SOURCE_BUNDLE_SCHEMA,
)
from pycforge.converter.core.request import ObservationOptions
from pycforge.converter.core.resource_policy import ResourcePolicy
from pycforge.converter.core.serialization import result_to_dict
from pycforge.converter.ir.c_ir import serialize_translation_unit, validate_translation_unit
from pycforge.converter.support_templates import default_helper_registry


ROOT = Path(__file__).resolve().parents[1]
ENV = {**os.environ, "PYTHONPATH": str(ROOT)}


def request(
    primary_text: str,
    companions: tuple[tuple[str, str, str], ...] = (),
    *,
    primary_module: str = "app",
    primary_name: str = "app.py",
    policy: ResourcePolicy | None = None,
) -> ConversionRequest:
    return ConversionRequest(
        SourceBundle(
            SourceDocumentInput(primary_name, primary_text, primary_module),
            tuple(
                SourceDocumentInput(logical_name, text, module_id)
                for module_id, logical_name, text in companions
            ),
        ),
        resource_policy=policy or ResourcePolicy(),
    )


def convert_bundle(
    primary_text: str,
    companions: tuple[tuple[str, str, str], ...] = (),
    *,
    full: bool = False,
    primary_module: str = "app",
    primary_name: str = "app.py",
    policy: ResourcePolicy | None = None,
):
    return PythonToCConverter().convert(
        request(
            primary_text,
            companions,
            primary_module=primary_module,
            primary_name=primary_name,
            policy=policy,
        ),
        observation=ObservationOptions("Full" if full else "None", False),
    )


def table(payload: dict, table_id: str) -> dict:
    return next(item for item in payload["fact_tables"] if item["table_id"] == table_id)


def kind_dicts(value: object, kind: str) -> list[dict]:
    found: list[dict] = []
    if isinstance(value, dict):
        if value.get("kind") == kind:
            found.append(value)
        for item in value.values():
            found.extend(kind_dicts(item, kind))
    elif isinstance(value, (list, tuple)):
        for item in value:
            found.extend(kind_dicts(item, kind))
    return found


def mutable(value: object):
    if isinstance(value, Mapping):
        return {key: mutable(item) for key, item in value.items()}
    if isinstance(value, (list, tuple)):
        return [mutable(item) for item in value]
    return value


class Phase12Tests(unittest.TestCase):
    def assert_primary_rejection(self, result, code: str) -> None:
        self.assertEqual(result.status, ResultStatus.REJECTED)
        self.assertIsNone(result.generated_c)
        self.assertEqual([item.code for item in result.diagnostics], [code])
        payload = result.stage_artifact.payload if result.stage_artifact else {}
        self.assertFalse(payload.get("c_ir"))
        self.assertFalse(payload.get("helper_manifest"))

    def test_accepts_absolute_from_import(self):
        result = convert_bundle(
            "from lib import identity\n\ndef run(value: int) -> int:\n    return identity(value)\n",
            (("lib", "lib.py", "def identity(value: int) -> int:\n    return value\n"),),
        )
        self.assertEqual(result.status, ResultStatus.CONVERTED)
        self.assertTrue(result.generated_c)
        self.assertTrue(validate_c_text(result.generated_c).accepted)
        self.assertNotIn("from lib import", result.generated_c)
        self.assertEqual(result.conversion_summary["translation_unit_count"], 1)
        self.assertEqual(
            {item["module_id"] for item in result.conversion_summary["modules"]},
            {"app", "lib"},
        )

    def test_accepts_aliases_and_multiple_ordered_names(self):
        result = convert_bundle(
            "from lib.math import increment as inc, decrement\n\n"
            "def run(value: int) -> int:\n"
            "    return decrement(inc(value))\n",
            ((
                "lib.math",
                "lib/math.py",
                "def increment(value: int) -> int:\n    return value + 1\n\n"
                "def decrement(value: int) -> int:\n    return value - 1\n",
            ),),
        )
        self.assertEqual(result.status, ResultStatus.CONVERTED)
        imports = result.conversion_summary["module_imports"]
        self.assertEqual([item["imported_name"] for item in imports], ["increment", "decrement"])
        self.assertEqual([item["local_name"] for item in imports], ["inc", "decrement"])
        self.assertTrue(all(item["supported"] for item in imports))
        self.assertEqual(len(kind_dicts(result.stage_artifact.payload["c_ir"], "CCallExpr")), 2)
        repeated_target = convert_bundle(
            "from lib import f as left, f as right\n\n"
            "def run(value: int) -> int:\n    return left(value) + right(value)\n",
            (("lib", "lib.py", "def f(value: int) -> int:\n    return value\n"),),
        )
        self.assertEqual(repeated_target.status, ResultStatus.CONVERTED)
        repeated_imports = repeated_target.conversion_summary["module_imports"]
        self.assertEqual([item["local_name"] for item in repeated_imports], ["left", "right"])
        self.assertEqual(
            repeated_target.conversion_summary["module_initialization"]["dependency_edges"],
            [{"importer_module_id": "app", "target_module_id": "lib"}],
        )

    def test_transitive_dependency_order_and_one_translation_unit(self):
        result = convert_bundle(
            "from middle import twice\n\ndef run(value: int) -> int:\n    return twice(value)\n",
            (
                (
                    "middle",
                    "middle.py",
                    "from base import increment\n\ndef twice(value: int) -> int:\n"
                    "    return increment(increment(value))\n",
                ),
                ("base", "base.py", "def increment(value: int) -> int:\n    return value + 1\n"),
            ),
        )
        self.assertEqual(result.status, ResultStatus.CONVERTED)
        payload = result.stage_artifact.payload
        initialization = table(payload, "module-initialization-facts")["records"]
        self.assertEqual(len(initialization), 1)
        self.assertEqual(initialization[0]["value"]["module_order"], ["base", "middle", "app"])
        functions = [item["value"] for item in table(payload, "module-function-facts")["records"]]
        ordered = [
            item["module_id"]
            for item in sorted(functions, key=lambda item: item["bundle_function_ordinal"])
        ]
        self.assertEqual(ordered, ["base", "middle", "app"])
        c_ir = payload["c_ir"]
        self.assertEqual(len(kind_dicts(c_ir, "CTranslationUnit")), 1)
        self.assertEqual(len(kind_dicts(c_ir, "CFunctionPrototype")), 3)
        self.assertEqual(len(kind_dicts(c_ir, "CFunctionDefinition")), 3)
        source_functions = kind_dicts(c_ir, "CFunctionPrototype") + kind_dicts(c_ir, "CFunctionDefinition")
        self.assertTrue(all(item["storage"] == "none" for item in source_functions))
        significant_prefix_probe = convert_bundle(
            "def f() -> int:\n    return 1\n",
            (("aaaaaaaaaaaaaaaaaaaaaaaaaay", "y.py", "def f() -> int:\n    return 2\n"),),
            primary_module="aaaaaaaaaaaaaaaaaaaaaaaaaax",
        )
        self.assertEqual(significant_prefix_probe.status, ResultStatus.CONVERTED)
        external_names = [
            item["generated_name"] for item in significant_prefix_probe.conversion_summary["functions"]
        ]
        self.assertEqual(len({name[:31] for name in external_names}), len(external_names))
        self.assertTrue(
            all(item["generated_name"].startswith("pycm_") for item in result.conversion_summary["functions"])
        )

    def test_module_facts_and_rule_plans_are_complete(self):
        result = convert_bundle(
            "from lib import identity as use\n\ndef run(value: int) -> int:\n    return use(value)\n",
            (("lib", "lib.py", "def identity(value: int) -> int:\n    return value\n"),),
        )
        self.assertEqual(result.status, ResultStatus.CONVERTED)
        payload = result.stage_artifact.payload
        required_tables = {
            "module-identity-facts",
            "module-import-facts",
            "module-function-facts",
            "module-initialization-facts",
            "module-namespace-facts",
            "module-source-facts",
        }
        tables = {item["table_id"]: item for item in payload["fact_tables"]}
        self.assertTrue(required_tables.issubset(tables))
        for table_id in required_tables:
            self.assertEqual(tables[table_id]["schema_version"], MODULE_FACT_SCHEMA)
            self.assertTrue(tables[table_id]["records"])
        initialization = tables["module-initialization-facts"]["records"][0]["value"]
        self.assertIn(initialization["cycle_policy"], {"reject-all-cycles", "reject-self-and-strongly-connected-components"})
        self.assertEqual(initialization["runtime_initialization"], "none")
        self.assertEqual(initialization["module_order"], ["lib", "app"])
        rule_ids = {item["rule_id"] for item in payload["rule_plans"]}
        self.assertTrue(
            {
                "phase12.module.document",
                "phase12.module.import_from",
                "phase12.module.imported_binding",
                "phase12.module.function_namespace",
                "phase12.module.cross_call",
                "phase12.module.initialization",
                "phase12.module.bundle_assembly",
            }.issubset(rule_ids)
        )
        self.assertTrue(all(not item["unresolved_obligations"] for item in payload["rule_plans"]))
        self._assert_analysis_validator_rejects_inconsistent_module_fact_closure()
        self._assert_analysis_validator_enforces_module_id_tie_breaking()

    def _assert_analysis_validator_rejects_inconsistent_module_fact_closure(self):
        result = convert_bundle(
            "from lib import f as use\n\ndef run(value: int) -> int:\n    return use(value)\n",
            (("lib", "lib.py", "def f(value: int) -> int:\n    return value\n"),),
        )
        self.assertEqual(result.status, ResultStatus.CONVERTED)
        baseline = mutable(result.stage_artifact.payload)
        baseline["schema_version"] = CONVERSION_PLAN_SCHEMA
        self.assertEqual(validate_analysis_payload(baseline), (True, ""))

        def module_table(payload: dict, table_id: str) -> dict:
            return next(item for item in payload["fact_tables"] if item["table_id"] == table_id)

        def swap_primary(payload: dict) -> None:
            for record in module_table(payload, "module-identity-facts")["records"]:
                record["value"]["is_primary"] = not record["value"]["is_primary"]

        def swap_function_order(payload: dict) -> None:
            records = module_table(payload, "module-function-facts")["records"]
            for record in records:
                value = record["value"]
                value["bundle_function_ordinal"] = 1 - value["bundle_function_ordinal"]

        def clear_identity_functions(payload: dict) -> None:
            module_table(payload, "module-identity-facts")["records"][0]["value"][
                "function_node_ids"
            ] = []

        def clear_namespace_functions(payload: dict) -> None:
            module_table(payload, "module-namespace-facts")["records"][0]["value"][
                "function_node_ids"
            ] = []

        def clear_imported_bindings(payload: dict) -> None:
            records = module_table(payload, "module-namespace-facts")["records"]
            next(item for item in records if item["value"]["module_id"] == "app")["value"][
                "imported_bindings"
            ] = []

        def change_generated_namespace(payload: dict) -> None:
            module_table(payload, "module-namespace-facts")["records"][0]["value"][
                "generated_function_names"
            ] = ["pycm_wrong"]

        def change_imported_name(payload: dict) -> None:
            module_table(payload, "module-import-facts")["records"][0]["value"][
                "imported_name"
            ] = "not_f"

        def change_local_name(payload: dict) -> None:
            module_table(payload, "module-import-facts")["records"][0]["value"][
                "local_name"
            ] = "run"

        def corrupt_content_fingerprint(payload: dict) -> None:
            module_table(payload, "module-source-facts")["records"][0]["value"][
                "content_fingerprint"
            ] = "not-a-sha256"

        def change_source_name(payload: dict) -> None:
            module_table(payload, "module-function-facts")["records"][0]["value"][
                "source_name"
            ] = "renamed"

        def change_flattened_name(payload: dict) -> None:
            module_table(payload, "module-function-facts")["records"][0]["value"][
                "flattened_name"
            ] = "pycm_12345678901234567890123456__wrong"

        mutations = (
            ("primary role", swap_primary),
            ("function order", swap_function_order),
            ("identity ownership", clear_identity_functions),
            ("namespace ownership", clear_namespace_functions),
            ("imported namespace", clear_imported_bindings),
            ("generated namespace", change_generated_namespace),
            ("imported spelling", change_imported_name),
            ("local spelling", change_local_name),
            ("content fingerprint", corrupt_content_fingerprint),
            ("function source name", change_source_name),
            ("flattened name", change_flattened_name),
        )
        for label, mutate in mutations:
            with self.subTest(label=label):
                payload = mutable(baseline)
                mutate(payload)
                valid, message = validate_analysis_payload(payload)
                self.assertFalse(valid, message)

    def _assert_analysis_validator_enforces_module_id_tie_breaking(self):
        result = convert_bundle(
            "def zed() -> int:\n    return 3\n",
            (
                ("b", "b.py", "def bee() -> int:\n    return 2\n"),
                ("a", "a.py", "def aye() -> int:\n    return 1\n"),
            ),
            primary_module="z",
            primary_name="z.py",
        )
        self.assertEqual(result.status, ResultStatus.CONVERTED)
        payload = mutable(result.stage_artifact.payload)
        payload["schema_version"] = CONVERSION_PLAN_SCHEMA
        initialization = next(
            item
            for item in payload["fact_tables"]
            if item["table_id"] == "module-initialization-facts"
        )["records"][0]["value"]
        self.assertEqual(initialization["dependency_edges"], [])
        self.assertEqual(initialization["module_order"], ["a", "b", "z"])
        initialization["module_order"] = ["b", "a", "z"]
        valid, message = validate_analysis_payload(payload)
        self.assertFalse(valid)
        self.assertIn("deterministic dependency ordering", message)

    def test_summary_trace_and_mappings_are_document_qualified(self):
        result = convert_bundle(
            "from lib.math import increment as inc\n\ndef run(value: int) -> int:\n    return inc(value)\n",
            (("lib.math", "lib/math.py", "def increment(value: int) -> int:\n    return value + 1\n"),),
            full=True,
        )
        self.assertEqual(result.status, ResultStatus.CONVERTED)
        self.assertEqual(result.conversion_summary["schema_version"], CONVERSION_SUMMARY_SCHEMA)
        self.assertEqual(result.decision_trace["schema_version"], DECISION_TRACE_SCHEMA)
        self.assertEqual(result.decision_trace["module_initialization"]["module_order"], ["lib.math", "app"])
        self.assertEqual(
            {item["module_id"] for item in result.decision_trace["module_manifest"]},
            {"app", "lib.math"},
        )
        mappings = result.stage_artifact.payload["source_output_mappings"]
        self.assertTrue(mappings)
        qualified = [item for item in mappings if item.get("source_document_id")]
        self.assertEqual({item["module_id"] for item in qualified}, {"app", "lib.math"})
        self.assertEqual(
            {item["logical_source_name"] for item in qualified},
            {"app.py", "lib/math.py"},
        )
        relationships = [
            item
            for item in mappings
            if item.get("mapping_kind") == "imported-function-alias-relationship"
        ]
        self.assertEqual(
            {item["target_output_kind"] for item in relationships},
            {"prototype", "definition"},
        )
        self.assertTrue(all(item["module_id"] == "app" for item in relationships))
        self.assertTrue(all(item["target_module_id"] == "lib.math" for item in relationships))
        self.assertTrue(all(item["source_span"]["document_id"] == item["source_document_id"] for item in relationships))
        self.assertTrue(all(item["target_binding_id"] for item in relationships))
        self.assertEqual(result.decision_trace["source_output_mappings"], list(mappings))
        unused = convert_bundle(
            "from lib import identity as unused\n\ndef run(value: int) -> int:\n    return value\n",
            (("lib", "lib.py", "def identity(value: int) -> int:\n    return value\n"),),
        )
        unused_relationships = [
            item
            for item in unused.stage_artifact.payload["source_output_mappings"]
            if item.get("mapping_kind") == "imported-function-alias-relationship"
        ]
        self.assertEqual(
            {item["target_output_kind"] for item in unused_relationships},
            {"prototype", "definition"},
        )

    def test_singleton_phase11_generated_c_is_byte_identical(self):
        source = (
            "def identity(value: int) -> int:\n    return value\n\n"
            "def run(value: int) -> int:\n"
            "    values = [identity(value), 2]\n"
            "    return values[0] + values[1]\n"
        )
        current = PythonToCConverter().convert(ConversionRequest.from_source(source))
        predecessor = PythonToCConverter().convert(
            ConversionRequest.from_source(
                source,
                rule_set_version=PHASE11_RULE_SET,
                renderer_version="c-renderer-v0.11",
            )
        )
        self.assertEqual(current.status, ResultStatus.CONVERTED)
        self.assertEqual(predecessor.status, ResultStatus.CONVERTED)
        self.assertEqual(current.generated_c, predecessor.generated_c)
        self.assertEqual(current.output_fingerprint, predecessor.output_fingerprint)
        self.assertEqual(current.stage_artifact.payload["c_ir_schema"], C_IR_SCHEMA)
        self.assertEqual(predecessor.stage_artifact.payload["c_ir_schema"], "c-ir/0.11")
        self.assertNotIn("pycm_", current.generated_c)

    def test_import_resolution_never_discovers_host_state(self):
        explicit = request(
            "from os import value\n\ndef run() -> int:\n    return value()\n",
            (("os", "supplied/os.py", "def value() -> int:\n    return 7\n"),),
        )
        missing = request("from definitely_absent import value\n\ndef run() -> int:\n    return value()\n")
        forbidden = AssertionError("source import attempted host discovery")
        with (
            patch("builtins.open", side_effect=forbidden),
            patch("os.listdir", side_effect=forbidden),
            patch("os.scandir", side_effect=forbidden),
            patch("importlib.import_module", side_effect=forbidden),
            patch.object(socket, "create_connection", side_effect=forbidden),
        ):
            accepted = PythonToCConverter().convert(explicit)
            rejected = PythonToCConverter().convert(missing)
        self.assertEqual(accepted.status, ResultStatus.CONVERTED)
        self.assert_primary_rejection(rejected, "PYC3503")
        self.assertIn("7LL", accepted.generated_c)

    def test_module_bundle_output_is_cross_process_deterministic(self):
        script = (
            "import json\n"
            "from pycforge import ConversionRequest,PythonToCConverter,SourceBundle,SourceDocumentInput\n"
            "request=ConversionRequest(SourceBundle("
            "SourceDocumentInput('app.py','from lib import f as use\\n\\ndef run(x: int) -> int:\\n    return use(x)\\n','app'),"
            "(SourceDocumentInput('lib.py','def f(x: int) -> int:\\n    return x + 1\\n','lib'),)))\n"
            "result=PythonToCConverter().convert(request)\n"
            "print(json.dumps({'status':result.status.value,'c':result.generated_c,'output':result.output_fingerprint.value,'artifact':result.stage_artifact.artifact_fingerprint.value},sort_keys=True))\n"
        )
        outputs = []
        for seed, timezone in (("1", "UTC"), ("777", "Pacific/Honolulu")):
            environment = {**ENV, "PYTHONHASHSEED": seed, "TZ": timezone, "LC_ALL": "C"}
            outputs.append(
                subprocess.run(
                    [sys.executable, "-c", script],
                    cwd=ROOT,
                    env=environment,
                    text=True,
                    capture_output=True,
                    check=True,
                ).stdout
            )
        self.assertEqual(outputs[0], outputs[1])

    def test_active_c_ir_serialization_is_single_unit_and_source_only(self):
        captured_units = []

        def capture_validation(unit):
            captured_units.append(unit)
            return validate_translation_unit(unit)

        with patch(
            "pycforge.converter.lowering.validate_translation_unit",
            side_effect=capture_validation,
        ):
            result = convert_bundle(
                "from lib import f\n\ndef run(value: int) -> int:\n    return f(value)\n",
                (("lib", "lib.py", "def f(value: int) -> int:\n    return value\n"),),
            )
        self.assertEqual(result.status, ResultStatus.CONVERTED)
        self.assertEqual(len(captured_units), 1)
        unit = captured_units[0]
        payload = result.stage_artifact.payload
        self.assertEqual(payload["schema_version"], GENERATED_C_SCHEMA)
        self.assertEqual(payload["c_ir_schema"], C_IR_SCHEMA)
        self.assertEqual(result.stage_artifact.schema_version, "0.14.3")
        self.assertEqual(CONVERSION_PLAN_SCHEMA, "conversion-plan/0.14.3")
        self.assertEqual(PYTHON_IR_BUNDLE_SCHEMA, "python-ir/0.4")
        self.assertEqual(SOURCE_BUNDLE_SCHEMA, "source-bundle/0.2")
        self.assertEqual(result_to_dict(result)["schema_version"], RESULT_SCHEMA_VERSION)
        serialized = json.dumps(payload["c_ir"], sort_keys=True, separators=(",", ":"))
        self.assertEqual(json.loads(serialized)["schema_version"], C_IR_SCHEMA)
        self.assertEqual(serialized.count('"kind":"CTranslationUnit"'), 1)
        self.assertNotIn("ImportFrom", serialized)
        self.assertNotIn("module_initializer", serialized)
        self.assertNotIn('#include "', result.generated_c)

        wrong_primary = replace(
            unit,
            module_manifest=tuple(
                replace(item, is_primary=item.bundle_ordinal != 0)
                for item in unit.module_manifest
            ),
        )
        self.assertIn(
            "module manifest primary marker must identify bundle ordinal zero",
            validate_translation_unit(wrong_primary).errors,
        )

        missing_dependency = replace(unit, module_dependencies=())
        self.assertIn(
            "module dependencies omit represented cross-module calls: app->lib",
            validate_translation_unit(missing_dependency).errors,
        )

        malformed_names = replace(
            unit,
            declarations=tuple(
                replace(
                    item,
                    identifier=replace(item.identifier, spelling="pycm_lib__f"),
                )
                if getattr(item, "owner_module_id", None) == "lib"
                else item
                for item in unit.declarations
            ),
        )
        self.assertTrue(
            any(
                "digest-first module-qualified spelling" in error
                for error in validate_translation_unit(malformed_names).errors
            )
        )

        module_field_names = (
            "module_manifest",
            "module_order",
            "module_dependencies",
            "owner_module_id",
            "owner_document_id",
            "bundle_function_ordinal",
        )
        for historical_schema in ("c-ir/0.8", "c-ir/0.9", "c-ir/0.10", "c-ir/0.11"):
            historical = json.dumps(
                serialize_translation_unit(replace(unit, schema_version=historical_schema)),
                sort_keys=True,
                separators=(",", ":"),
            )
            for field_name in module_field_names:
                self.assertNotIn(f'"{field_name}"', historical)

    def test_phase10_helper_registry_and_empty_manifest_are_stable(self):
        registry = default_helper_registry()
        result = convert_bundle(
            "from lib import f\n\ndef run(value: int) -> int:\n    return f(value)\n",
            (("lib", "lib.py", "def f(value: int) -> int:\n    return value\n"),),
        )
        self.assertEqual(result.status, ResultStatus.CONVERTED)
        self.assertEqual(
            registry.fingerprint,
            "fcb719f07984f3b79e17262e90f93823a9a0139a60529f8486ab09f6c3663d98",
        )
        self.assertEqual(
            [item["asset_fingerprint"] for item in registry.manifest],
            [
                "23fa88ff57ffe15bc20845c6a7359f6d35648ecffd3a30ea23fe43f24e1dd869",
                "cc2e29f5823a119009df78ed20dc410c6eef4d72c57ada115790bd1120dc663e",
            ],
        )
        self.assertEqual(result.stage_artifact.payload["helper_registry_fingerprint"], registry.fingerprint)
        self.assertFalse(result.stage_artifact.payload["helper_manifest"])
        self.assertNotIn("static int64_t pycf_", result.generated_c)

    def test_pyc3501_rejects_noncanonical_module_id(self):
        result = PythonToCConverter().convert(
            ConversionRequest(SourceBundle(SourceDocumentInput("app.py", "def run() -> int:\n    return 1\n", "Bad")))
        )
        self.assert_primary_rejection(result, "PYC3501")

    def test_pyc3502_rejects_ambiguous_bundle_identity(self):
        result = convert_bundle(
            "def run() -> int:\n    return 1\n",
            (("app", "other.py", "def other() -> int:\n    return 2\n"),),
        )
        self.assert_primary_rejection(result, "PYC3502")

    def test_pyc3503_rejects_missing_exact_module(self):
        result = convert_bundle("from absent import f\n\ndef run() -> int:\n    return f()\n")
        self.assert_primary_rejection(result, "PYC3503")

    def test_pyc3504_rejects_unsupported_import_form(self):
        result = convert_bundle(
            "import lib\n\ndef run() -> int:\n    return 1\n",
            (("lib", "lib.py", "def f() -> int:\n    return 1\n"),),
        )
        self.assert_primary_rejection(result, "PYC3504")
        conditional = convert_bundle(
            "if True:\n    from lib import f\n\ndef run() -> int:\n    return 1\n",
            (("lib", "lib.py", "def f() -> int:\n    return 1\n"),),
        )
        self.assert_primary_rejection(conditional, "PYC3504")
        for source in (
            "def run() -> int:\n    return importlib.util.find_spec('x')\n",
            "def run() -> int:\n    return builtins.__import__('x')\n",
        ):
            self.assert_primary_rejection(convert_bundle(source), "PYC3504")
        arbitrary_attribute = convert_bundle(
            "def run(obj: int) -> int:\n    return obj.reload()\n"
        )
        self.assertNotEqual(arbitrary_attribute.diagnostics[0].code, "PYC3504")

    def test_pyc3505_rejects_missing_member_with_source_identity(self):
        result = convert_bundle(
            "from lib import absent\n\ndef run() -> int:\n    return 1\n",
            (("lib", "lib.py", "def present() -> int:\n    return 1\n"),),
        )
        self.assert_primary_rejection(result, "PYC3505")
        diagnostic = result.diagnostics[0]
        self.assertEqual(diagnostic.source_module_id, "app")
        self.assertEqual(diagnostic.source_logical_name, "app.py")
        self.assertIsInstance(diagnostic.source_span["document_id"], str)
        self.assertTrue(diagnostic.source_span["document_id"])
        ineligible = convert_bundle(
            "from lib import present\n\ndef run() -> int:\n    return present()\n",
            (("lib", "lib.py", "def present():\n    return 1\n"),),
        )
        self.assert_primary_rejection(ineligible, "PYC3505")
        nested = convert_bundle(
            "from lib import present\n\ndef run() -> int:\n    return present()\n",
            ((
                "lib",
                "lib.py",
                "def present() -> int:\n"
                "    def nested() -> int:\n"
                "        return 1\n"
                "    return 1\n",
            ),),
        )
        self.assert_primary_rejection(nested, "PYC3505")

    def test_pyc3506_rejects_import_namespace_collision(self):
        result = convert_bundle(
            "from lib import f as run\n\ndef run() -> int:\n    return 1\n",
            (("lib", "lib.py", "def f() -> int:\n    return 1\n"),),
        )
        self.assert_primary_rejection(result, "PYC3506")
        unimported = convert_bundle(
            "def run() -> int:\n    return f()\n",
            (("lib", "lib.py", "def f() -> int:\n    return 1\n"),),
        )
        self.assert_primary_rejection(unimported, "PYC3506")
        module_value = convert_bundle(
            "from pkg import child\n\ndef run() -> int:\n    return 1\n",
            (
                ("pkg", "pkg.py", "def other() -> int:\n    return 1\n"),
                ("pkg.child", "pkg/child.py", "def child() -> int:\n    return 1\n"),
            ),
        )
        self.assert_primary_rejection(module_value, "PYC3506")
        attribute_module_value = convert_bundle(
            "def run() -> int:\n    return lib.f()\n",
            (("lib", "lib.py", "def f() -> int:\n    return 1\n"),),
        )
        self.assert_primary_rejection(attribute_module_value, "PYC3506")
        duplicated = convert_bundle(
            "from lib import f\nfrom lib import f\n\n"
            "def run() -> int:\n    return f()\n",
            (("lib", "lib.py", "def f() -> int:\n    return 1\n"),),
        )
        self.assert_primary_rejection(duplicated, "PYC3506")

    def test_pyc3507_rejects_dependency_cycle(self):
        result = convert_bundle(
            "from lib import f\n\ndef run() -> int:\n    return f()\n",
            (("lib", "lib.py", "from app import run\n\ndef f() -> int:\n    return run()\n"),),
        )
        self.assert_primary_rejection(result, "PYC3507")
        self_import = convert_bundle(
            "from app import run\n\ndef run() -> int:\n    return 1\n"
        )
        self.assert_primary_rejection(self_import, "PYC3507")

    def test_pyc3508_rejects_implicit_package_behavior(self):
        result = convert_bundle(
            "from pkg import child\n\ndef run() -> int:\n    return 1\n",
            (("pkg.child", "pkg/child.py", "def child() -> int:\n    return 1\n"),),
        )
        self.assert_primary_rejection(result, "PYC3508")

    def test_pyc3509_rejects_executable_module_initialization(self):
        result = convert_bundle("value = 1\n\ndef run() -> int:\n    return value\n")
        self.assert_primary_rejection(result, "PYC3509")

    def test_pyc3510_rejects_import_resource_ceiling(self):
        maximum_companions = tuple(
            (f"m{ordinal:02d}", f"m{ordinal:02d}.py", "def f() -> int:\n    return 1\n")
            for ordinal in range(63)
        )
        maximum = convert_bundle("def run() -> int:\n    return 1\n", maximum_companions)
        self.assertEqual(maximum.status, ResultStatus.CONVERTED)
        self.assertEqual(len(maximum.conversion_summary["modules"]), 64)
        too_many = convert_bundle(
            "def run() -> int:\n    return 1\n",
            maximum_companions + (("m63", "m63.py", "def f() -> int:\n    return 1\n"),),
        )
        self.assert_primary_rejection(too_many, "PYC3510")
        result = convert_bundle(
            "from lib import f\n\ndef run() -> int:\n    return f()\n",
            (("lib", "lib.py", "def f() -> int:\n    return 1\n"),),
            policy=ResourcePolicy(max_import_edges=0),
        )
        self.assert_primary_rejection(result, "PYC3510")
        oversized = ", ".join(f"f{ordinal}" for ordinal in range(4097))
        hard_ceiling = convert_bundle(
            f"from absent import {oversized}\n\ndef run() -> int:\n    return 1\n",
            policy=ResourcePolicy(max_import_edges=5000),
        )
        self.assert_primary_rejection(hard_ceiling, "PYC3510")


if __name__ == "__main__":
    unittest.main()
