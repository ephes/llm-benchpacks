#!/usr/bin/env python3
"""Build a cold-start, clean-lane product-matching fixture from the billiger scrape.

Reads the committed raw scrape (pilot-data/billiger-pilot-offers.csv), drops
confident label noise (clean lane), splits clusters cold-start (train/test
disjoint by product), anonymises ids, samples eval pairs, and writes the fixture
plus verifier-owned hidden labels and a build report. Deterministic given SEED.

See docs/superpowers/specs/2026-06-30-billiger-fixture-builder-design.md.
"""
from __future__ import annotations

import argparse
import csv
import json
import random
import re
import statistics
from collections import defaultdict
from pathlib import Path

SEED = 20260630

_MODEL_RE = re.compile(
    r"\b(galaxy s\d{2}|galaxy a\d{2}|iphone ?\d{1,2}e?|redmi note \d+|pixel \d+|rtx ?\d{4}|rx ?\d{4})\b"
)
_STORAGE_RE = re.compile(r"(\d[\d.,]*)\s?(tb|gb)\b")


def read_offers(path: Path) -> list[dict]:
    with open(path, newline="", encoding="utf-8") as fh:
        return list(csv.DictReader(fh))


def model_tokens(text: str) -> set[str]:
    return {re.sub(r"\s+", "", m) for m in _MODEL_RE.findall(text.lower())}


def storage_caps(text: str) -> set[int]:
    """Normalized STORAGE capacities (in GB) found in a title, for unit-conflict
    detection. Converts TB->GB, strips thousands separators, collapses the
    1000/1024 (and 2000/2048) TB ambiguity, and excludes RAM (sub-64 GB
    magnitudes, or a capacity immediately followed by "RAM")."""
    t = text.lower()
    caps: set[int] = set()
    for m in _STORAGE_RE.finditer(t):
        digits = m.group(1).replace(".", "").replace(",", "")
        if not digits.isdigit():
            continue
        gb = int(digits) * 1000 if m.group(2) == "tb" else int(digits)
        if gb < 64 or t[m.end():m.end() + 5].lstrip().startswith("ram"):
            continue  # likely RAM, not storage
        gb = {1024: 1000, 2048: 2000}.get(gb, gb)
        caps.add(gb)
    return caps


def clean_offers(rows: list[dict]) -> tuple[list[dict], dict]:
    """Clean lane: drop confident cross-model and unit conflicts; flag (keep)
    price outliers and degenerate titles. Returns (kept_rows, report)."""
    by_cluster: dict[str, list[dict]] = defaultdict(list)
    for r in rows:
        by_cluster[r["cluster_id"]].append(r)

    kept: list[dict] = []
    dropped_model = dropped_unit = flagged_price = flagged_degen = 0
    for offers in by_cluster.values():
        label = offers[0]["cluster_label"]
        lab_model = model_tokens(label)
        lab_caps = storage_caps(label)
        prices = [float(o["price_eur"]) for o in offers if o["price_eur"]]
        med = statistics.median(prices) if prices else 0.0
        mad = statistics.median([abs(p - med) for p in prices]) if prices else 0.0
        for o in offers:
            o_model = model_tokens(o["title"])
            if lab_model and o_model and o_model.isdisjoint(lab_model):
                dropped_model += 1
                continue
            o_caps = storage_caps(o["title"])
            if lab_caps and o_caps and o_caps.isdisjoint(lab_caps):
                dropped_unit += 1
                continue
            if o["price_eur"] and mad and abs(float(o["price_eur"]) - med) > 5 * mad:
                flagged_price += 1
            words = [t for t in re.findall(r"[a-z0-9]+", o["title"].lower()) if len(t) > 1]
            if len(words) < 3:
                flagged_degen += 1
            kept.append(o)

    report = {
        "input_offers": len(rows),
        "kept_offers": len(kept),
        "dropped_model_conflict": dropped_model,
        "dropped_unit_conflict": dropped_unit,
        "flagged_price_outlier": flagged_price,
        "flagged_degenerate_title": flagged_degen,
        "dropped_total": dropped_model + dropped_unit,
        "detectable_noise_rate": round((dropped_model + dropped_unit) / max(len(rows), 1), 4),
    }
    return kept, report


