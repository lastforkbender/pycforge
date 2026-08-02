from __future__ import annotations

import ast
import tokenize
from types import MappingProxyType
from typing import Any

from pycforge.converter.contracts.configuration import supports_modules
from pycforge.converter.core.diagnostics import Diagnostic
from pycforge.converter.core.enums import Severity, StageTerminal
from pycforge.converter.core.fingerprint import fingerprint
from pycforge.converter.core.stage_artifact import StageArtifact
from pycforge.converter.core.stage_outcome import StageOutcome
from pycforge.converter.ir.python_ir import PythonIRBundle, PythonIRBundleDocument

from .normalizer import PythonNormalizer
from .parser import ParserVersionError, Python311ParserAdapter
from .source_document import SourceDocument
from .validation import validate_python_ir, validate_python_ir_bundle


def _artifact(kind: str, version: str, prior: StageArtifact, payload: dict[str, object]) -> StageArtifact:
    serial = {key: list(value) if isinstance(value, tuple) else value for key, value in payload.items()}
    artifact_fingerprint = fingerprint(
        "stage-artifact",
        {
            "kind": kind,
            "conversion_id": prior.conversion_id,
            "parent": prior.artifact_fingerprint.value,
            "payload": serial,
        },
    )
    return StageArtifact(
        kind,
        version,
        prior.conversion_id,
        prior.artifact_fingerprint,
        MappingProxyType(payload),
        artifact_fingerprint,
    )


def _module_request(services: Any) -> bool:
    return supports_modules(services.context.canonical.request.rule_set_version)


def _inputs(services: Any):
    bundle = services.context.canonical.request.source_bundle
    return (bundle.primary,) + tuple(bundle.companions)


class SourceDocumentStage:
    stage_id = "frontend.source_document"
    input_schema = "initial/0.1"
    output_schema = "source-bundle/0.2"

    def run(self, artifact: StageArtifact, services: Any) -> StageOutcome:
        if services.context.cancellation.is_canceled:
            return _canceled(self.stage_id)
        if not _module_request(services):
            return self._legacy_run(artifact, services)

        policy = services.context.canonical.request.resource_policy
        documents: list[SourceDocument] = []
        published: list[dict[str, object]] = []
        total_lines = 0
        total_tokens = 0
        parser = Python311ParserAdapter()
        for ordinal, source in enumerate(_inputs(services)):
            if services.context.cancellation.is_canceled:
                return _canceled(self.stage_id)
            document = SourceDocument.create(source.logical_name, source.text)
            total_lines += len(document.line_starts)
            if total_lines > policy.max_source_lines:
                return _rejected(
                    self.stage_id,
                    "PYC3510",
                    "SourceBundle exceeds the aggregate max_source_lines ceiling",
                    source_span=_point_span(document, 1, 0),
                    source_module_id=source.module_id,
                    source_logical_name=source.logical_name,
                )
            try:
                document = parser.tokenize(document)
            except (tokenize.TokenError, IndentationError) as exc:
                return StageOutcome(
                    StageTerminal.REJECTED,
                    diagnostics=(
                        Diagnostic(
                            "PYC2002",
                            Severity.ERROR,
                            self.stage_id,
                            f"Tokenization failed: {exc}",
                            source_span=_tokenization_error_span(document, exc),
                        ),
                    ),
                )
            total_tokens += len(document.tokens)
            if total_tokens > policy.max_tokens:
                return _rejected(
                    self.stage_id,
                    "PYC3510",
                    "SourceBundle exceeds the aggregate max_tokens ceiling",
                    source_span=_point_span(document, 1, 0),
                    source_module_id=source.module_id,
                    source_logical_name=source.logical_name,
                )
            documents.append(document)
            published.append(
                {
                    "module_id": source.module_id,
                    "logical_name": source.logical_name,
                    "bundle_ordinal": ordinal,
                    "is_primary": ordinal == 0,
                    "document_id": document.document_id,
                    "source_document": document.to_dict(),
                }
            )

        services.context.frontend_documents = tuple(documents)
        order = tuple(artifact.payload.get("stage_order", ())) + (self.stage_id,)
        source_bundle = {
            "schema_version": "source-bundle/0.2",
            "primary_module_id": published[0]["module_id"],
            "documents": published,
            "aggregate_source_lines": total_lines,
            "aggregate_tokens": total_tokens,
        }
        return StageOutcome(
            StageTerminal.COMPLETED,
            _artifact(
                "source_bundle",
                "0.2",
                artifact,
                {"stage_order": order, "source_bundle": source_bundle},
            ),
        )

    def _legacy_run(self, artifact: StageArtifact, services: Any) -> StageOutcome:
        source = services.context.canonical.request.source_bundle.primary
        document = SourceDocument.create(source.logical_name, source.text)
        if len(document.line_starts) > services.context.canonical.request.resource_policy.max_source_lines:
            return _rejected(self.stage_id, "PYC2007", "Source line count exceeds max_source_lines")
        try:
            document = Python311ParserAdapter().tokenize(document)
        except (tokenize.TokenError, IndentationError) as exc:
            return StageOutcome(
                StageTerminal.REJECTED,
                diagnostics=(
                    Diagnostic(
                        "PYC2002",
                        Severity.ERROR,
                        self.stage_id,
                        f"Tokenization failed: {exc}",
                        source_span=_tokenization_error_span(document, exc),
                    ),
                ),
            )
        if len(document.tokens) > services.context.canonical.request.resource_policy.max_tokens:
            return _rejected(self.stage_id, "PYC2003", "Token count exceeds max_tokens")
        order = tuple(artifact.payload.get("stage_order", ())) + (self.stage_id,)
        return StageOutcome(
            StageTerminal.COMPLETED,
            _artifact(
                "source_document",
                "0.3",
                artifact,
                {"stage_order": order, "source_document": document.to_dict()},
            ),
        )

    def validate(self, artifact: StageArtifact, services: Any) -> tuple[bool, str]:
        if _module_request(services):
            bundle = artifact.payload.get("source_bundle", {})
            return (
                artifact.kind == "source_bundle"
                and artifact.schema_version == "0.2"
                and bundle.get("schema_version") == "source-bundle/0.2"
                and bool(bundle.get("documents")),
                "invalid source bundle artifact",
            )
        return (
            artifact.kind == "source_document" and "source_document" in artifact.payload,
            "invalid source document artifact",
        )


