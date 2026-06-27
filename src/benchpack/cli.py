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
from .registry import (
    BUNDLE_PROVENANCE_LABELS,
    RegistryError,
    create_result_bundle,
    export_registry_static_site,
    find_registry_duplicate_runs,
    import_agent_wrap_results,
    import_result_bundles,
    import_result_dirs,
    load_registry_report_runs,
    query_agent_wrap_results,
    query_registry_results,
    validate_result_bundle,
)
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


def _cmd_registry_report(args: argparse.Namespace) -> int:
    try:
        runs = load_registry_report_runs(
            args.db,
            run_ids=args.run_ids,
            labels=args.labels,
        )
        output = render_report(runs)
    except (RegistryError, ReportError) as exc:
        raise SystemExit(str(exc)) from exc
    print(output)
    return 0


def _cmd_registry_duplicates(args: argparse.Namespace) -> int:
    try:
        groups = find_registry_duplicate_runs(args.db)
    except RegistryError as exc:
        raise SystemExit(str(exc)) from exc
    if not groups:
        print("no duplicate run.jsonl artifacts found")
        return 0
    for group in groups:
        print(
            "duplicate run.jsonl sha256 {sha}: {count} runs".format(
                sha=group.run_jsonl_sha256,
                count=len(group.runs),
            )
        )
        for run in group.runs:
            print(
                (
                    "  run_id={run_id} label={label} rows={rows} "
                    "imported_at={imported_at} result_dir={result_dir}"
                ).format(
                    run_id=run.run_id,
                    label=run.label,
                    rows=run.row_count,
                    imported_at=run.imported_at,
                    result_dir=run.result_dir,
                )
            )
    return 0


def _cmd_registry_query(args: argparse.Namespace) -> int:
    try:
        rows = query_registry_results(
            args.db,
            run_ids=args.run_ids,
            labels=args.labels,
            pack_id=args.pack_id,
            case_id=args.case_id,
            adapter=args.adapter,
            model=args.model,
            host_label=args.host_label,
            runtime_name=args.runtime_name,
            model_quantization=args.model_quantization,
            ok=args.ok,
            scoring_passed=args.scoring_passed,
            limit=args.limit,
        )
    except RegistryError as exc:
        raise SystemExit(str(exc)) from exc
    print(json.dumps(rows, indent=2, sort_keys=True))
    return 0


def _cmd_registry_agent_wrap_import(args: argparse.Namespace) -> int:
    try:
        summary = import_agent_wrap_results(args.data, args.db)
    except RegistryError as exc:
        raise SystemExit(str(exc)) from exc
    row_word = "row" if summary.rows_imported == 1 else "rows"
    print(
        "imported {rows} agent-wrap {row_word} from {data_path}".format(
            rows=summary.rows_imported,
            row_word=row_word,
            data_path=summary.data_path,
        )
    )
    return 0


def _cmd_registry_agent_wrap_query(args: argparse.Namespace) -> int:
    try:
        rows = query_agent_wrap_results(
            args.db,
            status=args.status,
            harness=args.harness,
            provider=args.provider,
            model=args.model,
            thinking=args.thinking,
            limit=args.limit,
        )
    except RegistryError as exc:
        raise SystemExit(str(exc)) from exc
    print(json.dumps(rows, indent=2, sort_keys=True))
    return 0


def _cmd_registry_bundle_create(args: argparse.Namespace) -> int:
    try:
        summary = create_result_bundle(
            args.result_dirs,
            args.out,
            provenance=args.provenance,
            force=args.force,
        )
    except RegistryError as exc:
        raise SystemExit(str(exc)) from exc
    run_word = "run" if summary.runs == 1 else "runs"
    file_word = "file" if summary.files == 1 else "files"
    artifact_word = "artifact" if summary.omitted_artifacts == 1 else "artifacts"
    print(
        "created bundle {bundle_dir} with {runs} {run_word}, {files} {file_word}, "
        "{omitted} omitted {artifact_word} ({provenance})".format(
            bundle_dir=summary.bundle_dir,
            runs=summary.runs,
            run_word=run_word,
            files=summary.files,
            file_word=file_word,
            omitted=summary.omitted_artifacts,
            artifact_word=artifact_word,
            provenance=summary.provenance,
        )
    )
    return 0


def _cmd_registry_bundle_validate(args: argparse.Namespace) -> int:
    try:
        summary = validate_result_bundle(args.bundle_dir)
    except RegistryError as exc:
        raise SystemExit(str(exc)) from exc
    run_word = "run" if summary.runs == 1 else "runs"
    file_word = "file" if summary.files == 1 else "files"
    print(
        "validated bundle {bundle_dir}: {runs} {run_word}, {files} {file_word}, "
        "provenance {provenance}".format(
            bundle_dir=summary.bundle_dir,
            runs=summary.runs,
            run_word=run_word,
            files=summary.files,
            file_word=file_word,
            provenance=summary.provenance,
        )
    )
    return 0


