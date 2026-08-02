"""Validate the PyCForge Phase 15C IDE-workspace release gate.

The validator exercises import-safe action, menu, visual, custody, isolation,
and responsiveness contracts.  It does not invoke a C compiler, linker,
loader, foreign-function interface, generated program, or host toolchain.
Visible Windows and Linux certification remains a Phase 15D responsibility.
"""

from __future__ import annotations

import argparse
import ast
from hashlib import sha256
from io import BytesIO
import json
import math
import os
from pathlib import Path, PurePosixPath
import platform
import re
import sys
import tarfile
import tomllib
from typing import Callable, Mapping
import xml.etree.ElementTree as ET


ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from pycforge.ide.action_contract import (  # noqa: E402
    ACTION_SPECS,
    MAIN_MENU_SURFACES,
    SURFACE_SPECS,
    PlacementKind,
    SurfaceKind,
    validate_action_contract,
)
from pycforge.ide.icons import (  # noqa: E402
    PYCFORGE_ICON_FILES,
)
from pycforge.ide.theme import PYCFORGE_QSS  # noqa: E402
from pycforge.ide.visual_tokens import (  # noqa: E402
    PYCFORGE_COLORS,
    PYCFORGE_METRICS,
    color_tokens,
    contrast_ratio,
)
from tools._phase15a_runtime_validation import (  # noqa: E402
    audit_maximum_input_fixtures,
    scan_runtime_boundaries,
)
from tools._phase15c_release_contract import scan_release_tree  # noqa: E402
from tools.validate_phase15a import (  # noqa: E402
    CONVERTER_SUBTREE_DOMAIN,
    audit_direct_isolated_equivalence,
    audit_hundred_cycle_supervision,
    audit_safety_scope,
    canonical_converter_subtree_hash,
)


VALIDATION_SCHEMA = "pycforge.phase15c-validation-report/1"
EXPECTED_PACKAGE_VERSION = "0.15.2"
EXPECTED_CONVERTER_CONTRACT = "0.14.3"
EXPECTED_WORKSPACE_CONTRACT = "pycforge-workspace/0.5"
EXPECTED_WORKER_PROTOCOL = "pycforge.worker-protocol/0.1"
EXPECTED_ACTION_REGISTRY = "pycforge.action-registry/0.2"
EXPECTED_VISUAL_SYSTEM = "pycforge.visual-system/0.2"
EXPECTED_SETTINGS_SCHEMA = 1
EXPECTED_CONVERTER_SUBTREE_SHA256 = (
    "a45bc2c31b954f9856c8eab36e95f68b086d5fdd682d2cf47ba2186887743124"
)
EXPECTED_ACTION_COUNT = 48
EXPECTED_CONTEXT_COUNT = 11
EXPECTED_MAIN_MENU_COUNT = 5
EXPECTED_ICON_COUNT = 55
PERFORMANCE_EVIDENCE = PurePosixPath(
    "evidence/phase_15c/performance_evidence.json"
)
PERFORMANCE_EVIDENCE_SCHEMA = "pycforge.phase15c-performance-evidence/1"

PREDECESSOR_ARCHIVE_NAME = "pycforge_phase_15b_v0_15_1.tar.gz"
PREDECESSOR_ARCHIVE_ROOT = "pycforge_phase_15b_v0_15_1"
PREDECESSOR_ARCHIVE_SIZE = 1_544_352
PREDECESSOR_ARCHIVE_SHA256 = (
    "aefaebbacb12b458bcadd9aa25ac9f2678a374b51901bcc51aab3698049cd827"
)
PREDECESSOR_TREE_FINGERPRINT = (
    "d90225e2e75842dfd2ca581c08b844a3e640988e385cfc70a68dba8f27db9b36"
)


def _audit(
    name: str,
    errors: list[str],
    **evidence: object,
) -> dict[str, object]:
    return {"audit": name, "passed": not errors, "errors": errors, **evidence}


def _skipped(name: str) -> dict[str, object]:
    return _audit(
        name,
        [],
        status="skipped-by-mode",
        required_in_mode=False,
    )


def _safe_audit(
    name: str,
    function: Callable[..., dict[str, object]],
    *args: object,
    **kwargs: object,
) -> dict[str, object]:
    try:
        result = function(*args, **kwargs)
    except Exception as exc:
        return _audit(
            name,
            [
                "validator audit failed closed: "
                f"{type(exc).__name__}: {exc}"
            ],
            status="internal-error",
        )
    if (
        not isinstance(result, dict)
        or type(result.get("passed")) is not bool
    ):
        return _audit(
            name,
            ["validator audit returned a malformed result"],
            status="internal-error",
        )
    return result


def _literal_assignment(path: Path, name: str) -> object:
    tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
    for statement in tree.body:
        if not isinstance(statement, (ast.Assign, ast.AnnAssign)):
            continue
        targets = (
            statement.targets
            if isinstance(statement, ast.Assign)
            else (statement.target,)
        )
        if any(
            isinstance(target, ast.Name) and target.id == name
            for target in targets
        ):
            if statement.value is None:
                break
            return ast.literal_eval(statement.value)
    raise ValueError(f"{path}: literal assignment {name!r} is absent")


def audit_validator_root(root: Path = ROOT) -> dict[str, object]:
    requested = root.resolve()
    imported = ROOT.resolve()
    errors = (
        []
        if requested == imported
        else [
            "validation root differs from the imported candidate; "
            "run the validator from inside the candidate tree"
        ]
    )
    return _audit(
        "validator-root-custody",
        errors,
        requested_root=str(requested),
        imported_root=str(imported),
        imported_candidate_exercised=not errors,
    )


