from __future__ import annotations

import argparse
import importlib.util
import json
from pathlib import Path


EXPECTED = "Hello, Ada!"


def _load_greeter(workspace: Path):
    module_path = workspace / "greeter.py"
    spec = importlib.util.spec_from_file_location("benchpack_fixture_greeter", module_path)
    if spec is None or spec.loader is None:
        raise RuntimeError(f"could not load module from {module_path}")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--workspace", required=True)
    parser.add_argument("--case", required=True)
    parser.add_argument("--pack-id", required=True)
    parser.add_argument("--pack-version", required=True)
    parser.add_argument("--source-fixture-id", required=True)
    parser.add_argument("--patch", required=True)
    parser.add_argument("--output", required=True)
    args = parser.parse_args()

    workspace = Path(args.workspace)
    patch_path = Path(args.patch)
    output_path = Path(args.output)

    payload = {
        "case": args.case,
        "pack_id": args.pack_id,
        "pack_version": args.pack_version,
        "source_fixture_id": args.source_fixture_id,
        "expected": EXPECTED,
        "patch_exists": patch_path.is_file(),
        "patch_bytes": patch_path.stat().st_size if patch_path.is_file() else 0,
    }

    try:
        module = _load_greeter(workspace)
        actual = module.greet("Ada")
        payload["actual"] = actual
        payload["passed"] = (
            actual == EXPECTED
            and payload["patch_exists"]
            and payload["patch_bytes"] > 0
        )
    except Exception as exc:
        payload["error"] = str(exc)
        payload["passed"] = False

    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(
        json.dumps(payload, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    return 0 if payload["passed"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
