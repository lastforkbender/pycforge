"""Deterministic release checks for the GUI-only PyCForge 0.12.2 release.

The validator deliberately has no current-tree fingerprint.  It authenticates
the sealed Phase 12 converter subtree and its published rollback identities,
then validates the new optional workspace surface as data and Python source.
It never starts a Qt event loop or compiles, links, loads, or executes generated
C.
"""

from __future__ import annotations

import argparse
import ast
import hashlib
import importlib
import json
import re
import subprocess
import sys
import tarfile
import tomllib
import xml.etree.ElementTree as ET
from pathlib import Path, PurePosixPath
from typing import Iterable, Mapping


ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from pycforge import (  # noqa: E402
    ConversionRequest,
    PythonToCConverter,
    ResultStatus,
    SourceBundle,
    SourceDocumentInput,
    __version__,
)
from pycforge.converter.contracts.configuration import (  # noqa: E402
    DEFAULT_CONTAINER_POLICY,
    DEFAULT_HELPER_POLICY,
    DEFAULT_MODULE_POLICY,
    DEFAULT_RENDERER,
    DEFAULT_RULE_SET,
    DEFAULT_SEMANTIC_POLICY,
    DEFAULT_TARGET_CONTRACT,
    MAX_CONTAINER_ELEMENTS,
    MAX_IMPORT_ITEMS,
    MAX_SOURCE_DOCUMENTS,
)
from pycforge.converter.contracts.versions import (  # noqa: E402
    C_IR_SCHEMA,
    CONTAINER_FACT_SCHEMA,
    CONVERSION_PLAN_SCHEMA,
    CONVERSION_SUMMARY_SCHEMA,
    DECISION_TRACE_SCHEMA,
    GENERATED_C_SCHEMA,
    MODULE_FACT_SCHEMA,
    PYTHON_IR_BUNDLE_SCHEMA,
    RESULT_SCHEMA_VERSION,
    SOURCE_BUNDLE_SCHEMA,
)
from pycforge.converter.support_templates import default_helper_registry  # noqa: E402


RELEASE_VERSION = "0.12.2"
WORKSPACE_CONTRACT = "pycforge-workspace/0.1"
PREDECESSOR_ARCHIVE_NAME = "pycforge_phase_12_1_v0_12_1.tar.gz"
PREDECESSOR_ARCHIVE_SHA256 = "5fd2231024a57c9ca736991e2ca90f645357c1d4cca69dfcf3bd53d1860d507e"
PREDECESSOR_TREE_SHA256 = "aed47ffbf4e17aebccfe571d506856dc9cf497308e1769f7db7597089a873efb"
PHASE12_TREE_SHA256 = "f6530b4e081799f5db3bfe365d82ece2abdcb82f9b986ffe98f3077ab2fe0de6"
PHASE12_CONVERTER_TREE_SHA256 = "4d7676a46105652efd13efb699d00e7a39a4b1bfd7ae7daad32c22702fd41b51"
HELPER_REGISTRY_SHA256 = "fcb719f07984f3b79e17262e90f93823a9a0139a60529f8486ab09f6c3663d98"
SCALAR_GENERATED_C_SHA256 = "1f63ad089b6ce5765df1a26af2811451ce86b40766458e248fec290a0c80304b"
MODULE_GENERATED_C_SHA256 = "f502f44b5a0312b35a3475bd38f2916be8976b61bbb89116b5a9cbe9ebc2250d"
WHEEL_SHA256 = "74906f50cc97f071e43b81caf1da7a200737394338df5f82db6bb941ef5fba11"
EXPECTED_EVIDENCE_FILES = {
    "qt_widget_smoke_scale_1.json": (
        1843,
        "8b5d575b8806f33fbe3803cc876c72f640b9ce7d2dc1bfef70b0e21e159a9021",
    ),
    "qt_widget_smoke_scale_1.png": (
        158920,
        "89aed586ec4c5daf98f204ea439bc5789891551930f4dd37682295ec96a04718",
    ),
    "qt_widget_smoke_scale_2.json": (
        1843,
        "2612b96db4f8527d22e150a1c8b13c94b7f4267f84132afedd556564a7036eb2",
    ),
    "qt_widget_smoke_scale_2.png": (
        365774,
        "b86b8957470130f10dda9ce9a70379e1a655a0f523395561c13b71b3ba248170",
    ),
}