def choose_split(rows: list[dict], train_fraction: float, rng: random.Random) -> tuple[set[str], set[str]]:
    """Cold-start split: accumulate whole clusters into train until ~train_fraction
    of offers; the rest are test. Train/test products are disjoint by construction."""
    by_cluster: dict[str, list[dict]] = defaultdict(list)
    for r in rows:
        by_cluster[r["cluster_id"]].append(r)
    clusters = list(by_cluster)
    rng.shuffle(clusters)
    target = train_fraction * len(rows)
    train: set[str] = set()
    n = 0
    for cid in clusters:
        if n >= target:
            break
        train.add(cid)
        n += len(by_cluster[cid])
    test = set(clusters) - train
    return train, test


def anonymize(rows: list[dict], rng: random.Random,
              offer_start: int = 0, cluster_start: int = 0) -> list[dict]:
    """Shuffle rows and reassign opaque sequential offer/cluster ids so public row
    order and id sequence do not encode source cluster structure. New cluster ids
    are assigned in shuffled-encounter order; offers of one source cluster keep a
    shared new cluster id. `offer_start`/`cluster_start` offset the numbering so a
    later split (test) does not reuse an earlier split's (train) ids — the two
    splits share one global id namespace. Other columns are carried through."""
    shuffled = list(rows)
    rng.shuffle(shuffled)
    cluster_map: dict[str, str] = {}
    out: list[dict] = []
    for i, r in enumerate(shuffled, 1):
        src = r["cluster_id"]
        if src not in cluster_map:
            cluster_map[src] = f"c{cluster_start + len(cluster_map) + 1:05d}"
        out.append({**r, "offer_id": f"o{offer_start + i:05d}", "cluster_id": cluster_map[src]})
    return out


def sample_eval_pairs(
    rows: list[dict], n_pos: int, n_hard_neg: int, n_easy_neg: int, rng: random.Random
) -> tuple[list[dict], list[dict]]:
    """Sample eval pairs from test offers: positives within a cluster, hard
    negatives from the same (brand, category) different cluster, easy negatives
    across categories. Returns (pair_rows, label_rows) with hidden labels."""
    by_cluster: dict[str, list[dict]] = defaultdict(list)
    by_bc: dict[tuple, list[dict]] = defaultdict(list)
    by_cat: dict[str, list[dict]] = defaultdict(list)
    for r in rows:
        by_cluster[r["cluster_id"]].append(r)
        by_bc[(r["brand"], r["category_label"])].append(r)
        by_cat[r["category_label"]].append(r)

    pos_pool: list[tuple[dict, dict]] = []
    for members in by_cluster.values():
        for i in range(len(members)):
            for j in range(i + 1, len(members)):
                pos_pool.append((members[i], members[j]))
    rng.shuffle(pos_pool)
    positives = pos_pool[:n_pos]

    seen: set[tuple[str, str]] = set()

    def _key(a: dict, b: dict) -> tuple[str, str]:
        return tuple(sorted([a["offer_id"], b["offer_id"]]))

    hard: list[tuple[dict, dict]] = []
    bc_keys = [k for k, v in by_bc.items() if len({r["cluster_id"] for r in v}) > 1]
    attempts = 0
    while len(hard) < n_hard_neg and bc_keys and attempts < n_hard_neg * 200:
        attempts += 1
        a, b = rng.sample(by_bc[rng.choice(bc_keys)], 2)
        if a["cluster_id"] == b["cluster_id"] or _key(a, b) in seen:
            continue
        seen.add(_key(a, b))
        hard.append((a, b))

    easy: list[tuple[dict, dict]] = []
    cat_keys = list(by_cat)
    attempts = 0
    while len(easy) < n_easy_neg and len(cat_keys) > 1 and attempts < n_easy_neg * 200:
        attempts += 1
        c1, c2 = rng.sample(cat_keys, 2)
        a, b = rng.choice(by_cat[c1]), rng.choice(by_cat[c2])
        if _key(a, b) in seen:
            continue
        seen.add(_key(a, b))
        easy.append((a, b))

    labeled = [(p, 1) for p in positives] + [(p, 0) for p in hard + easy]
    rng.shuffle(labeled)
    pair_rows: list[dict] = []
    label_rows: list[dict] = []
    for i, ((a, b), lab) in enumerate(labeled, 1):
        pid = f"ep{i:06d}"
        pair_rows.append({"pair_id": pid, "offer_id_left": a["offer_id"], "offer_id_right": b["offer_id"]})
        label_rows.append({"pair_id": pid, "label": str(lab)})
    return pair_rows, label_rows


