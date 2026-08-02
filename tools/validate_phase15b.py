"""Validate the PyCForge Phase 15B application-shell release gate.

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
from tools._phase15b_release_contract import scan_release_tree  # noqa: E402
from tools.validate_phase15a import (  # noqa: E402
    CONVERTER_SUBTREE_DOMAIN,
    audit_direct_isolated_equivalence,
    audit_hundred_cycle_supervision,
    audit_safety_scope,
    canonical_converter_subtree_hash,
)


VALIDATION_SCHEMA = "pycforge.phase15b-validation-report/1"
EXPECTED_PACKAGE_VERSION = "0.15.1"
EXPECTED_CONVERTER_CONTRACT = "0.14.3"
EXPECTED_WORKSPACE_CONTRACT = "pycforge-workspace/0.4"
EXPECTED_WORKER_PROTOCOL = "pycforge.worker-protocol/0.1"
EXPECTED_ACTION_REGISTRY = "pycforge.action-registry/0.1"
EXPECTED_VISUAL_SYSTEM = "pycforge.visual-system/0.1"
EXPECTED_SETTINGS_SCHEMA = 1
EXPECTED_CONVERTER_SUBTREE_SHA256 = (
    "a45bc2c31b954f9856c8eab36e95f68b086d5fdd682d2cf47ba2186887743124"
)
EXPECTED_ACTION_COUNT = 33
EXPECTED_CONTEXT_COUNT = 8
EXPECTED_ICON_COUNT = 41

PREDECESSOR_ARCHIVE_NAME = "pycforge_phase_15a_v0_15_0.tar.gz"
PREDECESSOR_ARCHIVE_ROOT = "pycforge_phase_15a_v0_15_0"
PREDECESSOR_ARCHIVE_SIZE = 1_480_105
PREDECESSOR_ARCHIVE_SHA256 = (
    "da33821ef82d948a9204af76baa5495ae2ff5df4500b12f4a67c12663cd95a06"
)
PREDECESSOR_TREE_FINGERPRINT = (
    "52014b9bd92912fe25b5d2faf42a388e98e828be66a3b371277d552666cf172a"
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
        from tools.build_phase15b_release import (
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
        "phase15b-validation-subject",
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
        errors.append(f"cannot establish Phase 15B identities: {exc}")
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
        "phase15b-contract-identities",
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
        / "phase15a_release"
        / "final_0_15_0"
        / PREDECESSOR_ARCHIVE_NAME,
        root.parent / "final_0_15_0" / PREDECESSOR_ARCHIVE_NAME,
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
        errors = ["sealed Phase 15A predecessor archive is absent"] if required else []
        return _audit(
            "phase15a-predecessor-authentication",
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
                files["transition/phase_15a/release_fingerprint.json"]
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
        "phase15a-predecessor-authentication",
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
        "menu.conversion",
    ):
        errors.append("main-menu surface order differs")
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
        main_menus=list(MAIN_MENU_SURFACES),
        context_surfaces=list(contexts),
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


def audit_platform_scope() -> dict[str, object]:
    try:
        import PyQt5  # noqa: F401
    except (ImportError, ModuleNotFoundError):
        pyqt_available = False
    else:
        pyqt_available = True
    return _audit(
        "honest-platform-scope",
        [],
        validation_scope="phase15b-current-host-supporting-evidence",
        current_host_platform=sys.platform,
        platform_description=platform.platform(),
        machine=platform.machine(),
        python_version=platform.python_version(),
        logical_cpu_count=os.cpu_count(),
        optional_pyqt_available=pyqt_available,
        real_pyqt_widgets_exercised=False,
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
            "phase15b-validation-subject",
            audit_validation_subject,
            root,
        ),
        _safe_audit(
            "phase15b-contract-identities", audit_contract_identities, root
        ),
        _safe_audit(
            "frozen-converter-subtree", audit_frozen_converter_subtree, root
        ),
        _safe_audit(
            "phase15a-predecessor-authentication",
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
            _safe_audit("honest-platform-scope", audit_platform_scope),
            _safe_audit("source-transpiler-safety", audit_safety_scope),
        )
    )
    passed = all(audit.get("passed") is True for audit in audits)
    gate_eligible = passed and normalized_mode == "promotion"
    return {
        "schema": VALIDATION_SCHEMA,
        "mode": normalized_mode,
        "scope": "phase-15b-application-shell-current-host",
        "passed": passed,
        "promotion_eligible": gate_eligible,
        "promotion_scope": "phase-15b-milestone-only",
        "phase_15b_gate_eligible": gate_eligible,
        "visible_ui_promotion_eligible": False,
        "distribution_promotion_eligible": False,
        "phase_15b_opened": True,
        "phase_15c_opened": False,
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
        description="Validate the PyCForge Phase 15B application-shell gate."
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
