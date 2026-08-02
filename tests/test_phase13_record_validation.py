from __future__ import annotations

from copy import deepcopy
from dataclasses import dataclass
import unittest

from pycforge.converter.analysis.model import FactProvenance, FactRecord, FactTable, Completeness
from pycforge.converter.analysis.symbols import SymbolScopeAnalyzer
from pycforge.converter.analysis.validation import _validate_record_fact_tables
from pycforge.converter.contracts.configuration import DEFAULT_RECORD_POLICY
from pycforge.converter.contracts.versions import RECORD_FACT_SCHEMA
from pycforge.converter.frontend.normalizer import PythonNormalizer
from pycforge.converter.frontend.parser import Python311ParserAdapter
from pycforge.converter.frontend.source_document import SourceDocument
from pycforge.converter.records import StaticRecordAnalyzer


SOURCE = (
    "class Point:\n"
    "    x: int\n"
    "    y: int\n"
    "    def __init__(self, x: int, y: int) -> None:\n"
    "        self.x = x\n"
    "        self.y = y\n"
    "\n"
    "def run() -> int:\n"
    "    point = Point(1, 2)\n"
    "    return point.x + point.y\n"
)


@dataclass(frozen=True)
class _TableSpec:
    table_id: str
    key_domain: str
    key_field: str
    values: tuple[object, ...]
    provenance_fields: tuple[str, ...]


def _fixture() -> tuple[dict, list[dict]]:
    document = SourceDocument.create("app.py", SOURCE)
    tree = Python311ParserAdapter().parse(document, "3.11")
    module = PythonNormalizer().normalize(tree, document).to_dict()
    scopes, bindings, _ = SymbolScopeAnalyzer().analyze(module, allow_records=True)
    analysis = StaticRecordAnalyzer(
        module,
        bindings=tuple(item.to_dict() for item in bindings),
        default_module_id="app",
        default_logical_name="app.py",
    ).analyze()
    specs = (
        _TableSpec(
            "record-definition-facts",
            "record-id",
            "record_id",
            analysis.definitions,
            ("class_node_id",),
        ),
        _TableSpec(
            "record-field-facts",
            "record-field-id",
            "field_id",
            analysis.fields,
            ("declaration_node_id", "target_node_id", "annotation_node_id"),
        ),
        _TableSpec(
            "record-initializer-facts",
            "record-initializer-id",
            "initializer_id",
            analysis.initializers,
            (
                "function_node_id",
                "arguments_node_id",
                "self_parameter_node_id",
                "parameter_node_ids",
                "assignment_node_ids",
            ),
        ),
        _TableSpec(
            "record-instance-facts",
            "record-instance-id",
            "instance_id",
            analysis.instances,
            (
                "construction_node_id",
                "assignment_node_id",
                "target_node_id",
                "argument_node_ids",
            ),
        ),
        _TableSpec(
            "record-binding-facts",
            "binding-id",
            "binding_id",
            analysis.bindings,
            (
                "declaration_node_id",
                "occurrence_node_ids",
                "allowed_field_access_node_ids",
            ),
        ),
        _TableSpec(
            "record-access-facts",
            "attribute-node-id",
            "access_node_id",
            analysis.accesses,
            ("access_node_id",),
        ),
    )
    tables = []
    for spec in specs:
        records = []
        for fact in spec.values:
            value = fact.to_dict()
            source_node_ids = []
            for field in spec.provenance_fields:
                item = value[field]
                source_node_ids.extend(item if isinstance(item, list) else [item])
            records.append(
                FactRecord(
                    value[spec.key_field],
                    fact,
                    FactProvenance(tuple(dict.fromkeys(source_node_ids)), ("closed-proof",)),
                )
            )
        records.sort(key=lambda item: item.key)
        tables.append(
            FactTable(
                RECORD_FACT_SCHEMA,
                spec.table_id,
                "analysis.plan",
                spec.key_domain,
                Completeness.COMPLETE,
                ("python-ir",),
                tuple(records),
            ).to_dict()
        )
    definition = analysis.definitions[0]
    owner_id = analysis.instances[0].owner_function_node_id
    document_id = definition.document_id

    def auxiliary(table_id: str, values: tuple[dict, ...], key: str) -> dict:
        return {
            "table_id": table_id,
            "records": [
                {"key": value[key], "value": value}
                for value in values
            ],
        }

    binding_values = tuple(item.to_dict() for item in bindings)
    scope_values = tuple(item.to_dict() for item in scopes)
    category_values = []
    for node in module["nodes"]:
        if node["kind"] != "Constant":
            continue
        value = node["fields"].get("value")
        category = (
            "boolean-like"
            if isinstance(value, bool)
            else "integer-like"
            if isinstance(value, int)
            else "floating-like"
            if isinstance(value, float)
            else "unknown"
        )
        category_values.append({"key": node["node_id"], "value": category})
    tables.extend(
        (
            auxiliary("binding-facts", binding_values, "binding_id"),
            auxiliary("scope-facts", scope_values, "scope_id"),
            {
                "table_id": "value-category-facts",
                "records": category_values,
            },
            auxiliary(
                "module-identity-facts",
                ({
                    "module_id": "app",
                    "document_id": document_id,
                    "logical_name": "app.py",
                    "function_node_ids": [owner_id],
                },),
                "module_id",
            ),
            auxiliary(
                "module-source-facts",
                ({
                    "module_id": "app",
                    "document_id": document_id,
                    "logical_name": "app.py",
                    "function_node_ids": [owner_id],
                },),
                "module_id",
            ),
            auxiliary(
                "module-function-facts",
                ({
                    "function_node_id": owner_id,
                    "module_id": "app",
                    "document_id": document_id,
                },),
                "function_node_id",
            ),
        )
    )
    generated_name_ids = (
        [item.class_binding_id for item in analysis.definitions]
        + [item.field_id for item in analysis.fields]
        + [item.binding_id for item in analysis.bindings]
    )
    return {
        "record_policy_version": DEFAULT_RECORD_POLICY,
        "python_ir": module,
        "module_record_by_node": {
            definition.class_node_id: {
                "class_node_id": definition.class_node_id,
                "module_id": definition.module_id,
                "document_id": definition.document_id,
                "source_name": definition.source_name,
                "flattened_name": definition.flattened_name,
            }
        },
        "generated_name_plans": [
            {"binding_id": binding_id, "generated_name": f"record_name_{ordinal}"}
            for ordinal, binding_id in enumerate(generated_name_ids)
        ],
    }, tables