EXPECTED_CONTRACT_IDENTITIES = {
    "source_bundle": "source-bundle/0.2",
    "python_ir": "python-ir/0.4",
    "container_facts": "fact-table/0.11",
    "module_facts": "fact-table/0.12",
    "conversion_plan": "conversion-plan/0.12",
    "c_ir": "c-ir/0.12",
    "generated_c": "generated-c/0.12",
    "conversion_summary": "pycforge.conversion-summary/0.12",
    "decision_trace": "pycforge.decision-trace/0.12",
    "result": "0.5",
    "rule_set": "phase12-explicit-module-bundles-v0.12",
    "renderer": "c-renderer-v0.12",
    "module_policy": "phase12-explicit-sourcebundle-modules-v0.12",
    "helper_policy": "phase10-support-templates-v0.10",
    "container_policy": "phase11-fixed-local-containers-v0.11",
    "target_contract": "c11-portable-fixed-v1",
    "semantic_policy": "strict-source-v1",
    "container_limit": 64,
    "document_limit": 64,
    "import_item_limit": 4096,
}

REQUIRED_GUI_MODULES = {
    "pycforge/ide/controller.py": (
        "class WorkspaceController",
        "def convert_async",
        "def _fail_conversion",
        "self._sequence += 1",
    ),
    "pycforge/ide/model.py": ("class WorkspaceDocument", "class WorkspaceSnapshot"),
    "pycforge/ide/editor.py": (
        "class CodeEditor",
        "paint_quantum_rail",
        "activate_rail_marker",
        "class PyCForgeSyntaxHighlighter",
    ),
    "pycforge/ide/find_replace.py": (
        "class FindReplaceBar",
        "def replace_all",
        "def find_literal_ranges",
        "qt_position_length",
    ),
    "pycforge/ide/panels.py": (
        "class DocumentNavigator",
        "move_up_requested",
        "move_down_requested",
        "class DiagnosticsView",
        "class InspectorTree",
    ),
    "pycforge/ide/theme.py": ("PYCFORGE_QSS", "PYCFORGE_ICON_FILES", "def apply_pycforge_theme"),
    "pycforge/ide/qt.py": (
        "SETTINGS_SCHEMA_VERSION = 1",
        "class MainWindow",
        "QSettings",
        "def _commit_pending_identity",
        "def _move_document",
        "def closeEvent",
        "def run",
    ),
}

REQUIRED_SMOKE_MODULES = {
    "tools/smoke_pycforge_workspace_0_12_2.py": (
        "QApplication",
        "MainWindow",
        "--output",
        "--screenshot",
        '"responsive_splitter_layout"',
        '"toolbar_save_c_visible"',
        '"linked_destination_discoverable"',
    ),
}

EXPECTED_ICON_FILES = frozenset(
    {
        "add-document.svg",
        "cancel.svg",
        "close.svg",
        "convert.svg",
        "export.svg",
        "find.svg",
        "link-c.svg",
        "move-down.svg",
        "move-up.svg",
        "next.svg",
        "open.svg",
        "previous.svg",
        "remove-document.svg",
        "replace.svg",
        "save.svg",
        "settings.svg",
        "show-c.svg",
    }
)

EXPECTED_ACTION_LABELS = frozenset(
    {
        "Open Python…",
        "New Module",
        "Remove Module",
        "Save Python",
        "Save Python As…",
        "Convert",
        "Cancel",
        "Find",
        "Replace",
        "Link C…",
        "Save C",
        "Show C",
        "Show Details",
        "Show Bundle",
    }
)

BITMAP_SUFFIXES = frozenset(
    {".avif", ".bmp", ".gif", ".ico", ".jpeg", ".jpg", ".png", ".tif", ".tiff", ".webp"}
)
FORBIDDEN_EXECUTION_IMPORTS = frozenset(
    {"cffi", "ctypes", "multiprocessing", "pty", "runpy", "socket", "subprocess"}
)
FORBIDDEN_QT_EXECUTION_TYPES = frozenset(
    {"QProcess", "QPluginLoader", "QLibrary", "QSharedMemory"}
)
FORBIDDEN_ACTION_WORDS = frozenset(
    {"build", "compile", "debug", "execute", "load", "run", "terminal", "test"}
)


def sha256_bytes(value: bytes) -> str:
    return hashlib.sha256(value).hexdigest()


def canonical_subtree_hash(root: Path) -> str:
    """Hash files under *root* with paths relative to that subtree."""

    digest = hashlib.sha256()
    files = sorted(
        (
            path
            for path in root.rglob("*")
            if path.is_file()
            and "__pycache__" not in path.parts
            and not path.name.endswith(".pyc")
        ),
        key=lambda path: path.relative_to(root).as_posix(),
    )
    for path in files:
        relative = path.relative_to(root).as_posix().encode("utf-8")
        data = path.read_bytes()
        digest.update(len(relative).to_bytes(8, "big"))
        digest.update(relative)
        digest.update(len(data).to_bytes(8, "big"))
        digest.update(data)
    return digest.hexdigest()