def audit_validation_subject(root: Path = ROOT) -> dict[str, object]:
    """Bind validation evidence to the exact releasable candidate bytes."""

    errors: list[str] = []
    domain: str | None = None
    digest: str | None = None
    file_count: int | None = None
    excluded: list[str] = []
    try:
        from tools.build_phase15c_release import (
            INTERNAL_VALIDATION_REPORT,
            RELEASE_FINGERPRINT,
            VALIDATION_SUBJECT_DOMAIN,
            hash_file_map,
            release_file_map,
        )

        domain = VALIDATION_SUBJECT_DOMAIN
        excluded = [
            INTERNAL_VALIDATION_REPORT,
            RELEASE_FINGERPRINT.as_posix(),
        ]
        subject = dict(release_file_map(root))
        for path in excluded:
            subject.pop(path, None)
        digest = hash_file_map(subject, domain=domain)
        file_count = len(subject)
        if re.fullmatch(r"[0-9a-f]{64}", digest) is None:
            errors.append("validation-subject SHA-256 is malformed")
    except Exception as exc:
        errors.append(
            "cannot establish validation-subject custody: "
            f"{type(exc).__name__}: {exc}"
        )
    return _audit(
        "phase15c-validation-subject",
        errors,
        domain=domain,
        sha256=digest,
        file_count=file_count,
        excluded=excluded,
    )


def audit_contract_identities(root: Path = ROOT) -> dict[str, object]:
    errors: list[str] = []
    identities: dict[str, object] = {}
    try:
        project = tomllib.loads(
            (root / "pyproject.toml").read_text(encoding="utf-8")
        )
        identities = {
            "project_package": project["project"]["version"],
            "module_package": _literal_assignment(
                root / "pycforge" / "_version.py", "__version__"
            ),
            "converter": _literal_assignment(
                root
                / "pycforge"
                / "converter"
                / "contracts"
                / "versions.py",
                "CONVERTER_CONTRACT_VERSION",
            ),
            "workspace": _literal_assignment(
                root / "pycforge" / "ide" / "__init__.py",
                "WORKSPACE_CONTRACT_VERSION",
            ),
            "worker_protocol": _literal_assignment(
                root / "pycforge" / "ide" / "_worker_protocol_types.py",
                "PROTOCOL_SCHEMA",
            ),
            "action_registry": _literal_assignment(
                root / "pycforge" / "ide" / "__init__.py",
                "ACTION_REGISTRY_VERSION",
            ),
            "visual_system": _literal_assignment(
                root / "pycforge" / "ide" / "__init__.py",
                "VISUAL_SYSTEM_VERSION",
            ),
            "settings_schema": _literal_assignment(
                root / "pycforge" / "ide" / "qt_contract.py",
                "SETTINGS_SCHEMA_VERSION",
            ),
        }
    except (
        OSError,
        UnicodeError,
        SyntaxError,
        ValueError,
        KeyError,
        TypeError,
        tomllib.TOMLDecodeError,
    ) as exc:
        errors.append(f"cannot establish Phase 15C identities: {exc}")
    expected = {
        "project_package": EXPECTED_PACKAGE_VERSION,
        "module_package": EXPECTED_PACKAGE_VERSION,
        "converter": EXPECTED_CONVERTER_CONTRACT,
        "workspace": EXPECTED_WORKSPACE_CONTRACT,
        "worker_protocol": EXPECTED_WORKER_PROTOCOL,
        "action_registry": EXPECTED_ACTION_REGISTRY,
        "visual_system": EXPECTED_VISUAL_SYSTEM,
        "settings_schema": EXPECTED_SETTINGS_SCHEMA,
    }
    for key, value in expected.items():
        if identities.get(key) != value:
            errors.append(
                f"{key} identity is {identities.get(key)!r}, expected {value!r}"
            )
    return _audit(
        "phase15c-contract-identities",
        errors,
        identities=identities,
        expected=expected,
    )


def audit_frozen_converter_subtree(root: Path = ROOT) -> dict[str, object]:
    errors: list[str] = []
    actual: str | None = None
    file_count = 0
    try:
        actual, file_count = canonical_converter_subtree_hash(root)
    except (OSError, ValueError) as exc:
        errors.append(f"cannot hash frozen converter subtree: {exc}")
    if actual != EXPECTED_CONVERTER_SUBTREE_SHA256:
        errors.append(f"frozen converter subtree changed: {actual}")
    return _audit(
        "frozen-converter-subtree",
        errors,
        expected_sha256=EXPECTED_CONVERTER_SUBTREE_SHA256,
        actual_sha256=actual,
        file_count=file_count,
        converter_semantics_modified=False if not errors else None,
    )


def locate_predecessor_archive(root: Path = ROOT) -> Path | None:
    candidates = (
        root / PREDECESSOR_ARCHIVE_NAME,
        root.parent / PREDECESSOR_ARCHIVE_NAME,
        root.parent
        / "phase15b_release"
        / "final_0_15_1"
        / PREDECESSOR_ARCHIVE_NAME,
        root.parent / "final_0_15_1" / PREDECESSOR_ARCHIVE_NAME,
    )
    return next((path for path in candidates if path.is_file()), None)


def _hash_file_map(files: Mapping[str, bytes], *, domain: str) -> str:
    digest = sha256()
    domain_bytes = domain.encode("utf-8")
    digest.update(len(domain_bytes).to_bytes(8, "big"))
    digest.update(domain_bytes)
    for name in sorted(files):
        name_bytes = name.encode("utf-8")
        data = files[name]
        digest.update(len(name_bytes).to_bytes(8, "big"))
        digest.update(name_bytes)
        digest.update(len(data).to_bytes(8, "big"))
        digest.update(data)
    return digest.hexdigest()


