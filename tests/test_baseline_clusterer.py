import importlib.util
from fractions import Fraction as F
from pathlib import Path

import pytest

SCRIPT = Path('benchpacks/product-offer-matching/scripts/baseline-clusterer.py')


def load_baseline():
    spec = importlib.util.spec_from_file_location('baseline', SCRIPT)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def labels(values):
    return dict(zip('abcd', values))


@pytest.mark.parametrize('pred,gold,bp,br,bf,pf', [
    ('xxyy', 'aabb', F(1), F(1), F(1), F(1)),
    ('xxxx', 'aabb', F(1, 2), F(1), F(2, 3), F(1, 2)),
    ('wxyz', 'aabb', F(1), F(1, 2), F(2, 3), F(0)),
    ('xxyy', 'aaab', F(3, 4), F(2, 3), F(12, 17), F(2, 5)),
    ('wxyz', 'abcd', F(1), F(1), F(1), F(0)),
])
def test_independent_partition_fractions(pred, gold, bp, br, bf, pf):
    mod = load_baseline()
    expected = dict(bp=bp, br=br, bf=bf, pf=pf)
    result = mod.score(labels(pred), labels(gold))
    assert {key: result[key] for key in expected} == pytest.approx({key: float(value) for key, value in expected.items()})
    renamed = mod.score({oid: 'pred-' + value for oid, value in labels(pred).items()},
                        {oid: 'gold-' + value for oid, value in labels(gold).items()})
    assert renamed == result
    assert result['npred'] == len(set(pred)) and result['ngold'] == len(set(gold))


def partition(pred):
    return {frozenset(oid for oid, label in pred.items() if label == cluster) for cluster in pred.values()}


def row(oid, title, brand=' Brand ', category='cat'):
    return dict(offer_id=oid, title=title, brand=brand, category_label=category)


def test_transitive_partition_and_block_threshold_boundaries():
    mod = load_baseline()
    rows = [row('a', 'aa bb'), row('b', 'aa bb cc', brand='brand'), row('c', 'bb cc'),
            row('d', 'aa bb', category='other'), row('e', ''), row('f', '')]
    tok = {r['offer_id']: mod.toks(r['title']) for r in rows}
    assert mod.jaccard(tok['a'], tok['c']) == pytest.approx(float(F(1, 3)))
    expected = {frozenset('abc'), frozenset('d'), frozenset('e'), frozenset('f')}
    for ordering in [rows, rows[::-1], rows[2:] + rows[:2]]:
        pred, comparisons, blocks, largest = mod.cluster(ordering, tok, 2/3)
        assert partition(pred) == expected
        assert (comparisons, blocks, largest) == (10, 2, 5)
    assert len(partition(mod.cluster(rows, tok, 2/3 + 1e-9)[0])) == len(rows)
    assert mod.jaccard(frozenset(), frozenset()) == 0


def test_empty_csv_cluster_and_metrics(tmp_path):
    mod = load_baseline()
    path = tmp_path / 'empty.csv'
    path.write_text('offer_id,title,brand,category_label,cluster_id\n')
    rows, tok = mod.load(path)
    assert mod.cluster(rows, tok, .5) == ({}, 0, 0, 0)
    assert mod.score({}, {}) == dict(bp=0, br=0, bf=0, pf=0, npred=0, ngold=0)


def test_duplicate_offer_ids_are_rejected_before_union():
    rows = [row('a', 'one'), row('a', 'two')]
    with pytest.raises(ValueError, match='duplicate offer'):
        load_baseline().cluster(rows, {}, .5)
