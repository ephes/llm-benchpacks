"""``benchpack`` command-line entry point."""

from __future__ import annotations

import argparse
import re
import shutil
import sys
from datetime import datetime
from pathlib import Path

from .adapters import Adapter, AdapterRequest, get_adapter
from .hardware import collect_hardware, sample_resources
from .packs import Case, Pack, load_pack
from .results import RunReporter


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
) -> tuple[object, dict]:
    if case.prompt is None:
        raise SystemExit(f"case {case.id!r} has no 'prompt' field")
    request = AdapterRequest(
        prompt=case.prompt,
        model=model,
        endpoint=endpoint,
        defaults=pack.defaults,
        request_path=request_path,
        response_path=response_path,
    )
    result = adapter.run(request)
    sample = sample_resources()
    return result, sample


def _cmd_run(args: argparse.Namespace) -> int:
    pack_dir = _resolve_pack_dir(args.pack)
    pack = load_pack(pack_dir)
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
        request_path, response_path = reporter.case_paths(case)
        result, sample = _run_case(
            adapter,
            pack,
            case,
            model=args.model,
            endpoint=args.endpoint,
            request_path=request_path,
            response_path=response_path,
        )
        reporter.record(case, result, sample)

    reporter.write_hardware(hardware)
    reporter.write_summary(hardware)

    print(str(out_dir))
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
        "--force",
        action="store_true",
        help="Delete the output directory if a previous run.jsonl exists",
    )
    return parser


def main(argv: list[str] | None = None) -> int:
    parser = _build_parser()
    args = parser.parse_args(argv)
    if args.command == "run":
        return _cmd_run(args)
    parser.error(f"unknown command: {args.command}")
    return 2


if __name__ == "__main__":  # pragma: no cover
    sys.exit(main())