def audit_predecessor_archive(
    path: Path | None,
    *,
    required: bool,
) -> dict[str, object]:
    if path is None:
        errors = ["sealed Phase 15B predecessor archive is absent"] if required else []
        return _audit(
            "phase15b-predecessor-authentication",
            errors,
            status="missing-required" if required else "not-present-optional",
            required=required,
            archive_authenticated=False,
            archive_extracted=False,
        )
    errors: list[str] = []
    size: int | None = None
    file_digest: str | None = None
    converter_digest: str | None = None
    tree_fingerprint: str | None = None
    file_count = 0
    payload: bytes | None = None
    try:
        size = path.stat().st_size
    except OSError as exc:
        errors.append(f"cannot authenticate predecessor safely: {exc}")
    if path.name != PREDECESSOR_ARCHIVE_NAME:
        errors.append("predecessor archive filename differs")
    if size is not None and size != PREDECESSOR_ARCHIVE_SIZE:
        errors.append(f"predecessor archive size mismatch: {size}")
    if not errors:
        try:
            with path.open("rb") as stream:
                opened_size = os.fstat(stream.fileno()).st_size
                if opened_size != PREDECESSOR_ARCHIVE_SIZE:
                    errors.append(
                        "predecessor archive size changed while "
                        f"authenticating: {opened_size}"
                    )
                else:
                    payload = stream.read(PREDECESSOR_ARCHIVE_SIZE + 1)
        except OSError as exc:
            errors.append(f"cannot authenticate predecessor safely: {exc}")
    if payload is not None:
        if len(payload) != PREDECESSOR_ARCHIVE_SIZE:
            errors.append(
                "predecessor archive size changed while authenticating: "
                f"{len(payload)}"
            )
        else:
            file_digest = sha256(payload).hexdigest()
            if file_digest != PREDECESSOR_ARCHIVE_SHA256:
                errors.append(
                    f"predecessor archive SHA-256 mismatch: {file_digest}"
                )
    if not errors and payload is not None:
        try:
            files: dict[str, bytes] = {}
            roots: set[str] = set()
            with tarfile.open(
                fileobj=BytesIO(payload),
                mode="r:gz",
            ) as archive:
                for member in archive.getmembers():
                    pure = PurePosixPath(member.name)
                    if (
                        pure.is_absolute()
                        or not pure.parts
                        or any(part in {"", ".", ".."} for part in pure.parts)
                        or not member.isfile()
                    ):
                        raise ValueError(
                            "predecessor contains an unsafe member"
                        )
                    roots.add(pure.parts[0])
                    relative = PurePosixPath(*pure.parts[1:]).as_posix()
                    if not relative or relative in files:
                        raise ValueError(
                            "predecessor contains a duplicate member"
                        )
                    stream = archive.extractfile(member)
                    if stream is None:
                        raise ValueError(
                            "predecessor contains an unreadable member"
                        )
                    files[relative] = stream.read()
            if roots != {PREDECESSOR_ARCHIVE_ROOT}:
                errors.append("predecessor archive root differs")
            file_count = len(files)
            converter = {
                name.removeprefix("pycforge/converter/"): data
                for name, data in files.items()
                if name.startswith("pycforge/converter/")
            }
            converter_digest = _hash_file_map(
                converter,
                domain=CONVERTER_SUBTREE_DOMAIN,
            )
            if converter_digest != EXPECTED_CONVERTER_SUBTREE_SHA256:
                errors.append("predecessor converter custody differs")
            fingerprint = json.loads(
                files["transition/phase_15b/release_fingerprint.json"]
            )
            tree_fingerprint = fingerprint.get("value")
            if tree_fingerprint != PREDECESSOR_TREE_FINGERPRINT:
                errors.append(
                    "predecessor release-tree fingerprint differs"
                )
        except (
            OSError,
            tarfile.TarError,
            UnicodeError,
            ValueError,
            KeyError,
            json.JSONDecodeError,
        ) as exc:
            errors.append(f"cannot authenticate predecessor safely: {exc}")
    return _audit(
        "phase15b-predecessor-authentication",
        errors,
        status="authenticated" if not errors else "failed",
        required=required,
        archive_name=path.name,
        expected_size=PREDECESSOR_ARCHIVE_SIZE,
        actual_size=size,
        expected_sha256=PREDECESSOR_ARCHIVE_SHA256,
        actual_sha256=file_digest,
        expected_tree_fingerprint=PREDECESSOR_TREE_FINGERPRINT,
        actual_tree_fingerprint=tree_fingerprint,
        converter_subtree_sha256=converter_digest,
        regular_file_count=file_count,
        archive_authenticated=not errors,
        archive_extracted=False,
    )


def _surface_action_ids(surface_id: str) -> tuple[str, ...]:
    return tuple(
        placement.target
        for placement in SURFACE_SPECS[surface_id].placements
        if placement.kind is PlacementKind.ACTION
    )


