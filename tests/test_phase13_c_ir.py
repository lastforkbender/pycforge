from __future__ import annotations

import unittest
from dataclasses import replace

from pycforge.converter.c_output import CRenderer, validate_c_text
from pycforge.converter.ir.c_ir import (
    CAssignmentStatement,
    CBlock,
    CFunctionDefinition,
    CFunctionPrototype,
    CIdentifier,
    CIdentifierRef,
    CInclude,
    CIntegerLiteral,
    CMemberAccessExpr,
    CMemberAccessMode,
    CModuleManifestEntry,
    CParameter,
    CProvenance,
    CQualifier,
    CRecordDefinition,
    CRecordField,
    CRecordInitializer,
    CReturnStatement,
    CStorage,
    CTranslationUnitBuilder,
    CType,
    CVariableDeclaration,
    MODULE_SCHEMA_VERSION,
    RECORD_SCHEMA_VERSION,
    serialize_translation_unit,
    validate_translation_unit,
)


def _record_unit(*, initializer_elements: int = 2):
    source = CProvenance("source", "doc-main")
    record_provenance = CProvenance("source-record", "doc-main")
    point = CIdentifier("type-point", "PycfPoint", record_provenance)
    field_x = CRecordField(
        "field-x",
        CIdentifier("field-point-x", "x", record_provenance),
        CType("int64_t"),
        record_provenance,
    )
    field_y = CRecordField(
        "field-y",
        CIdentifier("field-point-y", "y", record_provenance),
        CType("int64_t"),
        record_provenance,
    )
    record = CRecordDefinition(
        "record-point",
        point,
        (field_x, field_y),
        record_provenance,
    )

    make_identifier = CIdentifier("function-make-x", "make_x", source)
    make_proto_parameters = (
        CParameter("make-a-proto", CIdentifier("make-a", "a", source), CType("int64_t"), source),
        CParameter("make-b-proto", CIdentifier("make-b", "b", source), CType("int64_t"), source),
    )
    make_definition_parameters = (
        CParameter("make-a-def", CIdentifier("make-a", "a", source), CType("int64_t"), source),
        CParameter("make-b-def", CIdentifier("make-b", "b", source), CType("int64_t"), source),
    )
    make_prototype = CFunctionPrototype(
        "make-prototype",
        make_identifier,
        CType("int64_t"),
        make_proto_parameters,
        CStorage.NONE,
        source,
        "main",
        "doc-main",
        0,
    )
    values = (
        CIdentifierRef("make-a-ref", "make-a", source),
        CIdentifierRef("make-b-ref", "make-b", source),
    )[:initializer_elements]
    local_point = CVariableDeclaration(
        "local-point-declaration",
        CIdentifier("local-point", "point", source),
        CType("PycfPoint", (CQualifier.CONST,)),
        CRecordInitializer("point-initializer", CType("PycfPoint"), values, source),
        CStorage.NONE,
        source,
    )
    direct_read = CMemberAccessExpr(
        "direct-x-read",
        CIdentifierRef("local-point-ref", "local-point", source),
        "field-point-x",
        CMemberAccessMode.DIRECT,
        source,
    )
    make_definition = CFunctionDefinition(
        "make-definition",
        make_identifier,
        CType("int64_t"),
        make_definition_parameters,
        CBlock(
            "make-body",
            (
                local_point,
                CReturnStatement("make-return", direct_read, source),
            ),
            source,
        ),
        CStorage.NONE,
        source,
        "main",
        "doc-main",
        0,
    )

    read_identifier = CIdentifier("function-read-x", "read_x", source)
    pointer_type = CType("PycfPoint", (CQualifier.CONST,), 1)
    read_prototype = CFunctionPrototype(
        "read-prototype",
        read_identifier,
        CType("int64_t"),
        (CParameter("read-point-proto", CIdentifier("read-point", "point", source), pointer_type, source),),
        CStorage.NONE,
        source,
        "main",
        "doc-main",
        1,
    )
    pointer_read = CMemberAccessExpr(
        "pointer-x-read",
        CIdentifierRef("read-point-ref", "read-point", source),
        "field-point-x",
        CMemberAccessMode.POINTER,
        source,
    )
    read_definition = CFunctionDefinition(
        "read-definition",
        read_identifier,
        CType("int64_t"),
        (CParameter("read-point-def", CIdentifier("read-point", "point", source), pointer_type, source),),
        CBlock(
            "read-body",
            (CReturnStatement("read-return", pointer_read, source),),
            source,
        ),
        CStorage.NONE,
        source,
        "main",
        "doc-main",
        1,
    )

    manifest = (CModuleManifestEntry("main", "doc-main", "main.py", 0, True),)
    builder = CTranslationUnitBuilder(
        "c11-portable-fixed-v1",
        schema_version=RECORD_SCHEMA_VERSION,
        provenance=source,
        module_manifest=manifest,
        module_order=("main",),
    )
    builder.add_include(CInclude("include-stdint", "stdint.h", True, source))
    for declaration in (
        record,
        make_prototype,
        read_prototype,
        make_definition,
        read_definition,
    ):
        builder.add_declaration(declaration)
    return builder.build()


