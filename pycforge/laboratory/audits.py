from __future__ import annotations
import ast, hashlib, json, re, subprocess, sys
from pathlib import Path
from typing import Any

from .keyword_audit import audit_keyword
from .keyword_only_audit import audit_keyword_only

FORBIDDEN_IMPORTS = {"PyQt5", "PySide6", "subprocess"}
FORBIDDEN_TOOLCHAIN_TOKENS = {"gcc", "clang", "cl.exe", "msvc", "cc "}

def audit_architecture(root: Path) -> dict[str, Any]:
    from pycforge.converter.contracts.configuration import DEFAULT_RENDERER, DEFAULT_RULE_SET
    from pycforge.converter.contracts.versions import (
        C_IR_SCHEMA,
        CONVERSION_PLAN_SCHEMA,
        GENERATED_C_SCHEMA,
        KEYWORD_CALL_FACT_SCHEMA,
        KEYWORD_ONLY_CALL_FACT_SCHEMA,
    )
    from pycforge.converter.keyword_calls import KEYWORD_CALL_RULE_ID
    from pycforge.converter.keyword_only_calls import KEYWORD_ONLY_CALL_RULE_ID

    violations=[]
    converter_root=root/"pycforge"/"converter"
    for path in sorted(converter_root.rglob("*.py")):
        tree=ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                for alias in node.names:
                    if alias.name.split(".")[0] in FORBIDDEN_IMPORTS: violations.append(f"{path.relative_to(root)} imports {alias.name}")
            elif isinstance(node, ast.ImportFrom) and node.module and node.module.split(".")[0] in FORBIDDEN_IMPORTS:
                violations.append(f"{path.relative_to(root)} imports {node.module}")
    # Future rules and helpers must not bypass structured C IR with final-text ownership.
    for relative in (Path("pycforge/converter/rules"),Path("pycforge/converter/support_templates")):
        base=root/relative
        if base.exists():
            for path in sorted(base.rglob("*.py")):
                source=path.read_text(encoding="utf-8")
                for token in ("generated_c =", "return_c_text", "append_c_text"):
                    if token in source: violations.append(f"{path.relative_to(root)} bypasses C IR via {token}")
    renderer=root/"pycforge/converter/c_output/renderer.py"
    cir=root/"pycforge/converter/ir/c_ir/model.py"
    if not renderer.exists(): violations.append("missing sole deterministic C renderer")
    if not cir.exists(): violations.append("missing versioned C IR model")
    for relative in (Path("pycforge/converter/analysis"), Path("pycforge/converter/rules")):
        base=root/relative
        if base.exists():
            for path in sorted(base.rglob("*.py")):
                source=path.read_text(encoding="utf-8")
                if "CRenderer" in source or "CTranslationUnitBuilder" in source:
                    violations.append(f"{path.relative_to(root)} crosses Phase 5 lowering boundary")
    container_analysis=root/"pycforge"/"converter"/"containers"/"analysis.py"
    container_lowering=root/"pycforge"/"converter"/"containers"/"lowering.py"
    if not container_analysis.exists() or not container_lowering.exists():
        violations.append("missing separated Phase 11 container analysis/lowering boundary")
    elif any(token in container_analysis.read_text(encoding="utf-8") for token in ("ir.c_ir", "CRenderer", "CTranslationUnitBuilder")):
        violations.append("container analysis depends on C IR or rendering")
    cumulative_lowerer=root/"pycforge"/"converter"/"lowering.py"
    if cumulative_lowerer.exists() and len(cumulative_lowerer.read_text(encoding="utf-8").splitlines()) > 1000:
        violations.append("cumulative lowering hotspot exceeds the Phase 11 structural ceiling")
    module_analysis=root/"pycforge"/"converter"/"modules"/"analysis.py"
    module_lowering=root/"pycforge"/"converter"/"modules"/"lowering.py"
    if not module_analysis.exists() or not module_lowering.exists():
        violations.append("missing separated Phase 12 module analysis/lowering boundary")
    elif any(token in module_analysis.read_text(encoding="utf-8") for token in ("ir.c_ir", "CRenderer", "CTranslationUnitBuilder")):
        violations.append("module analysis depends on C IR or rendering")
    if module_analysis.exists():
        tree=ast.parse(module_analysis.read_text(encoding="utf-8"),filename=str(module_analysis))
        forbidden_discovery={"importlib","pkgutil","site","sysconfig","os","pathlib","socket","urllib","requests","http","subprocess"}
        for node in ast.walk(tree):
            if isinstance(node,ast.Import):
                for alias in node.names:
                    if alias.name.split(".")[0] in forbidden_discovery:
                        violations.append(f"module analysis imports discovery-capable {alias.name}")
            elif isinstance(node,ast.ImportFrom) and node.module and node.module.split(".")[0] in forbidden_discovery:
                violations.append(f"module analysis imports discovery-capable {node.module}")
    record_analysis=root/"pycforge"/"converter"/"records"/"analysis.py"
    record_lowering=root/"pycforge"/"converter"/"records"/"lowering.py"
    if not record_analysis.exists() or not record_lowering.exists():
        violations.append("missing separated Phase 13 record analysis/lowering boundary")
    elif any(
        token in record_analysis.read_text(encoding="utf-8")
        for token in ("ir.c_ir", "CRenderer", "CTranslationUnitBuilder", "records.lowering")
    ):
        violations.append("record analysis depends on C IR, rendering, or record lowering")
    numeric_analysis=root/"pycforge"/"converter"/"numeric_semantics"/"analysis.py"
    numeric_lowering=root/"pycforge"/"converter"/"numeric_semantics"/"lowering.py"
    if not numeric_analysis.exists() or not numeric_lowering.exists():
        violations.append("missing separated Phase 14A numeric analysis/lowering boundary")
    elif any(
        token in numeric_analysis.read_text(encoding="utf-8")
        for token in ("ir.c_ir", "CRenderer", "CTranslationUnitBuilder", "numeric_semantics.lowering")
    ):
        violations.append("numeric analysis depends on C IR, rendering, or numeric lowering")
    conditional_analysis=root/"pycforge"/"converter"/"conditional_regions"/"analysis.py"
    conditional_validation=root/"pycforge"/"converter"/"conditional_regions"/"validation.py"
    conditional_lowering=root/"pycforge"/"converter"/"conditional_regions"/"lowering.py"
    conditional_analysis_forbidden=(
        "ir.c_ir",
        "CRenderer",
        "CTranslationUnitBuilder",
        "conditional_regions.lowering",
        "from .lowering",
    )
    conditional_validation_forbidden=(
        "ir.c_ir",
        "CRenderer",
        "CTranslationUnitBuilder",
        "ConditionalRegionAnalyzer",
        "ConditionalRegionCIRLowerer",
        "from .analysis",
        "from .lowering",
    )
    conditional_analysis_depends_on_c_ir=bool(
        conditional_analysis.exists()
        and any(
            token in conditional_analysis.read_text(encoding="utf-8")
            for token in conditional_analysis_forbidden
        )
    )
    conditional_validation_depends_on_producer_or_lowerer=bool(
        conditional_validation.exists()
        and any(
            token in conditional_validation.read_text(encoding="utf-8")
            for token in conditional_validation_forbidden
        )
    )
    if not all(
        path.exists()
        for path in (conditional_analysis,conditional_validation,conditional_lowering)
    ):
        violations.append("missing separated Phase 14B conditional analysis/validation/lowering boundary")
    if conditional_analysis_depends_on_c_ir:
        violations.append("conditional analysis depends on C IR, rendering, or conditional lowering")
    if conditional_validation_depends_on_producer_or_lowerer:
        violations.append("conditional validation depends on C IR, producer analysis, or lowering")
    keyword_analysis=root/"pycforge"/"converter"/"keyword_calls"/"analysis.py"
    keyword_validation=root/"pycforge"/"converter"/"keyword_calls"/"validation.py"
    keyword_lowering=root/"pycforge"/"converter"/"keyword_calls"/"lowering.py"
    keyword_analysis_forbidden=(
        "ir.c_ir",
        "CRenderer",
        "CTranslationUnitBuilder",
        "keyword_calls.lowering",
        "from .lowering",
    )
    keyword_validation_forbidden=(
        "ir.c_ir",
        "CRenderer",
        "CTranslationUnitBuilder",
        "KeywordCallAnalyzer",
        "KeywordCallCIRLowerer",
        "from .analysis",
        "from .lowering",
    )
    keyword_analysis_depends_on_c_ir=bool(
        keyword_analysis.exists()
        and any(
            token in keyword_analysis.read_text(encoding="utf-8")
            for token in keyword_analysis_forbidden
        )
    )
    keyword_validation_depends_on_producer_or_lowerer=bool(
        keyword_validation.exists()
        and any(
            token in keyword_validation.read_text(encoding="utf-8")
            for token in keyword_validation_forbidden
        )
    )
    if not all(
        path.exists() for path in (keyword_analysis,keyword_validation,keyword_lowering)
    ):
        violations.append("missing separated Phase 14C keyword analysis/validation/lowering boundary")
    if keyword_analysis_depends_on_c_ir:
        violations.append("keyword-call analysis depends on C IR, rendering, or keyword lowering")
    if keyword_validation_depends_on_producer_or_lowerer:
        violations.append("keyword-call validation depends on C IR, producer analysis, or lowering")
    keyword_only_analysis=root/"pycforge"/"converter"/"keyword_only_calls"/"analysis.py"
    keyword_only_validation=root/"pycforge"/"converter"/"keyword_only_calls"/"validation.py"
    keyword_only_lowering=root/"pycforge"/"converter"/"keyword_only_calls"/"lowering.py"
    keyword_only_analysis_depends_on_c_ir=bool(
        keyword_only_analysis.exists()
        and any(
            token in keyword_only_analysis.read_text(encoding="utf-8")
            for token in ("ir.c_ir","CRenderer","CTranslationUnitBuilder","keyword_only_calls.lowering","from .lowering")
        )
    )
    keyword_only_validation_depends_on_producer_or_lowerer=bool(
        keyword_only_validation.exists()
        and any(
            token in keyword_only_validation.read_text(encoding="utf-8")
            for token in ("ir.c_ir","CRenderer","CTranslationUnitBuilder","KeywordOnlyCallAnalyzer","KeywordOnlyCallCIRLowerer","from .analysis","from .lowering")
        )
    )
    if not all(path.exists() for path in (keyword_only_analysis,keyword_only_validation,keyword_only_lowering)):
        violations.append("missing separated Phase 14D keyword-only analysis/validation/lowering boundary")
    if keyword_only_analysis_depends_on_c_ir:
        violations.append("keyword-only analysis depends on C IR, rendering, or lowering")
    if keyword_only_validation_depends_on_producer_or_lowerer:
        violations.append("keyword-only validation depends on C IR, producer analysis, or lowering")
    active_contracts={
        "rule_set":DEFAULT_RULE_SET,
        "renderer":DEFAULT_RENDERER,
        "keyword_call_facts":KEYWORD_CALL_FACT_SCHEMA,
        "keyword_only_call_facts":KEYWORD_ONLY_CALL_FACT_SCHEMA,
        "conversion_plan":CONVERSION_PLAN_SCHEMA,
        "c_ir":C_IR_SCHEMA,
        "generated_c":GENERATED_C_SCHEMA,
    }
    active_contracts_valid=active_contracts=={
        "rule_set":"phase14-required-keyword-only-calls-v0.14.3",
        "renderer":"c-renderer-v0.14.3",
        "keyword_call_facts":"fact-table/0.14.2",
        "keyword_only_call_facts":"fact-table/0.14.3",
        "conversion_plan":"conversion-plan/0.14.3",
        "c_ir":"c-ir/0.14.3",
        "generated_c":"generated-c/0.14.3",
    }
    keyword_contract_valid=(
        KEYWORD_CALL_RULE_ID=="phase14.keyword_call.exact_binding"
        and KEYWORD_CALL_FACT_SCHEMA=="fact-table/0.14.2"
        and KEYWORD_ONLY_CALL_RULE_ID=="phase14.keyword_only_call.exact_binding"
        and KEYWORD_ONLY_CALL_FACT_SCHEMA=="fact-table/0.14.3"
    )
    if not active_contracts_valid:
        violations.append("active Phase 14D architecture identities are inconsistent")
    if not keyword_contract_valid:
        violations.append("Phase 14C keyword rule or fact identity is inconsistent")
    return {
        "audit":"architecture",
        "passed":not violations,
        "violations":violations,
        "record_analysis_present":record_analysis.is_file(),
        "record_lowering_present":record_lowering.is_file(),
        "record_analysis_depends_on_c_ir":bool(
            record_analysis.exists()
            and any(
                token in record_analysis.read_text(encoding="utf-8")
                for token in ("ir.c_ir", "CRenderer", "CTranslationUnitBuilder")
            )
        ),
        "numeric_analysis_present":numeric_analysis.is_file(),
        "numeric_lowering_present":numeric_lowering.is_file(),
        "numeric_analysis_depends_on_c_ir":bool(
            numeric_analysis.exists()
            and any(
                token in numeric_analysis.read_text(encoding="utf-8")
                for token in ("ir.c_ir", "CRenderer", "CTranslationUnitBuilder")
            )
        ),
        "conditional_analysis_present":conditional_analysis.is_file(),
        "conditional_validation_present":conditional_validation.is_file(),
        "conditional_lowering_present":conditional_lowering.is_file(),
        "conditional_analysis_depends_on_c_ir":conditional_analysis_depends_on_c_ir,
        "conditional_validation_depends_on_producer_or_lowerer":conditional_validation_depends_on_producer_or_lowerer,
        "keyword_analysis_present":keyword_analysis.is_file(),
        "keyword_validation_present":keyword_validation.is_file(),
        "keyword_lowering_present":keyword_lowering.is_file(),
        "keyword_analysis_depends_on_c_ir":keyword_analysis_depends_on_c_ir,
        "keyword_validation_depends_on_producer_or_lowerer":keyword_validation_depends_on_producer_or_lowerer,
        "keyword_only_analysis_present":keyword_only_analysis.is_file(),
        "keyword_only_validation_present":keyword_only_validation.is_file(),
        "keyword_only_lowering_present":keyword_only_lowering.is_file(),
        "keyword_only_analysis_depends_on_c_ir":keyword_only_analysis_depends_on_c_ir,
        "keyword_only_validation_depends_on_producer_or_lowerer":keyword_only_validation_depends_on_producer_or_lowerer,
        "keyword_rule_id":KEYWORD_CALL_RULE_ID,
        "keyword_fact_schema":KEYWORD_CALL_FACT_SCHEMA,
        "keyword_only_rule_id":KEYWORD_ONLY_CALL_RULE_ID,
        "keyword_only_fact_schema":KEYWORD_ONLY_CALL_FACT_SCHEMA,
        "keyword_contract_valid":keyword_contract_valid,
        "active_contracts":active_contracts,
        "active_contract_identities_valid":active_contracts_valid,
        "cumulative_lowerer_lines":len(cumulative_lowerer.read_text(encoding="utf-8").splitlines()) if cumulative_lowerer.exists() else None,
    }

