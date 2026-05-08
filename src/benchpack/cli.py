"""``benchpack`` command-line entry point."""

from __future__ import annotations

import argparse
import json
import os
import re
import shutil
import sys
from datetime import datetime
from pathlib import Path

from .adapters import Adapter, AdapterRequest, get_adapter
from .adapters.openai_chat import (
    OPENAI_API_KEY_ENV_KEY,
    OpenAIChatAuthError,
    OPENAI_STREAM_USAGE_INCLUDE,
    OPENAI_STREAM_USAGE_KEY,
    OPENAI_STREAM_USAGE_OMIT,
)
from .compare import CompareError, load_result_run, render_comparison
from .external_agent_context import (
    ExternalAgentContextError,
    build_external_agent_context,
    external_agent_context_path,
    external_agent_model_call_log_path,
    write_external_agent_context,
)
from .hardware import collect_hardware, sample_resources
from .packs import (
    Case,
    Pack,
    PUBLIC_HARNESS_EXTERNAL_AGENT,
    Scoring,
    load_pack,
    repetitions_from_defaults,
    warmup_from_defaults,
)
from .patches import PatchError, capture_workspace_patch
from .report import (
    ReportError,
    load_report_runs,
    load_report_set,
    render_report,
)
from .registry import RegistryError, import_result_dirs
from .results import RunReporter
from .run_metadata import RUN_METADATA_FILENAME, RunMetadataError, load_run_metadata
from .tasks import (
    ExternalProcessHarness,
    TaskError,
    TaskExecutionRequest,
    run_repo_task_executor,
    task_artifact_paths,
)
from .verifiers import (
    DEFAULT_VERIFY_TIMEOUT_S,
    VerifierError,
    resolve_verify_script,
    run_repo_task_verifier,
)
from .workspaces import (
    PreparedWorkspace,
    WorkspaceError,
    prepare_repo_task_workspace,
    validate_repo_task_cases,
    workspace_record,
)


EXTERNAL_AGENT_ARGV_ERROR = (
    "BENCHPACK_EXTERNAL_AGENT_ARGV must be a JSON array of non-empty strings "
    "without NUL bytes"
)


def _effective_scoring(pack: Pack, case: Case) -> Scoring | None:
    return case.scoring or pack.scoring


def _validate_verify_script_usage(pack: Pack) -> None:
    for case in pack.cases:
        scoring = _effective_scoring(pack, case)
        if scoring is None or scoring.mode != "verify-script":
            continue
        if case.kind != "repo-task":
            raise SystemExit(
                "scoring mode 'verify-script' is only supported for measured "
                f"repo-task cases; case {case.id!r} has kind {case.kind!r}"
            )
        try:
            resolve_verify_script(pack, scoring)
        except VerifierError as exc:
            raise SystemExit(str(exc)) from exc


def _load_external_agent_harness(pack: Pack) -> ExternalProcessHarness | None:
    if not any(
        case.harness is not None
        and case.harness.id == PUBLIC_HARNESS_EXTERNAL_AGENT
        for case in pack.cases
    ):
        return None

    raw_argv = os.environ.get("BENCHPACK_EXTERNAL_AGENT_ARGV")
    if raw_argv is None:
        raise SystemExit(
            "BENCHPACK_EXTERNAL_AGENT_ARGV is required for harness id "
            f"{PUBLIC_HARNESS_EXTERNAL_AGENT!r}"
        )
    try:
        argv = json.loads(raw_argv)
    except json.JSONDecodeError as exc:
        raise SystemExit(EXTERNAL_AGENT_ARGV_ERROR) from exc
    if (
        not isinstance(argv, list)
        or not argv
        or any(
            not isinstance(argument, str)
            or argument == ""
            or "\x00" in argument
            for argument in argv
        )
    ):
        raise SystemExit(EXTERNAL_AGENT_ARGV_ERROR)
    return ExternalProcessHarness(argv=tuple(argv))


def _effective_adapter_defaults(
    adapter: Adapter,
    pack: Pack,
    openai_stream_usage: str,
    openai_api_key_env: str | None = None,
) -> dict:
    defaults = dict(pack.defaults)
    if adapter.name == "openai-chat":
        defaults[OPENAI_STREAM_USAGE_KEY] = openai_stream_usage
        if openai_api_key_env is not None:
            defaults[OPENAI_API_KEY_ENV_KEY] = openai_api_key_env
    return defaults