def audit_action_and_menu_contract(root: Path = ROOT) -> dict[str, object]:
    errors = list(validate_action_contract())
    contexts = tuple(
        sorted(
            surface_id
            for surface_id, surface in SURFACE_SPECS.items()
            if surface.kind is SurfaceKind.CONTEXT
        )
    )
    if len(ACTION_SPECS) != EXPECTED_ACTION_COUNT:
        errors.append(f"action inventory contains {len(ACTION_SPECS)} entries")
    if len(contexts) != EXPECTED_CONTEXT_COUNT:
        errors.append(f"context inventory contains {len(contexts)} entries")
    if tuple(MAIN_MENU_SURFACES) != (
        "menu.file",
        "menu.edit",
        "menu.view",
        "menu.navigate",
        "menu.conversion",
    ):
        errors.append("main-menu surface order differs")
    if len(MAIN_MENU_SURFACES) != EXPECTED_MAIN_MENU_COUNT:
        errors.append(
            f"main-menu inventory contains {len(MAIN_MENU_SURFACES)} entries"
        )
    generated_c = _surface_action_ids("context.generated_c")
    if generated_c != ("edit.copy", "edit.select_all", "search.find"):
        errors.append("generated-C context is not the exact read-only allowlist")
    icon_names = set(PYCFORGE_ICON_FILES)
    missing_icons = sorted(
        {
            spec.icon_name
            for spec in ACTION_SPECS.values()
            if spec.icon_name is not None and spec.icon_name not in icon_names
        }
    )
    if missing_icons:
        errors.append("actions reference unknown icons: " + ", ".join(missing_icons))
    constructor_owners: list[str] = []
    for path in sorted((root / "pycforge" / "ide").glob("*.py")):
        source = path.read_text(encoding="utf-8")
        if re.search(r"\bQAction\s*\(", source):
            constructor_owners.append(path.name)
    if constructor_owners != ["qt_actions.py"]:
        errors.append(
            "persistent QAction construction is not singly owned: "
            + ", ".join(constructor_owners)
        )
    return _audit(
        "declarative-action-and-menu-contract",
        errors,
        action_registry=EXPECTED_ACTION_REGISTRY,
        actions=len(ACTION_SPECS),
        main_menu_surfaces=len(MAIN_MENU_SURFACES),
        main_menus=list(MAIN_MENU_SURFACES),
        context_surfaces=len(contexts),
        context_surface_ids=list(contexts),
        generated_c_context_actions=list(generated_c),
        generated_c_mutation_actions=0,
        qaction_constructor_owners=constructor_owners,
    )


def _local_name(value: str) -> str:
    return value.rsplit("}", 1)[-1]


def audit_visual_system(root: Path = ROOT) -> dict[str, object]:
    errors: list[str] = []
    icon_root = root / "pycforge" / "ide" / "resources" / "icons"
    icon_paths = tuple(sorted(icon_root.glob("*.svg")))
    if len(PYCFORGE_ICON_FILES) != EXPECTED_ICON_COUNT:
        errors.append(f"icon catalogue contains {len(PYCFORGE_ICON_FILES)} entries")
    if {path.name for path in icon_paths} != set(PYCFORGE_ICON_FILES.values()):
        errors.append("packaged SVG inventory differs from the icon catalogue")
    forbidden_elements = {"foreignObject", "image", "script", "style", "text"}
    allowed_colors = set(color_tokens().values())
    for path in icon_paths:
        try:
            document = ET.parse(path)
            svg = document.getroot()
        except (OSError, ET.ParseError) as exc:
            errors.append(f"{path.name}: invalid SVG: {exc}")
            continue
        if (
            _local_name(svg.tag) != "svg"
            or svg.attrib.get("viewBox") != "0 0 24 24"
            or "width" in svg.attrib
            or "height" in svg.attrib
        ):
            errors.append(f"{path.name}: SVG scaling contract differs")
        for element in svg.iter():
            if _local_name(element.tag) in forbidden_elements:
                errors.append(f"{path.name}: forbidden SVG element")
            for attribute, value in element.attrib.items():
                local = _local_name(attribute)
                if local in {"href", "src"} or re.search(
                    r"(?i)(?:data:|https?://|file:|javascript:)",
                    value,
                ):
                    errors.append(f"{path.name}: external SVG reference")
                if local in {"fill", "stroke"} and value != "none":
                    if value not in allowed_colors:
                        errors.append(f"{path.name}: non-token SVG color")
    colors = PYCFORGE_COLORS
    for background in (colors.canvas, colors.surface):
        for foreground in (
            colors.text,
            colors.text_soft,
            colors.text_muted,
            colors.text_disabled,
            colors.blue,
            colors.violet,
            colors.warm,
            colors.success,
            colors.warning,
            colors.error,
        ):
            if contrast_ratio(foreground, background) < 4.5:
                errors.append("visual token pair falls below WCAG AA")
    selectors = (
        "QMenu#PyCForgeMenu",
        "QMenuBar::item:selected",
        "QMenuBar::item:pressed",
        "QMenu::item:selected",
        "QMenu::item:pressed",
        "QMenu::item:disabled",
        'QMenu#PyCForgeMenu[pycforgeTone="primary"]::item:selected',
        'QMenu#PyCForgeMenu[pycforgeTone="danger"]::item:selected',
        "QMenu::separator",
        "QMenu::icon",
        "QMenu::indicator:checked",
        "QMenu::right-arrow",
        "QMenu::scroller",
    )
    missing_selectors = [
        selector for selector in selectors if selector not in PYCFORGE_QSS
    ]
    if missing_selectors:
        errors.append("menu visual states are incomplete")
    if len(PYCFORGE_QSS) <= 15_000:
        errors.append("central workspace stylesheet is incomplete")
    qt_source = (
        root / "pycforge" / "ide" / "qt.py"
    ).read_text(encoding="utf-8")
    shell_source = (
        root / "pycforge" / "ide" / "qt_shell.py"
    ).read_text(encoding="utf-8")
    high_dpi_tokens = (
        "Qt.AA_EnableHighDpiScaling",
        "Qt.AA_UseHighDpiPixmaps",
        "QApplication([])",
    )
    high_dpi_positions = tuple(
        qt_source.find(token) for token in high_dpi_tokens
    )
    high_dpi_startup_order = (
        all(position >= 0 for position in high_dpi_positions)
        and high_dpi_positions[0] < high_dpi_positions[2]
        and high_dpi_positions[1] < high_dpi_positions[2]
    )
    if not high_dpi_startup_order:
        errors.append("high-DPI attributes are not enabled before startup")
    window_brand_mark = 'pycforge_icon_path("brand-mark")' in shell_source
    if not window_brand_mark:
        errors.append("window branding does not use the packaged mark")
    return _audit(
        "pycforge-visual-system",
        errors,
        visual_system=EXPECTED_VISUAL_SYSTEM,
        svg_assets=len(icon_paths),
        catalogue_entries=len(PYCFORGE_ICON_FILES),
        vector_only=True,
        remote_references=False if not errors else None,
        logical_menu_icon_size=PYCFORGE_METRICS.icon_menu,
        logical_toolbar_icon_size=PYCFORGE_METRICS.icon_toolbar,
        menu_state_selectors=len(selectors),
        missing_menu_state_selectors=missing_selectors,
        high_dpi_attributes_before_application=high_dpi_startup_order,
        window_brand_mark=window_brand_mark,
    )