def audit_rules(root: Path) -> dict[str, Any]:
    from pycforge.converter.contracts.configuration import (
        DEFAULT_RENDERER,
        DEFAULT_RULE_SET,
        supports_conditional_regions,
        supports_keyword_calls,
        supports_keyword_only_calls,
        supports_numeric,
        supports_records,
    )
    from pycforge.converter.contracts.versions import (
        C_IR_SCHEMA,
        CONDITIONAL_FACT_SCHEMA,
        CONVERSION_PLAN_SCHEMA,
        CONVERSION_SUMMARY_SCHEMA,
        DECISION_TRACE_SCHEMA,
        GENERATED_C_SCHEMA,
        KEYWORD_CALL_FACT_SCHEMA,
        KEYWORD_ONLY_CALL_FACT_SCHEMA,
    )
    from pycforge.converter.analysis.planning import default_registry
    try:
        active_records=supports_records(DEFAULT_RULE_SET)
        active_numeric=supports_numeric(DEFAULT_RULE_SET)
        active_conditional=supports_conditional_regions(DEFAULT_RULE_SET)
        active_keyword_calls=supports_keyword_calls(DEFAULT_RULE_SET)
        active_keyword_only_calls=supports_keyword_only_calls(DEFAULT_RULE_SET)
        manifest=default_registry(
            include_records=active_records,
            include_numeric=active_numeric,
            include_conditional_regions=active_conditional,
            include_keyword_calls=active_keyword_calls,
            include_keyword_only_calls=active_keyword_only_calls,
        ).manifest
        identities=[(item["rule_id"],item["rule_version"]) for item in manifest]
        phase9={"phase9.call.understood_target"}
        phase11={
            "phase11.container.list_literal",
            "phase11.container.tuple_literal",
            "phase11.container.dict_literal",
            "phase11.container.index.proved",
            "phase11.container.for.bounded",
            "phase11.container.assignment",
            "phase11.container.name",
        }
        phase12={
            "phase12.module.document",
            "phase12.module.import_from",
            "phase12.module.imported_binding",
            "phase12.module.function_namespace",
            "phase12.module.cross_call",
            "phase12.module.initialization",
            "phase12.module.bundle_assembly",
        }
        phase13={
            "phase13.record.class",
            "phase13.record.field",
            "phase13.record.initializer",
            "phase13.record.construction",
            "phase13.record.binding",
            "phase13.record.name",
            "phase13.record.attribute_read",
        }
        phase14={"phase14.numeric.floor_arithmetic"}
        phase14b={
            "phase14.conditional.boolean_region",
            "phase14.conditional.comparison_region",
        }
        phase14c={"phase14.keyword_call.exact_binding"}
        phase14d={"phase14.keyword_only_call.exact_binding"}
        declared={item["rule_id"] for item in manifest}
        active_identities={
            "rule_set":DEFAULT_RULE_SET,
            "renderer":DEFAULT_RENDERER,
            "conditional_facts":CONDITIONAL_FACT_SCHEMA,
            "keyword_call_facts":KEYWORD_CALL_FACT_SCHEMA,
            "keyword_only_call_facts":KEYWORD_ONLY_CALL_FACT_SCHEMA,
            "conversion_plan":CONVERSION_PLAN_SCHEMA,
            "c_ir":C_IR_SCHEMA,
            "generated_c":GENERATED_C_SCHEMA,
            "conversion_summary":CONVERSION_SUMMARY_SCHEMA,
            "decision_trace":DECISION_TRACE_SCHEMA,
        }
        identities_valid=active_identities=={
            "rule_set":"phase14-required-keyword-only-calls-v0.14.3",
            "renderer":"c-renderer-v0.14.3",
            "conditional_facts":"fact-table/0.14.1",
            "keyword_call_facts":"fact-table/0.14.2",
            "keyword_only_call_facts":"fact-table/0.14.3",
            "conversion_plan":"conversion-plan/0.14.3",
            "c_ir":"c-ir/0.14.3",
            "generated_c":"generated-c/0.14.3",
            "conversion_summary":"pycforge.conversion-summary/0.14.3",
            "decision_trace":"pycforge.decision-trace/0.14.3",
        }
        passed=(
            len(identities)==len(set(identities))
            and len(manifest)>0
            and active_records
            and phase9.issubset(declared)
            and phase11.issubset(declared)
            and phase12.issubset(declared)
            and phase13.issubset(declared)
            and active_numeric
            and phase14.issubset(declared)
            and active_conditional
            and phase14b.issubset(declared)
            and active_keyword_calls
            and phase14c.issubset(declared)
            and active_keyword_only_calls
            and phase14d.issubset(declared)
            and identities_valid
        )
        return {
            "audit":"rules",
            "passed":passed,
            "active_rule_set":DEFAULT_RULE_SET,
            "active_registry_includes_records":active_records,
            "active_registry_includes_numeric":active_numeric,
            "active_registry_includes_conditional_regions":active_conditional,
            "active_registry_includes_keyword_calls":active_keyword_calls,
            "active_registry_includes_keyword_only_calls":active_keyword_only_calls,
            "active_contracts":active_identities,
            "active_contract_identities_valid":identities_valid,
            "rule_count":len(manifest),
            "manifest":list(manifest),
            "phase9_required_rules":sorted(phase9),
            "missing_phase9_rules":sorted(phase9-declared),
            "phase11_required_rules":sorted(phase11),
            "missing_phase11_rules":sorted(phase11-declared),
            "phase12_required_rules":sorted(phase12),
            "missing_phase12_rules":sorted(phase12-declared),
            "phase13_required_rules":sorted(phase13),
            "missing_phase13_rules":sorted(phase13-declared),
            "phase14_required_rules":sorted(phase14),
            "missing_phase14_rules":sorted(phase14-declared),
            "phase14b_required_rules":sorted(phase14b),
            "missing_phase14b_rules":sorted(phase14b-declared),
            "phase14c_required_rules":sorted(phase14c),
            "missing_phase14c_rules":sorted(phase14c-declared),
            "phase14d_required_rules":sorted(phase14d),
            "missing_phase14d_rules":sorted(phase14d-declared),
            "notes":[
                "Registry is frozen and sorted.",
                "Duplicate identities and equal-specificity overlaps reject at registry construction.",
                "The active cumulative registry includes the sealed Phase 14C keyword rule and one bounded Phase 14D required-keyword-only rule.",
            ],
        }
    except Exception as exc:
        return {"audit":"rules","passed":False,"rule_count":0,"error":str(exc)}

def audit_helpers(root: Path) -> dict[str, Any]:
    from pycforge.converter.support_templates import (
        FLOOR_DIV_REFERENCE,
        FLOOR_MOD_REFERENCE,
        FrozenHelperRegistry,
        builtin_definitions,
        default_helper_registry,
    )
    try:
        registry=default_helper_registry()
        reversed_registry=FrozenHelperRegistry(reversed(builtin_definitions()))
        references=[item["reference"] for item in registry.manifest]
        required=[FLOOR_DIV_REFERENCE.canonical,FLOOR_MOD_REFERENCE.canonical]
        plan=registry.resolve(required,target_contract="c11-portable-fixed-v1")
        fixture_names={
            FLOOR_DIV_REFERENCE.canonical:"pycf_i64_floor_div_v1.c",
            FLOOR_MOD_REFERENCE.canonical:"pycf_i64_floor_mod_v1.c",
        }
        golden_sha256={
            FLOOR_DIV_REFERENCE.canonical:"7d65353f363a713545180525d42d81f12beba69bf2a39654c6d1645089f62803",
            FLOOR_MOD_REFERENCE.canonical:"f8ee68c91b353542dd856ea2af72b0523a103a717eb35de808ec811ef4663b21",
        }
        golden_mismatches=[]
        golden_fixture_files_present=True
        for reference,name in fixture_names.items():
            path=root/"fixtures"/"support_templates"/name
            rendered=registry.rendered_asset(reference)
            if hashlib.sha256(rendered.encode("utf-8")).hexdigest() != golden_sha256[reference]:
                golden_mismatches.append(name)
            elif path.is_file() and path.read_text(encoding="utf-8") != rendered:
                golden_mismatches.append(name)
            elif not path.is_file():
                golden_fixture_files_present=False
        passed=(
            references==required
            and registry.manifest==reversed_registry.manifest
            and registry.fingerprint==reversed_registry.fingerprint
            and [item.reference.canonical for item in plan.manifest]==required
            and not golden_mismatches
        )
        return {
            "audit":"helpers",
            "passed":passed,
            "registry_version":registry.registry_version,
            "registry_fingerprint":registry.fingerprint,
            "helper_count":len(references),
            "helpers":references,
            "resolved_manifest_fingerprint":plan.manifest_fingerprint,
            "golden_mismatches":golden_mismatches,
            "golden_fixture_files_present":golden_fixture_files_present,
            "raw_text_ingestion_supported":False,
            "generated_c_compiled_or_executed":False,
        }
    except Exception as exc:
        return {"audit":"helpers","passed":False,"helper_count":0,"error":f"{type(exc).__name__}: {exc}"}