class ParseStage:
    stage_id = "frontend.parse"
    input_schema = "source-bundle/0.2"
    input_schemas = ("source-document/0.3", "source-bundle/0.2")
    output_schema = "python-ast-bundle/0.4"

    def run(self, artifact: StageArtifact, services: Any) -> StageOutcome:
        if services.context.cancellation.is_canceled:
            return _canceled(self.stage_id)
        if not _module_request(services):
            return self._legacy_run(artifact, services)

        request = services.context.canonical.request
        policy = request.resource_policy
        documents = services.context.frontend_documents
        if len(documents) != len(_inputs(services)):
            return _internal(self.stage_id, "Source bundle scratch state is incomplete")
        parser = Python311ParserAdapter()
        trees: list[ast.Module] = []
        counts: list[dict[str, object]] = []
        total_nodes = 0
        for ordinal, (source, document) in enumerate(zip(_inputs(services), documents)):
            if services.context.cancellation.is_canceled:
                return _canceled(self.stage_id)
            assert isinstance(document, SourceDocument)
            try:
                tree = parser.parse(document, request.python_version)
            except ParserVersionError as exc:
                return _rejected(self.stage_id, "PYC2004", str(exc))
            except SyntaxError as exc:
                where = f"line {exc.lineno or 1}, column {exc.offset or 1}"
                return StageOutcome(
                    StageTerminal.REJECTED,
                    diagnostics=(
                        Diagnostic(
                            "PYC2001",
                            Severity.ERROR,
                            self.stage_id,
                            f"Invalid Python syntax at {where}: {exc.msg}",
                            source_span=_syntax_error_span(document, exc),
                        ),
                    ),
                )
            if _ast_depth(tree) > policy.max_nesting_depth:
                return _rejected(
                    self.stage_id,
                    "PYC2006",
                    f"AST nesting depth exceeds max_nesting_depth in module {source.module_id}",
                    source_span=_point_span(document, 1, 0),
                    source_module_id=source.module_id,
                    source_logical_name=source.logical_name,
                )
            count = sum(1 for _ in ast.walk(tree))
            total_nodes += count
            if total_nodes > policy.max_ast_nodes:
                return _rejected(
                    self.stage_id,
                    "PYC3510",
                    "SourceBundle exceeds the aggregate max_ast_nodes ceiling",
                    source_span=_point_span(document, 1, 0),
                    source_module_id=source.module_id,
                    source_logical_name=source.logical_name,
                )
            trees.append(tree)
            counts.append(
                {
                    "module_id": source.module_id,
                    "document_id": document.document_id,
                    "bundle_ordinal": ordinal,
                    "ast_node_count": count,
                }
            )

        services.context.frontend_trees = tuple(trees)
        order = tuple(artifact.payload["stage_order"]) + (self.stage_id,)
        payload = {
            "stage_order": order,
            "source_bundle": artifact.payload["source_bundle"],
            "ast_documents": counts,
            "aggregate_ast_nodes": total_nodes,
        }
        return StageOutcome(
            StageTerminal.COMPLETED,
            _artifact("python_ast_bundle", "0.4", artifact, payload),
        )

    def _legacy_run(self, artifact: StageArtifact, services: Any) -> StageOutcome:
        source = services.context.canonical.request.source_bundle.primary
        document = SourceDocument.create(source.logical_name, source.text)
        try:
            tree = Python311ParserAdapter().parse(
                document,
                services.context.canonical.request.python_version,
            )
        except ParserVersionError as exc:
            return _rejected(self.stage_id, "PYC2004", str(exc))
        except SyntaxError as exc:
            where = f"line {exc.lineno or 1}, column {exc.offset or 1}"
            return StageOutcome(
                StageTerminal.REJECTED,
                diagnostics=(
                    Diagnostic(
                        "PYC2001",
                        Severity.ERROR,
                        self.stage_id,
                        f"Invalid Python syntax at {where}: {exc.msg}",
                        source_span=_syntax_error_span(document, exc),
                    ),
                ),
            )
        count = sum(1 for _ in ast.walk(tree))
        policy = services.context.canonical.request.resource_policy
        if _ast_depth(tree) > policy.max_nesting_depth:
            return _rejected(self.stage_id, "PYC2006", "AST nesting depth exceeds max_nesting_depth")
        if count > policy.max_ast_nodes:
            return _rejected(self.stage_id, "PYC2005", "AST node count exceeds max_ast_nodes")
        services.context.frontend_tree = tree
        order = tuple(artifact.payload["stage_order"]) + (self.stage_id,)
        return StageOutcome(
            StageTerminal.COMPLETED,
            _artifact(
                "python_ast",
                "0.3",
                artifact,
                {
                    "stage_order": order,
                    "ast_node_count": count,
                    "document_id": artifact.payload["source_document"]["document_id"],
                },
            ),
        )

    def validate(self, artifact: StageArtifact, services: Any) -> tuple[bool, str]:
        if _module_request(services):
            return (
                artifact.kind == "python_ast_bundle"
                and artifact.schema_version == "0.4"
                and len(services.context.frontend_trees) == len(_inputs(services)),
                "invalid parser bundle artifact",
            )
        return (
            artifact.kind == "python_ast" and services.context.frontend_tree is not None,
            "invalid parser artifact",
        )


