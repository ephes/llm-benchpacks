#!/usr/bin/env python3
from __future__ import annotations

import argparse
import csv
import gzip
import json
import random
import zipfile
from collections import Counter
from pathlib import Path
from typing import Any


SEED = 20260627
TRAIN_FILE = "wdcproducts20cc80rnd000un_train_small.json.gz"
TEST_FILE = "wdcproducts20cc80rnd000un_gs.json.gz"
FEATURE_FIELDS = [
    "brand_left",
    "title_left",
    "description_left",
    "price_left",
    "priceCurrency_left",
    "brand_right",
    "title_right",
    "description_right",
    "price_right",
    "priceCurrency_right",
]


def _load_jsonl_gz(zip_path: Path, member_name: str) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    with zipfile.ZipFile(zip_path) as archive:
        with archive.open(member_name) as raw:
            with gzip.open(raw, "rt", encoding="utf-8") as handle:
                for line in handle:
                    if line.strip():
                        loaded = json.loads(line)
                        if isinstance(loaded, dict):
                            rows.append(loaded)
    return rows


def _sample(
    rows: list[dict[str, Any]],
    *,
    positive: int,
    hard_negative: int,
    easy_negative: int,
    rng: random.Random,
) -> list[dict[str, Any]]:
    positives = [row for row in rows if row["label"] == 1]
    hard_negatives = [
        row
        for row in rows
        if row["label"] == 0 and bool(row.get("is_hard_negative"))
    ]
    easy_negatives = [
        row
        for row in rows
        if row["label"] == 0 and not bool(row.get("is_hard_negative"))
    ]
    selected = (
        rng.sample(positives, positive)
        + rng.sample(hard_negatives, hard_negative)
        + rng.sample(easy_negatives, easy_negative)
    )
    rng.shuffle(selected)
    return selected


def _clean(value: object) -> str:
    if value is None:
        return ""
    return str(value).replace("\r", " ").replace("\n", " ").strip()


def _write_pairs(path: Path, rows: list[dict[str, Any]], *, include_label: bool) -> None:
    fieldnames = ["pair_id", *FEATURE_FIELDS]
    if include_label:
        fieldnames.append("label")
    with path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=fieldnames, lineterminator="\n")
        writer.writeheader()
        for index, row in enumerate(rows, start=1):
            output = {"pair_id": f"p{index:04d}"}
            for field in FEATURE_FIELDS:
                output[field] = _clean(row.get(field))
            if include_label:
                output["label"] = str(row["label"])
            writer.writerow(output)


def _write_labels(path: Path, rows: list[dict[str, Any]]) -> None:
    with path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(
            handle,
            fieldnames=["pair_id", "label"],
            lineterminator="\n",
        )
        writer.writeheader()
        for index, row in enumerate(rows, start=1):
            writer.writerow({"pair_id": f"p{index:04d}", "label": str(row["label"])})


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--wdc-20pair-zip", required=True)
    parser.add_argument("--pack-dir", default=Path(__file__).parents[1])
    args = parser.parse_args()

    zip_path = Path(args.wdc_20pair_zip)
    pack_dir = Path(args.pack_dir)
    rng = random.Random(SEED)

    train_source = _load_jsonl_gz(zip_path, TRAIN_FILE)
    test_source = _load_jsonl_gz(zip_path, TEST_FILE)
    train_rows = _sample(
        train_source,
        positive=50,
        hard_negative=75,
        easy_negative=75,
        rng=rng,
    )
    test_rows = _sample(
        test_source,
        positive=30,
        hard_negative=60,
        easy_negative=30,
        rng=rng,
    )

    data_dir = pack_dir / "fixtures" / "matcher-repo" / "data"
    verify_dir = pack_dir / "verify"
    _write_pairs(data_dir / "train.csv", train_rows, include_label=True)
    _write_pairs(data_dir / "test_pairs.csv", test_rows, include_label=False)
    _write_labels(verify_dir / "hidden_labels.csv", test_rows)

    print(
        json.dumps(
            {
                "seed": SEED,
                "train_source": TRAIN_FILE,
                "test_source": TEST_FILE,
                "train_labels": Counter(row["label"] for row in train_rows),
                "test_labels": Counter(row["label"] for row in test_rows),
            },
            default=dict,
            sort_keys=True,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
