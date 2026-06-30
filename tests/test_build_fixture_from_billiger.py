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