class NormalizeStage:
    stage_id = "frontend.normalize"
    input_schema = "python-ast-bundle/0.4"
    input_schemas = ("python-ast/0.3", "python-ast-bundle/0.4")
    output_schema = "python-ir-bundle/0.4"

    def run(self, artifact: StageArtifact, services: Any) -> StageOutcome:
        if services.context.cancellation.is_canceled:
            return _canceled(self.stage_id)
        if not _module_request(services):
            return self._legacy_run(artifact, services)

        documents = services.context.frontend_documents
        trees = services.context.frontend_trees
        sources = _inputs(services)
        if len(documents) != len(trees) or len(trees) != len(sources):
            return _internal(self.stage_id, "Parser bundle scratch state is incomplete")
        normalized: list[PythonIRBundleDocument] = []
        normalizer = PythonNormalizer()
        try:
            for ordinal, (source, document, tree) in enumerate(zip(sources, documents, trees)):
                if services.context.cancellation.is_canceled:
                    return _canceled(self.stage_id)
                assert isinstance(document, SourceDocument)
                assert isinstance(tree, ast.Module)
                module = normalizer.normalize(tree, document)
                valid, message = validate_python_ir(module)
                if not valid:
                    return _internal(self.stage_id, message, code="PYC9003")
                normalized.append(
                    PythonIRBundleDocument(
                        module_id=source.module_id or "",
                        logical_name=source.logical_name,
                        bundle_ordinal=ordinal,
                        is_primary=ordinal == 0,
                        module=module,
                    )
                )
        except ValueError as exc:
            return _internal(self.stage_id, f"Invalid parser source span: {exc}", code="PYC9004")

        bundle = PythonIRBundle(
            "python-ir-bundle/0.4",
            normalized[0].module_id,
            tuple(normalized),
        )
        valid, message = validate_python_ir_bundle(bundle)
        if not valid:
            return _internal(self.stage_id, message, code="PYC9003")
        order = tuple(artifact.payload["stage_order"]) + (self.stage_id,)
        payload = {
            "stage_order": order,
            "source_bundle": artifact.payload["source_bundle"],
            "python_ir_bundle": bundle.to_dict(),
            "aggregate_ast_nodes": artifact.payload["aggregate_ast_nodes"],
        }
        return StageOutcome(
            StageTerminal.COMPLETED,
            _artifact("python_ir_bundle", "0.4", artifact, payload),
        )

    def _legacy_run(self, artifact: StageArtifact, services: Any) -> StageOutcome:
        source = services.context.canonical.request.source_bundle.primary
        document = SourceDocument.create(source.logical_name, source.text)
        try:
            module = PythonNormalizer().normalize(services.context.frontend_tree, document)
        except ValueError as exc:
            return _internal(
                self.stage_id,
                f"Invalid parser source span: {exc}",
                code="PYC9004",
            )
        valid, message = validate_python_ir(module)
        if not valid:
            return _internal(self.stage_id, message, code="PYC9003")
        order = tuple(artifact.payload["stage_order"]) + (self.stage_id,)
        return StageOutcome(
            StageTerminal.COMPLETED,
            _artifact(
                "python_ir",
                "0.3",
                artifact,
                {"stage_order": order, "python_ir": module.to_dict()},
            ),
        )

    def validate(self, artifact: StageArtifact, services: Any) -> tuple[bool, str]:
        if _module_request(services):
            bundle = artifact.payload.get("python_ir_bundle", {})
            return (
                artifact.kind == "python_ir_bundle"
                and artifact.schema_version == "0.4"
                and bundle.get("schema_version") == "python-ir-bundle/0.4",
                "invalid normalized Python IR bundle artifact",
            )
        return (
            artifact.kind == "python_ir"
            and artifact.payload.get("python_ir", {}).get("schema_version") == "python-ir/0.3",
            "invalid normalized Python IR artifact",
        )