def canonical_archive_tree_hash(archive: Path) -> str:
    """Hash a single-root source archive using release-tree relative paths."""

    files: dict[str, bytes] = {}
    root_name: str | None = None
    with tarfile.open(archive, mode="r:gz") as package:
        for member in package.getmembers():
            path = PurePosixPath(member.name)
            if path.is_absolute() or ".." in path.parts or not path.parts:
                raise ValueError(f"unsafe predecessor archive member: {member.name!r}")
            if root_name is None:
                root_name = path.parts[0]
            elif path.parts[0] != root_name:
                raise ValueError("predecessor archive has more than one release root")
            if member.isdir():
                continue
            if not member.isfile():
                raise ValueError(
                    f"predecessor archive contains a non-regular member: {member.name!r}"
                )
            if len(path.parts) == 1:
                raise ValueError("predecessor archive stores a file at its release root")
            relative = PurePosixPath(*path.parts[1:]).as_posix()
            if "__pycache__" in path.parts or relative.endswith(".pyc"):
                continue
            stream = package.extractfile(member)
            if stream is None:
                raise ValueError(f"cannot read predecessor member: {member.name!r}")
            if relative in files:
                raise ValueError(f"duplicate predecessor member: {relative!r}")
            files[relative] = stream.read()
    if root_name is None or not files:
        raise ValueError("predecessor archive is empty")
    digest = hashlib.sha256()
    for relative in sorted(files):
        path_bytes = relative.encode("utf-8")
        data = files[relative]
        digest.update(len(path_bytes).to_bytes(8, "big"))
        digest.update(path_bytes)
        digest.update(len(data).to_bytes(8, "big"))
        digest.update(data)
    return digest.hexdigest()


def current_contract_identities() -> dict[str, str | int]:
    return {
        "source_bundle": SOURCE_BUNDLE_SCHEMA,
        "python_ir": PYTHON_IR_BUNDLE_SCHEMA,
        "container_facts": CONTAINER_FACT_SCHEMA,
        "module_facts": MODULE_FACT_SCHEMA,
        "conversion_plan": CONVERSION_PLAN_SCHEMA,
        "c_ir": C_IR_SCHEMA,
        "generated_c": GENERATED_C_SCHEMA,
        "conversion_summary": CONVERSION_SUMMARY_SCHEMA,
        "decision_trace": DECISION_TRACE_SCHEMA,
        "result": RESULT_SCHEMA_VERSION,
        "rule_set": DEFAULT_RULE_SET,
        "renderer": DEFAULT_RENDERER,
        "module_policy": DEFAULT_MODULE_POLICY,
        "helper_policy": DEFAULT_HELPER_POLICY,
        "container_policy": DEFAULT_CONTAINER_POLICY,
        "target_contract": DEFAULT_TARGET_CONTRACT,
        "semantic_policy": DEFAULT_SEMANTIC_POLICY,
        "container_limit": MAX_CONTAINER_ELEMENTS,
        "document_limit": MAX_SOURCE_DOCUMENTS,
        "import_item_limit": MAX_IMPORT_ITEMS,
    }


def check_exact_mapping(
    actual: Mapping[str, object],
    expected: Mapping[str, object],
    *,
    label: str,
) -> tuple[str, ...]:
    errors: list[str] = []
    for key in sorted(set(actual) | set(expected)):
        if key not in expected:
            errors.append(f"{label}: unexpected key {key!r}")
        elif key not in actual:
            errors.append(f"{label}: missing key {key!r}")
        elif actual[key] != expected[key]:
            errors.append(
                f"{label}: {key!r} is {actual[key]!r}, expected {expected[key]!r}"
            )
    return tuple(errors)


def extract_action_labels(source: str) -> tuple[str, ...]:
    """Extract literal labels supplied to the workspace's action factory."""

    tree = ast.parse(source)
    labels: list[str] = []
    for node in ast.walk(tree):
        if not isinstance(node, ast.Call) or not node.args:
            continue
        function = node.func
        name = function.attr if isinstance(function, ast.Attribute) else function.id if isinstance(function, ast.Name) else ""
        if name != "_action":
            continue
        label = node.args[0]
        if isinstance(label, ast.Constant) and isinstance(label.value, str):
            labels.append(label.value)
    return tuple(labels)