def audit_workspace_completeness(root: Path = ROOT) -> dict[str, object]:
    """Audit the bounded Phase 15C authoring and observer workspace."""

    errors: list[str] = []
    ide = root / "pycforge" / "ide"
    required_modules = (
        "action_validation.py",
        "command_palette.py",
        "editor_commands_qt.py",
        "qt_command_palette.py",
        "qt_editor_buffers.py",
        "qt_editor_surfaces.py",
        "qt_shell_interactions.py",
        "qt_workspace_features.py",
        "qt_workspace_navigation.py",
        "qt_workspace_observers.py",
        "qt_workspace_panels.py",
        "qt_workspace_widgets.py",
        "session_history.py",
        "source_editing.py",
        "source_structure.py",
        "source_structure_async.py",
        "theme_workspace_stylesheet.py",
        "workspace_search.py",
        "workspace_session.py",
    )
    parsed_modules: list[str] = []
    for name in required_modules:
        path = ide / name
        try:
            source = path.read_text(encoding="utf-8")
            ast.parse(source, filename=str(path))
        except (OSError, UnicodeError, SyntaxError) as exc:
            errors.append(f"{name}: unavailable or invalid: {exc}")
            continue
        parsed_modules.append(name)
        if len(source.splitlines()) >= 600:
            errors.append(f"{name}: module budget is not bounded")

    constant_specs = {
        "source_document_limit": (
            "workspace_session.py",
            "MAX_SESSION_DOCUMENTS",
            64,
        ),
        "source_pane_limit": (
            "workspace_session.py",
            "MAX_EDITOR_PANES",
            2,
        ),
        "search_match_limit": (
            "workspace_search.py",
            "MAX_BUNDLE_MATCHES",
            5_000,
        ),
        "structure_symbol_limit": (
            "source_structure.py",
            "MAX_OUTLINE_SYMBOLS",
            4_096,
        ),
        "command_palette_limit": (
            "command_palette.py",
            "MAX_COMMAND_PALETTE_RESULTS",
            50,
        ),
        "history_entry_limit": (
            "session_history.py",
            "MAX_CONVERSION_HISTORY_ENTRIES",
            64,
        ),
    }
    bounds: dict[str, object] = {}
    for label, (filename, name, expected) in constant_specs.items():
        try:
            value = _literal_assignment(ide / filename, name)
        except (OSError, UnicodeError, SyntaxError, ValueError) as exc:
            errors.append(f"{filename}: cannot establish {name}: {exc}")
            value = None
        bounds[label] = value
        if value != expected:
            errors.append(f"{label} is {value!r}, expected {expected!r}")

    search_source = (ide / "workspace_search.py").read_text(
        encoding="utf-8"
    )
    structure_source = (ide / "source_structure_async.py").read_text(
        encoding="utf-8"
    )
    feature_source = (ide / "qt_workspace_features.py").read_text(
        encoding="utf-8"
    )
    output_source = (ide / "qt_editor_surfaces.py").read_text(
        encoding="utf-8"
    )
    documents_source = (ide / "qt_documents.py").read_text(
        encoding="utf-8"
    )
    latest_wins = all(
        token in source
        for source in (search_source, structure_source)
        for token in (
            "generation != self._generation",
            "self._pending =",
            "self._closed",
        )
    )
    pending_invalidation = (
        "if pending_id is not None:" in feature_source
        and "self.bundle_search.invalidate_results()" in feature_source
        and "self._invalidate_source_observers()" in documents_source
    )
    generated_read_only = "owner.output.setReadOnly(True)" in output_source
    generated_explicit_save = all(
        token in documents_source
        for token in (
            "def save_c(self)",
            "if not snapshot.can_save_c:",
            "save_generated_c_linked_async",
        )
    )
    if not latest_wins:
        errors.append("workspace observers are not demonstrably latest-wins")
    if not pending_invalidation:
        errors.append("pending source sync does not invalidate observers")
    if not generated_read_only:
        errors.append("generated C is not explicitly read-only")
    if not generated_explicit_save:
        errors.append("generated C lacks an explicit authenticated save path")
    return _audit(
        "phase15c-workspace-completeness",
        errors,
        required_modules=list(required_modules),
        parsed_modules=parsed_modules,
        module_line_limit=599,
        **bounds,
        latest_wins_observers=latest_wins,
        pending_sync_invalidates_observers=pending_invalidation,
        generated_c_read_only=generated_read_only,
        generated_c_explicit_save_only=generated_explicit_save,
    )


def audit_vocabulary_custody(root: Path = ROOT) -> dict[str, object]:
    scan = scan_release_tree(root)
    errors: list[str] = []
    if not scan.passed:
        errors.append(
            "release tree contains retired-theme vocabulary "
            f"(paths={len(scan.path_matches)}, "
            f"contents={len(scan.content_matches)})"
        )
    return _audit(
        "retired-theme-vocabulary-custody",
        errors,
        **scan.to_report(),
    )


