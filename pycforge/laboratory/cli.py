from __future__ import annotations
import argparse, json, sys
from pathlib import Path
from typing import Any
from pycforge import ConversionRequest, PythonToCConverter, ResultStatus
from pycforge.converter.contracts.configuration import DEFAULT_RENDERER, DEFAULT_RULE_SET
from pycforge.converter.core.artifact_io import ArtifactCompatibilityError, load_artifact, save_artifact
from pycforge.converter.core.request import ObservationOptions
from pycforge.converter.core.serialization import result_to_dict, result_to_json, result_to_text
from pycforge.converter.core.stage_artifact import StageArtifact
from pycforge.converter.io.atomic_writer import AtomicWriteError, AtomicWriter
from .audits import audit_architecture, audit_conditional, audit_containers, audit_determinism, audit_helpers, audit_keyword, audit_keyword_only, audit_modules, audit_numeric, audit_records, audit_rules, audit_transition
from .exit_codes import ExitCode

ROOT=Path(__file__).resolve().parents[2]

def _developer_tree_available() -> bool:
    """Return whether repository-only audit and suite resources are present."""
    return (ROOT / "tests").is_dir() and (ROOT / "transition").is_dir()

def _emit(value: Any, fmt: str) -> None:
    if fmt == "json": print(json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False))
    elif isinstance(value, str): print(value, end="" if value.endswith("\n") else "\n")
    else:
        for key in sorted(value): print(f"{key}: {value[key]}")

def _request_from_path(path: Path, args: argparse.Namespace) -> ConversionRequest:
    text=path.read_text(encoding="utf-8")
    return ConversionRequest.from_source(text, logical_name=path.name, rule_set_version=DEFAULT_RULE_SET, renderer_version=DEFAULT_RENDERER)

def _status_exit(status: ResultStatus) -> ExitCode:
    return {ResultStatus.CONVERTED:ExitCode.OK,ResultStatus.CONVERTED_WITH_WARNINGS:ExitCode.OK,ResultStatus.CONVERTED_WITH_APPROXIMATIONS:ExitCode.OK,ResultStatus.REJECTED:ExitCode.REJECTED,ResultStatus.CANCELED:ExitCode.CANCELED,ResultStatus.INTERNAL_FAILURE:ExitCode.INTERNAL_FAILURE}[status]

def cmd_convert(args: argparse.Namespace) -> int:
    try: request=_request_from_path(Path(args.source),args)
    except (OSError,UnicodeError) as exc:
        _emit({"error":{"code":"PYC3001","category":"io","message":str(exc)}},args.format); return ExitCode.IO_FAILURE
    observation=ObservationOptions(args.trace_level,args.telemetry)
    result=PythonToCConverter().convert(request,observation=observation)
    if args.output:
        if result.generated_c is not None and result.status in {ResultStatus.CONVERTED,ResultStatus.CONVERTED_WITH_WARNINGS,ResultStatus.CONVERTED_WITH_APPROXIMATIONS}:
            try: AtomicWriter().write_text(Path(args.output),result.generated_c)
            except AtomicWriteError as exc:
                _emit({"error":{"code":"PYC3002","category":"io","message":str(exc)}},args.format); return ExitCode.IO_FAILURE
        else:
            # An explicit output path must not make a semantic rejection
            # silent; leave any preceding file untouched and report why.
            _emit(result_to_dict(result) if args.format=="json" else result_to_text(result),args.format)
    else: _emit(result_to_dict(result) if args.format=="json" else result_to_text(result),args.format)
    if args.save_stage or args.save_final_stage:
        canonical_id=result.request_fingerprint.value if result.request_fingerprint else "rejected"
        artifact=(result.stage_artifact or StageArtifact.initial(canonical_id)) if args.save_final_stage else StageArtifact.initial(canonical_id)
        destination=args.save_final_stage or args.save_stage
        try: save_artifact(Path(destination),artifact,AtomicWriter())
        except AtomicWriteError as exc:
            _emit({"error":{"code":"PYC3002","category":"io","message":str(exc)}},args.format); return ExitCode.IO_FAILURE
    return _status_exit(result.status)

def cmd_inspect(args: argparse.Namespace) -> int:
    try: artifact=load_artifact(Path(args.artifact),accepted={("initial","0.1"),("empty","0.1"),("source_document","0.3"),("python_ast","0.3"),("python_ir","0.3"),("python_ir","0.4"),("conversion_plan","0.5"),("conversion_plan","0.9"),("conversion_plan","0.11"),("conversion_plan","0.12"),("conversion_plan","0.13"),("conversion_plan","0.14"),("conversion_plan","0.14.1"),("conversion_plan","0.14.2"),("conversion_plan","0.14.3"),("generated_c","0.6"),("generated_c","0.8"),("generated_c","0.9"),("generated_c","0.10"),("generated_c","0.11"),("generated_c","0.12"),("generated_c","0.13"),("generated_c","0.14"),("generated_c","0.14.1"),("generated_c","0.14.2"),("generated_c","0.14.3")})
    except ArtifactCompatibilityError as exc:
        _emit({"error":{"code":str(exc).split()[0],"category":"artifact-incompatible","message":str(exc)}},args.format); return ExitCode.ARTIFACT_INCOMPATIBLE
    value={"kind":artifact.kind,"schema_version":artifact.schema_version,"conversion_id":artifact.conversion_id,"artifact_fingerprint":artifact.artifact_fingerprint.to_dict(),"parent_fingerprint":None if artifact.parent_fingerprint is None else artifact.parent_fingerprint.to_dict(),"payload":{k:list(v) if isinstance(v,tuple) else v for k,v in artifact.payload.items()}}
    _emit(value,args.format); return ExitCode.OK