def check_action_surface(source: str) -> tuple[str, ...]:
    try:
        labels = extract_action_labels(source)
    except SyntaxError as exc:
        return (f"workspace action source is invalid Python: {exc.msg}",)
    errors = list(
        check_exact_mapping(
            {label: True for label in labels},
            {label: True for label in EXPECTED_ACTION_LABELS},
            label="workspace actions",
        )
    )
    if len(labels) != len(set(labels)):
        errors.append("workspace actions contain duplicate labels")
    for label in labels:
        words = set(re.findall(r"[a-z]+", label.casefold()))
        forbidden = sorted(words & FORBIDDEN_ACTION_WORDS)
        if forbidden:
            errors.append(
                f"workspace action {label!r} exposes forbidden execution control {forbidden[0]!r}"
            )
    return tuple(errors)


def check_execution_boundary(sources: Mapping[str, str]) -> tuple[str, ...]:
    """Reject process/native-loading capabilities in workspace modules."""

    errors: list[str] = []
    for name in sorted(sources):
        try:
            tree = ast.parse(sources[name], filename=name)
        except SyntaxError as exc:
            errors.append(f"{name}: invalid Python: {exc.msg}")
            continue
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                imported = {item.name.partition(".")[0] for item in node.names}
                for forbidden in sorted(imported & FORBIDDEN_EXECUTION_IMPORTS):
                    errors.append(f"{name}: forbidden execution import {forbidden!r}")
            elif isinstance(node, ast.ImportFrom):
                module = (node.module or "").partition(".")[0]
                if module in FORBIDDEN_EXECUTION_IMPORTS:
                    errors.append(f"{name}: forbidden execution import {module!r}")
                for item in node.names:
                    if item.name in FORBIDDEN_QT_EXECUTION_TYPES:
                        errors.append(f"{name}: forbidden Qt execution type {item.name!r}")
            elif isinstance(node, ast.Call) and isinstance(node.func, ast.Name):
                if node.func.id in {"__import__", "compile", "eval", "exec"}:
                    errors.append(f"{name}: forbidden dynamic execution call {node.func.id!r}")
    return tuple(errors)


def _local_name(value: str) -> str:
    return value.rsplit("}", 1)[-1]


def check_svg_asset(name: str, data: bytes) -> tuple[str, ...]:
    errors: list[str] = []
    try:
        text = data.decode("utf-8")
    except UnicodeDecodeError:
        return (f"{name}: SVG is not UTF-8 text",)
    try:
        root = ET.fromstring(text)
    except ET.ParseError as exc:
        return (f"{name}: invalid SVG XML: {exc}",)
    if _local_name(root.tag) != "svg":
        errors.append(f"{name}: root element is not svg")
    if root.attrib.get("viewBox") != "0 0 24 24":
        errors.append(f"{name}: viewBox must be '0 0 24 24'")
    forbidden_elements = {"foreignObject", "image", "script", "style"}
    for element in root.iter():
        local = _local_name(element.tag)
        if local in forbidden_elements:
            errors.append(f"{name}: forbidden SVG element {local!r}")
        for attribute, value in element.attrib.items():
            if _local_name(attribute) in {"href", "src"}:
                errors.append(f"{name}: external or embedded asset reference is forbidden")
            if re.search(r"(?i)(?:data:|https?://|file:|image/(?:png|jpeg|gif|webp|bmp))", value):
                errors.append(f"{name}: URI or raster payload is forbidden")
    if re.search(r"(?i)image/(?:png|jpeg|gif|webp|bmp)", text):
        errors.append(f"{name}: embedded raster MIME type is forbidden")
    return tuple(dict.fromkeys(errors))


def check_resource_inventory(resources: Mapping[str, bytes]) -> tuple[str, ...]:
    errors: list[str] = []
    raster = sorted(
        name for name in resources if Path(name).suffix.casefold() in BITMAP_SUFFIXES
    )
    errors.extend(f"resource {name!r} is a forbidden raster asset" for name in raster)
    icons = {
        Path(name).name
        for name in resources
        if Path(name).suffix.casefold() == ".svg"
    }
    errors.extend(
        check_exact_mapping(
            {name: True for name in icons},
            {name: True for name in EXPECTED_ICON_FILES},
            label="PyCForge SVG inventory",
        )
    )
    for name in sorted(resources):
        if Path(name).suffix.casefold() == ".svg":
            errors.extend(check_svg_asset(name, resources[name]))
    return tuple(errors)


