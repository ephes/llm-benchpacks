from __future__ import annotations

import csv
import importlib.util
import json
import random
from pathlib import Path

BUILDER_PATH = Path("benchpacks/product-offer-matching/scripts/build-fixture-from-billiger.py")


def load_builder():
    spec = importlib.util.spec_from_file_location("build_fixture_from_billiger", BUILDER_PATH)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def write_csv(path: Path, rows: list[dict], fieldnames: list[str]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", newline="", encoding="utf-8") as fh:
        writer = csv.DictWriter(fh, fieldnames=fieldnames, lineterminator="\n")
        writer.writeheader()
        writer.writerows(rows)


def test_read_offers_reads_rows(tmp_path):
    mod = load_builder()
    csv_path = tmp_path / "raw.csv"
    write_csv(
        csv_path,
        [{"offer_id": "b00001", "title": "Apple iPhone 17 256GB", "cluster_id": "c1"}],
        ["offer_id", "title", "cluster_id"],
    )
    rows = mod.read_offers(csv_path)
    assert rows == [{"offer_id": "b00001", "title": "Apple iPhone 17 256GB", "cluster_id": "c1"}]


def test_model_tokens_extracts_and_normalizes():
    mod = load_builder()
    assert mod.model_tokens("Samsung Galaxy S26 Ultra 256 GB Black") == {"galaxys26"}
    assert mod.model_tokens("Apple iPhone 17 256GB Nebelblau") == {"iphone17"}
    assert mod.model_tokens("Gigabyte RTX 5070 Gaming OC") == {"rtx5070"}
    assert mod.model_tokens("no model here") == set()


def test_unit_tokens_extracts_storage():
    mod = load_builder()
    assert mod.unit_tokens("iPhone 17 256GB") == {"256gb"}
    assert mod.unit_tokens("Galaxy 12 GB RAM 512 GB Black") == {"12gb", "512gb"}
    assert mod.unit_tokens("Sony WH-1000XM5") == set()


def _offer(oid, title, cid, label, price="100.00", brand="Apple", cat="Handys"):
    return {"offer_id": oid, "title": title, "shop_name": "shopX", "price_eur": price,
            "brand": brand, "category_label": cat, "image_url": "http://img",
            "cluster_id": cid, "cluster_label": label, "source_query": "q"}


def test_clean_offers_drops_cross_model_conflict():
    mod = load_builder()
    rows = [
        _offer("b1", "Samsung Galaxy S26 Ultra 256GB", "c1", "Galaxy S26 Ultra 256 GB", brand="Samsung"),
        _offer("b2", "Samsung Galaxy S26 Ultra 256GB Black", "c1", "Galaxy S26 Ultra 256 GB", brand="Samsung"),
        _offer("b3", "Samsung Galaxy S25 Ultra 256GB", "c1", "Galaxy S26 Ultra 256 GB", brand="Samsung"),
    ]
    kept, report = mod.clean_offers(rows)
    kept_ids = {r["offer_id"] for r in kept}
    assert kept_ids == {"b1", "b2"}  # b3 (S25 in S26 cluster) dropped
    assert report["dropped_model_conflict"] == 1


def test_clean_offers_drops_unit_conflict():
    mod = load_builder()
    rows = [
        _offer("b1", "iPhone 17 256GB", "c1", "iPhone 17 256 GB"),
        _offer("b2", "iPhone 17 256GB white", "c1", "iPhone 17 256 GB"),
        _offer("b3", "iPhone 17 512GB", "c1", "iPhone 17 256 GB"),
    ]
    kept, report = mod.clean_offers(rows)
    assert {r["offer_id"] for r in kept} == {"b1", "b2"}
    assert report["dropped_unit_conflict"] == 1


def test_clean_offers_keeps_terse_and_price_outlier():
    mod = load_builder()
    rows = [
        _offer("b1", "Apple iPhone 17 256GB Nebelblau", "c1", "iPhone 17 256 GB", price="800.00"),
        _offer("b2", "iPhone 17", "c1", "iPhone 17 256 GB", price="810.00"),          # terse: keep
        _offer("b3", "Apple iPhone 17 256GB", "c1", "iPhone 17 256 GB", price="3000.00"),  # outlier: keep
    ]
    kept, report = mod.clean_offers(rows)
    assert {r["offer_id"] for r in kept} == {"b1", "b2", "b3"}
    assert report["flagged_degenerate_title"] >= 1
    assert report["flagged_price_outlier"] >= 1


def test_choose_split_is_cluster_disjoint_and_hits_ratio():
    mod = load_builder()
    rows = []
    for c in range(20):  # 20 clusters x 5 offers = 100 offers
        for k in range(5):
            rows.append(_offer(f"b{c}_{k}", "iPhone 17", f"c{c}", "iPhone 17"))
    rng = random.Random(1)
    train_clusters, test_clusters = mod.choose_split(rows, 0.30, rng)
    assert train_clusters.isdisjoint(test_clusters)
    assert train_clusters | test_clusters == {f"c{c}" for c in range(20)}
    train_offers = sum(1 for r in rows if r["cluster_id"] in train_clusters)
    assert 25 <= train_offers <= 40  # ~30% of 100, whole-cluster granularity


def test_anonymize_reassigns_ids_and_preserves_cluster_grouping():
    mod = load_builder()
    rows = [
        _offer("bA", "t1", "src1", "L1"),
        _offer("bB", "t2", "src1", "L1"),
        _offer("bC", "t3", "src2", "L2"),
    ]
    out = mod.anonymize(rows, random.Random(2))
    # new opaque ids
    assert all(r["offer_id"].startswith("o") for r in out)
    assert all(r["cluster_id"].startswith("c") for r in out)
    assert len({r["offer_id"] for r in out}) == 3
    # offers from the same source cluster share one new cluster id; different sources differ.
    # t1,t2 came from src1; t3 from src2.
    new_by_title = {r["title"]: r["cluster_id"] for r in out}
    assert new_by_title["t1"] == new_by_title["t2"]
    assert new_by_title["t1"] != new_by_title["t3"]
    # title/price/brand carried through
    assert {r["title"] for r in out} == {"t1", "t2", "t3"}


def test_anonymize_offsets_shift_id_namespace():
    mod = load_builder()
    rows = [_offer("bA", "t1", "src1", "L1"), _offer("bC", "t3", "src2", "L2")]
    out = mod.anonymize(rows, random.Random(2), offer_start=100, cluster_start=5)
    assert {int(r["offer_id"][1:]) for r in out} == {101, 102}
    assert all(int(r["cluster_id"][1:]) > 5 for r in out)
