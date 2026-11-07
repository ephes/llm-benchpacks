from collections import Counter
import csv
import importlib.util
import io
import random
import sys
import zipfile
from pathlib import Path

import pytest

SCRIPT = Path('benchpacks/product-offer-matching/scripts/build-fixture-from-pricerunner.py')
FIELDS = ['Product ID', 'Product Title', 'Merchant ID', 'Category ID', 'Category Label', 'Cluster ID', 'Cluster Label']


def load_builder():
    spec = importlib.util.spec_from_file_location('pricerunner', SCRIPT)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def source_rows(sizes=(2, 3, 4, 2, 5, 3, 2, 4)):
    return [dict(zip(FIELDS, [f'p{c}-{i}', f'title {c}-{i}', 'shop', str(c % 2), f'category {c % 2}', str(c), f'cluster {c}']))
            for c, size in enumerate(sizes) for i in range(size)]


def write_source(path, rows, fields=FIELDS):
    buf = io.StringIO(newline='')
    writer = csv.DictWriter(buf, fieldnames=fields, lineterminator='\n')
    writer.writeheader()
    writer.writerows(rows)
    with zipfile.ZipFile(path, 'w') as archive:
        archive.writestr('pricerunner_aggregate.csv', '\ufeff' + buf.getvalue())


def generate(mod, monkeypatch, source, pack, seed=7, counts=(2, 2, 2), train=6):
    monkeypatch.setattr(sys, 'argv', ['builder', '--pricerunner-zip', str(source), '--pack-dir', str(pack),
        '--seed', str(seed), '--train-offers', str(train), '--eval-positive-pairs', str(counts[0]),
        '--eval-hard-negative-pairs', str(counts[1]), '--eval-easy-negative-pairs', str(counts[2])])
    return mod.main()


def outputs(pack):
    return {p.name: list(csv.DictReader(io.StringIO(p.read_text()))) for p in pack.rglob('*.csv')}


@pytest.mark.parametrize('sizes,counts', [((), (0, 1, 0)), ((1,), (0, 0, 1)), ((2,), (0, 1, 0)),
    ((1, 1), (1, 0, 0)), ((2, 2), (0, 3, 2)), ((2,), (-1, 0, 0))])
def test_impossible_pairs_fail_before_writes(tmp_path, monkeypatch, sizes, counts):
    mod = load_builder()
    source = tmp_path / 'source.zip'
    write_source(source, source_rows(sizes))
    pack = tmp_path / 'pack'
    with pytest.raises(ValueError, match='pairs'):
        generate(mod, monkeypatch, source, pack, counts=counts, train=0)
    assert not list(pack.rglob('*.csv'))


@pytest.mark.parametrize('sizes', [(), (1,), (2,)])
def test_zero_pairs_succeed(sizes):
    rows = source_rows(sizes)
    assert load_builder()._sample_eval_pairs(rows, positive_pairs=0, hard_negative_pairs=0,
        easy_negative_pairs=0, rng=random.Random(3)) == ([], [])


def test_exact_unique_exhausted_populations():
    rows = source_rows((2, 2, 2))
    # Categories 0,1,0: 4 same-category negatives, 8 remaining negatives.
    for i, row in enumerate(rows):
        row['_local_offer_id'] = str(i)
    mod = load_builder()
    args = dict(positive_pairs=3, hard_negative_pairs=4, easy_negative_pairs=8)
    pairs, labels = mod._sample_eval_pairs(rows, rng=random.Random(4), **args)
    assert (pairs, labels) == mod._sample_eval_pairs(rows, rng=random.Random(4), **args)
    assert len(pairs) == len(labels) == 15
    assert len({frozenset((p['offer_id_left'], p['offer_id_right'])) for p in pairs}) == 15
    assert sum(int(label['label']) for label in labels) == 3
    # A hard-only request may select only same-category, different-cluster rows.
    pairs, _ = mod._sample_eval_pairs(rows, positive_pairs=0, hard_negative_pairs=4,
                                    easy_negative_pairs=0, rng=random.Random(4))
    index = {r['_local_offer_id']: r for r in rows}
    assert all(index[p['offer_id_left']]['Category ID'] == index[p['offer_id_right']]['Category ID']
               and index[p['offer_id_left']]['Cluster ID'] != index[p['offer_id_right']]['Cluster ID'] for p in pairs)


def assert_joins(pack, source):
    files = outputs(pack)
    train, test = files['train_offers.csv'], files['test_offers.csv']
    hidden = files['hidden_test_clusters.csv']
    by_title = {r['Product Title']: r for r in source}
    train_gold = {by_title[r['title']]['Cluster ID'] for r in train}
    test_gold = {by_title[r['title']]['Cluster ID'] for r in test}
    assert train_gold.isdisjoint(test_gold)
    assert train_gold | test_gold == {r['Cluster ID'] for r in source}
    assert len(train) >= 6 and len(train) < 6 + max(Counter(r['Cluster ID'] for r in source).values())
    all_ids = [r['offer_id'] for r in train + test]
    assert all_ids == [f'o{i:05d}' for i in range(1, len(source) + 1)]
    assert len({r['offer_id'] for r in hidden}) == len(hidden) == len(test)
    assert {r['offer_id'] for r in hidden} == {r['offer_id'] for r in test}
    labels = {r['offer_id']: r['cluster_id'] for r in hidden}
    for row in test:
        assert not {'cluster_id', 'cluster_label'} & row.keys()
        assert labels[row['offer_id']] == f"c{int(by_title[row['title']]['Cluster ID']):05d}"
    pairs, gold = files['eval_pairs.csv'], files['hidden_eval_pair_labels.csv']
    assert len({r['pair_id'] for r in pairs}) == len(pairs) == len(gold)
    assert {r['pair_id'] for r in pairs} == {r['pair_id'] for r in gold}
    gold = {r['pair_id']: r['label'] for r in gold}
    for pair in pairs:
        a, b = pair['offer_id_left'], pair['offer_id_right']
        assert a != b and a in labels and b in labels
        assert gold[pair['pair_id']] == str(int(labels[a] == labels[b]))


def test_end_to_end_split_references_and_seed(tmp_path, monkeypatch):
    mod, rows = load_builder(), source_rows()
    source = tmp_path / 'source.zip'
    write_source(source, rows)
    for name, seed in [('one', 7), ('repeat', 7), ('changed', 9)]:
        assert generate(mod, monkeypatch, source, tmp_path / name, seed=seed) == 0
        assert_joins(tmp_path / name, rows)
    assert outputs(tmp_path / 'one') == outputs(tmp_path / 'repeat')
    assert outputs(tmp_path / 'one') != outputs(tmp_path / 'changed')


def test_split_uses_whole_cluster_crossing_target():
    rows = source_rows((4, 4))
    train, test = load_builder()._choose_split(rows, train_offer_target=3, rng=random.Random(1))
    assert len(train) == len(test) == 1
    assert train.isdisjoint(test)


def test_pair_source_identity_must_be_unique():
    rows = source_rows((2,))
    rows[1]['Product ID'] = rows[0]['Product ID']
    with pytest.raises(ValueError, match='unique Product IDs'):
        load_builder()._sample_eval_pairs(rows, positive_pairs=0, hard_negative_pairs=0,
                                          easy_negative_pairs=0, rng=random.Random(0))
