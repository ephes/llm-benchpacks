#!/usr/bin/env python3
from __future__ import annotations

import argparse
import csv
import json
import random
import zipfile
from collections import Counter, defaultdict
from pathlib import Path
from typing import Any


SEED = 20260628
SOURCE_MEMBER = "pricerunner_aggregate.csv"


def _clean(value: object) -> str:
    if value is None:
        return ""
    return str(value).replace("\r", " ").replace("\n", " ").strip()


def _read_rows(zip_path: Path, member_name: str) -> list[dict[str, str]]:
    rows: list[dict[str, str]] = []
    with zipfile.ZipFile(zip_path) as archive:
        with archive.open(member_name) as raw:
            text = (line.decode("utf-8-sig") for line in raw)
            for row in csv.DictReader(text):
                rows.append({key.strip(): _clean(value) for key, value in row.items()})
    return rows


def _local_offer(
    row: dict[str, str],
    *,
    index: int,
    include_cluster: bool,
) -> dict[str, str]:
    output = {
        "offer_id": f"o{index:05d}",
        "title": row["Product Title"],
        "merchant_id": row["Merchant ID"],
        "category_id": row["Category ID"],
        "category_label": row["Category Label"],
    }
    if include_cluster:
        output["cluster_id"] = f"c{int(row['Cluster ID']):05d}"
        output["cluster_label"] = row["Cluster Label"]
    return output


def _write_csv(path: Path, rows: list[dict[str, str]], fieldnames: list[str]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=fieldnames, lineterminator="\n")
        writer.writeheader()
        for row in rows:
            writer.writerow({field: row.get(field, "") for field in fieldnames})


def _choose_split(
    rows: list[dict[str, str]],
    *,
    train_offer_target: int,
    rng: random.Random,
) -> tuple[set[str], set[str]]:
    by_cluster: dict[str, list[dict[str, str]]] = defaultdict(list)
    for row in rows:
        by_cluster[row["Cluster ID"]].append(row)
    clusters = list(by_cluster)
    rng.shuffle(clusters)
    train_clusters: set[str] = set()
    train_offers = 0
    for cluster_id in clusters:
        if train_offers >= train_offer_target:
            break
        train_clusters.add(cluster_id)
        train_offers += len(by_cluster[cluster_id])
    return train_clusters, set(clusters) - train_clusters


def _sample_eval_pairs(
    test_rows: list[dict[str, str]],
    *,
    positive_pairs: int,
    hard_negative_pairs: int,
    easy_negative_pairs: int,
    rng: random.Random,
) -> tuple[list[dict[str, str]], list[dict[str, str]]]:
    by_cluster: dict[str, list[dict[str, str]]] = defaultdict(list)
    by_category: dict[str, list[dict[str, str]]] = defaultdict(list)
    for row in test_rows:
        by_cluster[row["Cluster ID"]].append(row)
        by_category[row["Category ID"]].append(row)

    positives: list[tuple[dict[str, str], dict[str, str]]] = []
    for cluster_rows in by_cluster.values():
        if len(cluster_rows) < 2:
            continue
        for left_index, left in enumerate(cluster_rows):
            for right in cluster_rows[left_index + 1 :]:
                positives.append((left, right))
    rng.shuffle(positives)
    positives = positives[:positive_pairs]

    hard_negatives: list[tuple[dict[str, str], dict[str, str]]] = []
    hard_seen: set[tuple[str, str]] = set()
    attempts = 0
    category_ids = [category_id for category_id, values in by_category.items() if len(values) > 1]
    while len(hard_negatives) < hard_negative_pairs and attempts < hard_negative_pairs * 80:
        attempts += 1
        category_id = rng.choice(category_ids)
        left, right = rng.sample(by_category[category_id], 2)
        if left["Cluster ID"] == right["Cluster ID"]:
            continue
        key = tuple(sorted([left["Product ID"], right["Product ID"]]))
        if key in hard_seen:
            continue
        hard_seen.add(key)
        hard_negatives.append((left, right))

    easy_negatives: list[tuple[dict[str, str], dict[str, str]]] = []
    easy_seen: set[tuple[str, str]] = set()
    attempts = 0
    while len(easy_negatives) < easy_negative_pairs and attempts < easy_negative_pairs * 80:
        attempts += 1
        left, right = rng.sample(test_rows, 2)
        if left["Cluster ID"] == right["Cluster ID"]:
            continue
        key = tuple(sorted([left["Product ID"], right["Product ID"]]))
        if key in easy_seen or key in hard_seen:
            continue
        easy_seen.add(key)
        easy_negatives.append((left, right))

    pairs = [(left, right, 1) for left, right in positives]
    pairs += [(left, right, 0) for left, right in hard_negatives]
    pairs += [(left, right, 0) for left, right in easy_negatives]
    rng.shuffle(pairs)

    public_rows: list[dict[str, str]] = []
    hidden_rows: list[dict[str, str]] = []
    for index, (left, right, label) in enumerate(pairs, start=1):
        pair_id = f"ep{index:06d}"
        public_rows.append(
            {
                "pair_id": pair_id,
                "offer_id_left": left["_local_offer_id"],
                "offer_id_right": right["_local_offer_id"],
            }
        )
        hidden_rows.append({"pair_id": pair_id, "label": str(label)})
    return public_rows, hidden_rows


