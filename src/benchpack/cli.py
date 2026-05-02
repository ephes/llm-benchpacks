"""``benchpack`` command-line entry point."""

from __future__ import annotations

import argparse
import re
import shutil
import sys
from datetime import datetime
from pathlib import Path

from .adapters import Adapter, AdapterRequest, get_adapter
from .adapters.openai_chat import (
    OPENAI_STREAM_USAGE_INCLUDE,
    OPENAI_STREAM_USAGE_KEY,
    OPENAI_STREAM_USAGE_OMIT,
)
from .compare import CompareError, load_result_run, render_comparison
from .hardware import collect_hardware, sample_resources
from .packs import (
    Case,
    Pack,
    Scoring,
    load_pack,
    repetitions_from_defaults,
    warmup_from_defaults,
)
from .patches import PatchError, capture_workspace_patch
from .results import RunReporter
from .tasks import TaskError, run_model_patch_task
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
    collect_resources: bool = True,
) -> tuple[object, dict]:
    if case.prompt is None:
        raise SystemExit(f"case {case.id!r} has no 'prompt' field")
    defaults = dict(pack.defaults)
    if adapter.name == "openai-chat":
        defaults[OPENAI_STREAM_USAGE_KEY] = openai_stream_usage
    request = AdapterRequest(
        prompt=case.prompt,
        model=model,
        endpoint=endpoint,
        defaults=defaults,
        request_path=request_path,
        response_path=response_path,
    )
    result = adapter.run(request)
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

    adapter = get_adapter(args.adapter)

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
            )
            if prepared_workspace is not None:
                try:
                    task_metadata = run_model_patch_task(
                        out_dir,
                        case,
                        repetition,
                        prepared_workspace.path,
                        result.output_text,
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
    reporter.write_summary(hardware)

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
    return parser


def main(argv: list[str] | None = None) -> int:
    parser = _build_parser()
    args = parser.parse_args(argv)
    if args.command == "run":
        return _cmd_run(args)
    if args.command == "compare":
        return _cmd_compare(args)
    parser.error(f"unknown command: {args.command}")
    return 2


if __name__ == "__main__":  # pragma: no cover
    sys.exit(main())