def _derive_host_label(hardware: dict) -> str:
    hostname = (hardware.get("hostname") or "host").split(".")[0].lower()
    label = re.sub(r"[^a-z0-9-]+", "-", hostname).strip("-")
    return label or "host"


def _resolve_pack_dir(name: str) -> Path:
    candidate = Path(name)
    if candidate.is_dir() and (candidate / "benchpack.toml").is_file():
        return candidate
    bundled = Path("benchpacks") / name
    if bundled.is_dir() and (bundled / "benchpack.toml").is_file():
        return bundled
    raise SystemExit(f"pack not found: {name}")


def _run_case(
    adapter: Adapter,
    pack: Pack,
    case: Case,
    model: str,
    endpoint: str | None,
    request_path: Path,
    response_path: Path,
    openai_stream_usage: str = OPENAI_STREAM_USAGE_INCLUDE,
    openai_api_key_env: str | None = None,
    collect_resources: bool = True,
) -> tuple[object, dict]:
    if case.prompt is None:
        raise SystemExit(f"case {case.id!r} has no 'prompt' field")
    defaults = _effective_adapter_defaults(
        adapter,
        pack,
        openai_stream_usage,
        openai_api_key_env,
    )
    request = AdapterRequest(
        prompt=case.prompt,
        model=model,
        endpoint=endpoint,
        defaults=defaults,
        request_path=request_path,
        response_path=response_path,
    )
    try:
        result = adapter.run(request)
    except OpenAIChatAuthError as exc:
        raise SystemExit(str(exc)) from exc
    sample = sample_resources() if collect_resources else {}
    return result, sample