def audit_transition(root: Path, phase: str) -> dict[str, Any]:
    base=root/"transition"/phase
    promoted={"phase_9","phase_10","phase_11","phase_12","phase_13","phase_14","phase_14d"}
    if phase == "phase_14b":
        required={
            "baseline_fingerprint.json",
            "breadth_and_change_budgets.md",
            "conditional_temporary_regions_decision.md",
            "entry_criteria.md",
            "opening_evidence.md",
            "rollback_conditions.md",
        }
    else:
        required={"manifest.json","baseline_fingerprint.json","entry_criteria.md","gate_evidence.md","rollback_conditions.md"} if phase in promoted else {"manifest.json","baseline_fingerprint.json"}
    if phase == "phase_13":
        required.update(
            {
                "candidate_reseed.md",
                "record_representation_decisions.md",
                "release_fingerprint.json",
            }
        )
    if phase == "phase_14":
        required.update(
            {
                "breadth_and_change_budgets.md",
                "integer_divmod_decision.md",
                "opening_evidence.md",
                "release_fingerprint.json",
            }
        )
    if phase == "phase_14d":
        required.update(
            {
                "breadth_and_change_budgets.md",
                "opening_evidence.md",
                "release_fingerprint.json",
                "required_keyword_only_calls_decision.md",
            }
        )
    missing=sorted(name for name in required if not (base/name).exists())
    manifest_error=None
    opening_error=None
    authenticated_predecessor_tests=None
    required_tests=None
    if not missing and phase == "phase_14b":
        try:
            baseline=json.loads((base/"baseline_fingerprint.json").read_text(encoding="utf-8"))
            predecessor=baseline.get("predecessor")
            sealed=baseline.get("sealed_release_evidence")
            authentication=baseline.get("authentication")
            authenticated_predecessor_tests=sealed.get("tests_discovered") if isinstance(sealed,dict) else None
            if (
                baseline.get("schema_version")!="pycforge.phase14b-opening-baseline/0.14.1"
                or baseline.get("phase")!=14
                or baseline.get("mini_phase")!="14B"
                or not isinstance(predecessor,dict)
                or predecessor.get("version")!="0.14.0"
                or predecessor.get("source_archive_size")!=1016512
                or predecessor.get("source_archive_sha256")!="d4fe065d168241b4371901e19eda346c38835c1d2ac07e3870f27abb5a7b3917"
                or predecessor.get("canonical_release_tree_sha256")!="6eb034b63d4f08b8ea6de08fd38e507d12d4fc2436f0d3a68443624fc4c05d76"
                or predecessor.get("converter_subtree_sha256")!="ccb92a82741202569e4639342e6ae711c246e2122a689f7831715ee182596c2d"
                or authenticated_predecessor_tests!=365
                or not isinstance(authentication,dict)
                or authentication.get("source_archive_digest_matched") is not True
                or authentication.get("archive_canonical_tree_recomputed") is not True
                or authentication.get("archive_tree_matched_promoted_release_fingerprint") is not True
                or authentication.get("archive_converter_subtree_recomputed") is not True
                or authentication.get("compiler_linker_loader_or_execution_invoked") is not False
            ):
                opening_error="Phase 14B opening baseline or predecessor authentication is invalid"
        except (OSError,json.JSONDecodeError,AttributeError,TypeError) as exc:
            opening_error=f"unreadable opening baseline: {type(exc).__name__}"
    if not missing and phase in promoted:
        try:
            manifest=json.loads((base/"manifest.json").read_text(encoding="utf-8"))
            expected_phase={"phase_9":9,"phase_10":10,"phase_11":11,"phase_12":12,"phase_13":13,"phase_14":14,"phase_14d":14}[phase]
            expected_version={"phase_9":"0.9.0","phase_10":"0.10.0","phase_11":"0.11.0","phase_12":"0.12.0","phase_13":"0.13.0","phase_14":"0.14.0","phase_14d":"0.14.3"}[phase]
            minimum_tests={"phase_9":92,"phase_10":154,"phase_11":169,"phase_12":189,"phase_13":224,"phase_14":335,"phase_14d":528}[phase]
            required_tests=manifest.get("required_tests")
            if manifest.get("phase") != expected_phase or manifest.get("version") != expected_version or type(required_tests) is not int or required_tests < minimum_tests:
                manifest_error=f"Phase {expected_phase} manifest identity or regression count is invalid"
            if phase == "phase_13" and manifest_error is None:
                required_schemas={
                    "record_facts":"fact-table/0.13",
                    "conversion_plan":"conversion-plan/0.13",
                    "c_ir":"c-ir/0.13",
                    "generated_c":"generated-c/0.13",
                    "rule_set":"phase13-static-records-v0.13",
                    "renderer":"c-renderer-v0.13",
                    "module_policy":"phase13-explicit-record-modules-v0.13",
                    "record_policy":"phase13-immutable-automatic-records-v0.13",
                }
                schemas=manifest.get("schemas")
                if not isinstance(schemas,dict) or any(schemas.get(key) != value for key,value in required_schemas.items()):
                    manifest_error="Phase 13 manifest contract identities are invalid"
            if phase == "phase_14" and manifest_error is None:
                required_schemas={
                    "numeric_facts":"fact-table/0.14",
                    "conversion_plan":"conversion-plan/0.14",
                    "c_ir":"c-ir/0.14",
                    "generated_c":"generated-c/0.14",
                    "conversion_summary":"pycforge.conversion-summary/0.14",
                    "decision_trace":"pycforge.decision-trace/0.14",
                    "rule_set":"phase14-bounded-numeric-v0.14",
                    "renderer":"c-renderer-v0.14",
                    "numeric_policy":"phase14-proved-floor-arithmetic-v0.14",
                }
                schemas=manifest.get("schemas")
                if not isinstance(schemas,dict) or any(schemas.get(key) != value for key,value in required_schemas.items()):
                    manifest_error="Phase 14A manifest contract identities are invalid"
            if phase == "phase_14d" and manifest_error is None:
                required_schemas={
                    "keyword_call_facts":"fact-table/0.14.2",
                    "keyword_only_call_facts":"fact-table/0.14.3",
                    "conversion_plan":"conversion-plan/0.14.3",
                    "c_ir":"c-ir/0.14.3",
                    "generated_c":"generated-c/0.14.3",
                    "conversion_summary":"pycforge.conversion-summary/0.14.3",
                    "decision_trace":"pycforge.decision-trace/0.14.3",
                    "rule_set":"phase14-required-keyword-only-calls-v0.14.3",
                    "renderer":"c-renderer-v0.14.3",
                }
                schemas=manifest.get("schemas")
                if (
                    manifest.get("schema_version")!="pycforge.phase14d-manifest/0.14.3"
                    or manifest.get("mini_phase")!="14D"
                    or not isinstance(schemas,dict)
                    or any(schemas.get(key) != value for key,value in required_schemas.items())
                ):
                    manifest_error="Phase 14D manifest contract identities are invalid"
        except (OSError,json.JSONDecodeError,AttributeError,TypeError) as exc:
            manifest_error=f"unreadable manifest: {type(exc).__name__}"
    result={
        "audit":"transition",
        "phase":phase,
        "passed":not missing and manifest_error is None and opening_error is None,
        "required_files":sorted(required),
        "missing":missing,
        "required_tests":required_tests,
        "minimum_tests":528 if phase == "phase_14d" else 335 if phase == "phase_14" else 224 if phase == "phase_13" else None,
        "manifest_error":manifest_error,
    }
    if phase == "phase_14b":
        result.update(
            {
                "opening_status":"entry-feasibility-only",
                "opening_error":opening_error,
                "authenticated_predecessor_tests":authenticated_predecessor_tests,
                "manifest_required":False,
                "promotion_claimed":False,
            }
        )
    return result

def audit_containers(root: Path) -> dict[str, Any]:
    from pycforge import ConversionRequest, PythonToCConverter, ResultStatus
    from pycforge.converter.c_output import validate_c_text
    from pycforge.converter.contracts.configuration import DEFAULT_RENDERER, DEFAULT_RULE_SET
    from pycforge.converter.contracts.versions import (
        C_IR_SCHEMA,
        CONVERSION_PLAN_SCHEMA,
        GENERATED_C_SCHEMA,
        KEYWORD_CALL_FACT_SCHEMA,
        KEYWORD_ONLY_CALL_FACT_SCHEMA,
    )
    from pycforge.converter.support_templates import default_helper_registry

    converter=PythonToCConverter()
    accepted_sources={
        "list-index":"def f() -> int:\n    values = [1, 2]\n    return values[-1]\n",
        "tuple-loop":"def f() -> int:\n    values = (1, 2)\n    total = 0\n    for value in values:\n        total = total + value\n    return total\n",
        "dict-lookup":"def f() -> int:\n    values = {\"a\": 1, \"b\": 2}\n    return values[\"b\"]\n",
    }
    rejection_sources={
        "PYC3401":"def f() -> int:\n    values = []\n    return 1\n",
        "PYC3402":"def f() -> int:\n    values = [1, 2.0]\n    return 1\n",
        "PYC3403":"def f() -> int:\n    values = [1]\n    alias = values\n    return 1\n",
        "PYC3404":"def f(i: int) -> int:\n    values = [1]\n    return values[i]\n",
        "PYC3405":"def f() -> int:\n    values = [1]\n    return values[2]\n",
        "PYC3406":"def f() -> int:\n    values = [1]\n    values[0] = 2\n    return 1\n",
        "PYC3407":"def f() -> int:\n    total = 0\n    for value in [1]:\n        total = total + value\n    return total\n",
    }
    accepted={name:converter.convert(ConversionRequest.from_source(source)) for name,source in accepted_sources.items()}
    rejected={code:converter.convert(ConversionRequest.from_source(source)) for code,source in rejection_sources.items()}
    required_tables={"container-shape-facts","container-binding-facts","container-access-facts","container-iteration-facts"}
    active_contracts={
        "rule_set":DEFAULT_RULE_SET,
        "renderer":DEFAULT_RENDERER,
        "keyword_call_facts":KEYWORD_CALL_FACT_SCHEMA,
        "keyword_only_call_facts":KEYWORD_ONLY_CALL_FACT_SCHEMA,
        "conversion_plan":CONVERSION_PLAN_SCHEMA,
        "c_ir":C_IR_SCHEMA,
        "generated_c":GENERATED_C_SCHEMA,
    }
    active_contracts_valid=active_contracts=={
        "rule_set":"phase14-required-keyword-only-calls-v0.14.3",
        "renderer":"c-renderer-v0.14.3",
        "keyword_call_facts":"fact-table/0.14.2",
        "keyword_only_call_facts":"fact-table/0.14.3",
        "conversion_plan":"conversion-plan/0.14.3",
        "c_ir":"c-ir/0.14.3",
        "generated_c":"generated-c/0.14.3",
    }
    accepted_identity_ok=all(
        result.stage_artifact is not None
        and result.stage_artifact.schema_version=="0.14.3"
        and result.stage_artifact.payload.get("schema_version")==GENERATED_C_SCHEMA
        and result.stage_artifact.payload.get("c_ir_schema")==C_IR_SCHEMA
        and result.stage_artifact.payload.get("rule_set_version")==DEFAULT_RULE_SET
        and result.stage_artifact.payload.get("renderer_version")==DEFAULT_RENDERER
        and len([
            table for table in result.stage_artifact.payload.get("fact_tables",())
            if table.get("table_id")=="keyword-call-binding-facts"
            and table.get("schema_version")==KEYWORD_CALL_FACT_SCHEMA
            and table.get("records")==[]
        ])==1
        and len([
            table for table in result.stage_artifact.payload.get("fact_tables",())
            if table.get("table_id")=="keyword-only-call-binding-facts"
            and table.get("schema_version")==KEYWORD_ONLY_CALL_FACT_SCHEMA
            and table.get("records")==[]
        ])==1
        for result in accepted.values()
    )
    accepted_ok=all(
        result.status is ResultStatus.CONVERTED
        and result.generated_c is not None
        and validate_c_text(result.generated_c).accepted
        and result.stage_artifact.payload.get("c_ir_schema") == C_IR_SCHEMA
        and required_tables.issubset({item["table_id"] for item in result.stage_artifact.payload.get("fact_tables",())})
        and not result.stage_artifact.payload.get("helper_manifest")
        for result in accepted.values()
    )
    rejected_ok=all(
        result.status is ResultStatus.REJECTED
        and result.generated_c is None
        and [item.code for item in result.diagnostics]==[code]
        and not result.stage_artifact.payload.get("helper_manifest")
        for code,result in rejected.items()
    )
    registry=default_helper_registry()
    helper_stable=(
        registry.fingerprint=="fcb719f07984f3b79e17262e90f93823a9a0139a60529f8486ab09f6c3663d98"
    )
    return {
        "audit":"containers",
        "passed":accepted_ok and rejected_ok and helper_stable and active_contracts_valid and accepted_identity_ok,
        "active_contracts":active_contracts,
        "active_contract_identities_valid":active_contracts_valid and accepted_identity_ok,
        "active_c_ir_schema":C_IR_SCHEMA,
        "historical_c_ir_schemas":["c-ir/0.11","c-ir/0.12"],
        "accepted_forms":sorted(accepted),
        "rejection_codes":sorted(rejected),
        "capacity_limit":64,
        "allocation":"none",
        "cleanup":"not-required",
        "aliasing":"rejected",
        "runtime_bounds_or_hash_failure_channel":"none; statically proved",
        "helper_manifest_empty":all(not item.stage_artifact.payload.get("helper_manifest") for item in (*accepted.values(),*rejected.values())),
        "phase10_helper_registry_fingerprint_preserved":helper_stable,
        "generated_c_compiled_or_executed":False,
    }