def _cmd_registry_bundle_import(args: argparse.Namespace) -> int:
    try:
        summaries = import_result_bundles(args.bundle_dirs, args.db)
    except RegistryError as exc:
        raise SystemExit(str(exc)) from exc
    for summary in summaries:
        row_word = "row" if summary.rows_imported == 1 else "rows"
        print(
            "imported {rows} {row_word} from bundled run {result_dir} into run_id {run_id}".format(
                rows=summary.rows_imported,
                row_word=row_word,
                result_dir=summary.result_dir,
                run_id=summary.run_id,
            )
        )
    return 0


def _cmd_registry_site(args: argparse.Namespace) -> int:
    try:
        summary = export_registry_static_site(
            args.db,
            args.out,
            run_ids=args.run_ids,
            labels=args.labels,
            force=args.force,
        )
    except RegistryError as exc:
        raise SystemExit(str(exc)) from exc
    run_word = "run" if summary.runs == 1 else "runs"
    file_word = "file" if summary.files == 1 else "files"
    print(
        "created registry site {out_dir} with {runs} {run_word}, {files} {file_word}".format(
            out_dir=summary.out_dir,
            runs=summary.runs,
            run_word=run_word,
            files=summary.files,
            file_word=file_word,
        )
    )
    return 0


def _parse_cli_bool(value: str) -> bool:
    if value == "true":
        return True
    if value == "false":
        return False
    raise argparse.ArgumentTypeError("expected 'true' or 'false'")


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
    registry_report = registry_sub.add_parser(
        "report",
        help="Render a Markdown report from indexed registry rows",
    )
    registry_report.add_argument(
        "--db",
        required=True,
        help="SQLite registry database path to read",
    )
    registry_report_selectors = registry_report.add_mutually_exclusive_group()
    registry_report_selectors.add_argument(
        "--run-id",
        dest="run_ids",
        action="append",
        type=int,
        default=None,
        help="Registry run id to include; may be repeated",
    )
    registry_report_selectors.add_argument(
        "--label",
        dest="labels",
        action="append",
        default=None,
        help="Registry run label to include; may be repeated",
    )
    registry_duplicates = registry_sub.add_parser(
        "duplicates",
        help="List imported runs with identical run.jsonl artifacts",
    )
    registry_duplicates.add_argument(
        "--db",
        required=True,
        help="SQLite registry database path to read",
    )
    registry_query = registry_sub.add_parser(
        "query",
        help="Query normalized registry result rows as JSON",
    )
    registry_query.add_argument(
        "--db",
        required=True,
        help="SQLite registry database path to read",
    )
    registry_query_selectors = registry_query.add_mutually_exclusive_group()
    registry_query_selectors.add_argument(
        "--run-id",
        dest="run_ids",
        action="append",
        type=int,
        default=None,
        help="Registry run id to include; may be repeated",
    )
    registry_query_selectors.add_argument(
        "--label",
        dest="labels",
        action="append",
        default=None,
        help="Registry run label to include; may be repeated",
    )
    registry_query.add_argument(
        "--pack",
        dest="pack_id",
        default=None,
        help="Filter rows by pack id",
    )
    registry_query.add_argument(
        "--case",
        dest="case_id",
        default=None,
        help="Filter rows by case id",
    )
    registry_query.add_argument(
        "--adapter",
        default=None,
        help="Filter rows by adapter id",
    )
    registry_query.add_argument(
        "--model",
        default=None,
        help="Filter rows by model id",
    )
    registry_query.add_argument(
        "--host-label",
        default=None,
        help="Filter rows by indexed run metadata host label",
    )
    registry_query.add_argument(
        "--runtime",
        dest="runtime_name",
        default=None,
        help="Filter rows by indexed run metadata runtime name",
    )
    registry_query.add_argument(
        "--quantization",
        dest="model_quantization",
        default=None,
        help="Filter rows by indexed run metadata model quantization",
    )
    registry_query.add_argument(
        "--ok",
        type=_parse_cli_bool,
        default=None,
        help="Filter rows by adapter success: true or false",
    )
    registry_query.add_argument(
        "--scoring-passed",
        type=_parse_cli_bool,
        default=None,
        help="Filter rows by deterministic scoring result: true or false",
    )
    registry_query.add_argument(
        "--limit",
        type=int,
        default=None,
        help="Maximum number of rows to return",
    )
    registry_bundle = registry_sub.add_parser(
        "bundle",
        help="Create, validate, or import compact public result bundles",
    )
    registry_bundle_sub = registry_bundle.add_subparsers(
        dest="registry_bundle_command",
        required=True,
    )
    registry_bundle_create = registry_bundle_sub.add_parser(
        "create",
        help="Create a compact public bundle from result directories",
    )
    registry_bundle_create.add_argument(
        "--out",
        required=True,
        help="Bundle output directory to create",
    )
    registry_bundle_create.add_argument(
        "--provenance",
        choices=tuple(sorted(BUNDLE_PROVENANCE_LABELS)),
        default="self-reported",
        help="Public provenance label for the bundled results",
    )
    registry_bundle_create.add_argument(
        "--force",
        action="store_true",
        help="Replace an existing bundle output path",
    )
    registry_bundle_create.add_argument(
        "result_dirs",
        nargs="+",
        help="Result directories containing run.jsonl",
    )
    registry_bundle_validate = registry_bundle_sub.add_parser(
        "validate",
        help="Validate a compact public result bundle offline",
    )
    registry_bundle_validate.add_argument(
        "bundle_dir",
        help="Bundle directory containing benchpack-bundle.json",
    )
    registry_bundle_import = registry_bundle_sub.add_parser(
        "import",
        help="Validate compact public bundles and import their runs into the registry",
    )
    registry_bundle_import.add_argument(
        "--db",
        required=True,
        help="SQLite registry database path to create or update",
    )
    registry_bundle_import.add_argument(
        "bundle_dirs",
        nargs="+",
        help="Bundle directories containing benchpack-bundle.json",
    )
    registry_agent_wrap = registry_sub.add_parser(
        "agent-wrap",
        help="Import or query normalized one-shot agent-wrap rows",
    )
    registry_agent_wrap_sub = registry_agent_wrap.add_subparsers(
        dest="registry_agent_wrap_command",
        required=True,
    )
    registry_agent_wrap_import = registry_agent_wrap_sub.add_parser(
        "import",
        help="Import normalized one-shot agent-wrap rows into SQLite",
    )
    registry_agent_wrap_import.add_argument(
        "--db",
        required=True,
        help="SQLite registry database path to create or update",
    )
    registry_agent_wrap_import.add_argument(
        "data",
        help="Normalized agent-wrap JSON dataset",
    )
    registry_agent_wrap_query = registry_agent_wrap_sub.add_parser(
        "query",
        help="Query normalized one-shot agent-wrap rows as JSON",
    )
    registry_agent_wrap_query.add_argument(
        "--db",
        required=True,
        help="SQLite registry database path to read",
    )
    registry_agent_wrap_query.add_argument(
        "--status",
        default=None,
        help="Filter by normalized status: pass, fail, or interrupted",
    )
    registry_agent_wrap_query.add_argument(
        "--harness",
        default=None,
        help="Filter by normalized harness id",
    )
    registry_agent_wrap_query.add_argument(
        "--provider",
        default=None,
        help="Filter by normalized provider id",
    )
    registry_agent_wrap_query.add_argument(
        "--model",
        default=None,
        help="Filter by normalized model id",
    )
    registry_agent_wrap_query.add_argument(
        "--thinking",
        default=None,
        help="Filter by normalized thinking level",
    )
    registry_agent_wrap_query.add_argument(
        "--limit",
        type=int,
        default=None,
        help="Maximum number of rows to return",
    )
    registry_site = registry_sub.add_parser(
        "site",
        help="Generate a static read-only site from indexed registry rows",
    )
    registry_site.add_argument(
        "--db",
        required=True,
        help="SQLite registry database path to read",
    )
    registry_site.add_argument(
        "--out",
        required=True,
        help="Output directory for index.html and report.md",
    )
    registry_site_selectors = registry_site.add_mutually_exclusive_group()
    registry_site_selectors.add_argument(
        "--run-id",
        dest="run_ids",
        action="append",
        type=int,
        default=None,
        help="Registry run id to include; may be repeated",
    )
    registry_site_selectors.add_argument(
        "--label",
        dest="labels",
        action="append",
        default=None,
        help="Registry run label to include; may be repeated",
    )
    registry_site.add_argument(
        "--force",
        action="store_true",
        help="Replace an existing site output path",
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
        if args.registry_command == "report":
            return _cmd_registry_report(args)
        if args.registry_command == "duplicates":
            return _cmd_registry_duplicates(args)
        if args.registry_command == "query":
            return _cmd_registry_query(args)
        if args.registry_command == "bundle":
            if args.registry_bundle_command == "create":
                return _cmd_registry_bundle_create(args)
            if args.registry_bundle_command == "validate":
                return _cmd_registry_bundle_validate(args)
            if args.registry_bundle_command == "import":
                return _cmd_registry_bundle_import(args)
            parser.error(f"unknown registry bundle command: {args.registry_bundle_command}")
        if args.registry_command == "agent-wrap":
            if args.registry_agent_wrap_command == "import":
                return _cmd_registry_agent_wrap_import(args)
            if args.registry_agent_wrap_command == "query":
                return _cmd_registry_agent_wrap_query(args)
            parser.error(
                f"unknown registry agent-wrap command: {args.registry_agent_wrap_command}"
            )
        if args.registry_command == "site":
            return _cmd_registry_site(args)
        parser.error(f"unknown registry command: {args.registry_command}")
    parser.error(f"unknown command: {args.command}")
    return 2


if __name__ == "__main__":  # pragma: no cover
    sys.exit(main())
