from __future__ import annotations

import argparse
import copy
import importlib.util
import json
from pathlib import Path
from typing import Any


VISIBLE_ROWS = [
    {"sku": "abc-1", "quantity": 4},
    {"sku": " ABC-1 ", "quantity": 3},
    {"sku": "xyz-9", "quantity": 2},
    {"sku": "", "quantity": 99},
]
VISIBLE_REORDER_ROWS = [
    {"sku": "abc-1", "quantity": 4},
    {"sku": " ABC-1 ", "quantity": 3},
    {"sku": "xyz-9", "quantity": 2},
    {"sku": "mno-2", "quantity": 2},
    {"sku": "rst-7", "quantity": 6},
]
EDGE_ROWS = [
    {"sku": "aa-1", "quantity": "2"},
    {"sku": "AA-1", "quantity": 1},
    {"sku": "bb-2", "quantity": 4},
    {"sku": "cc-3", "quantity": 0},
    {"sku": "  ", "quantity": 50},
]


def _load_inventory(workspace: Path):
    module_path = workspace / "inventory.py"
    spec = importlib.util.spec_from_file_location(
        "benchpack_fixture_inventory",
        module_path,
    )
    if spec is None or spec.loader is None:
        raise RuntimeError(f"could not load module from {module_path}")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _check_visible_aggregate(module: Any) -> dict[str, Any]:
    rows = copy.deepcopy(VISIBLE_ROWS)
    original = copy.deepcopy(rows)
    actual = module.aggregate_stock(rows)
    expected = {"ABC-1": 7, "XYZ-9": 2}
    return {
        "name": "aggregate_stock_visible",
        "expected": expected,
        "actual": actual,
        "input_unchanged": rows == original,
        "passed": actual == expected and rows == original,
    }


def _check_visible_reorder(module: Any) -> dict[str, Any]:
    actual = module.reorder_list(copy.deepcopy(VISIBLE_REORDER_ROWS), minimum=5)
    expected = ["MNO-2", "XYZ-9"]
    return {
        "name": "reorder_list_visible",
        "expected": expected,
        "actual": actual,
        "passed": actual == expected,
    }


def _check_edge_aggregate(module: Any) -> dict[str, Any]:
    rows = copy.deepcopy(EDGE_ROWS)
    original = copy.deepcopy(rows)
    aggregate = module.aggregate_stock(rows)
    expected_aggregate = {"AA-1": 3, "BB-2": 4, "CC-3": 0}
    return {
        "name": "hidden_numeric_string_blank_aggregate",
        "expected": expected_aggregate,
        "actual": aggregate,
        "input_unchanged": rows == original,
        "passed": aggregate == expected_aggregate and rows == original,
    }


def _check_edge_reorder(module: Any) -> dict[str, Any]:
    rows = copy.deepcopy(EDGE_ROWS)
    original = copy.deepcopy(rows)
    reorder = module.reorder_list(rows, minimum=4)
    expected_reorder = ["CC-3", "AA-1"]
    return {
        "name": "hidden_strict_threshold_quantity_then_sku_reorder",
        "expected_reorder": expected_reorder,
        "actual_reorder": reorder,
        "input_unchanged": rows == original,
        "passed": reorder == expected_reorder and rows == original,
    }


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

    payload: dict[str, Any] = {
        "case": args.case,
        "pack_id": args.pack_id,
        "pack_version": args.pack_version,
        "source_fixture_id": args.source_fixture_id,
        "patch_exists": patch_path.is_file(),
        "patch_bytes": patch_path.stat().st_size if patch_path.is_file() else 0,
        "checks": [],
    }

    try:
        module = _load_inventory(workspace)
        checks = [
            _check_visible_aggregate(module),
            _check_visible_reorder(module),
            _check_edge_aggregate(module),
            _check_edge_reorder(module),
        ]
        payload["checks"] = checks
        payload["passed"] = (
            all(check["passed"] for check in checks)
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