def _ast_depth(root: ast.AST) -> int:
    maximum = 0
    stack = [(root, 1)]
    while stack:
        node, depth = stack.pop()
        maximum = max(maximum, depth)
        stack.extend((child, depth + 1) for child in ast.iter_child_nodes(node))
    return maximum


def _canceled(stage_id: str) -> StageOutcome:
    return StageOutcome(
        StageTerminal.CANCELED,
        diagnostics=(Diagnostic("PYC1901", Severity.ERROR, stage_id, "Conversion canceled"),),
    )


def _rejected(
    stage_id: str,
    code: str,
    message: str,
    *,
    source_span: dict[str, object] | None = None,
    source_module_id: str | None = None,
    source_logical_name: str | None = None,
) -> StageOutcome:
    return StageOutcome(
        StageTerminal.REJECTED,
        diagnostics=(
            Diagnostic(
                code,
                Severity.ERROR,
                stage_id,
                message,
                source_span=source_span,
                source_module_id=source_module_id,
                source_logical_name=source_logical_name,
            ),
        ),
    )


def _internal(stage_id: str, message: str, *, code: str = "PYC9004") -> StageOutcome:
    return StageOutcome(
        StageTerminal.INTERNAL_FAILURE,
        diagnostics=(Diagnostic(code, Severity.INTERNAL_ERROR, stage_id, message),),
    )


def _point_span(document: SourceDocument, line: int, column: int) -> dict[str, object] | None:
    try:
        return document.span(line, column, line, column).to_dict()
    except ValueError:
        return None


def _tokenization_error_span(document: SourceDocument, exc: BaseException) -> dict[str, object] | None:
    if (
        isinstance(exc, tokenize.TokenError)
        and len(exc.args) > 1
        and isinstance(exc.args[1], tuple)
        and len(exc.args[1]) == 2
    ):
        line, column = exc.args[1]
        if isinstance(line, int) and isinstance(column, int):
            return _point_span(document, line, column)
    line = getattr(exc, "lineno", None)
    offset = getattr(exc, "offset", None)
    if isinstance(line, int) and isinstance(offset, int):
        return _point_span(document, line, max(offset - 1, 0))
    return None


def _syntax_error_span(document: SourceDocument, exc: SyntaxError) -> dict[str, object] | None:
    start_line = exc.lineno or 1
    start_column = max((exc.offset or 1) - 1, 0)
    end_line = exc.end_lineno or start_line
    end_offset = exc.end_offset if isinstance(exc.end_offset, int) and exc.end_offset > 0 else exc.offset
    end_column = max((end_offset or 1) - 1, 0)
    try:
        return document.span(start_line, start_column, end_line, end_column).to_dict()
    except ValueError:
        return _point_span(document, start_line, start_column)