def cmd_validate(args: argparse.Namespace) -> int:
    if args.artifact:
        return cmd_inspect(argparse.Namespace(artifact=args.artifact,format=args.format))
    try: request=_request_from_path(Path(args.source),args)
    except (OSError,UnicodeError) as exc:
        _emit({"valid":False,"diagnostics":[{"code":"PYC3001","message":str(exc)}]},args.format); return ExitCode.IO_FAILURE
    result=PythonToCConverter().convert(request)
    value={"valid":result.status in {ResultStatus.CONVERTED,ResultStatus.CONVERTED_WITH_WARNINGS,ResultStatus.CONVERTED_WITH_APPROXIMATIONS},"result":result_to_dict(result,include_observers=False)}
    _emit(value,args.format); return _status_exit(result.status)

def cmd_suite(args: argparse.Namespace) -> int:
    import unittest
    suite=unittest.defaultTestLoader.discover(str(ROOT/"tests"))
    result=unittest.TextTestRunner(stream=sys.stderr,verbosity=1).run(suite)
    value={"tests_run":result.testsRun,"failures":len(result.failures),"errors":len(result.errors),"passed":result.wasSuccessful()}
    _emit(value,args.format); return ExitCode.OK if result.wasSuccessful() else ExitCode.AUDIT_FAILURE

def cmd_audit(args: argparse.Namespace) -> int:
    fn={"architecture":lambda:audit_architecture(ROOT),"rules":lambda:audit_rules(ROOT),"helpers":lambda:audit_helpers(ROOT),"containers":lambda:audit_containers(ROOT),"modules":lambda:audit_modules(ROOT),"records":lambda:audit_records(ROOT),"numeric":lambda:audit_numeric(ROOT),"conditional":lambda:audit_conditional(ROOT),"keyword":lambda:audit_keyword(ROOT),"keyword-only":lambda:audit_keyword_only(ROOT),"determinism":lambda:audit_determinism(ROOT),"transition":lambda:audit_transition(ROOT,args.phase)}[args.audit_kind]
    value=fn(); _emit(value,args.format); return ExitCode.OK if value["passed"] else ExitCode.AUDIT_FAILURE

def cmd_diff(args: argparse.Namespace) -> int:
    try:
        left=json.loads(Path(args.left).read_text(encoding="utf-8")); right=json.loads(Path(args.right).read_text(encoding="utf-8"))
    except (OSError,UnicodeError,json.JSONDecodeError) as exc:
        _emit({"error":{"code":"PYC3201","category":"io","message":str(exc)}},args.format); return ExitCode.IO_FAILURE
    fields=("status","stage_order","diagnostics","output_fingerprint")
    changes={field:{"left":left.get(field),"right":right.get(field)} for field in fields if left.get(field)!=right.get(field)}
    value={"schema_version":"0.2","semantic_changes":changes,"telemetry_compared":False,"equal":not changes}
    _emit(value,args.format); return ExitCode.OK

def build_parser() -> argparse.ArgumentParser:
    parser=argparse.ArgumentParser(prog="pycforge",description="Headless PyCForge conversion laboratory")
    parser.add_argument("--format",choices=("text","json"),default="text")
    sub=parser.add_subparsers(dest="command",required=True)
    p=sub.add_parser("convert"); p.add_argument("source"); p.add_argument("--output"); p.add_argument("--save-stage"); p.add_argument("--save-final-stage"); p.add_argument("--trace-level",choices=("None","Summary","Decisions","Full"),default="None"); p.add_argument("--telemetry",action="store_true"); p.set_defaults(func=cmd_convert)
    p=sub.add_parser("inspect"); p.add_argument("artifact"); p.set_defaults(func=cmd_inspect)
    p=sub.add_parser("validate"); group=p.add_mutually_exclusive_group(required=True); group.add_argument("--source"); group.add_argument("--artifact"); p.set_defaults(func=cmd_validate)
    if _developer_tree_available():
        p=sub.add_parser("suite"); p.set_defaults(func=cmd_suite)
        p=sub.add_parser("audit"); p.add_argument("audit_kind",choices=("architecture","rules","helpers","containers","modules","records","numeric","conditional","keyword","keyword-only","determinism","transition")); p.add_argument("--phase",default="phase_2"); p.set_defaults(func=cmd_audit)
    p=sub.add_parser("diff"); p.add_argument("left"); p.add_argument("right"); p.set_defaults(func=cmd_diff)
    return parser

def main(argv: list[str] | None=None) -> int:
    parser=build_parser()
    try:
        args=parser.parse_args(argv)
        return int(args.func(args))
    except KeyboardInterrupt:
        _emit({"error":{"code":"PYC3901","category":"canceled","message":"Command interrupted"}},getattr(locals().get('args',None),'format','text'))
        return int(ExitCode.CANCELED)

if __name__ == "__main__": raise SystemExit(main())