def check_required_terms(
    texts: Mapping[str, str],
    requirements: Mapping[str, Iterable[str]],
) -> tuple[str, ...]:
    errors: list[str] = []
    for name in sorted(requirements):
        if name not in texts:
            errors.append(f"missing required file {name}")
            continue
        for term in requirements[name]:
            if term not in texts[name]:
                errors.append(f"{name}: missing required term {term!r}")
    return tuple(errors)


def check_version_metadata(
    *,
    imported_version: str,
    pyproject_version: str,
    package_metadata: str,
    readme: str,
    current_state: str,
    workspace_spec: str,
) -> tuple[str, ...]:
    errors: list[str] = []
    if imported_version != RELEASE_VERSION:
        errors.append(f"imported version is {imported_version!r}")
    if pyproject_version != RELEASE_VERSION:
        errors.append(f"pyproject version is {pyproject_version!r}")
    if f"Version: {RELEASE_VERSION}" not in package_metadata:
        errors.append("package metadata version is not 0.12.2")
    if not readme.startswith("# PyCForge 0.12.2 — Phase 12 PyCForge Workspace"):
        errors.append("README release heading is not PyCForge 0.12.2")
    if "Current release: `0.12.2` / Phase 12 PyCForge workspace" not in current_state:
        errors.append("CURRENT_STATE does not identify PyCForge 0.12.2")
    if f"`{WORKSPACE_CONTRACT}`" not in current_state:
        errors.append("CURRENT_STATE omits the workspace contract identity")
    if f"# PyCForge Workspace — `{WORKSPACE_CONTRACT}`" not in workspace_spec:
        errors.append("workspace specification identity mismatch")
    if "Status: active in PyCForge 0.12.2" not in workspace_spec:
        errors.append("workspace specification is not active for 0.12.2")
    return tuple(errors)


def _module_request() -> ConversionRequest:
    return ConversionRequest(
        SourceBundle(
            SourceDocumentInput(
                "app.py",
                "from lib.math import increment as inc\n\ndef run(value: int) -> int:\n    return inc(value)\n",
                "app",
            ),
            (
                SourceDocumentInput(
                    "lib/math.py",
                    "def increment(value: int) -> int:\n    return value + 1\n",
                    "lib.math",
                ),
            ),
        )
    )


def _converter_smoke_errors() -> tuple[str, ...]:
    converter = PythonToCConverter()
    scalar = converter.convert(
        ConversionRequest.from_source(
            "def f(value: int) -> int:\n    return value + 1\n"
        )
    )
    modules = converter.convert(_module_request())
    errors: list[str] = []
    for name, result, expected_hash in (
        ("singleton", scalar, SCALAR_GENERATED_C_SHA256),
        ("module bundle", modules, MODULE_GENERATED_C_SHA256),
    ):
        if result.status is not ResultStatus.CONVERTED or result.generated_c is None:
            errors.append(f"frozen {name} conversion did not convert")
        elif sha256_bytes(result.generated_c.encode("utf-8")) != expected_hash:
            errors.append(f"frozen {name} generated-C bytes changed")
    return tuple(errors)


def _read_texts(root: Path, names: Iterable[str]) -> tuple[dict[str, str], list[str]]:
    values: dict[str, str] = {}
    errors: list[str] = []
    for name in sorted(set(names)):
        path = root / name
        try:
            values[name] = path.read_text(encoding="utf-8")
        except (OSError, UnicodeError) as exc:
            errors.append(f"cannot read required file {name}: {exc}")
    return values, errors


