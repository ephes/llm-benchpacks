import builtins
import importlib.util
import itertools
import math
from collections import Counter
from fractions import Fraction as F
from pathlib import Path

import pytest

SCRIPTS = Path('benchpacks/product-offer-matching/scripts')
MODULES = ['analyze-pilot-signals', 'analyze-pilot-tfidf', 'analyze-amazon-google-signals']


def load(name):
    spec = importlib.util.spec_from_file_location(name.replace('-', '_'), SCRIPTS / (name + '.py'))
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


@pytest.mark.parametrize('name', MODULES)
@pytest.mark.parametrize('pairs,auc,ap', [
    ([(0, 1), (0, 0), (0, 1)], F(1, 2), F(2, 3)),
    ([(4, 1), (3, 1), (2, 0), (1, 0)], F(1), F(1)),
    ([(4, 0), (3, 0), (2, 1), (1, 1)], F(0), F(5, 12)),
    ([(2, 1), (2, 0), (1, 1), (0, 0)], F(5, 8), F(7, 12)),
])
def test_hand_rank_and_tie_group_oracles(name, pairs, auc, ap):
    mod = load(name)
    # Every tie ordering must preserve the hand-derived rank/group fractions.
    for perm in itertools.permutations(pairs):
        assert mod.auc(perm) == pytest.approx(float(auc))
        assert mod.ap(perm) == pytest.approx(float(ap))


@pytest.mark.parametrize('name', MODULES)
@pytest.mark.parametrize('pairs,expected_ap', [([], None), ([(1, 0), (0, 0)], None), ([(1, 1), (0, 1)], 1)])
def test_empty_single_class_and_pure_import(name, pairs, expected_ap, monkeypatch):
    original = builtins.__import__

    def forbid_science(name, *args, **kwargs):
        assert name.split('.')[0] not in {'sklearn', 'numpy', 'scipy'}
        return original(name, *args, **kwargs)

    monkeypatch.setattr(builtins, '__import__', forbid_science)
    mod = load(name)
    assert math.isnan(mod.auc(pairs))
    result = mod.ap(pairs)
    assert math.isnan(result) if expected_ap is None else result == expected_ap


def test_tokens_codes_and_counted_ngrams():
    mod = load(MODULES[0])
    title = 'Äpfel Straße AB123 RTX5070 X100 256GB 1TB 500W 2GHz 1000mAh'
    assert mod.codes(title) == {'ab123', 'rtx5070', 'x100'}
    assert mod.toks('ÄPFEL! Straße a 1') == {'äpfel', 'straße'}
    assert mod.first_tok('a ! Straße Äpfel') == 'straße'
    assert mod.first_tok('Äpfel Straße') == 'äpfel'
    assert mod.first_tok('') == '' and mod.toks('') == mod.codes('') == set()
    assert mod.ngrams('aaaaa') == Counter({'aaa': 3})
    assert mod.ngrams('A  B!') == Counter({'a b': 1})
    assert mod.ngrams('') == Counter()
    assert mod.cos(Counter({'aaa': 3}), Counter({'aaa': 1})) == 1
    assert mod.cos(Counter(), Counter({'aaa': 1})) == mod.jac(set(), {'x'}) == 0


def test_block_schemes_against_enumerated_candidate_pairs():
    mod = load(MODULES[0])
    rows = [dict(offer_id=oid, brand=brand, category_label=cat, title=title)
            for oid, brand, cat, title in [
                ('a', ' X ', 'phones', 'Äpfel AB123 256GB'),
                ('b', 'x', 'phones', 'AB123 Äpfel'),
                ('c', 'x', 'laptops', 'Äpfel AB124'),
                ('d', 'y', 'phones', 'Other AB123'),
                ('e', 'x', 'phones', ''),
                ('f', 'x', 'phones', 'Äpfel AB123')]]
    expected = {
        '(brand, category)': {'ab', 'ae', 'af', 'be', 'bf', 'ef'},
        'brand only': {'ab', 'ac', 'ae', 'af', 'bc', 'be', 'bf', 'ce', 'cf', 'ef'},
        'category only': {'ab', 'ad', 'ae', 'af', 'bd', 'be', 'bf', 'de', 'df', 'ef'},
        'first title token': {'ac', 'af', 'cf'},
    }
    schemes = mod.blocking_schemes()
    assert schemes.keys() == expected.keys()
    for name, key in schemes.items():
        actual = {a['offer_id'] + b['offer_id'] for a, b in itertools.combinations(rows, 2) if key(a) == key(b)}
        assert actual == expected[name]
    first_key = schemes['first title token']
    first_pairs = {a['offer_id'] + b['offer_id'] for a, b in itertools.combinations(rows, 2) if first_key(a) == first_key(b)}
    assert first_pairs & {'ab', 'af', 'bf'} == {'af'}


def test_real_union_find_bridge_and_bcubed_oracle():
    mod = load(MODULES[0])
    tokens = {'a': {'aa', 'bb'}, 'b': {'aa', 'bb', 'cc'}, 'c': {'bb', 'cc'}, 'd': {'aa', 'bb'}}
    blocks = {'one': list('abc'), 'other': ['d']}
    for ordering in [blocks, {'other': ['d'], 'one': list('cba')}]:
        pred = mod.union_find_cluster(ordering, lambda a, b, t: mod.jac(tokens[a], tokens[b]) >= t, 2/3)
        parts = {frozenset(oid for oid in pred if pred[oid] == label) for label in pred.values()}
        assert parts == {frozenset('abc'), frozenset('d')}
        assert mod.bcubed_f1(pred, dict(a='g', b='g', c='h', d='i')) == pytest.approx(float(F(4, 5)))
    assert mod.union_find_cluster({}, lambda *args: pytest.fail('no pairs'), .5) == {}
