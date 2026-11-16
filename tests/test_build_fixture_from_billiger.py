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


def test_storage_caps_normalizes_tb_separators_and_excludes_ram():
    mod = load_builder()
    assert mod.storage_caps("iPhone 17 256GB") == {256}
    assert mod.storage_caps("Galaxy S26 Ultra 1 TB") == {1000}
    assert mod.storage_caps("Samsung Galaxy S26 Ultra (1024 GB, Black)") == {1000}  # 1024 -> 1000
    assert mod.storage_caps("Galaxy 1.000 GB SSD") == {1000}                        # thousands sep
    assert mod.storage_caps("Galaxy S26 12 GB RAM 512 GB") == {512}                 # RAM excluded
    assert mod.storage_caps("Sony WH-1000XM5") == set()


def test_clean_offers_keeps_tb_equivalent_storage():
    mod = load_builder()
    rows = [
        _offer("b1", "Samsung Galaxy S26 Ultra 1 TB", "c1", "Galaxy S26 Ultra 1 TB", brand="Samsung"),
        _offer("b2", "Samsung Galaxy S26 Ultra 1024 GB Black", "c1", "Galaxy S26 Ultra 1 TB", brand="Samsung"),
        _offer("b3", "Samsung Galaxy S26 Ultra 1.000 GB", "c1", "Galaxy S26 Ultra 1 TB", brand="Samsung"),
    ]
    kept, report = mod.clean_offers(rows)
    assert {r["offer_id"] for r in kept} == {"b1", "b2", "b3"}  # all 1TB-equivalent
    assert report["dropped_unit_conflict"] == 0


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


def test_sample_eval_pairs_composition_and_labels():
    mod = load_builder()
    # 4 clusters of 4 offers across 2 (brand,category) blocks and 2 categories
    rows = []
    specs = [("c1", "Apple", "Handys"), ("c2", "Apple", "Handys"),
             ("c3", "Bosch", "Kaffee"), ("c4", "Bosch", "Kaffee")]
    for cid, brand, cat in specs:
        for k in range(4):
            rows.append(_offer(f"o_{cid}_{k}", f"{brand} {cid} item", cid, f"{cid} L",
                               brand=brand, cat=cat))
    pairs, labels = mod.sample_eval_pairs(rows, n_pos=6, n_hard_neg=6, n_easy_neg=4,
                                          rng=random.Random(3))
    label_by_id = {row_l["pair_id"]: row_l["label"] for row_l in labels}
    assert len(pairs) == len(labels) == 16
    idx = {r["offer_id"]: r for r in rows}
    pos = neg = 0
    for p in pairs:
        a, b = idx[p["offer_id_left"]], idx[p["offer_id_right"]]
        lab = label_by_id[p["pair_id"]]
        if lab == "1":
            pos += 1
            assert a["cluster_id"] == b["cluster_id"]      # positive => same cluster
        else:
            neg += 1
            assert a["cluster_id"] != b["cluster_id"]      # negative => different cluster
    assert pos == 6 and neg == 10


def _synthetic_raw(n_clusters=30, per=5):
    rows = []
    cats = [("Apple", "Handys"), ("Bosch", "Kaffee"), ("MSI", "Grafikkarten")]
    for c in range(n_clusters):
        brand, cat = cats[c % len(cats)]
        for k in range(per):
            rows.append(_offer(f"b{c}_{k}", f"{brand} model{c} item {k}", f"src{c}",
                               f"model{c} L", price=f"{100 + c}.00", brand=brand, cat=cat))
    return rows


def test_build_writes_all_outputs_with_anti_leakage(tmp_path):
    mod = load_builder()
    raw = tmp_path / "raw.csv"
    fields = ["offer_id", "title", "shop_name", "price_eur", "brand", "category_label",
              "image_url", "cluster_id", "cluster_label", "source_query"]
    write_csv(raw, _synthetic_raw(), fields)
    data_dir = tmp_path / "fixture" / "data"
    verify_dir = tmp_path / "verify"

    mod.build(raw, data_dir, verify_dir, train_fraction=0.30, n_pos=20, n_hard_neg=20,
              n_easy_neg=10, seed=1)

    train = mod.read_offers(data_dir / "train_offers.csv")
    test = mod.read_offers(data_dir / "test_offers.csv")
    hidden = mod.read_offers(verify_dir / "hidden_test_clusters.csv")
    pair_labels = mod.read_offers(verify_dir / "hidden_eval_pair_labels.csv")
    report = json.loads((data_dir.parent / "build-report.json").read_text())

    assert "cluster_id" not in test[0] and "cluster_label" not in test[0]
    assert "image_url" not in test[0] and "image_url" not in train[0]  # leak: stripped (D-038)
    assert set(train[0]) == {"offer_id", "title", "shop_name", "price_eur", "brand",
                             "category_label", "cluster_id", "cluster_label"}
    assert {r["offer_id"] for r in hidden} == {r["offer_id"] for r in test}
    assert {r["cluster_id"] for r in train}.isdisjoint({r["cluster_id"] for r in hidden})
    pairs = mod.read_offers(data_dir / "eval_pairs.csv")
    assert {p["pair_id"] for p in pairs} == {p["pair_id"] for p in pair_labels}
    assert report["kept_offers"] <= report["input_offers"]