def _multidoc_record_unit():
    unit = _record_unit()
    record, make_prototype, _, make_definition, _ = unit.declarations
    qualified_identifier = CIdentifier(
        "function-make-x",
        f"pycm_{'a' * 64}__main__make_x",
        make_prototype.identifier.provenance,
    )
    manifest = (
        CModuleManifestEntry("main", "doc-main", "main.py", 0, True),
        CModuleManifestEntry("other", "doc-other", "other.py", 1, False),
    )
    return replace(
        unit,
        declarations=(
            record,
            replace(make_prototype, identifier=qualified_identifier),
            replace(make_definition, identifier=qualified_identifier),
        ),
        module_manifest=manifest,
        module_order=("main", "other"),
    )


class Phase13CIRTests(unittest.TestCase):
    def test_record_nodes_validate_serialize_and_render_deterministically(self):
        unit = _record_unit()
        self.assertEqual(validate_translation_unit(unit).errors, ())
        rendered = CRenderer().render(unit).text
        self.assertEqual(
            rendered,
            "#include <stdint.h>\n"
            "\n"
            "typedef struct PycfPoint {\n"
            "    int64_t x;\n"
            "    int64_t y;\n"
            "} PycfPoint;\n"
            "\n"
            "int64_t make_x(int64_t a, int64_t b);\n"
            "\n"
            "int64_t read_x(const PycfPoint * point);\n"
            "\n"
            "int64_t make_x(int64_t a, int64_t b)\n"
            "{\n"
            "    const PycfPoint point = {a, b};\n"
            "    return point.x;\n"
            "}\n"
            "\n"
            "int64_t read_x(const PycfPoint * point)\n"
            "{\n"
            "    return point->x;\n"
            "}\n",
        )
        self.assertTrue(validate_c_text(rendered).accepted)
        serialized = serialize_translation_unit(unit)
        self.assertEqual(serialized["schema_version"], "c-ir/0.13")
        self.assertEqual(serialized["declarations"][0]["kind"], "CRecordDefinition")
        self.assertEqual(
            serialized["declarations"][3]["body"]["statements"][0]["initializer"]["kind"],
            "CRecordInitializer",
        )

    def test_record_initializer_requires_exact_field_arity(self):
        validation = validate_translation_unit(_record_unit(initializer_elements=1))
        self.assertFalse(validation.accepted)
        self.assertTrue(any("record initializer arity mismatch" in item for item in validation.errors))

    def test_record_fields_reject_every_type_outside_the_exact_scalar_profile(self):
        invalid_types = (
            CType("uint64_t"),
            CType("int"),
            CType("long"),
            CType("char", pointer_depth=1),
            CType("int64_t", pointer_depth=1),
            CType("int64_t", (CQualifier.CONST,)),
            CType("double", (CQualifier.VOLATILE,)),
            CType("bool", array_extents=(1,)),
            CType("int64_t", object_const=True),
            CType("int64_t", array_extents=(1,), object_const=True),
        )
        for invalid_type in invalid_types:
            with self.subTest(type_ref=invalid_type):
                unit = _record_unit()
                record = unit.declarations[0]
                self.assertIsInstance(record, CRecordDefinition)
                field = replace(record.fields[0], type_ref=invalid_type)
                bad_record = replace(record, fields=(field, *record.fields[1:]))
                validation = validate_translation_unit(
                    replace(unit, declarations=(bad_record, *unit.declarations[1:]))
                )
                self.assertFalse(validation.accepted)
                self.assertIn(
                    "record fields require an exact unqualified int64_t, "
                    "double, or bool type: x",
                    validation.errors,
                )

    def test_record_fields_accept_each_exact_scalar_profile_type(self):
        source = CProvenance("source-record", "doc-main")
        manifest = (CModuleManifestEntry("main", "doc-main", "main.py", 0, True),)
        for field_type, required_header in (
            (CType("int64_t"), "stdint.h"),
            (CType("double"), None),
            (CType("bool"), "stdbool.h"),
        ):
            with self.subTest(field_type=field_type):
                record = CRecordDefinition(
                    "record-scalar",
                    CIdentifier("type-scalar", "Scalar", source),
                    (
                        CRecordField(
                            "field-scalar-value",
                            CIdentifier("field-scalar-value", "value", source),
                            field_type,
                            source,
                        ),
                    ),
                    source,
                )
                builder = CTranslationUnitBuilder(
                    "c11-portable-fixed-v1",
                    schema_version=RECORD_SCHEMA_VERSION,
                    provenance=source,
                    module_manifest=manifest,
                    module_order=("main",),
                )
                if required_header is not None:
                    builder.add_include(
                        CInclude(
                            f"include-{required_header}",
                            required_header,
                            True,
                            source,
                        )
                    )
                builder.add_declaration(record)
                self.assertEqual(validate_translation_unit(builder.build()).errors, ())

    def test_record_and_field_provenance_are_manifest_bound_and_consistent(self):
        unit = _record_unit()
        record = unit.declarations[0]
        ghost_record = replace(
            record,
            provenance=CProvenance("source-record", "doc-ghost"),
        )
        ghost_validation = validate_translation_unit(
            replace(unit, declarations=(ghost_record, *unit.declarations[1:]))
        )
        self.assertFalse(ghost_validation.accepted)
        self.assertIn(
            "record definition PycfPoint provenance must reference a document "
            "in the module manifest",
            ghost_validation.errors,
        )

        multidoc = _multidoc_record_unit()
        self.assertEqual(validate_translation_unit(multidoc).errors, ())
        record = multidoc.declarations[0]
        foreign = CProvenance("source-record", "doc-other")
        foreign_field = replace(
            record.fields[0],
            provenance=foreign,
            identifier=replace(record.fields[0].identifier, provenance=foreign),
        )
        foreign_record = replace(
            record,
            fields=(foreign_field, *record.fields[1:]),
        )
        foreign_validation = validate_translation_unit(
            replace(multidoc, declarations=(foreign_record, *multidoc.declarations[1:]))
        )
        self.assertFalse(foreign_validation.accepted)
        self.assertIn(
            "record field x provenance disagrees with its owning source document",
            foreign_validation.errors,
        )

    def test_record_uses_are_anchored_to_the_owning_function_document(self):
        unit = _multidoc_record_unit()
        record, prototype, definition = unit.declarations
        local_record, return_statement = definition.body.statements
        initializer = local_record.initializer
        member = return_statement.expression
        self.assertIsInstance(initializer, CRecordInitializer)
        self.assertIsInstance(member, CMemberAccessExpr)
        foreign = CProvenance("source", "doc-other")
        ghost = CProvenance("source", "doc-ghost")

        cases = (
            (
                "initializer",
                replace(
                    definition,
                    body=replace(
                        definition.body,
                        statements=(
                            replace(local_record, initializer=replace(initializer, provenance=foreign)),
                            return_statement,
                        ),
                    ),
                ),
                "record initializer for PycfPoint provenance disagrees with its owning source document",
            ),
            (
                "member",
                replace(
                    definition,
                    body=replace(
                        definition.body,
                        statements=(
                            local_record,
                            replace(return_statement, expression=replace(member, provenance=foreign)),
                        ),
                    ),
                ),
                "record member access provenance disagrees with its owning source document",
            ),
            (
                "receiver",
                replace(
                    definition,
                    body=replace(
                        definition.body,
                        statements=(
                            local_record,
                            replace(
                                return_statement,
                                expression=replace(
                                    member,
                                    receiver=replace(member.receiver, provenance=ghost),
                                ),
                            ),
                        ),
                    ),
                ),
                "record member receiver provenance must reference a document in the module manifest",
            ),
            (
                "local",
                replace(
                    definition,
                    body=replace(
                        definition.body,
                        statements=(replace(local_record, provenance=foreign), return_statement),
                    ),
                ),
                "local record point provenance disagrees with its owning source document",
            ),
        )
        for label, bad_definition, expected_error in cases:
            with self.subTest(label=label):
                validation = validate_translation_unit(
                    replace(unit, declarations=(record, prototype, bad_definition))
                )
                self.assertFalse(validation.accepted)
                self.assertIn(expected_error, validation.errors)

    def test_member_access_is_a_structured_assignment_target(self):
        unit = _record_unit()
        source = CProvenance("source", "doc-main")
        function = CIdentifier("function-set-x", "set_x", source)
        pointer_type = CType("PycfPoint", pointer_depth=1)
        prototype_parameters = (
            CParameter("set-point-proto", CIdentifier("set-point", "point", source), pointer_type, source),
            CParameter("set-value-proto", CIdentifier("set-value", "value", source), CType("int64_t"), source),
        )
        definition_parameters = (
            CParameter("set-point-def", CIdentifier("set-point", "point", source), pointer_type, source),
            CParameter("set-value-def", CIdentifier("set-value", "value", source), CType("int64_t"), source),
        )
        prototype = CFunctionPrototype(
            "set-prototype",
            function,
            CType("void"),
            prototype_parameters,
            CStorage.NONE,
            source,
            "main",
            "doc-main",
            2,
        )
        assignment = CAssignmentStatement(
            "set-assignment",
            CMemberAccessExpr(
                "set-member",
                CIdentifierRef("set-point-ref", "set-point", source),
                "field-point-x",
                CMemberAccessMode.POINTER,
                source,
            ),
            CIdentifierRef("set-value-ref", "set-value", source),
            source,
        )
        definition = CFunctionDefinition(
            "set-definition",
            function,
            CType("void"),
            definition_parameters,
            CBlock("set-body", (assignment,), source),
            CStorage.NONE,
            source,
            "main",
            "doc-main",
            2,
        )
        record, make_prototype, read_prototype, make_definition, read_definition = unit.declarations
        extended = replace(
            unit,
            declarations=(
                record,
                make_prototype,
                read_prototype,
                prototype,
                make_definition,
                read_definition,
                definition,
            ),
        )
        self.assertEqual(validate_translation_unit(extended).errors, ())
        rendered = CRenderer().render(extended).text
        self.assertIn("    point->x = value;\n", rendered)
        self.assertTrue(validate_c_text(rendered).accepted)

    def test_direct_member_assignment_rejects_a_const_record_object(self):
        unit = _record_unit()
        source = CProvenance("source", "doc-main")
        make_definition = unit.declarations[3]
        local_point, return_statement = make_definition.body.statements
        assignment = CAssignmentStatement(
            "set-const-direct-assignment",
            CMemberAccessExpr(
                "set-const-direct-member",
                CIdentifierRef("set-const-direct-point-ref", "local-point", source),
                "field-point-x",
                CMemberAccessMode.DIRECT,
                source,
            ),
            CIntegerLiteral("set-const-direct-value", 1, provenance=source),
            source,
        )
        bad_definition = replace(
            make_definition,
            body=replace(
                make_definition.body,
                statements=(local_point, assignment, return_statement),
            ),
        )
        validation = validate_translation_unit(
            replace(
                unit,
                declarations=(*unit.declarations[:3], bad_definition, *unit.declarations[4:]),
            )
        )
        self.assertFalse(validation.accepted)
        self.assertIn(
            "assignment target is a member of a const record object",
            validation.errors,
        )

    def test_direct_member_assignment_preserves_mutable_record_objects(self):
        unit = _record_unit()
        source = CProvenance("source", "doc-main")
        make_definition = unit.declarations[3]
        local_point, return_statement = make_definition.body.statements
        mutable_point = replace(local_point, type_ref=CType("PycfPoint"))
        assignment = CAssignmentStatement(
            "set-mutable-direct-assignment",
            CMemberAccessExpr(
                "set-mutable-direct-member",
                CIdentifierRef("set-mutable-direct-point-ref", "local-point", source),
                "field-point-x",
                CMemberAccessMode.DIRECT,
                source,
            ),
            CIntegerLiteral("set-mutable-direct-value", 1, provenance=source),
            source,
        )
        mutable_definition = replace(
            make_definition,
            body=replace(
                make_definition.body,
                statements=(mutable_point, assignment, return_statement),
            ),
        )
        mutable_unit = replace(
            unit,
            declarations=(
                *unit.declarations[:3],
                mutable_definition,
                *unit.declarations[4:],
            ),
        )
        self.assertEqual(validate_translation_unit(mutable_unit).errors, ())
        rendered = CRenderer().render(mutable_unit).text
        self.assertIn("    point.x = 1;\n", rendered)
        self.assertTrue(validate_c_text(rendered).accepted)

    def test_pointer_member_assignment_rejects_a_pointer_to_const_record(self):
        unit = _record_unit()
        source = CProvenance("source", "doc-main")
        read_definition = unit.declarations[4]
        (return_statement,) = read_definition.body.statements
        assignment = CAssignmentStatement(
            "set-const-pointer-assignment",
            CMemberAccessExpr(
                "set-const-pointer-member",
                CIdentifierRef("set-const-pointer-point-ref", "read-point", source),
                "field-point-x",
                CMemberAccessMode.POINTER,
                source,
            ),
            CIntegerLiteral("set-const-pointer-value", 1, provenance=source),
            source,
        )
        bad_definition = replace(
            read_definition,
            body=replace(
                read_definition.body,
                statements=(assignment, return_statement),
            ),
        )
        validation = validate_translation_unit(
            replace(unit, declarations=(*unit.declarations[:4], bad_definition))
        )
        self.assertFalse(validation.accepted)
        self.assertIn(
            "assignment target is a member of a const record object",
            validation.errors,
        )

    def test_record_nodes_cannot_leak_into_historical_schema_serialization(self):
        historical = replace(_record_unit(), schema_version=MODULE_SCHEMA_VERSION)
        validation = validate_translation_unit(historical)
        self.assertFalse(validation.accepted)
        self.assertTrue(any("require C IR schema 0.13" in item for item in validation.errors))
        with self.assertRaisesRegex(ValueError, "record C IR nodes require schema c-ir/0.13"):
            serialize_translation_unit(historical)

    def test_independent_conformance_rejects_malformed_record_syntax(self):
        self.assertFalse(validate_c_text("typedef struct Point { int x; } Other;\n").accepted)
        self.assertFalse(validate_c_text("typedef struct Point { } Point;\n").accepted)
        self.assertTrue(
            validate_c_text(
                "typedef struct Point { int x; } Point;\n"
                "int read_point(const Point * point)\n"
                "{\n"
                "    return point->x;\n"
                "}\n"
            ).accepted
        )


if __name__ == "__main__":
    unittest.main()