TRAIN_FIELDS = ["offer_id", "title", "shop_name", "price_eur", "brand",
                "category_label", "image_url", "cluster_id", "cluster_label"]
TEST_FIELDS = ["offer_id", "title", "shop_name", "price_eur", "brand",
               "category_label", "image_url"]


def write_fixture_csv(path: Path, rows: list[dict], fieldnames: list[str]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", newline="", encoding="utf-8") as fh:
        writer = csv.DictWriter(fh, fieldnames=fieldnames, lineterminator="\n", extrasaction="ignore")
        writer.writeheader()
        writer.writerows(rows)


def build(in_path: Path, data_dir: Path, verify_dir: Path, train_fraction: float,
          n_pos: int, n_hard_neg: int, n_easy_neg: int, seed: int = SEED) -> dict:
    rng = random.Random(seed)
    raw = read_offers(in_path)
    kept, report = clean_offers(raw)

    train_clusters, test_clusters = choose_split(kept, train_fraction, rng)
    train_src = [r for r in kept if r["cluster_id"] in train_clusters]
    test_src = [r for r in kept if r["cluster_id"] in test_clusters]

    # Train and test share one global id namespace so their offer/cluster ids never
    # collide (test ids start above train's), keeping the splits unambiguously disjoint.
    train = anonymize(train_src, rng)
    train_cluster_count = len({r["cluster_id"] for r in train})
    test = anonymize(test_src, rng, offer_start=len(train), cluster_start=train_cluster_count)

    pair_rows, label_rows = sample_eval_pairs(test, n_pos, n_hard_neg, n_easy_neg, rng)

    write_fixture_csv(data_dir / "train_offers.csv", train, TRAIN_FIELDS)
    write_fixture_csv(data_dir / "test_offers.csv", test, TEST_FIELDS)
    write_fixture_csv(data_dir / "eval_pairs.csv", pair_rows,
                      ["pair_id", "offer_id_left", "offer_id_right"])
    write_fixture_csv(verify_dir / "hidden_test_clusters.csv",
                      [{"offer_id": r["offer_id"], "cluster_id": r["cluster_id"]} for r in test],
                      ["offer_id", "cluster_id"])
    write_fixture_csv(verify_dir / "hidden_eval_pair_labels.csv", label_rows,
                      ["pair_id", "label"])

    report.update({
        "train_offers": len(train), "test_offers": len(test),
        "train_clusters": len(train_clusters), "test_clusters": len(test_clusters),
        "eval_pairs": len(pair_rows),
        "eval_pos": sum(1 for r in label_rows if r["label"] == "1"),
        "eval_neg": sum(1 for r in label_rows if r["label"] == "0"),
        "seed": seed, "train_fraction": train_fraction,
    })
    data_dir.parent.mkdir(parents=True, exist_ok=True)
    (data_dir.parent / "build-report.json").write_text(json.dumps(report, indent=2) + "\n",
                                                       encoding="utf-8")
    return report


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--in", dest="in_path", type=Path,
                    default=Path("benchpacks/product-offer-matching/pilot-data/billiger-pilot-offers.csv"))
    ap.add_argument("--data-dir", type=Path,
                    default=Path("benchpacks/product-offer-matching/fixtures/billiger-matcher-repo/data"))
    ap.add_argument("--verify-dir", type=Path,
                    default=Path("benchpacks/product-offer-matching/verify"))
    ap.add_argument("--train-fraction", type=float, default=0.30)
    ap.add_argument("--pos", type=int, default=5000)
    ap.add_argument("--hard-neg", type=int, default=9000)
    ap.add_argument("--easy-neg", type=int, default=6000)
    ap.add_argument("--seed", type=int, default=SEED)
    args = ap.parse_args()
    report = build(args.in_path, args.data_dir, args.verify_dir, args.train_fraction,
                   args.pos, args.hard_neg, args.easy_neg, args.seed)
    print(json.dumps(report, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