def test_build_is_deterministic(tmp_path):
    mod = load_builder()
    raw = tmp_path / "raw.csv"
    fields = ["offer_id", "title", "shop_name", "price_eur", "brand", "category_label",
              "image_url", "cluster_id", "cluster_label", "source_query"]
    write_csv(raw, _synthetic_raw(), fields)
    mod.build(raw, tmp_path / "a" / "data", tmp_path / "a" / "verify", 0.30, 20, 20, 10, seed=1)
    mod.build(raw, tmp_path / "b" / "data", tmp_path / "b" / "verify", 0.30, 20, 20, 10, seed=1)
    assert (tmp_path / "a" / "data" / "train_offers.csv").read_text() == \
           (tmp_path / "b" / "data" / "train_offers.csv").read_text()
    assert (tmp_path / "a" / "data" / "eval_pairs.csv").read_text() == \
           (tmp_path / "b" / "data" / "eval_pairs.csv").read_text()


def test_positive_sampling_never_materializes_quadratic_pool():
    class TrackedRandom(random.Random):
        largest_shuffle = 0
        def shuffle(self, values):
            self.largest_shuffle = max(self.largest_shuffle, len(values))
            return super().shuffle(values)
    mod = load_builder()
    for n in (250, 500, 1000):
        rows = [_offer(str(i), 'synthetic item', 'c', 'synthetic') for i in range(n)]
        for count in (0, 1):
            rng = TrackedRandom(1)
            pairs, _ = mod.sample_eval_pairs(rows, count, 0, 0, rng)
            assert len(pairs) == count
            assert rng.largest_shuffle <= max(count, 1)


def test_positive_pair_index_mapping_exhaustive_and_seeded():
    import itertools
    mod = load_builder()
    rows = [_offer(f'{c}-{i}', 'synthetic item', c, c)
            for c, n in [('a', 4), ('b', 3), ('c', 1)] for i in range(n)]
    expected = {tuple(sorted([a['offer_id'], b['offer_id']]))
                for a, b in itertools.combinations(rows, 2) if a['cluster_id'] == b['cluster_id']}
    pairs, labels = mod.sample_eval_pairs(rows, 99, 0, 0, random.Random(7))
    assert {tuple(sorted([p['offer_id_left'], p['offer_id_right']])) for p in pairs} == expected
    assert len(pairs) == len(expected)
    assert all(row['label'] == '1' for row in labels)
    assert mod.sample_eval_pairs(rows, 3, 0, 0, random.Random(7)) == mod.sample_eval_pairs(rows, 3, 0, 0, random.Random(7))


def fixture_targets(data, verify):
    return [data / name for name in ['train_offers.csv', 'test_offers.csv', 'eval_pairs.csv']] + [
        verify / 'hidden_test_clusters.csv', verify / 'hidden_eval_pair_labels.csv',
        data.parent / 'build-report.json']


import pytest


@pytest.mark.parametrize('step', range(1, 7))
def test_fixture_publication_rolls_back_every_step(tmp_path, monkeypatch, step):
    mod = load_builder()
    raw = tmp_path / 'raw.csv'
    rows = _synthetic_raw(10, 3)
    write_csv(raw, rows, list(rows[0]))
    data, verify = tmp_path / 'fixture/data', tmp_path / 'verify'
    mod.build(raw, data, verify, .3, 3, 3, 3, seed=1)
    targets = fixture_targets(data, verify)
    before = {p: p.read_bytes() for p in targets}
    old_open = Path.open
    count = 0
    def fail_old_writer(self, mode='r', *args, **kwargs):
        nonlocal count
        if self in targets and 'w' in mode:
            count += 1
            if count == step:
                raise OSError('injected old direct write failure')
        return old_open(self, mode, *args, **kwargs)
    monkeypatch.setattr(Path, 'open', fail_old_writer)
    if hasattr(mod, 'os'):
        replace = mod.os.replace
        def fail_replace(src, dst):
            nonlocal count
            if Path(dst) in targets:
                count += 1
                if count == step:
                    raise OSError('injected publication failure')
            return replace(src, dst)
        monkeypatch.setattr(mod.os, 'replace', fail_replace)
    with pytest.raises(OSError):
        mod.build(raw, data, verify, .3, 3, 3, 3, seed=2)
    assert {p: p.read_bytes() for p in targets} == before