def _cmd_run(args: argparse.Namespace) -> int:
    pack_dir = _resolve_pack_dir(args.pack)
    pack = load_pack(pack_dir)
    warmup = warmup_from_defaults(pack.defaults)
    repetitions = repetitions_from_defaults(pack.defaults)
    try:
        validate_repo_task_cases(pack)
    except WorkspaceError as exc:
        raise SystemExit(str(exc)) from exc
    _validate_verify_script_usage(pack)
    if warmup > 0 and any(case.kind == "repo-task" for case in pack.cases):
        raise SystemExit(
            "repo-task warmups are not supported yet; set defaults.warmup = 0"
        )
    external_agent_harness = _load_external_agent_harness(pack)

    adapter = get_adapter(args.adapter)
    run_metadata = None
    if args.run_metadata is not None:
        try:
            run_metadata = load_run_metadata(args.run_metadata)
        except RunMetadataError as exc:
            raise SystemExit(str(exc)) from exc

    hardware = collect_hardware()
    host_label = args.host_label or _derive_host_label(hardware)
    date = datetime.now().strftime("%Y-%m-%d")
    out_dir = Path(args.out) if args.out else Path("results") / f"{date}-{host_label}"
    existing = out_dir / "run.jsonl"
    if existing.exists():
        if args.force:
            shutil.rmtree(out_dir)
        else:
            raise SystemExit(
                f"refusing to overwrite existing run at {out_dir} "
                f"(found {existing.name}); pass --force to replace it or "
                f"--out to write elsewhere"
            )
    out_dir.mkdir(parents=True, exist_ok=True)

    reporter = RunReporter(out_dir, pack)
    if run_metadata is not None:
        reporter.write_run_metadata(run_metadata)
    persisted_run_metadata_path = (
        out_dir / RUN_METADATA_FILENAME if run_metadata is not None else None
    )

    for case in pack.cases:
        for warmup_index in range(1, warmup + 1):
            request_path, response_path = reporter.warmup_paths(case, warmup_index)
            _run_case(
                adapter,
                pack,
                case,
                model=args.model,
                endpoint=args.endpoint,
                request_path=request_path,
                response_path=response_path,
                openai_stream_usage=args.openai_stream_usage,
                openai_api_key_env=args.openai_api_key_env,
                collect_resources=False,
            )

        for repetition in range(1, repetitions + 1):
            workspace_metadata = None
            patch_metadata = None
            task_metadata = None
            verify_metadata = None
            repo_task_metadata = None
            scoring_override = None
            prepared_workspace: PreparedWorkspace | None = None
            if case.kind == "repo-task":
                try:
                    prepared_workspace = prepare_repo_task_workspace(
                        pack,
                        case,
                        out_dir,
                        repetition,
                    )
                    workspace_metadata = workspace_record(prepared_workspace, out_dir)
                except WorkspaceError as exc:
                    raise SystemExit(str(exc)) from exc
            request_path, response_path = reporter.measured_paths(
                case,
                repetition,
                repetitions,
            )
            result, sample = _run_case(
                adapter,
                pack,
                case,
                model=args.model,
                endpoint=args.endpoint,
                request_path=request_path,
                response_path=response_path,
                openai_stream_usage=args.openai_stream_usage,
                openai_api_key_env=args.openai_api_key_env,
            )
            if prepared_workspace is not None:
                harness_id = (
                    case.harness.id
                    if case.harness is not None
                    and case.harness.id != PUBLIC_HARNESS_EXTERNAL_AGENT
                    else None
                )
                external_process_harness = (
                    external_agent_harness
                    if case.harness is not None
                    and case.harness.id == PUBLIC_HARNESS_EXTERNAL_AGENT
                    else None
                )
                external_context_file = None
                if external_process_harness is not None:
                    external_context_file = external_agent_context_path(
                        out_dir,
                        case,
                        repetition,
                    )
                    model_call_log_file = external_agent_model_call_log_path(
                        out_dir,
                        case,
                        repetition,
                    )
                    task_paths = task_artifact_paths(out_dir, case, repetition)
                    try:
                        context = build_external_agent_context(
                            pack=pack,
                            case=case,
                            prepared_workspace=prepared_workspace,
                            output_dir=out_dir,
                            repetition=repetition,
                            task_paths=task_paths,
                            adapter_id=adapter.name,
                            model=args.model,
                            endpoint=args.endpoint,
                            adapter_defaults=_effective_adapter_defaults(
                                adapter,
                                pack,
                                args.openai_stream_usage,
                                args.openai_api_key_env,
                            ),
                            run_metadata_path=persisted_run_metadata_path,
                            model_call_log_path=model_call_log_file,
                        )
                        write_external_agent_context(external_context_file, context)
                    except ExternalAgentContextError as exc:
                        raise SystemExit(str(exc)) from exc
                try:
                    task_metadata = run_repo_task_executor(
                        TaskExecutionRequest(
                            output_dir=out_dir,
                            case=case,
                            repetition=repetition,
                            workspace=prepared_workspace.path,
                            model_output_text=result.output_text,
                            harness_id=harness_id,
                            task_timeout_s=(
                                case.harness.timeout_s
                                if case.harness is not None
                                else None
                            ),
                            external_process_harness=external_process_harness,
                            external_context_path=external_context_file,
                        )
                    )
                    patch_metadata = capture_workspace_patch(
                        prepared_workspace,
                        out_dir,
                        case,
                        repetition,
                    )
                except TaskError as exc:
                    raise SystemExit(str(exc)) from exc
                except PatchError as exc:
                    raise SystemExit(str(exc)) from exc
            scoring = _effective_scoring(pack, case)
            if scoring is not None and scoring.mode == "verify-script":
                if prepared_workspace is None or patch_metadata is None:
                    raise SystemExit(
                        "scoring mode 'verify-script' requires a measured "
                        f"repo-task workspace for case {case.id!r}"
                    )
                try:
                    timeout_s = (
                        scoring.timeout_s
                        if scoring.timeout_s is not None
                        else DEFAULT_VERIFY_TIMEOUT_S
                    )
                    verifier_result = run_repo_task_verifier(
                        pack=pack,
                        case=case,
                        scoring=scoring,
                        prepared_workspace=prepared_workspace,
                        patch_path=out_dir / patch_metadata["path"],
                        output_dir=out_dir,
                        repetition=repetition,
                        timeout_s=timeout_s,
                    )
                except VerifierError as exc:
                    raise SystemExit(str(exc)) from exc
                verify_metadata = verifier_result.verify
                repo_task_metadata = verifier_result.repo_task
                scoring_override = verifier_result.scoring
            reporter.record(
                case,
                result,
                sample,
                repetition=repetition if repetitions > 1 else None,
                workspace=workspace_metadata,
                patch=patch_metadata,
                task=task_metadata,
                verify=verify_metadata,
                repo_task=repo_task_metadata,
                scoring_override=scoring_override,
            )

    reporter.write_hardware(hardware)
    reporter.write_summary(hardware, run_metadata=run_metadata)

    print(str(out_dir))
    return 0


def _cmd_compare(args: argparse.Namespace) -> int:
    if len(args.result_dirs) < 2:
        raise SystemExit("benchpack compare requires at least two result directories")
    try:
        runs = [load_result_run(path) for path in args.result_dirs]
    except CompareError as exc:
        raise SystemExit(str(exc)) from exc
    print(render_comparison(runs))
    return 0