def audit_modules(root: Path) -> dict[str, Any]:
    from pycforge import ConversionRequest, PythonToCConverter, ResultStatus, SourceBundle, SourceDocumentInput
    from pycforge.converter.contracts.configuration import DEFAULT_RENDERER, DEFAULT_RULE_SET
    from pycforge.converter.contracts.versions import (
        C_IR_SCHEMA,
        CONVERSION_PLAN_SCHEMA,
        GENERATED_C_SCHEMA,
        KEYWORD_CALL_FACT_SCHEMA,
        KEYWORD_ONLY_CALL_FACT_SCHEMA,
    )
    from pycforge.converter.core.resource_policy import ResourcePolicy

    def request(primary_text: str, companions: tuple[tuple[str, str, str], ...] = (), *, primary_module: str = "app", policy: ResourcePolicy | None = None) -> ConversionRequest:
        return ConversionRequest(
            SourceBundle(
                SourceDocumentInput("app.py", primary_text, primary_module),
                tuple(SourceDocumentInput(logical, text, module_id) for module_id, logical, text in companions),
            ),
            resource_policy=policy or ResourcePolicy(),
        )

    converter=PythonToCConverter()
    accepted=converter.convert(request(
        "from lib.math import increment as inc\n\ndef run(value: int) -> int:\n    return inc(value)\n",
        (("lib.math","lib/math.py","def increment(value: int) -> int:\n    return value + 1\n"),),
    ))

    def kind_count(value: Any, kind: str) -> int:
        if isinstance(value,dict):
            return (1 if value.get("kind")==kind else 0)+sum(kind_count(item,kind) for item in value.values())
        if isinstance(value,(list,tuple)):
            return sum(kind_count(item,kind) for item in value)
        return 0

    payload=accepted.stage_artifact.payload if accepted.stage_artifact else {}
    active_contracts={
        "rule_set":DEFAULT_RULE_SET,
        "renderer":DEFAULT_RENDERER,
        "keyword_call_facts":KEYWORD_CALL_FACT_SCHEMA,
        "keyword_only_call_facts":KEYWORD_ONLY_CALL_FACT_SCHEMA,
        "conversion_plan":CONVERSION_PLAN_SCHEMA,
        "c_ir":C_IR_SCHEMA,
        "generated_c":GENERATED_C_SCHEMA,
    }
    active_contracts_valid=active_contracts=={
        "rule_set":"phase14-required-keyword-only-calls-v0.14.3",
        "renderer":"c-renderer-v0.14.3",
        "keyword_call_facts":"fact-table/0.14.2",
        "keyword_only_call_facts":"fact-table/0.14.3",
        "conversion_plan":"conversion-plan/0.14.3",
        "c_ir":"c-ir/0.14.3",
        "generated_c":"generated-c/0.14.3",
    }
    accepted_identity_ok=bool(
        accepted.stage_artifact is not None
        and accepted.stage_artifact.schema_version=="0.14.3"
        and payload.get("schema_version")==GENERATED_C_SCHEMA
        and payload.get("c_ir_schema")==C_IR_SCHEMA
        and payload.get("rule_set_version")==DEFAULT_RULE_SET
        and payload.get("renderer_version")==DEFAULT_RENDERER
        and len([
            table for table in payload.get("fact_tables",())
            if table.get("table_id")=="keyword-call-binding-facts"
            and table.get("schema_version")==KEYWORD_CALL_FACT_SCHEMA
            and table.get("records")==[]
        ])==1
        and len([
            table for table in payload.get("fact_tables",())
            if table.get("table_id")=="keyword-only-call-binding-facts"
            and table.get("schema_version")==KEYWORD_ONLY_CALL_FACT_SCHEMA
            and table.get("records")==[]
        ])==1
    )
    c_ir=payload.get("c_ir",{})
    c_ir_manifest=c_ir.get("module_manifest",())
    table_ids={item.get("table_id") for item in payload.get("fact_tables",())}
    required_tables={
        "module-identity-facts","module-import-facts","module-function-facts",
        "module-initialization-facts","module-namespace-facts","module-source-facts",
    }
    rule_ids={item.get("rule_id") for item in payload.get("rule_plans",())}
    mappings=payload.get("source_output_mappings",())
    accepted_ok=bool(
        accepted.status is ResultStatus.CONVERTED
        and accepted.generated_c
        and payload.get("c_ir_schema")==C_IR_SCHEMA
        and kind_count(c_ir,"CTranslationUnit")==1
        and c_ir.get("module_order")==["lib.math","app"]
        and c_ir.get("module_dependencies")==[["app","lib.math"]]
        and [item.get("module_id") for item in c_ir_manifest]==["lib.math","app"]
        and sorted(item.get("bundle_ordinal") for item in c_ir_manifest)==[0,1]
        and sum(item.get("is_primary") is True for item in c_ir_manifest)==1
        and required_tables.issubset(table_ids)
        and "phase12.module.import_from" in rule_ids
        and "phase12.module.cross_call" in rule_ids
        and not payload.get("helper_manifest")
        and all(
            item.get("storage")=="none"
            and item.get("owner_module_id") in {"app","lib.math"}
            and item.get("owner_document_id")
            and isinstance(item.get("bundle_function_ordinal"),int)
            for item in _kind_dicts(c_ir,{"CFunctionPrototype","CFunctionDefinition"})
            if item.get("provenance",{}).get("origin_kind")!="support-template"
        )
        and {item.get("module_id") for item in mappings if item.get("source_document_id")} >= {"app","lib.math"}
    )

    negative_requests={
        "PYC3501":ConversionRequest(SourceBundle(SourceDocumentInput("app.py","def f() -> int:\n    return 1\n","Bad"))),
        "PYC3502":request("def f() -> int:\n    return 1\n",(("app","other.py","def g() -> int:\n    return 2\n"),)),
        "PYC3503":request("from absent import f\n\ndef run() -> int:\n    return f()\n"),
        "PYC3504":request("import lib\n\ndef run() -> int:\n    return 1\n",(("lib","lib.py","def f() -> int:\n    return 1\n"),)),
        "PYC3505":request("from lib import absent\n\ndef run() -> int:\n    return 1\n",(("lib","lib.py","def present() -> int:\n    return 1\n"),)),
        "PYC3506":request("from lib import f as run\n\ndef run() -> int:\n    return 1\n",(("lib","lib.py","def f() -> int:\n    return 1\n"),)),
        "PYC3507":request("from lib import f\n\ndef run() -> int:\n    return f()\n",(("lib","lib.py","from app import run\n\ndef f() -> int:\n    return run()\n"),)),
        "PYC3508":request("from pkg import child\n\ndef run() -> int:\n    return 1\n",(("pkg.child","pkg/child.py","def child() -> int:\n    return 1\n"),)),
        "PYC3509":request("value = 1\n\ndef run() -> int:\n    return value\n"),
        "PYC3510":request("from lib import f\n\ndef run() -> int:\n    return f()\n",(("lib","lib.py","def f() -> int:\n    return 1\n"),),policy=ResourcePolicy(max_import_edges=0)),
    }
    rejected={code:converter.convert(item) for code,item in negative_requests.items()}
    rejected_ok=all(
        result.status is ResultStatus.REJECTED
        and result.generated_c is None
        and [item.code for item in result.diagnostics]==[code]
        and not (result.stage_artifact and result.stage_artifact.payload.get("c_ir"))
        and not (result.stage_artifact and result.stage_artifact.payload.get("helper_manifest"))
        for code,result in rejected.items()
    )
    return {
        "audit":"modules",
        "passed":accepted_ok and rejected_ok and active_contracts_valid and accepted_identity_ok,
        "active_contracts":active_contracts,
        "active_contract_identities_valid":active_contracts_valid and accepted_identity_ok,
        "active_c_ir_schema":C_IR_SCHEMA,
        "historical_c_ir_schema":"c-ir/0.12",
        "accepted_forms":["absolute-from-import","aliased-from-import","single-translation-unit"],
        "rejection_codes":sorted(rejected),
        "document_limit":64,
        "import_edge_limit":4096,
        "resolution":"explicit-sourcebundle-only",
        "runtime_initialization":"none",
        "translation_unit_count":1 if accepted_ok else None,
        "generated_c_compiled_or_executed":False,
    }


def audit_records(root: Path) -> dict[str, Any]:
    """Audit the complete Phase 13 record slice without invoking a C toolchain."""
    from pycforge import (
        ConversionRequest,
        PythonToCConverter,
        ResultStatus,
        SourceBundle,
        SourceDocumentInput,
    )
    from pycforge.converter.c_output import validate_c_text
    from pycforge.converter.contracts.configuration import DEFAULT_RENDERER, DEFAULT_RULE_SET
    from pycforge.converter.contracts.versions import (
        C_IR_SCHEMA,
        CONVERSION_PLAN_SCHEMA,
        GENERATED_C_SCHEMA,
        KEYWORD_CALL_FACT_SCHEMA,
        KEYWORD_ONLY_CALL_FACT_SCHEMA,
        RECORD_FACT_SCHEMA,
    )

    accepted_source=(
        "class Sample:\n"
        "    count: int\n"
        "    ratio: float\n"
        "    enabled: bool\n"
        "    def __init__(self, count: int, ratio: float, enabled: bool) -> None:\n"
        "        self.count = count\n"
        "        self.ratio = ratio\n"
        "        self.enabled = enabled\n"
        "\n"
        "def read_count(count: int, ratio: float, enabled: bool) -> int:\n"
        "    sample = Sample(count, ratio, enabled)\n"
        "    return sample.count\n"
        "\n"
        "def read_ratio(count: int, ratio: float, enabled: bool) -> float:\n"
        "    sample = Sample(count, ratio, enabled)\n"
        "    return sample.ratio\n"
        "\n"
        "def read_enabled(count: int, ratio: float, enabled: bool) -> bool:\n"
        "    sample = Sample(count, ratio, enabled)\n"
        "    return sample.enabled\n"
    )
    base=(
        "class Point:\n"
        "    x: int\n"
        "    y: int\n"
        "    def __init__(self, x: int, y: int) -> None:\n"
        "        self.x = x\n"
        "        self.y = y\n"
    )
    rejection_sources={
        "PYC3601":(
            "class Point(Base):\n"
            "    x: int\n"
            "    def __init__(self, x: int) -> None:\n"
            "        self.x = x\n"
            "\ndef run() -> int:\n    return 1\n"
        ),
        "PYC3602":(
            "class Point:\n"
            "    x: str\n"
            "    def __init__(self, x: str) -> None:\n"
            "        self.x = x\n"
            "\ndef run() -> int:\n    return 1\n"
        ),
        "PYC3603":base.replace(
            "        self.x = x\n        self.y = y\n",
            "        self.y = y\n        self.x = x\n",
        )+"\ndef run() -> int:\n    return 1\n",
        "PYC3604":base+(
            "    def total(self) -> int:\n"
            "        return self.x + self.y\n"
            "\ndef run() -> int:\n    return 1\n"
        ),
        "PYC3605":base+(
            "\ndef run() -> int:\n"
            "    point = Point(x=1, y=2)\n"
            "    return point.x\n"
        ),
        "PYC3606":base+(
            "\ndef run() -> int:\n"
            "    point = Point(1, 2)\n"
            "    alias = point\n"
            "    return point.x\n"
        ),
        "PYC3607":base+(
            "\ndef run() -> int:\n"
            "    point = Point(1, 2)\n"
            "    point.x = 3\n"
            "    return point.x\n"
        ),
    }
    record_tables_required={
        "record-definition-facts",
        "record-field-facts",
        "record-initializer-facts",
        "record-instance-facts",
        "record-binding-facts",
        "record-access-facts",
    }
    record_rules_required={
        "phase13.record.class",
        "phase13.record.field",
        "phase13.record.initializer",
        "phase13.record.construction",
        "phase13.record.binding",
        "phase13.record.name",
        "phase13.record.attribute_read",
    }

    try:
        converter=PythonToCConverter()
        first=converter.convert(ConversionRequest.from_source(accepted_source))
        second=PythonToCConverter().convert(ConversionRequest.from_source(accepted_source))
        payload=first.stage_artifact.payload if first.stage_artifact else {}
        active_contracts={
            "rule_set":DEFAULT_RULE_SET,
            "renderer":DEFAULT_RENDERER,
            "keyword_call_facts":KEYWORD_CALL_FACT_SCHEMA,
            "keyword_only_call_facts":KEYWORD_ONLY_CALL_FACT_SCHEMA,
            "conversion_plan":CONVERSION_PLAN_SCHEMA,
            "c_ir":C_IR_SCHEMA,
            "generated_c":GENERATED_C_SCHEMA,
        }
        active_contracts_valid=active_contracts=={
            "rule_set":"phase14-required-keyword-only-calls-v0.14.3",
            "renderer":"c-renderer-v0.14.3",
            "keyword_call_facts":"fact-table/0.14.2",
            "keyword_only_call_facts":"fact-table/0.14.3",
            "conversion_plan":"conversion-plan/0.14.3",
            "c_ir":"c-ir/0.14.3",
            "generated_c":"generated-c/0.14.3",
        }
        accepted_identity_ok=bool(
            first.stage_artifact is not None
            and first.stage_artifact.schema_version=="0.14.3"
            and payload.get("schema_version")==GENERATED_C_SCHEMA
            and payload.get("c_ir_schema")==C_IR_SCHEMA
            and payload.get("rule_set_version")==DEFAULT_RULE_SET
            and payload.get("renderer_version")==DEFAULT_RENDERER
            and len([
                table for table in payload.get("fact_tables",())
                if table.get("table_id")=="keyword-call-binding-facts"
                and table.get("schema_version")==KEYWORD_CALL_FACT_SCHEMA
                and table.get("records")==[]
            ])==1
            and len([
                table for table in payload.get("fact_tables",())
                if table.get("table_id")=="keyword-only-call-binding-facts"
                and table.get("schema_version")==KEYWORD_ONLY_CALL_FACT_SCHEMA
                and table.get("records")==[]
            ])==1
        )
        c_ir=payload.get("c_ir",{})
        generated=first.generated_c or ""
        conformance=validate_c_text(generated)
        tables={
            item.get("table_id"):item
            for item in payload.get("fact_tables",())
            if str(item.get("table_id","")).startswith("record-")
        }
        values={
            table_id:[item.get("value",{}) for item in table.get("records",())]
            for table_id,table in tables.items()
        }
        definitions=values.get("record-definition-facts",[])
        fields=values.get("record-field-facts",[])
        instances=values.get("record-instance-facts",[])
        bindings=values.get("record-binding-facts",[])
        accesses=values.get("record-access-facts",[])
        facts_ok=bool(
            set(tables)==record_tables_required
            and all(
                table.get("schema_version")==RECORD_FACT_SCHEMA
                and table.get("producer_stage")=="analysis.plan"
                and table.get("completeness")=="complete"
                for table in tables.values()
            )
            and len(definitions)==1
            and sorted(item.get("category") for item in fields)==[
                "boolean-like","floating-like","integer-like"
            ]
            and len(instances)==3
            and len(bindings)==3
            and len(accesses)==3
            and all(item.get("mutable") is False for item in (*definitions,*fields,*instances))
            and all(
                item.get("storage_model")=="automatic-inline-record"
                and item.get("ownership_model")=="unique-lexical-owner"
                and item.get("cleanup_model")=="none"
                and item.get("nullability_model")=="non-null-by-construction"
                for item in (*definitions,*instances)
            )
            and all(
                item.get("allocation_model")=="none"
                and item.get("aliasing_model")=="forbidden"
                for item in instances
            )
            and all(
                item.get("single_assignment") is True
                and item.get("noalias") is True
                and item.get("escapes") is False
                for item in bindings
            )
            and all(
                item.get("access_mode")=="read"
                and item.get("statically_bound") is True
                for item in accesses
            )
        )
        rule_ids={item.get("rule_id") for item in payload.get("rule_plans",())}
        rules_ok=record_rules_required.issubset(rule_ids)
        record_defs=_kind_dicts(c_ir,{"CRecordDefinition"})
        initializers=_kind_dicts(c_ir,{"CRecordInitializer"})
        members=_kind_dicts(c_ir,{"CMemberAccessExpr"})
        record_objects=[
            item for item in _kind_dicts(c_ir,{"CVariableDeclaration"})
            if item.get("initializer",{}).get("kind")=="CRecordInitializer"
        ]
        rendered_typedef=bool(re.search(
            r"typedef\s+struct\s+[A-Za-z_][A-Za-z0-9_]*\s*\{[^}]+\}\s*[A-Za-z_][A-Za-z0-9_]*\s*;",
            generated,
            re.DOTALL,
        ))
        rendered_aggregate=bool(re.search(
            r"const\s+[A-Za-z_][A-Za-z0-9_]*\s+[A-Za-z_][A-Za-z0-9_]*\s*=\s*\{[^}]+\}\s*;",
            generated,
        ))
        rendered_member_access=bool(re.search(
            r"[A-Za-z_][A-Za-z0-9_]*\.[A-Za-z_][A-Za-z0-9_]*",
            generated,
        ))
        cir_ok=bool(
            payload.get("c_ir_schema")==C_IR_SCHEMA
            and len(record_defs)==1
            and [field.get("type_ref",{}).get("base") for field in record_defs[0].get("fields",())]
            == ["int64_t","double","bool"]
            and len(initializers)==3
            and len(record_objects)==3
            and all(item.get("type_ref",{}).get("qualifiers")==["const"] for item in record_objects)
            and len(members)==3
            and all(item.get("mode")=="direct" for item in members)
            and rendered_typedef
            and rendered_aggregate
            and rendered_member_access
        )
        forbidden_c_identifiers={"malloc","calloc","realloc","free","NULL","nullptr"}
        c_identifiers=set(re.findall(r"[A-Za-z_][A-Za-z0-9_]*",generated))
        no_runtime=bool(
            not payload.get("helper_manifest")
            and forbidden_c_identifiers.isdisjoint(c_identifiers)
            and all(
                item.get("provenance",{}).get("origin_kind")!="support-template"
                for item in _kind_dicts(c_ir,{"CRecordDefinition","CVariableDeclaration","CMemberAccessExpr"})
            )
        )
        in_process_deterministic=bool(
            generated
            and generated==second.generated_c
            and first.output_fingerprint==second.output_fingerprint
            and first.stage_artifact is not None
            and second.stage_artifact is not None
            and first.stage_artifact.artifact_fingerprint==second.stage_artifact.artifact_fingerprint
        )
        fresh_process_determinism=audit_determinism(root,accepted_source)
        deterministic=in_process_deterministic and fresh_process_determinism["passed"]
        accepted_ok=bool(
            first.status is ResultStatus.CONVERTED
            and second.status is ResultStatus.CONVERTED
            and not first.diagnostics
            and conformance.accepted
            and facts_ok
            and rules_ok
            and cir_ok
            and no_runtime
            and deterministic
            and active_contracts_valid
            and accepted_identity_ok
        )

        rejected={
            code:converter.convert(ConversionRequest.from_source(source))
            for code,source in rejection_sources.items()
        }
        rejected_ok=all(
            result.status is ResultStatus.REJECTED
            and result.generated_c is None
            and [item.code for item in result.diagnostics]==[code]
            and not (result.stage_artifact and result.stage_artifact.payload.get("c_ir"))
            and not (result.stage_artifact and result.stage_artifact.payload.get("helper_manifest"))
            for code,result in rejected.items()
        )

        imported_record=converter.convert(
            ConversionRequest(
                SourceBundle(
                    SourceDocumentInput(
                        "app.py",
                        "from lib import Point\n\ndef run() -> int:\n"
                        "    point = Point(1, 2)\n    return point.x\n",
                        "app",
                    ),
                    (
                        SourceDocumentInput(
                            "lib.py",
                            base+"\ndef keep() -> int:\n    return 1\n",
                            "lib",
                        ),
                    ),
                )
            )
        )
        cross_module_ok=bool(
            imported_record.status is ResultStatus.REJECTED
            and imported_record.generated_c is None
            and [item.code for item in imported_record.diagnostics]==["PYC3610"]
            and not (imported_record.stage_artifact and imported_record.stage_artifact.payload.get("c_ir"))
        )
        return {
            "audit":"records",
            "passed":accepted_ok and rejected_ok and cross_module_ok,
            "active_contracts":active_contracts,
            "active_contract_identities_valid":active_contracts_valid and accepted_identity_ok,
            "accepted_field_categories":["integer-like","floating-like","boolean-like"],
            "record_fact_schema":RECORD_FACT_SCHEMA,
            "record_fact_tables":sorted(tables),
            "record_rule_ids":sorted(record_rules_required & rule_ids),
            "c_ir_schema":payload.get("c_ir_schema"),
            "c_ir_record_definitions":len(record_defs),
            "c_ir_record_initializers":len(initializers),
            "c_ir_direct_member_accesses":sum(item.get("mode")=="direct" for item in members),
            "rendered_typedef_struct":rendered_typedef,
            "rendered_const_aggregate":rendered_aggregate,
            "rendered_direct_member_access":rendered_member_access,
            "generated_c_textually_valid":conformance.accepted,
            "generated_c_validation_message":conformance.message,
            "deterministic":deterministic,
            "fresh_process_determinism_sha256":fresh_process_determinism["sha256"],
            "helper_manifest_empty":not payload.get("helper_manifest"),
            "allocation":"none",
            "cleanup":"none",
            "nullability":"non-null-by-construction",
            "ownership":"unique automatic local",
            "rejection_codes":sorted(rejected),
            "cross_module_record_rejection_code":"PYC3610",
            "generated_c_validation":"structured C IR and independent textual conformance only",
            "c_toolchain_invoked":False,
            "generated_c_compiled_or_executed":False,
        }
    except Exception as exc:
        return {
            "audit":"records",
            "passed":False,
            "error":f"{type(exc).__name__}: {exc}",
            "c_toolchain_invoked":False,
            "generated_c_compiled_or_executed":False,
        }


