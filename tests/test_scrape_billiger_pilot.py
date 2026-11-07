import base64
import importlib.util
import json
from pathlib import Path

import pytest

SCRIPT = Path('benchpacks/product-offer-matching/scripts/scrape-billiger-pilot.py')


def load():
    spec = importlib.util.spec_from_file_location('scraper', SCRIPT)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def tag(payload, title='Merchant &amp; title'):
    encoded = base64.b64encode(json.dumps(payload).encode()).decode()
    return f'<a title="{title}" data-econda-clickout-params="{encoded}">'


def payload(cid='101', shop='Shop &amp; Co'):
    return {'LeadEvent': [['unused', cid, 'Name &amp; Co', 'unused', 'Tech [1]/Phones [2]', 'Brand', None, shop, '100.00']]}


@pytest.mark.parametrize('bad', [[], None, 7, {}, {'LeadEvent': 42}, {'LeadEvent': [None]},
    {'LeadEvent': []}, {'LeadEvent': {}}, {'LeadEvent': ['abcdefghi']}, {'LeadEvent': [[1, 2]]}])
def test_malformed_payload_siblings_are_isolated(bad, capsys):
    mod = load()
    html = tag(bad) + '<a data-econda-clickout-params="%%%">' + tag(payload()) + tag(bad)
    offers = mod._decode_clickouts(html)
    assert len(offers) == 1
    assert offers[0]['merchant_title'] == 'Merchant & title'
    assert offers[0]['norm_name'] == 'Name & Co' and offers[0]['shop_name'] == 'Shop & Co'
    err = capsys.readouterr().err
    assert 'rejected' in err and len(err) < 100
    assert 'Merchant' not in err and 'Shop' not in err


@pytest.mark.parametrize('index,value', [(1, []), (1, True), (1, None), (1, ''), (2, {}),
    (4, 5), (5, []), (7, 42), (8, {}), (8, True), (8, float('nan')), (8, float('inf'))])
def test_consumed_field_types_are_checked(index, value):
    bad = payload()
    bad['LeadEvent'][0][index] = value
    mod = load()
    offers = mod._decode_clickouts(tag(bad) + tag(payload()))
    assert offers == mod._decode_clickouts(tag(payload()))


def test_cluster_aware_dedup_and_optional_fields():
    mod = load()
    a, b = payload('foreign'), payload('101')
    assert [o['cluster_id'] for o in mod._decode_clickouts(tag(a) + tag(b) + tag(b))] == ['foreign', '101']
    optional = payload(101)
    for i in (2, 4, 5, 7, 8):
        optional['LeadEvent'][0][i] = None
    offer = mod._decode_clickouts(tag(optional))[0]
    assert offer['cluster_id'] == 101 and offer['shop_name'] == ''


@pytest.fixture
def fake_web(monkeypatch):
    mod = load()
    monkeypatch.setattr(mod.urllib.request, 'urlopen', lambda *a, **kw: pytest.fail('real network forbidden'))
    calls, sleeps, pages = [], [], {}

    def fetch(url):
        calls.append(url)
        value = pages[url]
        if isinstance(value, list):
            return value.pop(0)
        return value

    monkeypatch.setattr(mod, 'fetch', fetch)
    monkeypatch.setattr(mod.time, 'sleep', sleeps.append)
    pages['search'] = '/baseproducts/1-base /baseproducts/2-base'
    pages[mod.BASE + '/baseproducts/1-base'] = '/products/101-one /products/102-two /products/101-one'
    pages[mod.BASE + '/baseproducts/2-base'] = '/products/102-two /products/103-three'
    for cid, suffix in [('101', 'one'), ('102', 'two'), ('103', 'three')]:
        pages[mod.BASE + f'/products/{cid}-{suffix}'] = tag(payload(cid)) + '<meta property="og:image" content="https://example.invalid/a&amp;b">'
    return mod, pages, calls, sleeps


def test_budget_exhaustion_leaves_unfetched_queue_retryable(fake_web):
    mod, pages, calls, sleeps = fake_web
    seen = set()
    assert mod.scrape('search', 2, 3, 3, seen_variants=seen) == []
    assert not seen and len(calls) == 3 and len(sleeps) == 2
    calls.clear(); sleeps.clear()
    rows = mod.scrape('search', 2, 3, 5, seen_variants=seen)
    assert [r['cluster_id'] for r in rows] == ['101', '102']
    assert seen == {'/products/101-one', '/products/102-two'}
    assert len(calls) == 5 and len(sleeps) == 4
    calls.clear()
    rows = mod.scrape('search', 2, 3, 4, seen_variants=seen)
    assert [r['cluster_id'] for r in rows] == ['103']
    assert len(calls) == 4


def test_failed_variant_retries_but_success_is_not_refetched(fake_web):
    mod, pages, calls, sleeps = fake_web
    seen = set()
    url = mod.BASE + '/products/101-one'
    good = pages[url]
    pages[url] = [None, good]
    rows = mod.scrape('search', 1, 2, 4, seen_variants=seen)
    assert [r['cluster_id'] for r in rows] == ['102']
    assert '/products/101-one' not in seen and '/products/102-two' in seen
    calls.clear()
    rows = mod.scrape('search', 1, 2, 3, seen_variants=seen)
    assert [r['cluster_id'] for r in rows] == ['101']
    assert calls.count(url) == 1 and mod.BASE + '/products/102-two' not in calls


def test_target_isolation_soft_budget_and_duplicate_pages(fake_web):
    mod, pages, calls, sleeps = fake_web
    pages[mod.BASE + '/products/101-one'] = tag([]) + tag({'LeadEvent': [None]}) + tag(payload('999')) + tag(payload('101')) + tag(payload('101', 'second shop'))
    seen = set()
    rows = mod.scrape('search', 2, 3, 20, query='synthetic', max_offers=1, seen_variants=seen)
    assert len(rows) == 2  # complete cluster may overshoot soft cap
    assert {r['cluster_id'] for r in rows} == {'101'}
    assert {r['source_query'] for r in rows} == {'synthetic'}
    assert rows[0]['category_label'] == 'Phones'
    assert seen == {'/products/101-one'}
    assert len(calls) == 4
    assert len(sleeps) == 3 and set(sleeps) == {mod.DELAY_S}
    calls.clear()
    rows = mod.scrape('search', 2, 3, 20, seen_variants=seen)
    assert [r['cluster_id'] for r in rows] == ['102', '103']
    assert calls.count(mod.BASE + '/products/102-two') == 1


def test_non_alphabet_base64_is_rejected():
    malformed = tag(payload('bad')).replace('params="', 'params="!', 1)
    mod = load()
    assert mod._decode_clickouts(malformed + tag(payload())) == mod._decode_clickouts(tag(payload()))