def validate_tree(
    root: Path = ROOT,
    *,
    predecessor_archive: Path | None = None,
    converter_smoke: bool = True,
) -> tuple[str, ...]:
    root = Path(root)
    required_text_files = set(REQUIRED_GUI_MODULES) | set(REQUIRED_SMOKE_MODULES) | {
        "CURRENT_STATE.md",
        "README.md",
        "pycforge.egg-info/PKG-INFO",
        "evidence/pycforge_workspace_0_12_2/manual_review.md",
        "specifications/pycforge_workspace_legacy_0_1.md",
    }
    texts, read_errors = _read_texts(root, required_text_files)
    errors: list[str] = list(read_errors)

    try:
        project = tomllib.loads((root / "pyproject.toml").read_text(encoding="utf-8"))
        project_version = project["project"]["version"]
    except (OSError, UnicodeError, tomllib.TOMLDecodeError, KeyError, TypeError) as exc:
        errors.append(f"cannot read pyproject release identity: {exc}")
        project = {}
        project_version = ""

    errors.extend(
        check_version_metadata(
            imported_version=__version__,
            pyproject_version=str(project_version),
            package_metadata=texts.get("pycforge.egg-info/PKG-INFO", ""),
            readme=texts.get("README.md", ""),
            current_state=texts.get("CURRENT_STATE.md", ""),
            workspace_spec=texts.get("specifications/pycforge_workspace_legacy_0_1.md", ""),
        )
    )
    errors.extend(
        check_exact_mapping(
            current_contract_identities(),
            EXPECTED_CONTRACT_IDENTITIES,
            label="frozen converter contracts",
        )
    )

    converter_root = root / "pycforge/converter"
    if not converter_root.is_dir():
        errors.append("frozen converter subtree is missing")
    elif canonical_subtree_hash(converter_root) != PHASE12_CONVERTER_TREE_SHA256:
        errors.append("sealed Phase 12 converter subtree bytes changed")

    try:
        manifest = json.loads(
            (root / "transition/phase_12/manifest.json").read_text(encoding="utf-8")
        )
        baseline = json.loads(
            (root / "transition/phase_12/baseline_fingerprint.json").read_text(
                encoding="utf-8"
            )
        )
    except (OSError, UnicodeError, json.JSONDecodeError) as exc:
        errors.append(f"cannot authenticate sealed Phase 12 records: {exc}")
    else:
        if manifest.get("phase") != 12 or manifest.get("version") != "0.12.0" or manifest.get("status") != "promoted":
            errors.append("sealed Phase 12 manifest identity changed")
        if baseline.get("value") != PHASE12_TREE_SHA256 or baseline.get("status") != "promoted":
            errors.append("sealed Phase 12 tree identity changed")
        manifest_contracts = dict(manifest.get("schemas", {}))
        expected_manifest_contracts = {
            "source_bundle": EXPECTED_CONTRACT_IDENTITIES["source_bundle"],
            "python_ir": EXPECTED_CONTRACT_IDENTITIES["python_ir"],
            "fact_tables": EXPECTED_CONTRACT_IDENTITIES["module_facts"],
            "conversion_plan": EXPECTED_CONTRACT_IDENTITIES["conversion_plan"],
            "c_ir": EXPECTED_CONTRACT_IDENTITIES["c_ir"],
            "generated_c": EXPECTED_CONTRACT_IDENTITIES["generated_c"],
            "conversion_summary": EXPECTED_CONTRACT_IDENTITIES["conversion_summary"],
            "decision_trace": EXPECTED_CONTRACT_IDENTITIES["decision_trace"],
            "result_serialization": EXPECTED_CONTRACT_IDENTITIES["result"],
            "rule_set": EXPECTED_CONTRACT_IDENTITIES["rule_set"],
            "renderer": EXPECTED_CONTRACT_IDENTITIES["renderer"],
            "module_policy": EXPECTED_CONTRACT_IDENTITIES["module_policy"],
            "helper_policy": EXPECTED_CONTRACT_IDENTITIES["helper_policy"],
            "container_policy": EXPECTED_CONTRACT_IDENTITIES["container_policy"],
            "target_contract": EXPECTED_CONTRACT_IDENTITIES["target_contract"],
        }
        errors.extend(
            check_exact_mapping(
                manifest_contracts,
                expected_manifest_contracts,
                label="sealed Phase 12 manifest contracts",
            )
        )

    try:
        workspace_manifest = json.loads(
            (root / "transition/workspace_hardening_0_12_2/manifest.json").read_text(
                encoding="utf-8"
            )
        )
    except (OSError, UnicodeError, json.JSONDecodeError) as exc:
        errors.append(f"cannot read PyCForge transition manifest: {exc}")
    else:
        if (
            workspace_manifest.get("release") != "workspace-hardening"
            or workspace_manifest.get("version") != RELEASE_VERSION
            or workspace_manifest.get("phase") != 12
            or workspace_manifest.get("workspace_contract") != WORKSPACE_CONTRACT
            or workspace_manifest.get("settings_schema_version") != 1
            or workspace_manifest.get("status") != "promoted"
        ):
            errors.append("PyCForge transition manifest identity is invalid")
        if (
            workspace_manifest.get("predecessor_archive_sha256")
            != PREDECESSOR_ARCHIVE_SHA256
            or workspace_manifest.get("predecessor_tree_sha256")
            != PREDECESSOR_TREE_SHA256
            or workspace_manifest.get("predecessor_converter_tree_sha256")
            != PHASE12_CONVERTER_TREE_SHA256
        ):
            errors.append("PyCForge transition predecessor identity changed")
        if any(
            key in workspace_manifest
            for key in ("current_tree_sha256", "release_tree_sha256", "tree_sha256")
        ):
            errors.append("PyCForge transition manifest embeds a mutable current-tree hash")

    report_path = root / "evidence/pycforge_workspace_0_12_2/release_report.json"
    try:
        release_report = json.loads(report_path.read_text(encoding="utf-8"))
    except (OSError, UnicodeError, json.JSONDecodeError) as exc:
        errors.append(f"cannot read PyCForge release report: {exc}")
    else:
        if (
            release_report.get("release_version") != RELEASE_VERSION
            or release_report.get("status") != "promoted"
            or release_report.get("phase") != 12
            or release_report.get("phase_13_opened") is not False
            or release_report.get("workspace_contract") != WORKSPACE_CONTRACT
            or release_report.get("settings_schema_version") != 1
        ):
            errors.append("PyCForge release report identity is invalid")
        widget_smoke = release_report.get("widget_smoke", {})
        if not isinstance(widget_smoke, dict) or not all(
            widget_smoke.get(key) is True
            for key in (
                "scale_1_passed",
                "scale_2_passed",
                "repeated_scale_1_json_byte_identical",
            )
        ):
            errors.append("PyCForge release report omits passing widget-smoke evidence")
        artifacts = release_report.get("artifacts", {})
        wheel = artifacts.get("wheel", {}) if isinstance(artifacts, dict) else {}
        source_archive = (
            artifacts.get("source_archive", {})
            if isinstance(artifacts, dict)
            else {}
        )
        if (
            wheel.get("sha256") != WHEEL_SHA256
            or wheel.get("fixed_epoch_builds_byte_identical") is not True
            or wheel.get("isolated_install_passed") is not True
            or wheel.get("installed_actual_widget_offscreen_passed") is not True
            or wheel.get("installed_source_bundle_conversion_passed") is not True
            or wheel.get("installed_linked_c_atomic_save_passed") is not True
            or source_archive.get("deterministic_builds_byte_identical") is not True
        ):
            errors.append("PyCForge release report artifact gates are incomplete")
        generated_operations = release_report.get("generated_c_operations", {})
        if generated_operations != {
            "compiled": False,
            "linked": False,
            "loaded": False,
            "executed": False,
        }:
            errors.append("PyCForge release report generated-C safety claim changed")

    evidence_root = root / "evidence/pycforge_workspace_0_12_2"
    for name, (expected_size, expected_hash) in sorted(
        EXPECTED_EVIDENCE_FILES.items()
    ):
        path = evidence_root / name
        try:
            data = path.read_bytes()
        except OSError as exc:
            errors.append(f"cannot read PyCForge evidence {name}: {exc}")
            continue
        if len(data) != expected_size or sha256_bytes(data) != expected_hash:
            errors.append(f"PyCForge evidence custody mismatch: {name}")

    if default_helper_registry().fingerprint != HELPER_REGISTRY_SHA256:
        errors.append("Phase 10 StableInternal helper registry identity changed")
    if converter_smoke:
        errors.extend(_converter_smoke_errors())

    errors.extend(check_required_terms(texts, REQUIRED_GUI_MODULES))
    errors.extend(check_required_terms(texts, REQUIRED_SMOKE_MODULES))
    workspace_requirements = {
        "specifications/pycforge_workspace_legacy_0_1.md": (
            "Frozen converter boundary",
            "Explicit bundle workspace",
            "quantum visibility rail",
            "Find and replace",
            "Diagnostics and inspection",
            "Linked generated-C save",
            "PyCForge visual and accessibility contract",
            "Presentation persistence",
            "does not compile, link, load, or execute",
        ),
        "evidence/pycforge_workspace_0_12_2/manual_review.md": (
            "real `QApplication`",
            "`MainWindow`",
            "DPR 1 and DPR 2",
            "Generated C was not compiled",
            "linked, loaded, or executed",
            "does not claim a physical-display",
        ),
    }
    errors.extend(check_required_terms(texts, workspace_requirements))
    qt_source = texts.get("pycforge/ide/qt.py", "")
    errors.extend(check_action_surface(qt_source))
    gui_sources = {
        name: texts[name]
        for name in REQUIRED_GUI_MODULES
        if name in texts
    }
    errors.extend(check_execution_boundary(gui_sources))

    resource_root = root / "pycforge/ide/resources"
    resources = {
        path.relative_to(resource_root).as_posix(): path.read_bytes()
        for path in sorted(resource_root.rglob("*"))
        if path.is_file()
    } if resource_root.is_dir() else {}
    if not resources:
        errors.append("PyCForge resource inventory is empty")
    else:
        errors.extend(check_resource_inventory(resources))

    # Import probes must never instantiate QApplication or any widget.
    required_symbols = {
        "pycforge.ide.editor": ("CodeEditor", "EditorMarker", "normalize_markers"),
        "pycforge.ide.find_replace": ("FindReplaceBar", "find_literal_ranges"),
        "pycforge.ide.panels": ("DocumentNavigator", "DiagnosticsView", "InspectorTree"),
        "pycforge.ide.theme": ("PYCFORGE_QSS", "PYCFORGE_ICON_FILES", "apply_pycforge_theme"),
    }
    for module_name in sorted(required_symbols):
        try:
            module = importlib.import_module(module_name)
        except Exception as exc:  # pragma: no cover - diagnostic path
            errors.append(f"headless-safe import failed for {module_name}: {exc}")
            continue
        missing = [name for name in required_symbols[module_name] if not hasattr(module, name)]
        if missing:
            errors.append(f"{module_name} omits public symbols: {', '.join(missing)}")

    project_table = project.get("project", {}) if isinstance(project, dict) else {}
    scripts = project_table.get("scripts", {}) if isinstance(project_table, dict) else {}
    optional = project_table.get("optional-dependencies", {}) if isinstance(project_table, dict) else {}
    package_data = project.get("tool", {}).get("setuptools", {}).get("package-data", {}) if isinstance(project, dict) else {}
    if scripts.get("pycforge-workspace") != "pycforge.ide.qt:run":
        errors.append("workspace entry point is missing or changed")
    if optional.get("workspace") != ["PyQt5>=5.15,<6"]:
        errors.append("optional PyQt5 workspace dependency contract changed")
    if "resources/icons/*.svg" not in package_data.get("pycforge.ide", []):
        errors.append("SVG workspace assets are not declared as package data")

    if predecessor_archive is not None:
        archive = Path(predecessor_archive)
        if not archive.is_file():
            errors.append(f"requested predecessor archive is absent: {archive}")
        else:
            digest = sha256_bytes(archive.read_bytes())
            if digest != PREDECESSOR_ARCHIVE_SHA256:
                errors.append(
                    f"sealed 0.12.1 predecessor archive hash mismatch: {digest}"
                )
            else:
                try:
                    tree_digest = canonical_archive_tree_hash(archive)
                except (OSError, tarfile.TarError, ValueError) as exc:
                    errors.append(f"cannot authenticate predecessor release tree: {exc}")
                else:
                    if tree_digest != PREDECESSOR_TREE_SHA256:
                        errors.append(
                            "sealed 0.12.1 predecessor tree hash mismatch: "
                            + tree_digest
                        )
    return tuple(dict.fromkeys(errors))


