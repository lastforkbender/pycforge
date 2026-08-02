"""Deterministic analyzer for the first Phase 13 static-record slice.

The accepted profile is intentionally smaller than Python's object model:

* top-level, base-less, undecorated classes;
* one to sixty-four value-less ``int``/``float``/``bool`` fields;
* one exact field-copying ``__init__`` and no other methods;
* fresh automatic locals constructed by a direct function-body assignment;
* immutable, statically bound field reads and no aliasing or escape.

Anything outside that closed profile is rejected before lowering.
"""

from __future__ import annotations

import hashlib
from collections import defaultdict
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from typing import Any

from pycforge.converter.analysis.model import ValueCategory
from pycforge.converter.analysis.symbols import PythonIRIndex, SymbolScopeAnalyzer
from pycforge.converter.ir.python_ir import python_ir_reference_ids

from .model import (
    MAX_RECORD_FIELDS,
    RecordAnalysisCanceled,
    RecordAnalysisError,
    RecordDefinitionFact,
    RecordFieldAccessFact,
    RecordFieldFact,
    RecordInitializerFact,
    RecordInstanceBindingFact,
    RecordInstanceFact,
    RecordValueCategory,
    StaticRecordAnalysis,
)


_FIELD_CATEGORIES = {
    "int": ValueCategory.INTEGER,
    "float": ValueCategory.FLOAT,
    "bool": ValueCategory.BOOLEAN,
}
_STORE_PARENT_SLOTS = {
    ("Assign", "targets"),
    ("AnnAssign", "target"),
    ("AugAssign", "target"),
    ("Delete", "targets"),
    ("NamedExpr", "target"),
    ("For", "target"),
    ("AsyncFor", "target"),
    ("comprehension", "target"),
    ("withitem", "optional_vars"),
}
_DYNAMIC_ATTRIBUTE_BUILTINS = {"getattr", "setattr", "delattr", "hasattr"}


def _stable_id(prefix: str, *parts: str) -> str:
    return prefix + hashlib.sha256("\x1f".join(parts).encode("utf-8")).hexdigest()[:20]


@dataclass(frozen=True, slots=True)
class _Identity:
    module_id: str
    document_id: str
    logical_name: str


@dataclass(frozen=True, slots=True)
class _RecordSpec:
    definition: RecordDefinitionFact
    fields: tuple[RecordFieldFact, ...]
    initializer: RecordInitializerFact