def _strict_json_object(path: Path) -> tuple[dict[str, object], bytes]:
    payload = path.read_bytes()

    def unique_object(
        pairs: list[tuple[str, object]],
    ) -> dict[str, object]:
        result: dict[str, object] = {}
        for key, value in pairs:
            if key in result:
                raise ValueError(f"duplicate object key: {key}")
            result[key] = value
        return result

    def reject_constant(value: str) -> object:
        raise ValueError(f"non-finite JSON number: {value}")

    value = json.loads(
        payload.decode("utf-8"),
        object_pairs_hook=unique_object,
        parse_constant=reject_constant,
    )
    if not isinstance(value, dict):
        raise ValueError("top-level value is not an object")
    return value, payload


def _is_nonnegative_number(value: object) -> bool:
    return (
        type(value) in {int, float}
        and math.isfinite(float(value))
        and value >= 0
    )


def _validate_offscreen_runtime(
    value: object,
    errors: list[str],
) -> None:
    if not isinstance(value, dict):
        errors.append("offscreen runtime record is absent")
        return
    expected_keys = {
        "python_version",
        "pyqt_version",
        "qt_build_version",
        "qt_runtime_version",
        "qpa_platform",
        "qapplication_instances",
        "workspace_test_cases",
        "workspace_test_failures",
        "workspace_test_errors",
        "workspace_test_skips",
        "event_loop",
        "large_file",
        "shutdown",
    }
    if set(value) != expected_keys:
        errors.append("offscreen runtime field inventory is not exact")
        return
    expected_strings = {
        "python_version": "3.12.13",
        "pyqt_version": "5.15.11",
        "qt_build_version": "5.15.14",
        "qt_runtime_version": "5.15.19",
        "qpa_platform": "offscreen",
    }
    if any(value.get(key) != expected for key, expected in expected_strings.items()):
        errors.append("offscreen runtime identity is not exact")
    counts = {
        key: value.get(key)
        for key in (
            "qapplication_instances",
            "workspace_test_cases",
            "workspace_test_failures",
            "workspace_test_errors",
            "workspace_test_skips",
        )
    }
    if (
        any(type(item) is not int or item < 0 for item in counts.values())
        or counts["qapplication_instances"] != 1
        or counts["workspace_test_cases"] < 1
        or counts["workspace_test_failures"] != 0
        or counts["workspace_test_errors"] != 0
    ):
        errors.append("offscreen QApplication/widget execution is not passing")

    event_loop = value.get("event_loop")
    event_keys = {
        "large_source_characters",
        "large_source_minimum_characters",
        "first_turn_seconds",
        "first_turn_limit_seconds",
        "timer_interval_seconds",
        "timer_ticks_while_waiting",
        "within_limit",
    }
    if not isinstance(event_loop, dict) or set(event_loop) != event_keys:
        errors.append("event-loop timing record is absent or malformed")
    else:
        first_turn = event_loop.get("first_turn_seconds")
        first_limit = event_loop.get("first_turn_limit_seconds")
        if (
            type(event_loop.get("large_source_characters")) is not int
            or type(event_loop.get("large_source_minimum_characters")) is not int
            or event_loop["large_source_minimum_characters"] < 250_000
            or event_loop["large_source_characters"]
            < event_loop["large_source_minimum_characters"]
            or not _is_nonnegative_number(first_turn)
            or not _is_nonnegative_number(first_limit)
            or first_limit <= 0
            or first_turn >= first_limit
            or not _is_nonnegative_number(
                event_loop.get("timer_interval_seconds")
            )
            or event_loop["timer_interval_seconds"] <= 0
            or type(event_loop.get("timer_ticks_while_waiting")) is not int
            or event_loop["timer_ticks_while_waiting"] < 1
            or event_loop.get("within_limit") is not True
        ):
            errors.append("event-loop timing evidence is not passing")

    large_file = value.get("large_file")
    large_keys = {
        "window_construction_seconds",
        "window_construction_limit_seconds",
        "transpilation_seconds",
        "transpilation_limit_seconds",
        "large_file_mode",
        "syntax_highlighter_detached",
        "shared_buffer_preserved",
    }
    if not isinstance(large_file, dict) or set(large_file) != large_keys:
        errors.append("large-file runtime record is absent or malformed")
    else:
        construction = large_file.get("window_construction_seconds")
        construction_limit = large_file.get("window_construction_limit_seconds")
        transpilation = large_file.get("transpilation_seconds")
        transpilation_limit = large_file.get("transpilation_limit_seconds")
        if (
            not all(
                _is_nonnegative_number(item)
                for item in (
                    construction,
                    construction_limit,
                    transpilation,
                    transpilation_limit,
                )
            )
            or construction_limit <= 0
            or transpilation_limit <= 0
            or construction >= construction_limit
            or transpilation >= transpilation_limit
            or large_file.get("large_file_mode") is not True
            or large_file.get("syntax_highlighter_detached") is not True
            or large_file.get("shared_buffer_preserved") is not True
        ):
            errors.append("large-file runtime evidence is not passing")

    shutdown = value.get("shutdown")
    if (
        not isinstance(shutdown, dict)
        or set(shutdown)
        != {"new_pycforge_threads_after_close", "worker_leaks"}
        or type(shutdown.get("new_pycforge_threads_after_close")) is not int
        or shutdown["new_pycforge_threads_after_close"] != 0
        or type(shutdown.get("worker_leaks")) is not int
        or shutdown["worker_leaks"] != 0
    ):
        errors.append("offscreen runtime shutdown evidence is not clean")