def locate_predecessor_archive(root: Path = ROOT) -> Path | None:
    candidates = (
        root / PREDECESSOR_ARCHIVE_NAME,
        root.parent / PREDECESSOR_ARCHIVE_NAME,
        root.parents[1] / PREDECESSOR_ARCHIVE_NAME,
        root.parents[1] / "release" / PREDECESSOR_ARCHIVE_NAME,
    )
    return next((path for path in candidates if path.is_file()), None)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--predecessor-archive")
    parser.add_argument("--require-predecessor", action="store_true")
    parser.add_argument("--skip-converter-smoke", action="store_true")
    parser.add_argument("--run-tests", action="store_true")
    args = parser.parse_args(argv)

    archive = (
        Path(args.predecessor_archive).resolve()
        if args.predecessor_archive
        else locate_predecessor_archive(ROOT)
    )
    errors = list(
        validate_tree(
            ROOT,
            predecessor_archive=archive,
            converter_smoke=not args.skip_converter_smoke,
        )
    )
    if args.require_predecessor and archive is None:
        errors.append("sealed 0.12.1 predecessor archive is required but absent")

    if args.run_tests and not errors:
        completed = subprocess.run(
            [sys.executable, "-m", "unittest", "discover", "-s", "tests"],
            cwd=ROOT,
            text=True,
            capture_output=True,
        )
        if completed.returncode:
            transcript = (completed.stdout + "\n" + completed.stderr).strip()
            errors.append("workspace regression suite failed\n" + transcript)

    if errors:
        print("PyCForge 0.12.2 validation failed")
        for error in errors:
            print(f"- {error}")
        return 1

    print("PyCForge 0.12.2 validation passed")
    print(f"Workspace contract: {WORKSPACE_CONTRACT}")
    print(f"Frozen Phase 12 converter tree SHA-256: {PHASE12_CONVERTER_TREE_SHA256}")
    print(f"Sealed 0.12.1 archive verified: {archive is not None}")
    print("Workspace exposes no C compilation, linking, loading, or execution controls")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