class StaticRecordAnalyzer:
    """Prove and publish the bounded immutable static-record profile.

    ``module_records`` is keyed by ``ClassDef`` node ID.  A record may contain
    ``source_name``, ``flattened_name``, ``module_id``, ``document_id``, and
    ``logical_name`` (or ``logical_source_name``).  This allows the Phase 12
    bundle resolver to qualify class names without losing source identity.

    ``function_records`` supplies equivalent owner-module metadata keyed by
    top-level ``FunctionDef`` node ID.  ``bindings`` and ``categories`` are the
    already-published cumulative analysis values; both are optional so this
    semantic gate remains independently testable on a single normalized file.
    """

    def __init__(
        self,
        module: dict[str, Any],
        *,
        module_records: Mapping[str, Mapping[str, Any]] | None = None,
        function_records: Mapping[str, Mapping[str, Any]] | None = None,
        bindings: Sequence[Mapping[str, Any]] = (),
        categories: Mapping[str, ValueCategory | str] | None = None,
        cancellation: Any | None = None,
        default_module_id: str = "__main__",
        default_logical_name: str = "<memory>",
    ) -> None:
        self.module = module
        self.cancellation = cancellation
        self._check_canceled()
        self.index = PythonIRIndex(module)
        self.module_records = {
            key: dict(value) for key, value in (module_records or {}).items()
        }
        self.function_records = {
            key: dict(value) for key, value in (function_records or {}).items()
        }
        supplied_bindings = tuple(dict(item) for item in bindings)
        class_node_ids = {
            item["node_id"] for item in module.get("nodes", ()) if item.get("kind") == "ClassDef"
        }
        supplied_record_declarations = {
            item.get("declaration_node_id")
            for item in supplied_bindings
            if item.get("binding_kind") == "record-class"
        }
        if supplied_bindings and class_node_ids.issubset(supplied_record_declarations):
            self.bindings = supplied_bindings
        else:
            # Keep the analyzer independently usable while retaining the same
            # lexical-identity proof as the cumulative analysis stage.  Older
            # isolated callers may supply ordinary bindings produced without
            # the Phase 13 record switch; those are intentionally recomputed.
            _, inferred_bindings, _ = SymbolScopeAnalyzer().analyze(
                module,
                allow_records=True,
            )
            self.bindings = tuple(item.to_dict() for item in inferred_bindings)
        self.categories = {
            key: self._coerce_category(value)
            for key, value in (categories or {}).items()
        }
        self.default_module_id = default_module_id
        self.default_logical_name = default_logical_name
        self.identity_by_document: dict[str, _Identity] = {}
        for metadata in (
            *(
                self.module_records[key]
                for key in sorted(self.module_records)
            ),
            *(
                self.function_records[key]
                for key in sorted(self.function_records)
            ),
        ):
            self._check_canceled()
            document_id = str(
                metadata.get("document_id")
                or metadata.get("source_document_id")
                or ""
            )
            if not document_id:
                continue
            self.identity_by_document.setdefault(
                document_id,
                _Identity(
                    str(metadata.get("module_id") or default_module_id),
                    document_id,
                    str(
                        metadata.get("logical_name")
                        or metadata.get("logical_source_name")
                        or default_logical_name
                    ),
                ),
            )
        self.binding_by_occurrence = {
            occurrence: binding
            for binding in self.bindings
            for occurrence in binding.get("occurrence_node_ids", ())
            if isinstance(occurrence, str)
        }
        self.binding_by_declaration = {
            declaration: binding
            for binding in self.bindings
            for declaration in (binding.get("declaration_node_id"),)
            if isinstance(declaration, str)
        }
        self.parents: dict[str, list[tuple[str, str]]] = defaultdict(list)
        known_ids = self.index.nodes
        for parent in self.index.nodes.values():
            self._check_canceled()
            for field_name, value in parent.get("fields", {}).items():
                self._check_canceled()
                for child_id in python_ir_reference_ids(
                    parent["kind"], field_name, value, known_ids
                ):
                    self.parents[child_id].append((parent["node_id"], field_name))

    def analyze(self) -> StaticRecordAnalysis:
        self._check_canceled()
        root = self.index.node(self.module["root_node_id"])
        if root["kind"] != "Module":
            self._reject("PYC3601", "Static-record analysis requires a Module root", root)
        root_body = tuple(root["fields"].get("body", ()))
        root_members = set(root_body)
        class_nodes = tuple(
            sorted(
                (
                    node
                    for node in self._nodes()
                    if node["kind"] == "ClassDef"
                ),
                key=lambda item: self._ordinal(item["node_id"]),
            )
        )
        for node in class_nodes:
            self._check_canceled()
            if node["node_id"] not in root_members:
                self._reject(
                    "PYC3601",
                    "Static-record classes must be declared directly at module scope",
                    node,
                )

        specs_list: list[_RecordSpec] = []
        for node in class_nodes:
            self._check_canceled()
            specs_list.append(self._definition(node))
        specs = tuple(specs_list)
        by_resolution_name: dict[str, _RecordSpec] = {}
        for spec in specs:
            self._check_canceled()
            name = spec.definition.flattened_name
            if name in by_resolution_name:
                self._reject(
                    "PYC3601",
                    f"Static-record constructor name {name!r} is not unique",
                    self.index.node(spec.definition.class_node_id),
                )
            by_resolution_name[name] = spec

        self._reject_cross_module_imports(specs)
        self._reject_forward_object_annotations(specs)
        by_class_binding = {
            item.definition.class_binding_id: item for item in specs
        }
        by_record_id = {
            item.definition.record_id: item for item in specs
        }
        if len(by_class_binding) != len(specs):
            self._reject(
                "PYC3601",
                "Static-record class bindings are not unique",
                self.index.node(specs[0].definition.class_node_id),
            )
        instances = self._instances(
            by_resolution_name,
            by_class_binding,
            root_members,
        )
        bindings: list[RecordInstanceBindingFact] = []
        accesses: list[RecordFieldAccessFact] = []
        for instance in instances:
            self._check_canceled()
            binding, instance_accesses = self._validate_instance_uses(
                instance, by_record_id
            )
            bindings.append(binding)
            accesses.extend(instance_accesses)

        return StaticRecordAnalysis(
            definitions=tuple(item.definition for item in specs),
            fields=tuple(field for item in specs for field in item.fields),
            initializers=tuple(item.initializer for item in specs),
            instances=tuple(instances),
            bindings=tuple(bindings),
            accesses=tuple(
                sorted(accesses, key=lambda item: self._ordinal(item.access_node_id))
            ),
        )

    def _definition(self, node: dict[str, Any]) -> _RecordSpec:
        fields = node["fields"]
        if (
            fields.get("bases")
            or fields.get("keywords")
            or fields.get("decorator_list")
        ):
            self._reject(
                "PYC3601",
                "Static-record classes cannot have bases, keywords, metaclasses, or decorators",
                node,
            )

        metadata = self.module_records.get(node["node_id"], {})
        source_name = str(metadata.get("source_name", fields.get("name", "")))
        flattened_name = str(metadata.get("flattened_name", fields.get("name", "")))
        if not source_name or not flattened_name:
            self._reject("PYC3601", "Static-record class name is missing", node)
        if source_name in {"int", "float", "bool", "str"}:
            self._reject(
                "PYC3601",
                "Static-record class names cannot shadow the closed annotation builtins",
                node,
            )
        identity = self._identity(node, metadata)
        record_id = _stable_id(
            "record-", identity.module_id, node["node_id"], source_name
        )
        lexical_binding = self.binding_by_declaration.get(node["node_id"])
        class_binding_id = str(
            metadata.get("binding_id")
            or (lexical_binding or {}).get("binding_id")
            or _stable_id("bind-record-class-", record_id, flattened_name)
        )
        if lexical_binding is not None and (
            lexical_binding.get("binding_kind") != "record-class"
            or lexical_binding.get("source_name") != flattened_name
        ):
            self._reject(
                "PYC3601",
                "Static-record definition lacks its exact lexical class binding",
                node,
                identity,
            )

        body_ids = tuple(fields.get("body", ()))
        body_nodes = tuple(self.index.node(item) for item in body_ids)
        methods = tuple(item for item in body_nodes if item["kind"] == "FunctionDef")
        for method in methods:
            self._check_canceled()
            if method["fields"].get("name") != "__init__":
                self._reject(
                    "PYC3604",
                    "The first static-record slice supports __init__ only; other methods are deferred",
                    method,
                    identity,
                )
        if len(methods) != 1:
            self._reject(
                "PYC3603",
                "A static-record class must declare exactly one __init__",
                methods[1] if len(methods) > 1 else node,
                identity,
            )
        initializer_node = methods[0]
        field_nodes = tuple(item for item in body_nodes if item["kind"] == "AnnAssign")
        unsupported = tuple(
            item for item in body_nodes if item["kind"] not in {"AnnAssign", "FunctionDef"}
        )
        if unsupported:
            self._reject(
                "PYC3604",
                "Static-record class bodies contain only value-less fields followed by __init__",
                unsupported[0],
                identity,
            )
        if body_nodes != field_nodes + (initializer_node,):
            self._reject(
                "PYC3604",
                "Static-record fields must precede the sole __init__ declaration",
                node,
                identity,
            )
        if not field_nodes:
            self._reject(
                "PYC3602",
                "A static-record class must declare at least one field",
                node,
                identity,
            )
        if len(field_nodes) > MAX_RECORD_FIELDS:
            self._reject(
                "PYC3602",
                f"Static-record field count exceeds the fixed limit of {MAX_RECORD_FIELDS}",
                field_nodes[MAX_RECORD_FIELDS],
                identity,
            )

        field_facts: list[RecordFieldFact] = []
        seen_names: set[str] = set()
        for ordinal, field_node in enumerate(field_nodes):
            self._check_canceled()
            fact = self._field(
                field_node,
                record_id=record_id,
                class_node_id=node["node_id"],
                ordinal=ordinal,
                identity=identity,
            )
            if fact.source_name in seen_names:
                self._reject(
                    "PYC3602",
                    f"Duplicate static-record field {fact.source_name!r}",
                    field_node,
                    identity,
                )
            seen_names.add(fact.source_name)
            field_facts.append(fact)

        initializer = self._initializer(
            initializer_node,
            record_id=record_id,
            fields=tuple(field_facts),
            identity=identity,
        )
        definition = RecordDefinitionFact(
            record_id=record_id,
            class_node_id=node["node_id"],
            class_binding_id=class_binding_id,
            source_name=source_name,
            flattened_name=flattened_name,
            module_id=identity.module_id,
            document_id=identity.document_id,
            logical_name=identity.logical_name,
            field_ids=tuple(item.field_id for item in field_facts),
            initializer_id=initializer.initializer_id,
            category=RecordValueCategory.DEFINITION,
            storage_model="automatic-inline-record",
            ownership_model="unique-lexical-owner",
            lifetime_model="enclosing-function-activation",
            aliasing_model="forbidden",
            cleanup_model="none",
            nullability_model="non-null-by-construction",
            mutable=False,
        )
        return _RecordSpec(definition, tuple(field_facts), initializer)

    def _field(
        self,
        node: dict[str, Any],
        *,
        record_id: str,
        class_node_id: str,
        ordinal: int,
        identity: _Identity,
    ) -> RecordFieldFact:
        fields = node["fields"]
        target = self.index.nodes.get(fields.get("target"))
        annotation = self.index.nodes.get(fields.get("annotation"))
        if (
            target is None
            or target["kind"] != "Name"
            or fields.get("simple") != 1
            or fields.get("value") is not None
        ):
            self._reject(
                "PYC3602",
                "Static-record fields must be simple value-less annotated names",
                node,
                identity,
            )
        annotation_name = (
            annotation["fields"].get("id")
            if annotation is not None and annotation["kind"] == "Name"
            else None
        )
        if annotation_name not in _FIELD_CATEGORIES:
            self._reject(
                "PYC3602",
                "Static-record fields require an exact int, float, or bool annotation",
                annotation or node,
                identity,
            )
        source_name = str(target["fields"].get("id", ""))
        if (
            not source_name
            or source_name == "self"
            or (source_name.startswith("__") and source_name.endswith("__"))
        ):
            self._reject(
                "PYC3602",
                "Static-record field name is unsupported; Python dunder descriptors are excluded",
                target,
                identity,
            )
        field_id = _stable_id("record-field-", record_id, source_name, str(ordinal))
        return RecordFieldFact(
            field_id=field_id,
            record_id=record_id,
            class_node_id=class_node_id,
            declaration_node_id=node["node_id"],
            target_node_id=target["node_id"],
            annotation_node_id=annotation["node_id"],
            source_name=source_name,
            ordinal=ordinal,
            category=_FIELD_CATEGORIES[annotation_name],
            module_id=identity.module_id,
            document_id=identity.document_id,
            logical_name=identity.logical_name,
            mutable=False,
        )

    def _initializer(
        self,
        node: dict[str, Any],
        *,
        record_id: str,
        fields: tuple[RecordFieldFact, ...],
        identity: _Identity,
    ) -> RecordInitializerFact:
        values = node["fields"]
        if values.get("decorator_list") or values.get("type_comment"):
            self._reject(
                "PYC3603", "Static-record __init__ cannot be decorated or type-commented", node, identity
            )
        if not self._is_none_annotation(values.get("returns")):
            target = self.index.nodes.get(values.get("returns"), node)
            self._reject(
                "PYC3603", "Static-record __init__ must declare -> None", target, identity
            )
        arguments = self.index.nodes.get(values.get("args"))
        if arguments is None or arguments["kind"] != "arguments":
            self._reject("PYC3603", "Static-record __init__ arguments are malformed", node, identity)
        arg_fields = arguments["fields"]
        positional = tuple(arg_fields.get("args", ()))
        if (
            arg_fields.get("posonlyargs")
            or arg_fields.get("vararg") is not None
            or arg_fields.get("kwonlyargs")
            or arg_fields.get("kw_defaults")
            or arg_fields.get("kwarg") is not None
            or arg_fields.get("defaults")
            or len(positional) != len(fields) + 1
        ):
            self._reject(
                "PYC3603",
                "Static-record __init__ is exact positional self plus one parameter per field",
                arguments,
                identity,
            )
        parameters = tuple(self.index.node(item) for item in positional)
        self_parameter = parameters[0]
        if (
            self_parameter["kind"] != "arg"
            or self_parameter["fields"].get("arg") != "self"
            or self_parameter["fields"].get("annotation") is not None
            or self_parameter["fields"].get("type_comment") is not None
        ):
            self._reject(
                "PYC3603", "Static-record __init__ begins with unannotated self", self_parameter, identity
            )
        value_parameters = parameters[1:]
        for parameter, field in zip(value_parameters, fields):
            self._check_canceled()
            annotation = self.index.nodes.get(parameter["fields"].get("annotation"))
            expected = next(
                name for name, category in _FIELD_CATEGORIES.items() if category is field.category
            )
            if (
                parameter["kind"] != "arg"
                or parameter["fields"].get("arg") != field.source_name
                or annotation is None
                or annotation["kind"] != "Name"
                or annotation["fields"].get("id") != expected
                or parameter["fields"].get("type_comment") is not None
            ):
                self._reject(
                    "PYC3603",
                    "Static-record __init__ parameters must match field names, order, and exact types",
                    parameter,
                    identity,
                )

        assignments = tuple(values.get("body", ()))
        if len(assignments) != len(fields):
            self._reject(
                "PYC3603",
                "Static-record __init__ assigns every field exactly once and performs no other work",
                node,
                identity,
            )
        for assignment_id, field, parameter in zip(assignments, fields, value_parameters):
            self._check_canceled()
            assignment = self.index.node(assignment_id)
            assign_fields = assignment["fields"]
            targets = tuple(assign_fields.get("targets", ()))
            target = self.index.nodes.get(targets[0]) if len(targets) == 1 else None
            receiver = (
                self.index.nodes.get(target["fields"].get("value"))
                if target is not None and target["kind"] == "Attribute"
                else None
            )
            source = self.index.nodes.get(assign_fields.get("value"))
            if (
                assignment["kind"] != "Assign"
                or assign_fields.get("type_comment") is not None
                or target is None
                or target["kind"] != "Attribute"
                or target["fields"].get("attr") != field.source_name
                or receiver is None
                or receiver["kind"] != "Name"
                or receiver["fields"].get("id") != "self"
                or source is None
                or source["kind"] != "Name"
                or source["fields"].get("id") != parameter["fields"].get("arg")
            ):
                self._reject(
                    "PYC3603",
                    "Static-record __init__ body is the ordered direct copy self.field = field",
                    assignment,
                    identity,
                )

        initializer_id = _stable_id("record-init-", record_id, node["node_id"])
        return RecordInitializerFact(
            initializer_id=initializer_id,
            record_id=record_id,
            function_node_id=node["node_id"],
            arguments_node_id=arguments["node_id"],
            self_parameter_node_id=self_parameter["node_id"],
            parameter_node_ids=tuple(item["node_id"] for item in value_parameters),
            assignment_node_ids=assignments,
            field_ids=tuple(item.field_id for item in fields),
            module_id=identity.module_id,
            document_id=identity.document_id,
            logical_name=identity.logical_name,
            receiver_model="direct-addressed-initialization-receiver",
            evaluation_order="field-declaration-order-left-to-right-once",
            initialization_completeness="all-fields-exactly-once",
        )

    def _instances(
        self,
        by_resolution_name: Mapping[str, _RecordSpec],
        by_class_binding: Mapping[str, _RecordSpec],
        root_members: set[str],
    ) -> tuple[RecordInstanceFact, ...]:
        recognized_constructor_names: set[str] = set()
        instances: list[RecordInstanceFact] = []
        used_bindings: dict[tuple[str, str], str] = {}
        known_instance_fields: dict[tuple[str, str], dict[str, ValueCategory]] = {}
        record_constructor_spellings = {
            name
            for item in by_resolution_name.values()
            for name in (
                item.definition.source_name,
                item.definition.flattened_name,
            )
        }
        for call in sorted(
            (item for item in self._nodes() if item["kind"] == "Call"),
            key=lambda item: self._ordinal(item["node_id"]),
        ):
            self._check_canceled()
            function = self.index.nodes.get(call["fields"].get("func"))
            if function is None or function["kind"] != "Name":
                continue
            callee_binding = self.binding_by_occurrence.get(function["node_id"])
            spec = (
                by_class_binding.get(str(callee_binding.get("binding_id")))
                if callee_binding is not None
                else None
            )
            if spec is None:
                if function["fields"].get("id") in record_constructor_spellings:
                    self._reject(
                        "PYC3606",
                        "Static-record constructor call does not resolve to its lexical class binding",
                        function,
                    )
                continue
            recognized_constructor_names.add(function["node_id"])
            parent = self._one_parent(call["node_id"])
            assignment = self.index.nodes.get(parent[0]) if parent else None
            if (
                assignment is None
                or assignment["kind"] != "Assign"
                or parent[1] != "value"
                or len(tuple(assignment["fields"].get("targets", ()))) != 1
                or assignment["fields"].get("type_comment") is not None
            ):
                self._reject(
                    "PYC3605",
                    "Static-record construction must be the complete value of one direct local assignment",
                    call,
                )
            target = self.index.nodes.get(assignment["fields"]["targets"][0])
            if target is None or target["kind"] != "Name":
                self._reject(
                    "PYC3605", "Static-record construction target must be one fresh local name", assignment
                )
            owner_id = self._enclosing_function(assignment["node_id"])
            owner = self.index.nodes.get(owner_id)
            if (
                owner is None
                or owner_id not in root_members
                or assignment["node_id"] not in tuple(owner["fields"].get("body", ()))
            ):
                self._reject(
                    "PYC3605",
                    "Static-record construction is allowed only as a direct top-level-function-body statement",
                    assignment,
                )
            self._require_same_module(spec.definition, owner)
            arguments = tuple(call["fields"].get("args", ()))
            if call["fields"].get("keywords") or len(arguments) != len(spec.fields):
                self._reject(
                    "PYC3605",
                    "Static-record construction uses exact positional arity and no keywords",
                    call,
                )
            for argument_id, field in zip(arguments, spec.fields):
                self._check_canceled()
                category = self._argument_category(
                    argument_id,
                    owner,
                    known_instance_fields,
                )
                if category is not field.category:
                    self._reject(
                        "PYC3605",
                        f"Constructor argument for {field.source_name!r} must be exactly {field.category.value}",
                        self.index.node(argument_id),
                    )

            target_name = str(target["fields"].get("id", ""))
            if target_name in self._parameter_names(owner):
                self._reject(
                    "PYC3606", "A static-record instance cannot replace a function parameter", target
                )
            source_binding = self.binding_by_occurrence.get(target["node_id"])
            if (
                source_binding is None
                or source_binding.get("binding_kind") != "local"
                or source_binding.get("declaration_node_id") != target["node_id"]
                or source_binding.get("source_name") != target_name
            ):
                self._reject(
                    "PYC3606",
                    "A static-record instance requires one fresh ordinary function-local binding",
                    target,
                )
            conflict = self._owner_binding_conflict(
                owner,
                target_name,
                target["node_id"],
            )
            if conflict is not None:
                self._reject(
                    "PYC3606",
                    "A static-record instance binding cannot be redirected, rebound, or deleted",
                    conflict,
                )
            binding_id = str(
                source_binding.get("binding_id")
            )
            binding_key = (owner_id, binding_id)
            if binding_key in used_bindings:
                self._reject(
                    "PYC3606",
                    "A static-record instance binding is single-assignment and cannot be rebound",
                    target,
                )
            instance_id = _stable_id(
                "record-instance-", spec.definition.record_id, owner_id, call["node_id"], binding_id
            )
            used_bindings[binding_key] = instance_id
            identity = self._identity(owner, self.function_records.get(owner_id, {}))
            instances.append(
                RecordInstanceFact(
                    instance_id=instance_id,
                    record_id=spec.definition.record_id,
                    class_node_id=spec.definition.class_node_id,
                    owner_function_node_id=owner_id,
                    construction_node_id=call["node_id"],
                    assignment_node_id=assignment["node_id"],
                    target_node_id=target["node_id"],
                    binding_id=binding_id,
                    source_name=target_name,
                    argument_node_ids=arguments,
                    module_id=identity.module_id,
                    document_id=identity.document_id,
                    logical_name=identity.logical_name,
                    category=RecordValueCategory.INSTANCE,
                    storage_model="automatic-inline-record",
                    ownership_model="unique-lexical-owner",
                    lifetime_model="enclosing-function-activation",
                    aliasing_model="forbidden",
                    cleanup_model="none",
                    nullability_model="non-null-by-construction",
                    allocation_model="none",
                    mutable=False,
                )
            )
            known_instance_fields[(owner_id, binding_id)] = {
                field.source_name: field.category for field in spec.fields
            }

        record_class_binding_ids = set(by_class_binding)
        for node in sorted(
            (
                item
                for item in self._nodes()
                if item["kind"] == "Name"
                and (
                    self.binding_by_occurrence.get(item["node_id"], {}).get("binding_id")
                    in record_class_binding_ids
                )
            ),
            key=lambda item: self._ordinal(item["node_id"]),
        ):
            self._check_canceled()
            if node["node_id"] not in recognized_constructor_names:
                self._reject(
                    "PYC3606",
                    "Static-record class values, object annotations, and indirect constructors are unsupported",
                    node,
                )
        return tuple(instances)

    def _validate_instance_uses(
        self,
        instance: RecordInstanceFact,
        specs_by_record_id: Mapping[str, _RecordSpec],
    ) -> tuple[RecordInstanceBindingFact, tuple[RecordFieldAccessFact, ...]]:
        self._check_canceled()
        spec = specs_by_record_id.get(instance.record_id)
        if spec is None:
            self._reject(
                "PYC3606",
                "Static-record instance does not resolve to its proved definition",
                self.index.node(instance.construction_node_id),
            )
        fields = {item.source_name: item for item in spec.fields}
        source_binding = self.binding_by_occurrence.get(instance.target_node_id)
        if source_binding is not None:
            occurrence_ids = tuple(
                item
                for item in source_binding.get("occurrence_node_ids", ())
                if item in self.index.nodes
            )
        else:
            occurrence_ids = self._function_name_occurrences(
                instance.owner_function_node_id, instance.source_name
            )
        if instance.target_node_id not in occurrence_ids:
            occurrence_ids = (instance.target_node_id,) + occurrence_ids
        occurrence_ids = tuple(
            sorted(set(occurrence_ids), key=self._ordinal)
        )
        access_facts: list[RecordFieldAccessFact] = []
        for occurrence_id in occurrence_ids:
            self._check_canceled()
            if occurrence_id == instance.target_node_id:
                continue
            occurrence = self.index.node(occurrence_id)
            if (
                self._enclosing_function(occurrence_id) != instance.owner_function_node_id
                or self._crosses_nested_scope(occurrence_id, instance.owner_function_node_id)
            ):
                self._reject(
                    "PYC3606",
                    "Static-record instances cannot be captured by a nested scope",
                    occurrence,
                )
            parent_slot = self._one_parent(occurrence_id)
            parent = self.index.nodes.get(parent_slot[0]) if parent_slot else None
            if (
                parent is not None
                and parent["kind"] == "Attribute"
                and parent_slot[1] == "value"
            ):
                occurrence_position = self._owner_body_position(
                    occurrence_id,
                    instance.owner_function_node_id,
                )
                construction_position = self._owner_body_position(
                    instance.assignment_node_id,
                    instance.owner_function_node_id,
                )
                if (
                    occurrence_position is None
                    or construction_position is None
                    or occurrence_position <= construction_position
                ):
                    self._reject(
                        "PYC3606",
                        "Static-record fields cannot be read before construction completes",
                        parent,
                    )
                field_name = parent["fields"].get("attr")
                field = fields.get(field_name)
                if field is None:
                    self._reject(
                        "PYC3607",
                        f"Static-record field {field_name!r} is not declared",
                        parent,
                    )
                if self._is_store_target(parent["node_id"]):
                    self._reject(
                        "PYC3607",
                        "Static-record fields are immutable after construction",
                        parent,
                    )
                outer = self._one_parent(parent["node_id"])
                if outer and self.index.node(outer[0])["kind"] == "Attribute":
                    self._reject(
                        "PYC3607", "Dynamic or chained attribute lookup is unsupported", self.index.node(outer[0])
                    )
                identity = self._identity(
                    occurrence,
                    self.function_records.get(instance.owner_function_node_id, {}),
                )
                access_facts.append(
                    RecordFieldAccessFact(
                        access_node_id=parent["node_id"],
                        instance_id=instance.instance_id,
                        binding_id=instance.binding_id,
                        record_id=instance.record_id,
                        field_id=field.field_id,
                        field_name=field.source_name,
                        field_category=field.category,
                        owner_function_node_id=instance.owner_function_node_id,
                        module_id=identity.module_id,
                        document_id=identity.document_id,
                        logical_name=identity.logical_name,
                        access_mode="read",
                        statically_bound=True,
                    )
                )
                continue
            if self._is_dynamic_attribute_use(occurrence_id):
                self._reject(
                    "PYC3607", "Dynamic attribute access on static records is unsupported", occurrence
                )
            self._reject(
                "PYC3606",
                "Static-record instances cannot be aliased, rebound, escaped, compared by identity, tested for truth, passed, returned, or stored in containers",
                occurrence,
            )
        identity = self._identity(
            self.index.node(instance.owner_function_node_id),
            self.function_records.get(instance.owner_function_node_id, {}),
        )
        binding = RecordInstanceBindingFact(
            binding_id=instance.binding_id,
            instance_id=instance.instance_id,
            record_id=instance.record_id,
            source_name=instance.source_name,
            declaration_node_id=instance.target_node_id,
            occurrence_node_ids=occurrence_ids,
            allowed_field_access_node_ids=tuple(
                item.access_node_id for item in access_facts
            ),
            owner_function_node_id=instance.owner_function_node_id,
            module_id=identity.module_id,
            document_id=identity.document_id,
            logical_name=identity.logical_name,
            category=RecordValueCategory.INSTANCE,
            single_assignment=True,
            noalias=True,
            escapes=False,
        )
        return binding, tuple(access_facts)

    def _reject_cross_module_imports(self, specs: tuple[_RecordSpec, ...]) -> None:
        by_source = defaultdict(list)
        for spec in specs:
            self._check_canceled()
            by_source[spec.definition.source_name].append(spec)
        for node in sorted(
            (item for item in self._nodes() if item["kind"] == "ImportFrom"),
            key=lambda item: self._ordinal(item["node_id"]),
        ):
            self._check_canceled()
            imported_module = node["fields"].get("module")
            for alias_id in node["fields"].get("names", ()):
                self._check_canceled()
                alias = self.index.nodes.get(alias_id)
                if alias is None:
                    continue
                for spec in by_source.get(alias["fields"].get("name"), ()):
                    if imported_module == spec.definition.module_id:
                        self._reject(
                            "PYC3608",
                            "Cross-module static-record imports are deferred; records remain module-local",
                            alias,
                        )

    def _reject_forward_object_annotations(self, specs: tuple[_RecordSpec, ...]) -> None:
        names = {
            name
            for spec in specs
            for name in (
                spec.definition.source_name,
                spec.definition.flattened_name,
            )
        }
        for function in sorted(
            (
                item
                for item in self._nodes()
                if item["kind"] in {"FunctionDef", "AsyncFunctionDef"}
            ),
            key=lambda item: self._ordinal(item["node_id"]),
        ):
            self._check_canceled()
            arguments = self.index.nodes.get(function["fields"].get("args"), {})
            parameter_ids = tuple(arguments.get("fields", {}).get("posonlyargs", ())) + tuple(
                arguments.get("fields", {}).get("args", ())
            ) + tuple(arguments.get("fields", {}).get("kwonlyargs", ()))
            annotation_ids = [
                self.index.node(item)["fields"].get("annotation")
                for item in parameter_ids
            ]
            annotation_ids.append(function["fields"].get("returns"))
            for annotation_id in annotation_ids:
                self._check_canceled()
                annotation = self.index.nodes.get(annotation_id)
                if annotation and (
                    (
                        annotation["kind"] == "Constant"
                        and annotation["fields"].get("value") in names
                    )
                    or (
                        annotation["kind"] == "Name"
                        and annotation["fields"].get("id") in names
                    )
                ):
                    self._reject(
                        "PYC3606",
                        "Static-record parameters and returns are unsupported, including forward annotations",
                        annotation,
                    )

    def _require_same_module(
        self, definition: RecordDefinitionFact, owner: dict[str, Any]
    ) -> None:
        metadata = self.function_records.get(owner["node_id"])
        if metadata and metadata.get("module_id") is not None:
            if str(metadata["module_id"]) != definition.module_id:
                self._reject(
                    "PYC3608",
                    "Static-record construction is restricted to the defining module",
                    owner,
                )
            return
        owner_document = self._node_document_id(owner)
        if owner_document and definition.document_id and owner_document != definition.document_id:
            self._reject(
                "PYC3608",
                "Static-record construction is restricted to the defining source document",
                owner,
            )

    def _argument_category(
        self,
        node_id: str,
        owner: dict[str, Any],
        known_instance_fields: Mapping[tuple[str, str], Mapping[str, ValueCategory]] | None = None,
    ) -> ValueCategory:
        known = self.categories.get(node_id, ValueCategory.UNKNOWN)
        if known not in {ValueCategory.UNKNOWN, ValueCategory.CONTRADICTORY}:
            return known
        node = self.index.node(node_id)
        if node["kind"] == "Constant":
            value = node["fields"].get("value")
            if isinstance(value, bool):
                return ValueCategory.BOOLEAN
            if isinstance(value, int):
                return ValueCategory.INTEGER
            if isinstance(value, float):
                return ValueCategory.FLOAT
            return ValueCategory.UNKNOWN
        if node["kind"] == "Name":
            name = node["fields"].get("id")
            arguments = self.index.nodes.get(owner["fields"].get("args"), {})
            for argument_id in tuple(arguments.get("fields", {}).get("posonlyargs", ())) + tuple(
                arguments.get("fields", {}).get("args", ())
            ) + tuple(arguments.get("fields", {}).get("kwonlyargs", ())):
                self._check_canceled()
                argument = self.index.node(argument_id)
                if argument["fields"].get("arg") != name:
                    continue
                annotation = self.index.nodes.get(argument["fields"].get("annotation"))
                if annotation and annotation["kind"] == "Name":
                    return _FIELD_CATEGORIES.get(
                        annotation["fields"].get("id"), ValueCategory.UNKNOWN
                    )
        if node["kind"] == "Attribute" and known_instance_fields:
            receiver = self.index.nodes.get(node["fields"].get("value"))
            source_binding = (
                self.binding_by_occurrence.get(receiver["node_id"])
                if receiver is not None and receiver["kind"] == "Name"
                else None
            )
            fields = known_instance_fields.get(
                (owner["node_id"], str(source_binding.get("binding_id")))
            ) if source_binding else None
            if fields is not None:
                return fields.get(node["fields"].get("attr"), ValueCategory.UNKNOWN)
        if node["kind"] == "UnaryOp":
            return self._argument_category(
                node["fields"].get("operand"), owner, known_instance_fields
            )
        if node["kind"] == "BinOp":
            left = self._argument_category(
                node["fields"].get("left"), owner, known_instance_fields
            )
            right = self._argument_category(
                node["fields"].get("right"), owner, known_instance_fields
            )
            if left is right and left in {ValueCategory.INTEGER, ValueCategory.FLOAT}:
                operator = self.index.nodes.get(node["fields"].get("op"), {})
                if operator.get("kind") != "Div" or left is ValueCategory.FLOAT:
                    return left
        return ValueCategory.UNKNOWN

    def _parameter_names(self, function: dict[str, Any]) -> set[str]:
        arguments = self.index.nodes.get(function["fields"].get("args"), {})
        ids = tuple(arguments.get("fields", {}).get("posonlyargs", ())) + tuple(
            arguments.get("fields", {}).get("args", ())
        ) + tuple(arguments.get("fields", {}).get("kwonlyargs", ()))
        return {
            str(self.index.node(item)["fields"].get("arg", "")) for item in ids
        }

    def _function_name_occurrences(
        self, function_node_id: str, source_name: str
    ) -> tuple[str, ...]:
        found: list[str] = []
        stack = list(reversed(self.index.node(function_node_id)["fields"].get("body", ())))
        while stack:
            self._check_canceled()
            node_id = stack.pop()
            node = self.index.node(node_id)
            if node["kind"] == "Name" and node["fields"].get("id") == source_name:
                found.append(node_id)
            if node["kind"] in {"FunctionDef", "AsyncFunctionDef", "ClassDef"}:
                continue
            stack.extend(reversed(self.index.child_ids(node)))
        return tuple(found)

    def _owner_binding_conflict(
        self,
        owner: dict[str, Any],
        source_name: str,
        declaration_node_id: str,
    ) -> dict[str, Any] | None:
        """Return any second owner-scope binding/unbinding form.

        Python binds names through more syntax than ordinary assignments.  The
        general symbol facts deliberately serve the cumulative language, so
        the record gate independently closes its stricter one-declaration
        proof over exception aliases, patterns, imports, nested definitions,
        scope directives, context-manager targets, and deletion as well.
        """

        owner_id = owner["node_id"]
        for node in sorted(self._nodes(), key=lambda item: self._ordinal(item["node_id"])):
            self._check_canceled()
            node_id = node["node_id"]
            if node_id == declaration_node_id:
                continue
            if self._enclosing_function(node_id) != owner_id:
                continue
            if self._crosses_class_or_lambda_scope(node_id, owner_id):
                continue
            kind = node["kind"]
            fields = node["fields"]
            if kind == "Name" and fields.get("id") == source_name:
                if self._is_comprehension_iteration_target(node_id):
                    continue
                if self._is_store_target(node_id):
                    return node
                continue
            if kind in {"Global", "Nonlocal"} and source_name in tuple(fields.get("names", ())):
                return node
            if kind == "ExceptHandler" and fields.get("name") == source_name:
                return node
            if kind in {"MatchAs", "MatchStar"} and fields.get("name") == source_name:
                return node
            if kind == "MatchMapping" and fields.get("rest") == source_name:
                return node
            if (
                kind in {"FunctionDef", "AsyncFunctionDef", "ClassDef"}
                and node_id != owner_id
                and fields.get("name") == source_name
            ):
                return node
            if kind == "alias":
                imported = str(fields.get("name") or "")
                bound_name = str(fields.get("asname") or imported.split(".", 1)[0])
                if bound_name == source_name:
                    return node
        return None

    def _owner_body_position(
        self,
        node_id: str,
        owner_function_node_id: str,
    ) -> int | None:
        owner = self.index.nodes.get(owner_function_node_id)
        if owner is None:
            return None
        body = tuple(owner["fields"].get("body", ()))
        current = node_id
        seen: set[str] = set()
        while current not in seen:
            self._check_canceled()
            seen.add(current)
            parent = self._one_parent(current)
            if not parent:
                return None
            if parent[0] == owner_function_node_id and parent[1] == "body":
                try:
                    return body.index(current)
                except ValueError:
                    return None
            current = parent[0]
        return None

    def _crosses_class_or_lambda_scope(
        self,
        node_id: str,
        owner_function_node_id: str,
    ) -> bool:
        current = node_id
        seen: set[str] = set()
        while current not in seen:
            self._check_canceled()
            seen.add(current)
            parent = self._one_parent(current)
            if not parent or parent[0] == owner_function_node_id:
                return False
            parent_node = self.index.node(parent[0])
            if parent_node["kind"] in {"ClassDef", "Lambda"}:
                return True
            current = parent[0]
        return True

    def _is_comprehension_iteration_target(self, node_id: str) -> bool:
        current = node_id
        seen: set[str] = set()
        while current not in seen:
            self._check_canceled()
            seen.add(current)
            parent = self._one_parent(current)
            if not parent:
                return False
            parent_node = self.index.node(parent[0])
            if parent_node["kind"] == "comprehension":
                return parent[1] == "target"
            if parent_node["kind"] not in {"Tuple", "List", "Starred"}:
                return False
            current = parent[0]
        return False

    def _is_dynamic_attribute_use(self, occurrence_id: str) -> bool:
        parent_slot = self._one_parent(occurrence_id)
        if not parent_slot:
            return False
        parent = self.index.node(parent_slot[0])
        if parent["kind"] != "Call" or parent_slot[1] not in {"args", "keywords"}:
            return False
        function = self.index.nodes.get(parent["fields"].get("func"))
        return bool(
            function
            and function["kind"] == "Name"
            and function["fields"].get("id") in _DYNAMIC_ATTRIBUTE_BUILTINS
        )

    def _is_store_target(self, node_id: str) -> bool:
        current = node_id
        while True:
            self._check_canceled()
            parent_slot = self._one_parent(current)
            if not parent_slot:
                return False
            parent = self.index.node(parent_slot[0])
            if (parent["kind"], parent_slot[1]) in _STORE_PARENT_SLOTS:
                return True
            if parent["kind"] in {"Tuple", "List"} and parent_slot[1] == "elts":
                current = parent["node_id"]
                continue
            return False

    def _enclosing_function(self, node_id: str) -> str | None:
        current = node_id
        seen: set[str] = set()
        while current not in seen:
            self._check_canceled()
            seen.add(current)
            parent = self._one_parent(current)
            if not parent:
                return None
            node = self.index.node(parent[0])
            if node["kind"] in {"FunctionDef", "AsyncFunctionDef"}:
                return node["node_id"]
            current = node["node_id"]
        return None

    def _crosses_nested_scope(self, node_id: str, owner_function_node_id: str) -> bool:
        current = node_id
        seen: set[str] = set()
        nested_scope_kinds = {"Lambda", "ListComp", "SetComp", "DictComp", "GeneratorExp"}
        while current not in seen:
            self._check_canceled()
            seen.add(current)
            parent = self._one_parent(current)
            if not parent:
                return False
            parent_id = parent[0]
            if parent_id == owner_function_node_id:
                return False
            node = self.index.node(parent_id)
            if node["kind"] in nested_scope_kinds:
                return True
            current = parent_id
        return True

    def _one_parent(self, node_id: str) -> tuple[str, str] | None:
        values = self.parents.get(node_id, ())
        if not values:
            return None
        return min(values, key=lambda item: (self._ordinal(item[0]), item[1]))

    def _identity(
        self, node: dict[str, Any], metadata: Mapping[str, Any]
    ) -> _Identity:
        node_document_id = self._node_document_id(node)
        document_identity = self.identity_by_document.get(node_document_id)
        document_id = str(
            metadata.get("document_id")
            or metadata.get("source_document_id")
            or node_document_id
            or self.module.get("document_id", "")
        )
        module_id = str(
            metadata.get("module_id")
            or (document_identity.module_id if document_identity else None)
            or self.default_module_id
        )
        logical_name = str(
            metadata.get("logical_name")
            or metadata.get("logical_source_name")
            or (document_identity.logical_name if document_identity else None)
            or self.default_logical_name
        )
        return _Identity(module_id, document_id, logical_name)

    @staticmethod
    def _coerce_category(value: ValueCategory | str) -> ValueCategory:
        if isinstance(value, ValueCategory):
            return value
        try:
            return ValueCategory(value)
        except ValueError:
            return ValueCategory.UNKNOWN

    def _is_none_annotation(self, node_id: Any) -> bool:
        node = self.index.nodes.get(node_id)
        return bool(
            node
            and node["kind"] == "Constant"
            and node["fields"].get("value") is None
        )

    @staticmethod
    def _node_document_id(node: Mapping[str, Any]) -> str:
        span = node.get("provenance", {}).get("source_span") or {}
        return str(span.get("document_id") or "")

    def _ordinal(self, node_id: str) -> int:
        return self.index.ordinals.get(node_id, 2**63 - 1)

    def _nodes(self):
        """Yield normalized nodes with a bounded cancellation safe point."""

        for node in self.index.nodes.values():
            self._check_canceled()
            yield node

    def _reject(
        self,
        code: str,
        message: str,
        node: dict[str, Any],
        identity: _Identity | None = None,
    ) -> None:
        self._check_canceled()
        actual = identity or self._identity(node, {})
        raise RecordAnalysisError(
            code,
            message,
            node_id=node["node_id"],
            module_id=actual.module_id,
            document_id=actual.document_id,
            logical_name=actual.logical_name,
            source_span=node.get("provenance", {}).get("source_span"),
        )

    def _check_canceled(self) -> None:
        if self.cancellation is not None and bool(
            getattr(self.cancellation, "is_canceled", False)
        ):
            raise RecordAnalysisCanceled