def _validate_performance_record(
    record: dict[str, object],
    *,
    require_runtime_evidence: bool,
) -> list[str]:
    errors: list[str] = []
    base_keys = {
        "schema",
        "package",
        "workspace",
        "worker_protocol",
        "absolute_bounds",
        "background_services",
        "routine_interaction_contracts",
        "measurement_scope",
        "phase15a_architecture_preserved",
        "generated_c_executed",
        "toolchain_invoked",
        "status",
        "promotion_eligible",
    }
    allowed_keys = base_keys | {"offscreen_runtime"}
    if set(record) not in (base_keys, allowed_keys):
        errors.append("performance evidence field inventory is not exact")
        return errors
    expected_identities = {
        "schema": PERFORMANCE_EVIDENCE_SCHEMA,
        "package": EXPECTED_PACKAGE_VERSION,
        "workspace": EXPECTED_WORKSPACE_CONTRACT,
        "worker_protocol": EXPECTED_WORKER_PROTOCOL,
    }
    if any(
        record.get(key) != expected
        for key, expected in expected_identities.items()
    ):
        errors.append("performance evidence identity is not exact")
    expected_bounds = {
        "editor_panes": 2,
        "source_documents": 64,
        "bundle_search_matches": 5_000,
        "bundle_search_query_characters": 4_096,
        "bundle_search_preview_characters": 512,
        "command_palette_results": 50,
        "command_palette_query_characters": 256,
        "session_history_entries": 64,
        "outline_symbols": 4_096,
        "outline_depth": 64,
        "outline_name_characters": 256,
        "outline_text_characters": 262_144,
    }
    expected_services = {
        "conversion_process_isolated": True,
        "conversion_one_active_one_latest": True,
        "bundle_search_latest_wins": True,
        "bundle_search_file_io": False,
        "source_structure_latest_wins": True,
        "source_structure_file_io": False,
        "stale_publication_suppressed": True,
    }
    expected_routine = {
        "go_to_line_complete_source_copy": False,
        "tab_state_retains_source_payload": False,
        "split_state_retains_source_payload": False,
        "command_palette_retains_handlers": False,
        "history_retains_semantic_payload": False,
        "routine_host_scan": False,
        "routine_converter_invocation": False,
    }
    if record.get("absolute_bounds") != expected_bounds:
        errors.append("performance evidence bounds are not exact")
    if record.get("background_services") != expected_services:
        errors.append("background-service evidence is not exact")
    if record.get("routine_interaction_contracts") != expected_routine:
        errors.append("routine-interaction evidence is not exact")
    if (
        record.get("phase15a_architecture_preserved") is not True
        or record.get("generated_c_executed") is not False
        or record.get("toolchain_invoked") is not False
    ):
        errors.append("performance evidence safety boundary is not exact")

    measurement = record.get("measurement_scope")
    measurement_keys = {
        "headless_contract_tests",
        "static_qt_integration_tests",
        "real_qapplication_exercised",
        "real_pyqt_widgets_exercised",
        "offscreen_pyqt_widgets_exercised",
        "visible_windows_11_exercised",
        "visible_linux_desktop_exercised",
        "display_scaling_matrix_exercised",
        "assistive_technology_exercised",
        "gui_event_loop_timing_recorded",
    }
    if not isinstance(measurement, dict) or set(measurement) != measurement_keys:
        errors.append("performance measurement scope is absent or malformed")
        measurement = {}
    fixed_true = ("headless_contract_tests", "static_qt_integration_tests")
    fixed_false = (
        "visible_windows_11_exercised",
        "visible_linux_desktop_exercised",
        "display_scaling_matrix_exercised",
        "assistive_technology_exercised",
    )
    if any(measurement.get(key) is not True for key in fixed_true) or any(
        measurement.get(key) is not False for key in fixed_false
    ):
        errors.append("performance measurement scope is not honest")

    promoted_record = record.get("promotion_eligible") is True
    runtime_flags = (
        "real_qapplication_exercised",
        "real_pyqt_widgets_exercised",
        "offscreen_pyqt_widgets_exercised",
        "gui_event_loop_timing_recorded",
    )
    if promoted_record:
        if record.get("status") != "supporting-offscreen-runtime-evidence-passed":
            errors.append("promoted performance evidence status is not exact")
        if any(measurement.get(key) is not True for key in runtime_flags):
            errors.append("recorded QApplication/widget evidence is incomplete")
        _validate_offscreen_runtime(record.get("offscreen_runtime"), errors)
    else:
        if (
            type(record.get("promotion_eligible")) is not bool
            or record.get("status")
            != "supporting-headless-and-static-contracts-passed"
            or any(measurement.get(key) is not False for key in runtime_flags)
            or "offscreen_runtime" in record
        ):
            errors.append("candidate performance evidence is contradictory")
    if require_runtime_evidence and not promoted_record:
        errors.append("promotion requires recorded offscreen runtime evidence")
    return errors


