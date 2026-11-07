import csv
import importlib.util
import json
import subprocess
from html.parser import HTMLParser
from pathlib import Path

SCRIPT = Path('benchpacks/product-offer-matching/scripts/build-billiger-viewer.py')
RUNNER = Path(__file__).with_name('viewer_dom_runner.cjs')


def load():
    spec = importlib.util.spec_from_file_location('viewer', SCRIPT)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def offer(cid, price='', **extra):
    return dict(cluster_id=cid, cluster_label=cid, category_label='test', source_query='query',
                image_url='https://example.invalid/image', title='title', shop_name='shop', price_eur=price) | extra


def execute(rows, actions=None):
    html = load().build(rows)
    proc = subprocess.run(['node', str(RUNNER)], input=json.dumps(dict(html=html, actions=actions or [])),
                          text=True, capture_output=True, timeout=10)
    assert proc.returncode == 0, proc.stderr
    return html, json.loads(proc.stdout)


class DOM(HTMLParser):
    def __init__(self, html):
        super().__init__(convert_charrefs=True)
        self.tags, self.attrs, self.text = [], [], []
        self.feed(html)

    def handle_starttag(self, tag, attrs):
        self.tags.append(tag)
        self.attrs.append((tag, dict(attrs)))

    def handle_data(self, data):
        self.text.append(data)


def test_hostile_csv_fields_remain_literal_and_grouped(tmp_path):
    hostile = '</script><script>injected()</script><img src=x onerror="injected()"> & "quotes"'
    rows = [offer('__proto__', '1', cluster_label=hostile, category_label='__proto__', title=hostile, shop_name=hostile,
                  image_url='https://example.invalid/" onerror="injected()'),
            offer('constructor', '2', category_label=hostile, cluster_label=hostile, title=hostile, shop_name=hostile,
                  image_url='javascript:injected()'),
            offer(hostile, hostile, category_label='constructor', cluster_label=hostile,
                  title=hostile, shop_name=hostile, source_query=hostile, image_url='data:text/html,injected()')]
    path = tmp_path / 'offers.csv'
    with path.open('w', newline='', encoding='utf-8') as handle:
        writer = csv.DictWriter(handle, fieldnames=list(rows[0]))
        writer.writeheader(); writer.writerows(rows)
    html, states = execute(load().load(path), [{'cat': hostile}, {'cat': '__proto__'}, {'cat': '', 'q': 'quotes'}])
    assert DOM(html).tags.count('script') == 1
    initial = states[0]
    assert {c['cluster_id'] for c in initial['clusters']} == {'__proto__', 'constructor', hostile}
    assert [o['text'] for o in initial['options']] == ['all categories'] + sorted(['__proto__', hostile, 'constructor'])
    assert [o['value'] for o in initial['options']] == ['', *sorted(['__proto__', hostile, 'constructor'])]
    assert initial['optionHTML'] == ''
    dom = DOM(initial['html'])
    assert 'script' not in dom.tags
    assert dom.tags.count('img') == 3
    assert hostile in ''.join(dom.text)
    for tag, attrs in dom.attrs:
        assert not any(key.startswith('on') for key in attrs)
        if tag == 'img':
            assert attrs['src'] == '' or attrs['src'].startswith('https://example.invalid/')
    assert '1 clusters' in states[1]['stat'] and '1 clusters' in states[2]['stat']
    assert '3 clusters' in states[3]['stat']


def test_finite_price_ranges_medians_outliers_and_filters():
    specs = {'missing': ['', 'NaN', 'Infinity', '-Infinity', 'oops'], 'zero': ['0'],
             'odd': ['18', '20', '22'], 'even': ['10', '20', '30', '40'],
             'outlier': ['10', '10', '10', '100'], 'partial': ['7junk', '0x10', '0b11', '0o17'], 'large': ['1e308', '1e308']}
    rows = [offer(cid, price) for cid, prices in specs.items() for price in prices]
    _, states = execute(rows, [{'sort': 'spread'}, {'onlyout': True}, {'onlyout': False, 'q': 'missing'}, {'q': '', 'sort': 'label'}])
    initial = states[0]
    clusters = {c['cluster_id']: c for c in initial['clusters']}
    assert initial['finite'] and initial['medians'] == [None, 3, 2, 2]
    for cid in ['missing', 'partial']:
        assert [clusters[cid][key] for key in ('min', 'max', 'med')] == [None, None, None]
        assert clusters[cid]['spread'] == 0 and not clusters[cid]['hasOut']
    assert [clusters['zero'][key] for key in ('min', 'max', 'med', 'spread')] == [0, 0, 0, 0]
    assert clusters['odd']['med'] == 20 and clusters['even']['med'] == 25
    assert clusters['outlier']['spread'] == 9
    assert [o['_out'] for o in clusters['outlier']['offers']] == [False, False, False, True]
    assert clusters['large']['med'] == 1e308
    assert 'Infinity' not in initial['html'] and 'NaN' not in initial['html']
    assert '0.00 €' in initial['html'] and '—' in initial['html']
    spread_html = states[1]['html']
    assert spread_html.index('>outlier</div>') < spread_html.index('>even</div>') < spread_html.index('>odd</div>')
    assert '2 clusters' in states[2]['stat']  # low even-price offer and high outlier
    assert '1 clusters' in states[3]['stat'] and '—' in states[3]['html']
    label_html = states[4]['html']
    assert label_html.index('>even</div>') < label_html.index('>large</div>') < label_html.index('>missing</div>')


def test_empty_viewer():
    _, states = execute([])
    assert states[0]['clusters'] == [] and states[0]['finite']
    assert states[0]['stat'] == '0 clusters · 0 offers shown'
    assert 'no clusters match' in states[0]['html']


def test_embedded_json_cannot_enter_html_script_escape_states():
    hostile = '<!--<script> & > \u2028 \u2029 </script>'
    rows = [offer('safe', title=hostile)]
    html, states = execute(rows)
    payload = html.split('const DATA = ', 1)[1].split(';\n\nfunction median', 1)[0]
    assert not any(char in payload for char in '<>&\u2028\u2029')
    assert json.loads(payload) == rows
    assert states[0]['clusters'][0]['offers'][0]['title'] == hostile