def _phase14_floor_reference(dividend: int, divisor: int) -> tuple[int, int]:
    """Model the frozen helpers without compiling or executing generated C."""
    magnitude=abs(dividend)//abs(divisor)
    quotient=-magnitude if (dividend < 0) != (divisor < 0) else magnitude
    remainder=dividend-(quotient*divisor)
    if remainder != 0 and (remainder < 0) != (divisor < 0):
        quotient-=1
        remainder+=divisor
    return quotient,remainder


def audit_numeric(root: Path) -> dict[str, Any]:
    """Independently gate the bounded Phase 14A integer ``//``/``%`` slice."""
    from pycforge import ConversionRequest, PythonToCConverter, ResultStatus
    from pycforge.converter.c_output import validate_c_text
    from pycforge.converter.contracts.configuration import (
        DEFAULT_NUMERIC_POLICY,
        DEFAULT_RENDERER,
        DEFAULT_RULE_SET,
        PHASE13_RENDERER,
        PHASE13_RULE_SET,
    )
    from pycforge.converter.contracts.versions import (
        C_IR_SCHEMA,
        CONVERSION_PLAN_SCHEMA,
        CONVERSION_SUMMARY_SCHEMA,
        DECISION_TRACE_SCHEMA,
        GENERATED_C_SCHEMA,
        KEYWORD_CALL_FACT_SCHEMA,
        KEYWORD_ONLY_CALL_FACT_SCHEMA,
        NUMERIC_FACT_SCHEMA,
    )
    from pycforge.converter.core.serialization import result_to_json
    from pycforge.converter.lowering import FirstSliceLoweringStage
    from pycforge.converter.support_templates import (
        FLOOR_DIV_REFERENCE,
        FLOOR_MOD_REFERENCE,
        default_helper_registry,
    )

    expected_helpers=(FLOOR_DIV_REFERENCE.canonical,FLOOR_MOD_REFERENCE.canonical)
    expected_assets={
        FLOOR_DIV_REFERENCE.canonical:"23fa88ff57ffe15bc20845c6a7359f6d35648ecffd3a30ea23fe43f24e1dd869",
        FLOOR_MOD_REFERENCE.canonical:"cc2e29f5823a119009df78ed20dc410c6eef4d72c57ada115790bd1120dc663e",
    }
    source=(
        "def left(value: int) -> int:\n"
        "    return value + 1\n\n"
        "def run(value: int) -> int:\n"
        "    return left(value) // 3 + value % -2\n"
    )
    rejection_sources={
        "float-right":("PYC3701","def f(value: int) -> int:\n    return value // 2.0\n"),
        "bool-right":("PYC3701","def f(value: int) -> int:\n    return value % True\n"),
        "prohibited-context":("PYC3701","def f(value: int) -> int:\n    inner = lambda: value // 2\n    return value\n"),
        "zero":("PYC3702","def f(value: int) -> int:\n    return value // 0\n"),
        "negative-one":("PYC3702","def f(value: int) -> int:\n    return value % -1\n"),
        "variable":("PYC3702","def f(value: int, divisor: int) -> int:\n    return value // divisor\n"),
        "folded-expression":("PYC3702","def f(value: int) -> int:\n    return value % (1 + 1)\n"),
        "positive-out-of-range":("PYC3702","def f(value: int) -> int:\n    return value // 9223372036854775808\n"),
        "int64-minimum":("PYC3702","def f(value: int) -> int:\n    return value % -9223372036854775808\n"),
    }
    try:
        converter=PythonToCConverter()
        accepted=converter.convert(ConversionRequest.from_source(source))
        repeated=converter.convert(ConversionRequest.from_source(source))
        if accepted.stage_artifact is None:
            raise ValueError("accepted conversion omitted its final stage artifact")
        payload=accepted.stage_artifact.payload
        fact_tables=[table for table in payload.get("fact_tables",()) if table.get("table_id")=="numeric-operation-facts"]
        facts=[] if len(fact_tables)!=1 else [record["value"] for record in fact_tables[0].get("records",())]
        plans=[plan for plan in payload.get("rule_plans",()) if plan.get("rule_id")=="phase14.numeric.floor_arithmetic"]
        manifest=list(payload.get("helper_manifest",()))
        manifest_references=tuple(item.get("reference") for item in manifest)
        manifest_assets={item.get("reference"):item.get("asset_fingerprint") for item in manifest}
        generated=accepted.generated_c or ""

        accepted_identity_ok=(
            accepted.status is ResultStatus.CONVERTED
            and bool(generated)
            and accepted.stage_artifact.kind=="generated_c"
            and accepted.stage_artifact.schema_version=="0.14.3"
            and payload.get("schema_version")==GENERATED_C_SCHEMA
            and FirstSliceLoweringStage.input_schema==CONVERSION_PLAN_SCHEMA
            and payload.get("c_ir_schema")==C_IR_SCHEMA
            and payload.get("c_ir",{}).get("schema_version")==C_IR_SCHEMA
            and payload.get("rule_set_version")==DEFAULT_RULE_SET
            and payload.get("renderer_version")==DEFAULT_RENDERER
            and payload.get("numeric_policy_version")==DEFAULT_NUMERIC_POLICY
            and accepted.conversion_summary is not None
            and accepted.conversion_summary.get("schema_version")==CONVERSION_SUMMARY_SCHEMA
            and accepted.decision_trace is not None
            and accepted.decision_trace.get("schema_version")==DECISION_TRACE_SCHEMA
            and accepted.decision_trace.get("numeric_policy_version")==DEFAULT_NUMERIC_POLICY
            and len([
                table for table in payload.get("fact_tables",())
                if table.get("table_id")=="keyword-call-binding-facts"
                and table.get("schema_version")==KEYWORD_CALL_FACT_SCHEMA
                and table.get("records")==[]
            ])==1
            and len([
                table for table in payload.get("fact_tables",())
                if table.get("table_id")=="keyword-only-call-binding-facts"
                and table.get("schema_version")==KEYWORD_ONLY_CALL_FACT_SCHEMA
                and table.get("records")==[]
            ])==1
        )
        fact_keys={
            "operation_id","binop_node_id","function_node_id","module_id","document_id","logical_name",
            "operator_node_id","operator_kind","left_node_id","right_node_id","left_category","right_category",
            "result_category","left_c_type","right_c_type","result_c_type","divisor_value",
            "divisor_literal_node_ids","literal_shape","divisor_in_admitted_domain","divisor_nonzero_proved",
            "negative_one_divisor_excluded","minimum_signed_divisor_excluded","helper_requirement",
            "evaluation_order","operands_evaluated_once","c_type","failure_policy","support_state",
            "parameter_ownership","result_ownership","allocation_model","cleanup_model",
            "runtime_failure_channel","target_contract",
        }
        facts_ok=(
            len(fact_tables)==1
            and fact_tables[0].get("schema_version")==NUMERIC_FACT_SCHEMA
            and len(facts)==2
            and {fact.get("operator_kind") for fact in facts}=={"floor-divide","floor-modulo"}
            and {fact.get("divisor_value") for fact in facts}=={3,-2}
            and {fact.get("literal_shape") for fact in facts}=={"constant","unary-minus"}
            and {fact.get("helper_requirement") for fact in facts}==set(expected_helpers)
            and all(fact_keys.issubset(fact) for fact in facts)
            and all(
                fact.get("left_category")=="integer-like"
                and fact.get("right_category")=="integer-like"
                and fact.get("result_category")=="integer-like"
                and fact.get("left_c_type")==fact.get("right_c_type")==fact.get("result_c_type")==fact.get("c_type")=="int64_t"
                and fact.get("divisor_in_admitted_domain") is True
                and fact.get("divisor_nonzero_proved") is True
                and fact.get("negative_one_divisor_excluded") is True
                and fact.get("minimum_signed_divisor_excluded") is True
                and fact.get("evaluation_order")==[fact.get("left_node_id"),fact.get("right_node_id")]
                and fact.get("operands_evaluated_once") is True
                and fact.get("support_state")=="SupportedWithHelper"
                and fact.get("parameter_ownership")=="scalar-values-by-value"
                and fact.get("result_ownership")=="scalar-value-by-value"
                and fact.get("allocation_model")==fact.get("cleanup_model")=="none"
                and fact.get("runtime_failure_channel")=="none"
                and fact.get("target_contract")=="c11-portable-fixed-v1"
                and all(isinstance(fact.get(key),str) and fact.get(key) for key in ("module_id","document_id","logical_name","function_node_id"))
                for fact in facts
            )
        )
        plans_ok=(
            len(plans)==2
            and {item for plan in plans for item in plan.get("helper_requirements",())}==set(expected_helpers)
            and all(
                plan.get("rule_version")=="0.14"
                and plan.get("support_state")=="SupportedWithHelper"
                and not plan.get("unresolved_obligations")
                and set(plan.get("resolved_obligations",()))==set(plan.get("semantic_obligations",()))
                for plan in plans
            )
        )
        registry=default_helper_registry()
        helpers_ok=(
            manifest_references==expected_helpers
            and manifest_assets==expected_assets
            and tuple(payload.get("helper_requirements",()))==expected_helpers
            and payload.get("helper_registry_fingerprint")==registry.fingerprint
            and registry.fingerprint=="fcb719f07984f3b79e17262e90f93823a9a0139a60529f8486ab09f6c3663d98"
            and all(item.get("factory_kind")=="structured-c-ir" for item in manifest)
        )
        c_calls=_kind_dicts(payload.get("c_ir",{}),{"CCallExpr"})
        helper_calls=[
            call for call in c_calls
            if isinstance(call.get("callee"),dict)
            and str(call["callee"].get("binding_id","")).startswith("helper-binding:pycf.i64.floor_")
        ]
        temporary_names=re.findall(r"^\s*int64_t (pycf_numeric_(?:left|right|result)_[0-9a-f]+) =",generated,re.MULTILINE)
        temporary_kinds=[next(kind for kind in ("left","right","result") if name.startswith(f"pycf_numeric_{kind}_")) for name in temporary_names]
        staging_ok=(
            len(helper_calls)==2
            and temporary_kinds==["left","right","result","left","right","result"]
            and generated.find("int64_t pycf_call_") < generated.find("int64_t pycf_numeric_left_")
            and generated.count("pycf_i64_floor_div_v1(")==3
            and generated.count("pycf_i64_floor_mod_v1(")==3
        )
        conformance=validate_c_text(generated)
        deterministic=(
            result_to_json(accepted)==result_to_json(repeated)
            and accepted.output_fingerprint==repeated.output_fingerprint
            and accepted.request_fingerprint==repeated.request_fingerprint
        )
        fresh_code=(
            "import hashlib,json; from pycforge import ConversionRequest,PythonToCConverter; "
            f"r=PythonToCConverter().convert(ConversionRequest.from_source({source!r})); "
            "print(json.dumps({'generated_sha256':hashlib.sha256((r.generated_c or '').encode()).hexdigest(),"
            "'output_fingerprint':None if r.output_fingerprint is None else r.output_fingerprint.value,"
            "'request_fingerprint':None if r.request_fingerprint is None else r.request_fingerprint.value},sort_keys=True))"
        )
        env={**__import__("os").environ,"PYTHONPATH":str(root)}
        fresh=json.loads(subprocess.check_output([sys.executable,"-c",fresh_code],cwd=root,env=env,text=True))
        fresh_process_ok=fresh=={
            "generated_sha256":hashlib.sha256(generated.encode()).hexdigest(),
            "output_fingerprint":accepted.output_fingerprint.value if accepted.output_fingerprint else None,
            "request_fingerprint":accepted.request_fingerprint.value if accepted.request_fingerprint else None,
        }

        rejected={label:converter.convert(ConversionRequest.from_source(text)) for label,(_,text) in rejection_sources.items()}
        rejection_codes={label:[item.code for item in result.diagnostics] for label,result in rejected.items()}
        rejections_ok=all(
            result.status is ResultStatus.REJECTED
            and result.generated_c is None
            and result.output_fingerprint is None
            and rejection_codes[label]==[expected_code]
            for label,(expected_code,_) in rejection_sources.items()
            for result in (rejected[label],)
        )

        dividends=(-(2**63),-(2**63)+1,-7,-1,0,1,7,2**63-1)
        divisors=(-(2**63)+1,-7,-2,1,2,7,2**63-1)
        reference_cases=[(a,b) for a in dividends for b in divisors]
        reference_ok=all(_phase14_floor_reference(a,b)==(a//b,a%b) for a,b in reference_cases)

        phase13_source=(
            "def plus(value: int) -> int:\n"
            "    return value + 1\n\n"
            "def run() -> int:\n"
            "    return plus(2)\n"
        )
        phase13_request=ConversionRequest.from_source(
            phase13_source,
            rule_set_version=PHASE13_RULE_SET,
            renderer_version=PHASE13_RENDERER,
        )
        phase13=converter.convert(phase13_request)
        phase13_payload={} if phase13.stage_artifact is None else phase13.stage_artifact.payload
        historical_ok=(
            phase13.status is ResultStatus.CONVERTED
            and phase13.stage_artifact is not None
            and phase13.stage_artifact.schema_version=="0.13"
            and phase13_payload.get("schema_version")=="generated-c/0.13"
            and phase13_payload.get("c_ir_schema")=="c-ir/0.13"
            and "numeric_policy_version" not in phase13_payload
            and phase13.conversion_summary is not None
            and phase13.conversion_summary.get("schema_version")=="pycforge.conversion-summary/0.13"
            and "numeric_policy_version" not in phase13.conversion_summary
            and phase13.decision_trace is not None
            and phase13.decision_trace.get("schema_version")=="pycforge.decision-trace/0.13"
            and "numeric_policy_version" not in phase13.decision_trace
            and hashlib.sha256((phase13.generated_c or "").encode()).hexdigest()=="d54ec54f5d9b0553d73c77179c3429928eb2c2deaa4963776429b628918cf257"
            and phase13.output_fingerprint is not None
            and phase13.output_fingerprint.value=="da9e27bd909e2ddf9154b072d668c98576a925aa7a342244db566d254ec0e556"
            and phase13.request_fingerprint is not None
            and phase13.request_fingerprint.value=="a8cb25e7596427d78a9b6560e833786920216631f3179da4abc5a8a12fabe3fb"
        )
        legacy_active=converter.convert(ConversionRequest.from_source(phase13_source,target_contract="pycforge-c11-int64-v0.1"))
        legacy_historical=converter.convert(ConversionRequest.from_source(
            phase13_source,
            target_contract="pycforge-c11-int64-v0.1",
            rule_set_version=PHASE13_RULE_SET,
            renderer_version=PHASE13_RENDERER,
        ))
        target_gate_ok=(
            legacy_active.status is ResultStatus.REJECTED
            and [item.code for item in legacy_active.diagnostics]==["PYC1008"]
            and legacy_historical.status is ResultStatus.CONVERTED
        )
        passed=all((
            accepted_identity_ok,facts_ok,plans_ok,helpers_ok,staging_ok,conformance.accepted,
            deterministic,fresh_process_ok,rejections_ok,reference_ok,historical_ok,target_gate_ok,
        ))
        return {
            "audit":"numeric",
            "passed":passed,
            "active_contracts":{
                "rule_set":DEFAULT_RULE_SET,
                "renderer":DEFAULT_RENDERER,
                "numeric_policy":DEFAULT_NUMERIC_POLICY,
                "numeric_facts":NUMERIC_FACT_SCHEMA,
                "keyword_call_facts":KEYWORD_CALL_FACT_SCHEMA,
                "keyword_only_call_facts":KEYWORD_ONLY_CALL_FACT_SCHEMA,
                "conversion_plan":CONVERSION_PLAN_SCHEMA,
                "c_ir":C_IR_SCHEMA,
                "generated_c":GENERATED_C_SCHEMA,
                "conversion_summary":CONVERSION_SUMMARY_SCHEMA,
                "decision_trace":DECISION_TRACE_SCHEMA,
            },
            "active_contract_identities_valid":accepted_identity_ok,
            "accepted_identity_valid":accepted_identity_ok,
            "numeric_fact_count":len(facts),
            "numeric_facts_valid":facts_ok,
            "numeric_rule_plan_count":len(plans),
            "numeric_rule_plans_valid":plans_ok,
            "helper_registry_fingerprint":registry.fingerprint,
            "helper_references":list(manifest_references),
            "helpers_valid":helpers_ok,
            "c_ir_helper_call_count":len(helper_calls),
            "temporary_order":temporary_kinds,
            "evaluation_staging_valid":staging_ok,
            "generated_c_conformance":conformance.accepted,
            "deterministic":deterministic,
            "fresh_process_deterministic":fresh_process_ok,
            "generated_c_sha256":hashlib.sha256(generated.encode()).hexdigest(),
            "rejection_codes":rejection_codes,
            "rejections_publish_no_c":rejections_ok,
            "reference_model_case_count":len(reference_cases),
            "reference_model_matches_python":reference_ok,
            "phase13_exact_compatibility":historical_ok,
            "target_contract_gate_valid":target_gate_ok,
            "c_toolchain_invoked":False,
            "generated_c_compiled_or_executed":False,
        }
    except Exception as exc:
        return {
            "audit":"numeric",
            "passed":False,
            "error":f"{type(exc).__name__}: {exc}",
            "c_toolchain_invoked":False,
            "generated_c_compiled_or_executed":False,
        }


def _kind_dicts(value: Any, kinds: set[str]) -> list[dict[str, Any]]:
    result: list[dict[str, Any]]=[]
    if isinstance(value,dict):
        if value.get("kind") in kinds:
            result.append(value)
        for item in value.values():
            result.extend(_kind_dicts(item,kinds))
    elif isinstance(value,(list,tuple)):
        for item in value:
            result.extend(_kind_dicts(item,kinds))
    return result


def audit_conditional(root: Path) -> dict[str, Any]:
    """Independently gate the bounded Phase 14B conditional-region slice."""
    from pycforge import ConversionRequest, PythonToCConverter, ResultStatus
    from pycforge.converter.c_output import validate_c_text
    from pycforge.converter.conditional_regions import (
        CONDITIONAL_REGION_KEY_DOMAIN,
        CONDITIONAL_REGION_LOWERING_SHAPE,
        CONDITIONAL_REGION_OBLIGATIONS,
        CONDITIONAL_REGION_PROVENANCE_EVIDENCE,
        CONDITIONAL_REGION_TABLE_DEPENDENCIES,
        CONDITIONAL_REGION_TABLE_ID,
    )
    from pycforge.converter.contracts.configuration import (
        DEFAULT_NUMERIC_POLICY,
        DEFAULT_RENDERER,
        DEFAULT_RULE_SET,
        PHASE14A_RENDERER,
        PHASE14A_RULE_SET,
        PHASE14B_RENDERER,
        PHASE14B_RULE_SET,
    )
    from pycforge.converter.contracts.versions import (
        C_IR_SCHEMA,
        CONDITIONAL_FACT_SCHEMA,
        CONVERSION_PLAN_SCHEMA,
        CONVERSION_SUMMARY_SCHEMA,
        DECISION_TRACE_SCHEMA,
        GENERATED_C_SCHEMA,
        KEYWORD_CALL_FACT_SCHEMA,
        KEYWORD_ONLY_CALL_FACT_SCHEMA,
        RESULT_SCHEMA_VERSION,
    )
    from pycforge.converter.core.request import ObservationOptions
    from pycforge.converter.core.serialization import result_to_json
    from pycforge.converter.support_templates import (
        FLOOR_DIV_REFERENCE,
        default_helper_registry,
    )

    expected_obligations=(
        "scalar-operand-representations-proved",
        "unconditional-prefix-proved",
        "guard-polarity-proved",
        "short-circuit-order-preserved",
        "operands-evaluated-left-to-right-once",
        "prerequisite-statements-branch-contained",
        "intermediate-values-reused-without-reevaluation",
        "structured-c-ir-only",
        "result-materialized-once",
        "allocation-and-cleanup-absent",
        "runtime-failure-channel-unchanged",
        "source-provenance-anchored",
        "cancellation-safe-points-honored",
        "target-contract-exact",
    )
    expected_dependencies=(
        "value-category-facts",
        "evaluation-order-facts",
        "call-target-facts",
        "container-access-facts",
        "record-access-facts",
        "numeric-operation-facts",
    )
    expected_provenance=(
        "exact-scalar-operands",
        "unconditional-prefix",
        "accumulated-result-guard",
        "left-to-right-once",
        "branch-contained-prerequisites",
        "flat-structured-c-ir",
    )
    source=(
        "def flag(value: bool) -> bool:\n"
        "    return value\n\n"
        "def value(item: int) -> int:\n"
        "    return item\n\n"
        "def both(a: bool, b: bool, c: bool) -> bool:\n"
        "    return flag(a) and b and flag(c)\n\n"
        "def either(a: bool, b: bool) -> bool:\n"
        "    return a or flag(b)\n\n"
        "def ordered(a: int, b: int, c: int, d: int) -> bool:\n"
        "    return a < b < (value(c) // 2) < d + 1\n"
    )
    boolean_region_source=(
        "def flag(value: bool) -> bool:\n"
        "    return value\n\n"
        "def run(a: bool, b: bool) -> bool:\n"
        "    return a and flag(b)\n"
    )
    comparison_region_source=(
        "def value(item: int) -> int:\n"
        "    return item\n\n"
        "def run(a: int, b: int, c: int) -> bool:\n"
        "    return a < b < value(c)\n"
    )
    try:
        converter=PythonToCConverter()
        observation=ObservationOptions("Full",False)
        accepted=converter.convert(
            ConversionRequest.from_source(source),observation=observation
        )
        repeated=converter.convert(
            ConversionRequest.from_source(source),observation=observation
        )
        if accepted.stage_artifact is None:
            raise ValueError("conditional audit conversion omitted its final artifact")
        payload=accepted.stage_artifact.payload
        summary=accepted.conversion_summary or {}
        trace=accepted.decision_trace or {}

        constants_valid=(
            CONDITIONAL_REGION_TABLE_ID=="conditional-region-facts"
            and CONDITIONAL_REGION_KEY_DOMAIN=="conditional-region-node-id"
            and CONDITIONAL_REGION_LOWERING_SHAPE=="flat-guarded-assignment-v1"
            and CONDITIONAL_REGION_OBLIGATIONS==expected_obligations
            and CONDITIONAL_REGION_TABLE_DEPENDENCIES==expected_dependencies
            and CONDITIONAL_REGION_PROVENANCE_EVIDENCE==expected_provenance
        )
        identity_valid=(
            accepted.status is ResultStatus.CONVERTED
            and accepted.generated_c is not None
            and accepted.stage_artifact.kind=="generated_c"
            and accepted.stage_artifact.schema_version=="0.14.3"
            and payload.get("schema_version")==GENERATED_C_SCHEMA=="generated-c/0.14.3"
            and payload.get("c_ir_schema")==C_IR_SCHEMA=="c-ir/0.14.3"
            and payload.get("rule_set_version")==DEFAULT_RULE_SET=="phase14-required-keyword-only-calls-v0.14.3"
            and payload.get("renderer_version")==DEFAULT_RENDERER=="c-renderer-v0.14.3"
            and payload.get("numeric_policy_version")==DEFAULT_NUMERIC_POLICY
            and CONVERSION_PLAN_SCHEMA=="conversion-plan/0.14.3"
            and CONDITIONAL_FACT_SCHEMA=="fact-table/0.14.1"
            and KEYWORD_CALL_FACT_SCHEMA=="fact-table/0.14.2"
            and KEYWORD_ONLY_CALL_FACT_SCHEMA=="fact-table/0.14.3"
            and CONVERSION_SUMMARY_SCHEMA=="pycforge.conversion-summary/0.14.3"
            and DECISION_TRACE_SCHEMA=="pycforge.decision-trace/0.14.3"
            and RESULT_SCHEMA_VERSION=="0.5"
        )

        tables=[
            item for item in payload.get("fact_tables",())
            if item.get("table_id")==CONDITIONAL_REGION_TABLE_ID
        ]
        table=tables[0] if len(tables)==1 else {}
        records=list(table.get("records",()))
        facts=[record.get("value",{}) for record in records]
        table_valid=(
            len(tables)==1
            and table.get("schema_version")==CONDITIONAL_FACT_SCHEMA
            and table.get("producer_stage")=="analysis.plan"
            and table.get("key_domain")==CONDITIONAL_REGION_KEY_DOMAIN
            and table.get("completeness")=="complete"
            and tuple(table.get("invalidation_dependencies",()))==expected_dependencies
            and len(records)==3
            and len({record.get("key") for record in records})==3
            and all(
                record.get("key")==record.get("value",{}).get("region_node_id")
                and tuple(record.get("provenance",{}).get("evidence",()))==expected_provenance
                and set(record.get("value",{}).get("prerequisite_node_ids",())).issubset(
                    set(record.get("provenance",{}).get("source_node_ids",()))
                )
                for record in records
            )
        )

        def fact_valid(fact: dict[str, Any]) -> bool:
            kind=fact.get("region_kind")
            operands=list(fact.get("operand_node_ids",()))
            categories=list(fact.get("operand_categories",()))
            placements=list(fact.get("placements",()))
            prefix=1 if kind=="boolean-short-circuit" else 2 if kind=="chained-comparison" else -1
            polarity=(
                "when-result-false"
                if kind=="boolean-short-circuit" and fact.get("operator_kinds")==["Or"]
                else "when-result-true"
            )
            if (
                prefix < 0
                or not re.fullmatch(r"conditional-region-[0-9a-f]{20}",str(fact.get("region_id","")))
                or len(operands) < prefix
                or len(categories)!=len(operands)
                or len(placements)!=len(operands)
                or fact.get("evaluation_order")!=operands
                or fact.get("guarded_operand_node_ids")!=operands[prefix:]
                or fact.get("unconditional_prefix_count")!=prefix
                or fact.get("operands_evaluated_once") is not True
                or fact.get("lowering_shape")!="flat-guarded-assignment-v1"
                or fact.get("result_category")!="boolean-like"
                or fact.get("result_c_type")!="bool"
                or fact.get("allocation_model")!="none"
                or fact.get("cleanup_model")!="none"
                or fact.get("runtime_failure_channel")!="unchanged"
                or fact.get("target_contract")!="c11-portable-fixed-v1"
                or not all(
                    isinstance(fact.get(key),str) and fact.get(key)
                    for key in ("region_node_id","function_node_id","module_id","document_id","logical_name")
                )
            ):
                return False
            for ordinal,(operand,category,placement) in enumerate(
                zip(operands,categories,placements)
            ):
                unconditional=ordinal < prefix
                if (
                    placement.get("operand_node_id")!=operand
                    or placement.get("ordinal")!=ordinal
                    or placement.get("category")!=category
                    or placement.get("evaluation_mode")!=("unconditional" if unconditional else "guarded")
                    or placement.get("guard_polarity")!=("none" if unconditional else polarity)
                    or placement.get("guard_after_operand_ordinal")!=(None if unconditional else ordinal-1)
                    or placement.get("requires_statement_prelude") is not bool(placement.get("prerequisite_node_ids"))
                ):
                    return False
            prerequisites=list(dict.fromkeys(
                item
                for placement in placements
                for item in placement.get("prerequisite_node_ids",())
            ))
            if fact.get("prerequisite_node_ids")!=prerequisites:
                return False
            if kind=="boolean-short-circuit":
                return (
                    fact.get("operator_kinds") in (["And"],["Or"])
                    and all(category=="boolean-like" for category in categories)
                )
            return (
                len(fact.get("operator_kinds",()))==len(operands)-1
                and all(item in {"Eq","NotEq","Lt","LtE","Gt","GtE"} for item in fact.get("operator_kinds",()))
                and bool(categories)
                and categories[0] in {"integer-like","floating-like","boolean-like"}
                and all(category==categories[0] for category in categories)
            )

        fact_kinds=[fact.get("region_kind") for fact in facts]
        facts_valid=(
            fact_kinds.count("boolean-short-circuit")==2
            and fact_kinds.count("chained-comparison")==1
            and all(fact_valid(fact) for fact in facts)
        )

        plans=[
            plan for plan in payload.get("rule_plans",())
            if str(plan.get("rule_id","")).startswith("phase14.conditional.")
        ]
        plans_by_source={plan.get("source_node_id"):plan for plan in plans}

        def plan_valid(fact: dict[str, Any]) -> bool:
            plan=plans_by_source.get(fact.get("region_node_id"),{})
            kind=fact.get("region_kind")
            rule=(
                "phase14.conditional.boolean_region"
                if kind=="boolean-short-circuit"
                else "phase14.conditional.comparison_region"
            )
            node_kind="BoolOp" if kind=="boolean-short-circuit" else "Compare"
            guarded_count=len(fact.get("guarded_operand_node_ids",()))
            expected_facts={
                f"conditional-region:{fact.get('region_node_id')}",
                f"conditional-region-kind:{kind}",
                f"conditional-unconditional-prefix:{fact.get('unconditional_prefix_count')}",
                f"conditional-guarded-operand-count:{guarded_count}",
                "conditional-lowering-shape:flat-guarded-assignment-v1",
                "conditional-target:c11-portable-fixed-v1",
                "value-category:boolean-like",
            }
            expected_explanation=[
                "selected",rule,"for",node_kind,"conditional-region",kind,
                "unconditional-prefix",str(fact.get("unconditional_prefix_count")),
                "guarded-operands",str(guarded_count),"lowered-as",
                "flat-guarded-assignment-v1",
            ]
            return (
                plan.get("rule_id")==rule
                and plan.get("rule_version")=="0.14.1"
                and plan.get("support_state")=="SupportedDirect"
                and set(plan.get("facts_used",()))==expected_facts
                and len(plan.get("facts_used",()))==len(expected_facts)
                and tuple(plan.get("semantic_obligations",()))==expected_obligations
                and tuple(plan.get("resolved_obligations",()))==expected_obligations
                and plan.get("unresolved_obligations")==[]
                and plan.get("helper_requirements")==[]
                and plan.get("explanation_tokens")==expected_explanation
            )

        plans_valid=(
            len(plans)==3
            and len(plans_by_source)==3
            and {plan.get("rule_id") for plan in plans}=={
                "phase14.conditional.boolean_region",
                "phase14.conditional.comparison_region",
            }
            and all(plan_valid(fact) for fact in facts)
        )

        helper_reference=FLOOR_DIV_REFERENCE.canonical
        numeric_plans=[
            plan for plan in payload.get("rule_plans",())
            if plan.get("rule_id")=="phase14.numeric.floor_arithmetic"
        ]
        helper_registry=default_helper_registry()
        helper_ownership_valid=(
            len(numeric_plans)==1
            and numeric_plans[0].get("helper_requirements")==[helper_reference]
            and all(not plan.get("helper_requirements") for plan in plans)
            and payload.get("helper_requirements")==[helper_reference]
            and [item.get("reference") for item in payload.get("helper_manifest",())]==[helper_reference]
            and payload.get("helper_registry_fingerprint")==helper_registry.fingerprint
            and helper_registry.fingerprint=="fcb719f07984f3b79e17262e90f93823a9a0139a60529f8486ab09f6c3663d98"
        )

        c_ir=payload.get("c_ir",{})
        region_prefixes=("c-bool-region-if-","c-chain-region-if-")
        region_ifs=[
            item for item in _kind_dicts(c_ir,{"CIfStatement"})
            if str(item.get("node_id","")).startswith(region_prefixes)
        ]

        def source_ids(value: Any) -> set[str]:
            found: set[str]=set()
            if isinstance(value,dict):
                provenance=value.get("provenance")
                if isinstance(provenance,dict):
                    found.update(
                        item for item in provenance.get("source_node_ids",())
                        if isinstance(item,str)
                    )
                for child in value.values():
                    found.update(source_ids(child))
            elif isinstance(value,(list,tuple)):
                for child in value:
                    found.update(source_ids(child))
            return found

        guard_by_placement: dict[tuple[str,int],dict[str,Any]]={}
        guard_checks: list[bool]=[]
        for fact in facts:
            region_node_id=fact.get("region_node_id")
            for placement in fact.get("placements",()):
                if placement.get("evaluation_mode")!="guarded":
                    continue
                operand_id=placement.get("operand_node_id")
                candidates=[
                    item for item in region_ifs
                    if {region_node_id,operand_id}.issubset(
                        set(item.get("provenance",{}).get("source_node_ids",()))
                    )
                ]
                if len(candidates)!=1:
                    guard_checks.append(False)
                    continue
                guard=candidates[0]
                guard_by_placement[(str(region_node_id),int(placement.get("ordinal")))]=guard
                condition=guard.get("condition",{})
                expected_false=placement.get("guard_polarity")=="when-result-false"
                polarity_ok=(
                    condition.get("kind")=="CUnaryExpr"
                    and condition.get("op")=="!"
                ) if expected_false else condition.get("kind")=="CIdentifierRef"
                then_block=guard.get("then_block",{})
                nested_region_ifs=[
                    item for item in _kind_dicts(then_block,{"CIfStatement"})
                    if str(item.get("node_id","")).startswith(region_prefixes)
                ]
                prerequisites=set(placement.get("prerequisite_node_ids",()))
                guard_checks.append(
                    polarity_ok
                    and guard.get("else_block") is None
                    and not nested_region_ifs
                    and prerequisites.issubset(source_ids(then_block))
                    and bool(_kind_dicts(then_block,{"CAssignmentStatement"}))
                )
        expected_guard_count=sum(
            len(fact.get("guarded_operand_node_ids",())) for fact in facts
        )
        flat_branch_containment_valid=(
            len(region_ifs)==expected_guard_count==5
            and len(guard_checks)==expected_guard_count
            and all(guard_checks)
        )

        accumulator_valid=True
        rolling_reuse_valid=True
        for fact in facts:
            region_node_id=str(fact.get("region_node_id"))
            guarded=[
                placement for placement in fact.get("placements",())
                if placement.get("evaluation_mode")=="guarded"
            ]
            if fact.get("region_kind")=="boolean-short-circuit":
                for placement in guarded:
                    guard=guard_by_placement.get((region_node_id,placement["ordinal"]),{})
                    condition=guard.get("condition",{})
                    if condition.get("kind")=="CUnaryExpr":
                        condition=condition.get("operand",{})
                    assignments=[
                        item for item in _kind_dicts(guard.get("then_block",{}),{"CAssignmentStatement"})
                        if str(item.get("node_id","")).startswith("c-bool-region-assign-")
                    ]
                    accumulator_valid=accumulator_valid and (
                        len(assignments)==1
                        and condition.get("binding_id")==assignments[0].get("target",{}).get("binding_id")
                    )
            else:
                pairs=[]
                for placement in guarded:
                    guard=guard_by_placement.get((region_node_id,placement["ordinal"]),{})
                    assignments=[
                        item for item in _kind_dicts(guard.get("then_block",{}),{"CAssignmentStatement"})
                        if str(item.get("node_id","")).startswith("c-chain-region-result-assign-")
                    ]
                    if len(assignments)!=1:
                        rolling_reuse_valid=False
                        continue
                    expression=assignments[0].get("value",{})
                    pairs.append((
                        expression.get("left",{}).get("binding_id"),
                        expression.get("right",{}).get("binding_id"),
                    ))
                rolling_reuse_valid=rolling_reuse_valid and all(
                    pairs[index][1]==pairs[index+1][0]
                    for index in range(len(pairs)-1)
                )

        c_ir_node_ids=[]
        def collect_c_ir_node_ids(value: Any) -> None:
            if isinstance(value,dict):
                if isinstance(value.get("node_id"),str):
                    c_ir_node_ids.append(value["node_id"])
                for child in value.values():
                    collect_c_ir_node_ids(child)
            elif isinstance(value,(list,tuple)):
                for child in value:
                    collect_c_ir_node_ids(child)
        collect_c_ir_node_ids(c_ir)
        c_ir_ids_unique=len(c_ir_node_ids)==len(set(c_ir_node_ids))
        conformance=validate_c_text(accepted.generated_c or "")

        def canonical_dicts(values: Any) -> list[str]:
            return sorted(json.dumps(item,sort_keys=True,separators=(",",":")) for item in values)

        trace_plans=[
            plan for plan in trace.get("rule_decisions",())
            if str(plan.get("rule_id","")).startswith("phase14.conditional.")
        ]
        observer_valid=(
            summary.get("schema_version")==CONVERSION_SUMMARY_SCHEMA
            and summary.get("rule_set_version")==DEFAULT_RULE_SET
            and summary.get("renderer_version")==DEFAULT_RENDERER
            and canonical_dicts(summary.get("conditional_regions",()))==canonical_dicts(facts)
            and trace.get("schema_version")==DECISION_TRACE_SCHEMA
            and trace.get("trace_level")=="Full"
            and trace.get("completeness")=="complete"
            and trace.get("truncated") is False
            and trace.get("observer_failed") is False
            and canonical_dicts(trace_plans)==canonical_dicts(plans)
            and bool(trace.get("source_output_mappings"))
            and bool(trace.get("stage_summaries"))
        )

        deterministic=(
            result_to_json(accepted)==result_to_json(repeated)
            and accepted.request_fingerprint==repeated.request_fingerprint
            and accepted.output_fingerprint==repeated.output_fingerprint
            and accepted.stage_artifact.artifact_fingerprint==repeated.stage_artifact.artifact_fingerprint
        )
        fresh_code=(
            "import hashlib,json; "
            "from pycforge import ConversionRequest,PythonToCConverter; "
            "from pycforge.converter.core.request import ObservationOptions; "
            "from pycforge.converter.core.serialization import result_to_json; "
            f"r=PythonToCConverter().convert(ConversionRequest.from_source({source!r}),"
            "observation=ObservationOptions('Full',False)); "
            "print(json.dumps({'serialized_sha256':hashlib.sha256(result_to_json(r).encode()).hexdigest(),"
            "'generated_sha256':hashlib.sha256((r.generated_c or '').encode()).hexdigest(),"
            "'request_fingerprint':None if r.request_fingerprint is None else r.request_fingerprint.value,"
            "'output_fingerprint':None if r.output_fingerprint is None else r.output_fingerprint.value,"
            "'artifact_fingerprint':None if r.stage_artifact is None else r.stage_artifact.artifact_fingerprint.value},sort_keys=True))"
        )
        env={**__import__("os").environ,"PYTHONPATH":str(root)}
        fresh=json.loads(subprocess.check_output(
            [sys.executable,"-c",fresh_code],cwd=root,env=env,text=True
        ))
        fresh_process_valid=fresh=={
            "serialized_sha256":hashlib.sha256(result_to_json(accepted).encode()).hexdigest(),
            "generated_sha256":hashlib.sha256((accepted.generated_c or "").encode()).hexdigest(),
            "request_fingerprint":accepted.request_fingerprint.value if accepted.request_fingerprint else None,
            "output_fingerprint":accepted.output_fingerprint.value if accepted.output_fingerprint else None,
            "artifact_fingerprint":accepted.stage_artifact.artifact_fingerprint.value,
        }

        historical_witness="def run() -> int:\n    return 1\n"
        historical=converter.convert(
            ConversionRequest.from_source(
                historical_witness,
                rule_set_version=PHASE14A_RULE_SET,
                renderer_version=PHASE14A_RENDERER,
            ),
            observation=observation,
        )
        active_no_region=converter.convert(
            ConversionRequest.from_source(historical_witness),observation=observation
        )
        historical_payload=(
            historical.stage_artifact.payload
            if historical.stage_artifact is not None else {}
        )
        historical_exact=(
            historical.status is ResultStatus.CONVERTED
            and historical.stage_artifact is not None
            and historical.stage_artifact.schema_version=="0.14"
            and historical_payload.get("schema_version")=="generated-c/0.14"
            and historical_payload.get("c_ir_schema")=="c-ir/0.14"
            and historical_payload.get("rule_set_version")==PHASE14A_RULE_SET=="phase14-bounded-numeric-v0.14"
            and historical_payload.get("renderer_version")==PHASE14A_RENDERER=="c-renderer-v0.14"
            and historical.conversion_summary is not None
            and historical.conversion_summary.get("schema_version")=="pycforge.conversion-summary/0.14"
            and historical.decision_trace is not None
            and historical.decision_trace.get("schema_version")=="pycforge.decision-trace/0.14"
            and CONDITIONAL_REGION_TABLE_ID not in {
                item.get("table_id") for item in historical_payload.get("fact_tables",())
            }
            and historical.request_fingerprint is not None
            and historical.request_fingerprint.value=="f3bdc058becb0854692235850037797872afc00a18a132c88b7bb2950a2d4360"
            and hashlib.sha256((historical.generated_c or "").encode()).hexdigest()=="0ba73812646f4113b99bbe72661d7a7eef129901439422cc2d47bbc6ddaa64c5"
            and historical.output_fingerprint is not None
            and historical.output_fingerprint.value=="27f2abb910f41170714de587158e2eacc66ef81d8535b28a754f5f960e9b6f0d"
        )
        active_no_region_compatible=(
            active_no_region.status is ResultStatus.CONVERTED
            and active_no_region.stage_artifact is not None
            and active_no_region.stage_artifact.schema_version=="0.14.3"
            and active_no_region.generated_c==historical.generated_c
            and active_no_region.output_fingerprint==historical.output_fingerprint
            and len([
                table for table in active_no_region.stage_artifact.payload.get("fact_tables",())
                if table.get("table_id")==CONDITIONAL_REGION_TABLE_ID
                and table.get("records")==[]
            ])==1
        )

        historical_cases={
            "PYC2950":boolean_region_source,
            "PYC2951":comparison_region_source,
        }
        historical_rejections={}
        historical_rejections_valid=True
        for code,text in historical_cases.items():
            result=converter.convert(ConversionRequest.from_source(
                text,
                rule_set_version=PHASE14A_RULE_SET,
                renderer_version=PHASE14A_RENDERER,
            ))
            historical_rejections[code]=[item.code for item in result.diagnostics]
            result_payload={} if result.stage_artifact is None else result.stage_artifact.payload
            historical_rejections_valid=historical_rejections_valid and (
                result.status is ResultStatus.REJECTED
                and historical_rejections[code]==[code]
                and result.generated_c is None
                and result.output_fingerprint is None
                and result.stage_artifact is not None
                and result.stage_artifact.kind=="conversion_plan"
                and result.stage_artifact.schema_version=="0.14"
                and CONDITIONAL_REGION_TABLE_ID not in {
                    item.get("table_id") for item in result_payload.get("fact_tables",())
                }
            )
        keyword_source=(
            "def flag(value: bool) -> bool:\n"
            "    return value\n\n"
            "def run(a: bool, b: bool) -> bool:\n"
            "    return a and flag(value=b)\n"
        )
        keyword_rejection=converter.convert(ConversionRequest.from_source(
            keyword_source,
            rule_set_version=PHASE14B_RULE_SET,
            renderer_version=PHASE14B_RENDERER,
        ))
        root_cause_precedence_valid=(
            keyword_rejection.status is ResultStatus.REJECTED
            and [item.code for item in keyword_rejection.diagnostics]==["PYC2910"]
            and keyword_rejection.generated_c is None
            and keyword_rejection.output_fingerprint is None
        )

        passed=all((
            constants_valid,identity_valid,table_valid,facts_valid,plans_valid,
            helper_ownership_valid,flat_branch_containment_valid,accumulator_valid,
            rolling_reuse_valid,c_ir_ids_unique,conformance.accepted,observer_valid,
            deterministic,fresh_process_valid,historical_exact,
            active_no_region_compatible,historical_rejections_valid,
            root_cause_precedence_valid,
        ))
        return {
            "audit":"conditional",
            "passed":passed,
            "active_contracts":{
                "rule_set":DEFAULT_RULE_SET,
                "renderer":DEFAULT_RENDERER,
                "conditional_facts":CONDITIONAL_FACT_SCHEMA,
                "keyword_call_facts":KEYWORD_CALL_FACT_SCHEMA,
                "keyword_only_call_facts":KEYWORD_ONLY_CALL_FACT_SCHEMA,
                "conversion_plan":CONVERSION_PLAN_SCHEMA,
                "c_ir":C_IR_SCHEMA,
                "generated_c":GENERATED_C_SCHEMA,
                "conversion_summary":CONVERSION_SUMMARY_SCHEMA,
                "decision_trace":DECISION_TRACE_SCHEMA,
                "result_serialization":RESULT_SCHEMA_VERSION,
            },
            "active_contract_identities_valid":identity_valid,
            "contract_constants_valid":constants_valid,
            "accepted_identity_valid":identity_valid,
            "conditional_fact_count":len(facts),
            "conditional_fact_kinds":sorted(fact_kinds),
            "conditional_fact_table_valid":table_valid,
            "conditional_facts_valid":facts_valid,
            "conditional_rule_plan_count":len(plans),
            "conditional_rule_plans_valid":plans_valid,
            "region_owned_helper_requirements_empty":all(
                not plan.get("helper_requirements") for plan in plans
            ),
            "composed_helper_references":[
                item.get("reference") for item in payload.get("helper_manifest",())
            ],
            "helper_ownership_valid":helper_ownership_valid,
            "expected_region_guard_count":expected_guard_count,
            "c_ir_region_guard_count":len(region_ifs),
            "flat_branch_containment_valid":flat_branch_containment_valid,
            "boolean_accumulator_reuse_valid":accumulator_valid,
            "chained_middle_reuse_valid":rolling_reuse_valid,
            "c_ir_node_ids_unique":c_ir_ids_unique,
            "generated_c_conformance":conformance.accepted,
            "observer_evidence_valid":observer_valid,
            "deterministic":deterministic,
            "fresh_process_deterministic":fresh_process_valid,
            "generated_c_sha256":hashlib.sha256((accepted.generated_c or "").encode()).hexdigest(),
            "phase14a_exact_compatibility":historical_exact,
            "active_no_region_output_compatible":active_no_region_compatible,
            "historical_placement_rejections":historical_rejections,
            "historical_placement_rejections_valid":historical_rejections_valid,
            "specific_root_cause_precedence_valid":root_cause_precedence_valid,
            "phase14b_keyword_rejection_precedence_valid":root_cause_precedence_valid,
            "python_subprocess_used_for_determinism_only":True,
            "c_toolchain_invoked":False,
            "generated_c_compiled_or_executed":False,
        }
    except Exception as exc:
        return {
            "audit":"conditional",
            "passed":False,
            "error":f"{type(exc).__name__}: {exc}",
            "c_toolchain_invoked":False,
            "generated_c_compiled_or_executed":False,
        }

def audit_determinism(root: Path, source: str="def add(a: int, b: int) -> int:\n    return a + b\n\ndef twice(x: int) -> int:\n    return add(x, x)\n") -> dict[str, Any]:
    code=("from pycforge import PythonToCConverter,ConversionRequest; "
          "from pycforge.converter.core.serialization import result_to_json; "
          f"print(result_to_json(PythonToCConverter().convert(ConversionRequest.from_source({source!r}))),end='')")
    env={**__import__('os').environ,"PYTHONPATH":str(root)}
    a=subprocess.check_output([sys.executable,"-c",code],cwd=root,env=env)
    b=subprocess.check_output([sys.executable,"-c",code],cwd=root,env=env)
    return {"audit":"determinism","passed":a==b,"sha256":hashlib.sha256(a).hexdigest()}