def _cmd_report(args: argparse.Namespace) -> int:
    try:
        if args.report_set is not None and args.result_dirs:
            raise ReportError(
                "benchpack report accepts either --set or result directories, not both"
            )
        if args.report_set is None and not args.result_dirs:
            raise ReportError(
                "benchpack report requires at least one result directory or --set"
            )
        result_dirs = (
            load_report_set(args.report_set)
            if args.report_set is not None
            else args.result_dirs
        )
        runs = load_report_runs(result_dirs)
        output = render_report(runs)
    except ReportError as exc:
        raise SystemExit(str(exc)) from exc
    print(output)
    return 0


def _cmd_registry_import(args: argparse.Namespace) -> int:
    try:
        summaries = import_result_dirs(args.result_dirs, args.db)
    except RegistryError as exc:
        raise SystemExit(str(exc)) from exc
    for summary in summaries:
        row_word = "row" if summary.rows_imported == 1 else "rows"
        print(
            "imported {rows} {row_word} from {result_dir} into run_id {run_id}".format(
                rows=summary.rows_imported,
                row_word=row_word,
                result_dir=summary.result_dir,
                run_id=summary.run_id,
            )
        )
    return 0


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="benchpack")
    sub = parser.add_subparsers(dest="command", required=True)

    run = sub.add_parser("run", help="Run a benchpack against an adapter/endpoint")
    run.add_argument("pack", help="Pack name (under benchpacks/) or pack directory")
    run.add_argument("--adapter", required=True, help="Adapter name (openai-chat, ollama-generate)")
    run.add_argument("--model", required=True, help="Model identifier passed to the adapter")
    run.add_argument("--endpoint", default=None, help="Endpoint URL (adapter-specific default if omitted)")
    run.add_argument("--out", default=None, help="Output directory (default: results/<date>-<host-label>/)")
    run.add_argument("--host-label", default=None, help="Host label override for the default --out path")
    run.add_argument(
        "--run-metadata",
        default=None,
        help="Path to a JSON object persisted as run-metadata.json",
    )
    run.add_argument(
        "--openai-stream-usage",
        choices=(OPENAI_STREAM_USAGE_INCLUDE, OPENAI_STREAM_USAGE_OMIT),
        default=OPENAI_STREAM_USAGE_INCLUDE,
        help=(
            "For openai-chat streaming requests, include "
            "stream_options.include_usage or omit stream_options entirely "
            "(default: include)"
        ),
    )
    run.add_argument(
        "--openai-api-key-env",
        default=None,
        help=(
            "For openai-chat requests, read the bearer token from this named "
            "environment variable and send it as Authorization: Bearer <token>"
        ),
    )
    run.add_argument(
        "--force",
        action="store_true",
        help="Delete the output directory if a previous run.jsonl exists",
    )

    compare = sub.add_parser("compare", help="Compare existing result directories")
    compare.add_argument(
        "result_dirs",
        nargs="+",
        help="Result directories containing run.jsonl",
    )

    report = sub.add_parser(
        "report",
        help="Render a read-only Markdown report from existing result directories",
    )
    report.add_argument(
        "result_dirs",
        nargs="*",
        help="Result directories containing run.jsonl",
    )
    report.add_argument(
        "--set",
        dest="report_set",
        default=None,
        help="TOML report-set manifest with result_dirs entries",
    )

    registry = sub.add_parser(
        "registry",
        help="Manage a local read-only index over existing result directories",
    )
    registry_sub = registry.add_subparsers(dest="registry_command", required=True)
    registry_import = registry_sub.add_parser(
        "import",
        help="Import existing result directories into a local SQLite registry",
    )
    registry_import.add_argument(
        "--db",
        required=True,
        help="SQLite registry database path to create or update",
    )
    registry_import.add_argument(
        "result_dirs",
        nargs="+",
        help="Result directories containing run.jsonl",
    )
    return parser


def main(argv: list[str] | None = None) -> int:
    parser = _build_parser()
    args = parser.parse_args(argv)
    if args.command == "run":
        return _cmd_run(args)
    if args.command == "compare":
        return _cmd_compare(args)
    if args.command == "report":
        return _cmd_report(args)
    if args.command == "registry":
        if args.registry_command == "import":
            return _cmd_registry_import(args)
        parser.error(f"unknown registry command: {args.registry_command}")
    parser.error(f"unknown command: {args.command}")
    return 2


if __name__ == "__main__":  # pragma: no cover
    sys.exit(main())