def audit_platform_scope(
    root: Path = ROOT,
    *,
    require_runtime_evidence: bool = False,
) -> dict[str, object]:
    try:
        import PyQt5  # noqa: F401
    except (ImportError, ModuleNotFoundError):
        pyqt_available = False
    else:
        pyqt_available = True
    path = root / PERFORMANCE_EVIDENCE
    errors: list[str] = []
    record: dict[str, object] = {}
    payload = b""
    try:
        record, payload = _strict_json_object(path)
    except (OSError, UnicodeError, json.JSONDecodeError, ValueError) as exc:
        errors.append(f"performance evidence is unavailable or invalid: {exc}")
    else:
        errors.extend(
            _validate_performance_record(
                record,
                require_runtime_evidence=require_runtime_evidence,
            )
        )
    measurement = record.get("measurement_scope")
    if not isinstance(measurement, dict):
        measurement = {}
    return _audit(
        "honest-platform-scope",
        errors,
        validation_scope="phase15c-current-host-supporting-evidence",
        current_host_platform=sys.platform,
        platform_description=platform.platform(),
        machine=platform.machine(),
        python_version=platform.python_version(),
        logical_cpu_count=os.cpu_count(),
        optional_pyqt_available=pyqt_available,
        evidence_path=PERFORMANCE_EVIDENCE.as_posix(),
        evidence_sha256=sha256(payload).hexdigest() if payload else None,
        evidence_file_bytes=len(payload),
        evidence_authenticated=not errors,
        real_qapplication_exercised=measurement.get(
            "real_qapplication_exercised"
        )
        is True,
        real_pyqt_widgets_exercised=measurement.get(
            "real_pyqt_widgets_exercised"
        )
        is True,
        offscreen_pyqt_widgets_exercised=measurement.get(
            "offscreen_pyqt_widgets_exercised"
        )
        is True,
        gui_event_loop_timing_recorded=measurement.get(
            "gui_event_loop_timing_recorded"
        )
        is True,
        visible_windows_11_exercised=False,
        visible_linux_desktop_exercised=False,
        display_scaling_matrix_exercised=False,
        assistive_technology_exercised=False,
        phase_15d_platform_gate_required=True,
    )


def run_validation(
    *,
    root: Path = ROOT,
    mode: str = "promotion",
    predecessor: Path | None = None,
    search_predecessor: bool = True,
) -> dict[str, object]:
    if mode not in {"quick", "full", "promotion"}:
        raise ValueError("validation mode must be quick, full, or promotion")
    normalized_mode = "promotion" if mode in {"full", "promotion"} else "quick"
    selected_predecessor = predecessor
    if selected_predecessor is None and search_predecessor:
        selected_predecessor = locate_predecessor_archive(root)
    predecessor_required = (
        normalized_mode == "promotion" or predecessor is not None
    )
    audits = [
        _safe_audit("validator-root-custody", audit_validator_root, root),
        _safe_audit(
            "phase15c-validation-subject",
            audit_validation_subject,
            root,
        ),
        _safe_audit(
            "phase15c-contract-identities", audit_contract_identities, root
        ),
        _safe_audit(
            "frozen-converter-subtree", audit_frozen_converter_subtree, root
        ),
        _safe_audit(
            "phase15b-predecessor-authentication",
            audit_predecessor_archive,
            selected_predecessor,
            required=predecessor_required,
        ),
        _safe_audit(
            "retired-theme-vocabulary-custody",
            audit_vocabulary_custody,
            root,
        ),
        _safe_audit(
            "declarative-action-and-menu-contract",
            audit_action_and_menu_contract,
            root,
        ),
        _safe_audit("pycforge-visual-system", audit_visual_system, root),
        _safe_audit(
            "phase15c-workspace-completeness",
            audit_workspace_completeness,
            root,
        ),
        _safe_audit(
            "runtime-isolation-and-toolchain-boundary",
            scan_runtime_boundaries,
            root,
        ),
    ]
    if normalized_mode == "promotion":
        audits.extend(
            (
                _safe_audit(
                    "direct-vs-isolated-equivalence",
                    audit_direct_isolated_equivalence,
                ),
                _safe_audit(
                    "bounded-maximum-input-fixtures",
                    audit_maximum_input_fixtures,
                ),
                _safe_audit(
                    "hundred-edit-convert-cancel-cycles",
                    audit_hundred_cycle_supervision,
                ),
            )
        )
    else:
        audits.extend(
            (
                _skipped("direct-vs-isolated-equivalence"),
                _skipped("bounded-maximum-input-fixtures"),
                _skipped("hundred-edit-convert-cancel-cycles"),
            )
        )
    audits.extend(
        (
            _safe_audit(
                "honest-platform-scope",
                audit_platform_scope,
                root,
                require_runtime_evidence=normalized_mode == "promotion",
            ),
            _safe_audit("source-transpiler-safety", audit_safety_scope),
        )
    )
    passed = all(audit.get("passed") is True for audit in audits)
    gate_eligible = passed and normalized_mode == "promotion"
    return {
        "schema": VALIDATION_SCHEMA,
        "mode": normalized_mode,
        "scope": "phase-15c-workspace-current-host",
        "passed": passed,
        "promotion_eligible": gate_eligible,
        "promotion_scope": "phase-15c-milestone-only",
        "phase_15c_gate_eligible": gate_eligible,
        "visible_ui_promotion_eligible": False,
        "distribution_promotion_eligible": False,
        "phase_15b_opened": True,
        "phase_15c_opened": True,
        "phase_15d_opened": False,
        "audits": audits,
    }


def _json_bytes(value: object) -> bytes:
    return (
        json.dumps(
            value,
            sort_keys=True,
            separators=(",", ":"),
            ensure_ascii=False,
            allow_nan=False,
        ).encode("utf-8")
        + b"\n"
    )


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Validate the PyCForge Phase 15C IDE-workspace gate."
    )
    parser.add_argument(
        "--mode",
        choices=("quick", "full", "promotion"),
        default="promotion",
    )
    parser.add_argument("--root", type=Path, default=ROOT)
    parser.add_argument("--predecessor", type=Path)
    parser.add_argument("--no-predecessor-search", action="store_true")
    parser.add_argument("--output", type=Path)
    args = parser.parse_args(argv)
    report = run_validation(
        root=args.root.resolve(),
        mode=args.mode,
        predecessor=(
            None if args.predecessor is None else args.predecessor.resolve()
        ),
        search_predecessor=not args.no_predecessor_search,
    )
    payload = _json_bytes(report)
    if args.output is not None:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_bytes(payload)
    sys.stdout.buffer.write(payload)
    return 0 if report["passed"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