def test_rollback_failure_retains_backups_and_manifest(tmp_path, monkeypatch):
    mod = load_builder()
    raw = tmp_path / 'raw.csv'
    rows = _synthetic_raw(10, 3)
    write_csv(raw, rows, list(rows[0]))
    data, verify = tmp_path / 'fixture/data', tmp_path / 'verify'
    mod.build(raw, data, verify, .3, 3, 3, 3, seed=1)
    before = {p: p.read_bytes() for p in fixture_targets(data, verify)}
    replace = mod.os.replace
    count = 0
    def fail(src, dst):
        nonlocal count
        count += 1
        if count >= 2:
            raise OSError('publication and compensation failure')
        return replace(src, dst)
    monkeypatch.setattr(mod.os, 'replace', fail)
    with pytest.raises(RuntimeError, match='recovery retained at'):
        mod.build(raw, data, verify, .3, 3, 3, 3, seed=2)
    manifests = list(tmp_path.rglob('.billiger-stage-*/manifest.json'))
    assert manifests
    manifest = json.loads(manifests[0].read_text())
    assert all(Path(row['backup']).read_bytes() == before[Path(row['target'])]
               for row in manifest if row['existed'])


def test_concurrent_builders_publish_serial_generations(tmp_path):
    import subprocess
    import sys
    import time
    mod = load_builder()
    raw = tmp_path / 'raw.csv'
    rows = _synthetic_raw(10, 3)
    write_csv(raw, rows, list(rows[0]))
    data, verify = tmp_path / 'fixture/data', tmp_path / 'verify'
    code = '''import importlib.util, pathlib, sys, time
spec=importlib.util.spec_from_file_location('b', sys.argv[1])
b=importlib.util.module_from_spec(spec); spec.loader.exec_module(b)
root=pathlib.Path(sys.argv[2]); seed=int(sys.argv[3])
replace=b.os.replace
def observe(src,dst):
    with (root/'events').open('a') as f: f.write(str(seed)+'\\n')
    time.sleep(.02)
    return replace(src,dst)
b.os.replace=observe
(root/('ready'+str(seed))).touch()
while not (root/'go').exists(): time.sleep(.01)
b.build(root/'raw.csv',root/'fixture/data',root/'verify',.3,3,3,3,seed=seed)
'''
    processes = [subprocess.Popen([sys.executable, '-c', code, str(BUILDER_PATH.resolve()),
                                  str(tmp_path), str(seed)]) for seed in (1, 2)]
    try:
        deadline = time.monotonic() + 5
        while not all((tmp_path / f'ready{seed}').exists() for seed in (1, 2)):
            assert time.monotonic() < deadline
            time.sleep(.01)
        (tmp_path / 'go').touch()
        for process in processes:
            assert process.wait(timeout=5) == 0
        events = (tmp_path / 'events').read_text().splitlines()
        assert events in [['1'] * 6 + ['2'] * 6, ['2'] * 6 + ['1'] * 6]
        last_seed = int(events[-1])
        expected_data, expected_verify = tmp_path / 'expected/data', tmp_path / 'expected-verify'
        mod.build(raw, expected_data, expected_verify, .3, 3, 3, 3, seed=last_seed)
        assert [p.read_bytes() for p in fixture_targets(data, verify)] == [
            p.read_bytes() for p in fixture_targets(expected_data, expected_verify)]
    finally:
        for process in processes:
            if process.poll() is None:
                process.kill()
                process.wait()


def test_staging_failure_preserves_all_fixture_bytes(tmp_path, monkeypatch):
    mod = load_builder()
    raw = tmp_path / 'raw.csv'
    rows = _synthetic_raw(10, 3)
    write_csv(raw, rows, list(rows[0]))
    data, verify = tmp_path / 'fixture/data', tmp_path / 'verify'
    mod.build(raw, data, verify, .3, 3, 3, 3, seed=1)
    before = {p: p.read_bytes() for p in fixture_targets(data, verify)}
    write_bytes = Path.write_bytes
    def fail(self, content):
        if self.name == 'new-3':
            raise OSError('staging failed')
        return write_bytes(self, content)
    monkeypatch.setattr(Path, 'write_bytes', fail)
    with pytest.raises(OSError, match='staging failed'):
        mod.build(raw, data, verify, .3, 3, 3, 3, seed=2)
    assert {p: p.read_bytes() for p in before} == before


def test_failed_first_publication_removes_new_generation(tmp_path, monkeypatch):
    mod = load_builder()
    data, verify = tmp_path / 'fixture/data', tmp_path / 'verify'
    targets = fixture_targets(data, verify)
    replace = mod.os.replace
    def fail(src, dst):
        if Path(dst) == targets[-1]:
            raise OSError('report replacement failed')
        return replace(src, dst)
    monkeypatch.setattr(mod.os, 'replace', fail)
    with pytest.raises(OSError):
        mod._publish_fixture([(p, b'synthetic') for p in targets])
    assert not any(p.exists() for p in targets)