class Phase13RecordValidationTests(unittest.TestCase):
    def test_accepts_closed_record_tables(self) -> None:
        payload, tables = _fixture()
        self.assertEqual(_validate_record_fact_tables(payload, tables), (True, ""))

    def test_requires_policy_all_tables_and_exact_table_identity(self) -> None:
        payload, tables = _fixture()
        bad_policy = deepcopy(payload)
        bad_policy["record_policy_version"] = "record-policy/unknown"
        self.assertFalse(_validate_record_fact_tables(bad_policy, tables)[0])
        missing_record_table = [
            item for item in tables if item["table_id"] != "record-access-facts"
        ]
        self.assertFalse(_validate_record_fact_tables(payload, missing_record_table)[0])
        bad_domain = deepcopy(tables)
        bad_domain[0]["key_domain"] = "python-node-id"
        self.assertFalse(_validate_record_fact_tables(payload, bad_domain)[0])

    def test_rejects_field_ordinal_and_initializer_coverage_tampering(self) -> None:
        payload, tables = _fixture()
        bad_ordinal = deepcopy(tables)
        fields = next(item for item in bad_ordinal if item["table_id"] == "record-field-facts")
        fields["records"][0]["value"]["ordinal"] = 9
        self.assertFalse(_validate_record_fact_tables(payload, bad_ordinal)[0])

        bad_initializer = deepcopy(tables)
        initializers = next(
            item for item in bad_initializer if item["table_id"] == "record-initializer-facts"
        )
        initializers["records"][0]["value"]["field_ids"].pop()
        self.assertFalse(_validate_record_fact_tables(payload, bad_initializer)[0])

    def test_rejects_ownership_access_and_provenance_tampering(self) -> None:
        payload, tables = _fixture()
        bad_ownership = deepcopy(tables)
        instances = next(item for item in bad_ownership if item["table_id"] == "record-instance-facts")
        instances["records"][0]["value"]["allocation_model"] = "heap"
        self.assertFalse(_validate_record_fact_tables(payload, bad_ownership)[0])

        bad_access = deepcopy(tables)
        accesses = next(item for item in bad_access if item["table_id"] == "record-access-facts")
        accesses["records"][0]["value"]["field_id"] = "record-field-absent"
        self.assertFalse(_validate_record_fact_tables(payload, bad_access)[0])

        bad_provenance = deepcopy(tables)
        definitions = next(
            item for item in bad_provenance if item["table_id"] == "record-definition-facts"
        )
        definitions["records"][0]["provenance"]["source_node_ids"] = ["py-node-absent"]
        self.assertFalse(_validate_record_fact_tables(payload, bad_provenance)[0])

    def test_anchors_record_identity_to_module_evidence(self) -> None:
        payload, tables = _fixture()
        ghost = deepcopy(tables)
        for table in ghost:
            if table["table_id"].startswith("record-"):
                for record in table["records"]:
                    record["value"]["module_id"] = "ghost"
        self.assertFalse(_validate_record_fact_tables(payload, ghost)[0])

        bad_module_record = deepcopy(payload)
        class_record = next(iter(bad_module_record["module_record_by_node"].values()))
        class_record["document_id"] = "src-forged"
        self.assertFalse(_validate_record_fact_tables(bad_module_record, tables)[0])

    def test_anchors_instances_to_ordinary_lexical_bindings(self) -> None:
        payload, tables = _fixture()
        forged = deepcopy(tables)
        instance_table = next(
            item for item in forged if item["table_id"] == "record-instance-facts"
        )
        record_binding_table = next(
            item for item in forged if item["table_id"] == "record-binding-facts"
        )
        old_id = instance_table["records"][0]["value"]["binding_id"]
        forged_id = "bind-forged-record-instance"
        instance_table["records"][0]["value"]["binding_id"] = forged_id
        record_binding_table["records"][0]["key"] = forged_id
        record_binding_table["records"][0]["value"]["binding_id"] = forged_id
        forged_payload = deepcopy(payload)
        for plan in forged_payload["generated_name_plans"]:
            if plan["binding_id"] == old_id:
                plan["binding_id"] = forged_id
        self.assertFalse(_validate_record_fact_tables(forged_payload, forged)[0])

    def test_rechecks_argument_categories_and_access_order(self) -> None:
        payload, tables = _fixture()
        bad_category = deepcopy(tables)
        instance = next(
            item for item in bad_category if item["table_id"] == "record-instance-facts"
        )["records"][0]["value"]
        categories = next(
            item for item in bad_category if item["table_id"] == "value-category-facts"
        )
        argument_id = instance["argument_node_ids"][0]
        next(item for item in categories["records"] if item["key"] == argument_id)[
            "value"
        ] = "floating-like"
        self.assertFalse(_validate_record_fact_tables(payload, bad_category)[0])

        bad_order = deepcopy(payload)
        instance_table = next(
            item for item in tables if item["table_id"] == "record-instance-facts"
        )
        fact = instance_table["records"][0]["value"]
        owner = next(
            item
            for item in bad_order["python_ir"]["nodes"]
            if item["node_id"] == fact["owner_function_node_id"]
        )
        assignment_id = fact["assignment_node_id"]
        owner["fields"]["body"].remove(assignment_id)
        owner["fields"]["body"].append(assignment_id)
        self.assertFalse(_validate_record_fact_tables(bad_order, tables)[0])

        bad_context = deepcopy(payload)
        access_table = next(
            item for item in tables if item["table_id"] == "record-access-facts"
        )
        access_id = access_table["records"][0]["value"]["access_node_id"]
        owner = next(
            item
            for item in bad_context["python_ir"]["nodes"]
            if item["node_id"] == fact["owner_function_node_id"]
        )
        return_node = next(
            item
            for item in bad_context["python_ir"]["nodes"]
            if item["node_id"] in owner["fields"]["body"] and item["kind"] == "Return"
        )
        return_node["kind"] = "Delete"
        return_node["fields"] = {"targets": [access_id]}
        self.assertFalse(_validate_record_fact_tables(bad_context, tables)[0])

    def test_rechecks_hidden_binding_forms_and_source_shape(self) -> None:
        payload, tables = _fixture()
        instance = next(
            item for item in tables if item["table_id"] == "record-instance-facts"
        )["records"][0]["value"]

        hidden_global = deepcopy(payload)
        owner = next(
            item
            for item in hidden_global["python_ir"]["nodes"]
            if item["node_id"] == instance["owner_function_node_id"]
        )
        global_id = "py-forged-global-record-binding"
        hidden_global["python_ir"]["nodes"].append(
            {
                "node_id": global_id,
                "kind": "Global",
                "fields": {"names": [instance["source_name"]]},
                "provenance": owner["provenance"],
            }
        )
        owner["fields"]["body"].insert(0, global_id)
        self.assertFalse(_validate_record_fact_tables(hidden_global, tables)[0])

        typed_assignment = deepcopy(payload)
        assignment = next(
            item
            for item in typed_assignment["python_ir"]["nodes"]
            if item["node_id"] == instance["assignment_node_id"]
        )
        assignment["fields"]["type_comment"] = "Point"
        self.assertFalse(_validate_record_fact_tables(typed_assignment, tables)[0])

        based_class = deepcopy(payload)
        class_id = next(iter(based_class["module_record_by_node"]))
        class_node = next(
            item
            for item in based_class["python_ir"]["nodes"]
            if item["node_id"] == class_id
        )
        annotation_id = next(
            item["node_id"]
            for item in based_class["python_ir"]["nodes"]
            if item["kind"] == "Name" and item["fields"].get("id") == "int"
        )
        class_node["fields"]["bases"] = [annotation_id]
        self.assertFalse(_validate_record_fact_tables(based_class, tables)[0])

    def test_rejects_missing_record_generated_name_plan(self) -> None:
        payload, tables = _fixture()
        payload["generated_name_plans"].pop()
        self.assertFalse(_validate_record_fact_tables(payload, tables)[0])


if __name__ == "__main__":
    unittest.main()