def _summarize(rows: list[dict[str, str]]) -> dict[str, Any]:
    clusters = Counter(row["Cluster ID"] for row in rows)
    categories = Counter(row["Category Label"] for row in rows)
    return {
        "offers": len(rows),
        "clusters": len(clusters),
        "singleton_clusters": sum(1 for count in clusters.values() if count == 1),
        "max_cluster_size": max(clusters.values()) if clusters else 0,
        "categories": dict(sorted(categories.items())),
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--pricerunner-zip", required=True)
    parser.add_argument("--pack-dir", default=Path(__file__).parents[1])
    parser.add_argument("--member-name", default=SOURCE_MEMBER)
    parser.add_argument("--seed", type=int, default=SEED)
    parser.add_argument("--train-offers", type=int, default=10_000)
    parser.add_argument("--eval-positive-pairs", type=int, default=5_000)
    parser.add_argument("--eval-hard-negative-pairs", type=int, default=12_000)
    parser.add_argument("--eval-easy-negative-pairs", type=int, default=3_000)
    args = parser.parse_args()

    rng = random.Random(args.seed)
    rows = _read_rows(Path(args.pricerunner_zip), args.member_name)
    train_clusters, test_clusters = _choose_split(
        rows,
        train_offer_target=args.train_offers,
        rng=rng,
    )
    train_source = [row for row in rows if row["Cluster ID"] in train_clusters]
    test_source = [row for row in rows if row["Cluster ID"] in test_clusters]
    rng.shuffle(train_source)
    rng.shuffle(test_source)

    for index, row in enumerate(train_source + test_source, start=1):
        local_offer_id = f"o{index:05d}"
        row["_local_offer_id"] = local_offer_id

    train_rows = [
        _local_offer(row, index=index, include_cluster=True)
        for index, row in enumerate(train_source, start=1)
    ]
    test_rows = [
        _local_offer(row, index=index, include_cluster=False)
        for index, row in enumerate(test_source, start=len(train_rows) + 1)
    ]
    hidden_cluster_rows = [
        {
            "offer_id": row["_local_offer_id"],
            "cluster_id": f"c{int(row['Cluster ID']):05d}",
        }
        for row in test_source
    ]
    eval_pairs, hidden_pair_labels = _sample_eval_pairs(
        test_source,
        positive_pairs=args.eval_positive_pairs,
        hard_negative_pairs=args.eval_hard_negative_pairs,
        easy_negative_pairs=args.eval_easy_negative_pairs,
        rng=rng,
    )

    pack_dir = Path(args.pack_dir)
    data_dir = pack_dir / "fixtures" / "matcher-repo" / "data"
    verify_dir = pack_dir / "verify"
    _write_csv(
        data_dir / "train_offers.csv",
        train_rows,
        [
            "offer_id",
            "title",
            "merchant_id",
            "category_id",
            "category_label",
            "cluster_id",
            "cluster_label",
        ],
    )
    _write_csv(
        data_dir / "test_offers.csv",
        test_rows,
        ["offer_id", "title", "merchant_id", "category_id", "category_label"],
    )
    _write_csv(
        data_dir / "eval_pairs.csv",
        eval_pairs,
        ["pair_id", "offer_id_left", "offer_id_right"],
    )
    _write_csv(
        verify_dir / "hidden_test_clusters.csv",
        hidden_cluster_rows,
        ["offer_id", "cluster_id"],
    )
    _write_csv(
        verify_dir / "hidden_eval_pair_labels.csv",
        hidden_pair_labels,
        ["pair_id", "label"],
    )

    print(
        json.dumps(
            {
                "seed": args.seed,
                "source_member": args.member_name,
                "source_rows": len(rows),
                "source": _summarize(rows),
                "train": _summarize(train_source),
                "test": _summarize(test_source),
                "eval_pairs": {
                    "rows": len(eval_pairs),
                    "labels": dict(Counter(row["label"] for row in hidden_pair_labels)),
                },
            },
            sort_keys=True,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
