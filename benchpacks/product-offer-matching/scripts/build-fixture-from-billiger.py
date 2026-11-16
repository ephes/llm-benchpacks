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
import io
import os
import fcntl
import stat
import shutil
import tempfile
from bisect import bisect_right
from contextlib import ExitStack
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

    # Sample uniformly without replacement over compact cluster pair counts.
    # Unrank each selected index in the lexicographic upper triangle.
    groups = []
    ends = []
    total = 0
    for members in by_cluster.values():
        count = len(members) * (len(members) - 1) // 2
        if count:
            groups.append(members)
            total += count
            ends.append(total)
    positives = []
    for rank in rng.sample(range(total), min(max(n_pos, 0), total)):
        group = bisect_right(ends, rank)
        local = rank - (ends[group - 1] if group else 0)
        members = groups[group]
        n = len(members)
        lo, hi = 0, n - 1
        while lo + 1 < hi:
            mid = (lo + hi) // 2
            if mid * (2 * n - mid - 1) // 2 <= local:
                lo = mid
            else:
                hi = mid
        offset = local - lo * (2 * n - lo - 1) // 2
        positives.append((members[lo], members[lo + 1 + offset]))

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


# image_url is deliberately excluded from the published offers: it is the canonical
# billiger product image (one per cluster), so it leaks the gold cluster id like a
# reliable identifier (decision D-038, analogous to GTIN in D-035). It stays in the
# raw scrape for provenance but never reaches the matcher.
TRAIN_FIELDS = ["offer_id", "title", "shop_name", "price_eur", "brand",
                "category_label", "cluster_id", "cluster_label"]
TEST_FIELDS = ["offer_id", "title", "shop_name", "price_eur", "brand",
               "category_label"]


def write_fixture_csv(path: Path, rows: list[dict], fieldnames: list[str]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", newline="", encoding="utf-8") as fh:
        writer = csv.DictWriter(fh, fieldnames=fieldnames, lineterminator="\n", extrasaction="ignore")
        writer.writeheader()
        writer.writerows(rows)


def _publish_fixture(files: list[tuple[Path, bytes]]) -> None:
    """Serialize writers, stage all bytes, and compensate a failed publication.

    Locks stay named after exit. Stages live on each destination filesystem;
    rollback failures retain all backups and a manifest for manual recovery.
    Readers should consume a finished build, not read while it is publishing.
    """
    files = [(target.parent.resolve() / target.name, data) for target, data in files]
    if len({target for target, _ in files}) != len(files):
        raise ValueError("duplicate fixture destination")
    parents = sorted({target.parent for target, _ in files})
    stages = {}
    published = []
    keep_recovery = False
    with ExitStack() as locks:
        for parent in parents:
            parent.mkdir(parents=True, exist_ok=True)
            lock_path = parent / ".billiger-publication.lock"
            fd = os.open(lock_path, os.O_RDWR | os.O_CREAT | os.O_NOFOLLOW | os.O_NONBLOCK, 0o600)
            locks.callback(os.close, fd)
            info = os.fstat(fd)
            if not stat.S_ISREG(info.st_mode) or info.st_nlink != 1:
                raise ValueError("invalid fixture publication lock")
            fcntl.flock(fd, fcntl.LOCK_EX)
            named = lock_path.lstat()
            if (info.st_dev, info.st_ino) != (named.st_dev, named.st_ino):
                raise ValueError("fixture publication lock changed")
        try:
            for parent in parents:
                stages[parent] = Path(tempfile.mkdtemp(prefix=".billiger-stage-", dir=parent))
            manifest = []
            for index, (target, data) in enumerate(files):
                stage = stages[target.parent]
                new, old = stage / f"new-{index}", stage / f"old-{index}"
                new.write_bytes(data)
                if new.read_bytes() != data:
                    raise ValueError("staged fixture bytes changed")
                if target.is_symlink() or (target.exists() and not target.is_file()):
                    raise ValueError("fixture target must be regular")
                existed = target.exists()
                if existed:
                    shutil.copy2(target, old)
                manifest.append({"target": str(target), "existed": existed,
                                 "backup": str(old), "staged": str(new)})
            for stage in stages.values():
                (stage / "manifest.json").write_text(json.dumps(manifest), encoding="utf-8")
            try:
                for index, (target, _) in enumerate(files):
                    os.replace(stages[target.parent] / f"new-{index}", target)
                    published.append((index, target))
            except BaseException:
                failed = False
                for index, target in reversed(published):
                    try:
                        old = stages[target.parent] / f"old-{index}"
                        if old.exists():
                            os.replace(old, target)
                        else:
                            target.unlink()
                    except OSError:
                        failed = True
                if failed:
                    keep_recovery = True
                    locations = ", ".join(str(stage) for stage in stages.values())
                    raise RuntimeError(f"fixture rollback failed; recovery retained at {locations}")
                raise
        finally:
            if not keep_recovery:
                for stage in stages.values():
                    shutil.rmtree(stage)


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

    report.update({
        "train_offers": len(train), "test_offers": len(test),
        "train_clusters": len(train_clusters), "test_clusters": len(test_clusters),
        "eval_pairs": len(pair_rows),
        "eval_pos": sum(1 for r in label_rows if r["label"] == "1"),
        "eval_neg": sum(1 for r in label_rows if r["label"] == "0"),
        "seed": seed, "train_fraction": train_fraction,
    })
    specs = [
        (data_dir / "train_offers.csv", train, TRAIN_FIELDS),
        (data_dir / "test_offers.csv", test, TEST_FIELDS),
        (data_dir / "eval_pairs.csv", pair_rows, ["pair_id", "offer_id_left", "offer_id_right"]),
        (verify_dir / "hidden_test_clusters.csv", test, ["offer_id", "cluster_id"]),
        (verify_dir / "hidden_eval_pair_labels.csv", label_rows, ["pair_id", "label"]),
    ]
    files = []
    for target, rows, fields in specs:
        text = io.StringIO(newline="")
        writer = csv.DictWriter(text, fieldnames=fields, lineterminator="\n", extrasaction="ignore")
        writer.writeheader()
        writer.writerows(rows)
        encoded = text.getvalue().encode("utf-8")
        projected = [{key: row[key] for key in fields} for row in rows]
        if list(csv.DictReader(io.StringIO(encoded.decode("utf-8")))) != projected:
            raise ValueError("fixture serialization validation failed")
        files.append((target, encoded))
    files.append((data_dir.parent / "build-report.json",
                  (json.dumps(report, indent=2, allow_nan=False) + "\n").encode("utf-8")))
    _publish_fixture(files)
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
