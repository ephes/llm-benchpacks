from collections import Counter
import csv
import importlib.util
import io
import json
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


@pytest.mark.parametrize('fault', ['missing_header', 'extra_header', 'duplicate_header', 'surplus', 'short', 'blank_id', 'duplicate_id', 'bad_cluster'])
def test_source_schema_preflight_preserves_previous_generation(tmp_path, monkeypatch, fault):
    mod, rows = load_builder(), source_rows()
    source, pack = tmp_path / 'source.zip', tmp_path / 'pack'
    write_source(source, rows)
    generate(mod, monkeypatch, source, pack)
    before = {p: p.read_bytes() for p in pack.rglob('*.csv')}
    fields = FIELDS.copy()
    if fault == 'missing_header':
        fields.remove('Product Title')
        rows = [{k: v for k, v in r.items() if k in fields} for r in rows]
    elif fault == 'extra_header':
        fields.append('Unexpected')
    elif fault == 'duplicate_header':
        fields.append('Product ID')
    elif fault == 'blank_id':
        rows[1]['Product ID'] = '  '
    elif fault == 'duplicate_id':
        rows[1]['Product ID'] = rows[0]['Product ID']
    elif fault == 'bad_cluster':
        rows[1]['Cluster ID'] = 'SECRET invalid value'
    write_source(source, rows, fields)
    if fault in ('surplus', 'short'):
        with zipfile.ZipFile(source) as archive:
            text = archive.read(mod.SOURCE_MEMBER).decode('utf-8-sig')
        lines = text.splitlines()
        lines[2] = lines[2] + ',SECRET' if fault == 'surplus' else ','.join(lines[2].split(',')[:-1])
        with zipfile.ZipFile(source, 'w') as archive:
            archive.writestr(mod.SOURCE_MEMBER, '\n'.join(lines))
    with pytest.raises(ValueError) as exc:
        generate(mod, monkeypatch, source, pack)
    assert 'SECRET' not in str(exc.value)
    assert len(str(exc.value)) < 200
    assert {p: p.read_bytes() for p in pack.rglob('*.csv')} == before


def test_source_bom_unicode_quoted_multiline_values(tmp_path, monkeypatch):
    mod, rows = load_builder(), source_rows()
    rows[0]['Product Title'] = 'Küche, "groß"\nzweite Zeile'
    source, pack = tmp_path / 'source.zip', tmp_path / 'pack'
    write_source(source, rows)
    generate(mod, monkeypatch, source, pack)
    titles = [r['title'] for name, rs in outputs(pack).items() if name in ('train_offers.csv', 'test_offers.csv') for r in rs]
    assert 'Küche, "groß" zweite Zeile' in titles


@pytest.mark.parametrize('boundary', ['stage', 'backup', 'publish'])
@pytest.mark.parametrize('nth', range(1, 6))
@pytest.mark.parametrize('existing', [False, True])
def test_generation_failure_is_all_or_previous(tmp_path, monkeypatch, boundary, nth, existing, capsys):
    mod, rows = load_builder(), source_rows()
    source, pack = tmp_path / 'source.zip', tmp_path / 'pack'
    write_source(source, rows)
    if existing:
        generate(mod, monkeypatch, source, pack)
    before = {p: p.read_bytes() for p in pack.rglob('*.csv')}
    capsys.readouterr()
    calls = 0
    owner, name = (mod, '_write_csv') if boundary == 'stage' else ((mod.shutil, 'copy2') if boundary == 'backup' else (mod.os, 'replace'))
    original = getattr(owner, name)

    def fail(*args, **kwargs):
        nonlocal calls
        calls += 1
        if calls == nth:
            if boundary == 'stage':  # includes failures after a complete write/close
                original(*args, **kwargs)
            raise OSError('synthetic I/O failure')
        return original(*args, **kwargs)

    if boundary == 'backup' and not existing:
        pytest.skip('no backups exist on first generation')
    with monkeypatch.context() as patch:
        patch.setattr(owner, name, fail)
        with pytest.raises(OSError, match='synthetic'):
            generate(mod, monkeypatch, source, pack, seed=9)
    assert calls >= nth
    assert not capsys.readouterr().out  # success summary only follows publication
    assert {p: p.read_bytes() for p in pack.rglob('*.csv')} == before
    assert not list(pack.glob('.pricerunner-*'))
    generate(mod, monkeypatch, source, pack, seed=9)
    assert_joins(pack, rows)


def test_failed_rollback_retains_recovery_files(tmp_path, monkeypatch):
    mod, rows = load_builder(), source_rows()
    source, pack = tmp_path / 'source.zip', tmp_path / 'pack'
    write_source(source, rows)
    generate(mod, monkeypatch, source, pack)
    calls = 0
    original = mod.os.replace

    def fail(src, dst):
        nonlocal calls
        calls += 1
        if calls >= 2:
            raise OSError('synthetic rollback failure')
        return original(src, dst)

    with monkeypatch.context() as patch:
        patch.setattr(mod.os, 'replace', fail)
        with pytest.raises(RuntimeError, match='recovery files retained at') as exc:
            generate(mod, monkeypatch, source, pack, seed=9)
    recovery = Path(str(exc.value).split(' at ', 1)[1])
    assert recovery.is_dir()
    assert len(list((recovery / 'backup').glob('*.csv'))) == 5


@pytest.mark.parametrize('raw', [b'\xff', b'Product ID,Product Title,Merchant ID,Category ID,Category Label,Cluster ID,Cluster Label\np,"unterminated'])
def test_invalid_source_encoding_and_csv_fail_without_outputs(tmp_path, monkeypatch, raw):
    source, pack = tmp_path / 'source.zip', tmp_path / 'pack'
    with zipfile.ZipFile(source, 'w') as archive:
        archive.writestr('pricerunner_aggregate.csv', raw)
    with pytest.raises(ValueError, match='encoding/shape'):
        generate(load_builder(), monkeypatch, source, pack)
    assert not list(pack.rglob('*.csv'))


def test_numeric_cluster_aliases_share_one_split_identity(tmp_path):
    rows = source_rows((2,))
    rows[1]['Cluster ID'] = '00'
    source = tmp_path / 'source.zip'
    write_source(source, rows)
    mod = load_builder()
    admitted = mod._read_rows(source, mod.SOURCE_MEMBER)
    train, test = mod._choose_split(admitted, train_offer_target=1, rng=random.Random(1))
    assert train == {'0'} and not test


def test_staged_content_is_validated_before_publication(tmp_path, monkeypatch):
    mod, rows = load_builder(), source_rows()
    source, pack = tmp_path / 'source.zip', tmp_path / 'pack'
    write_source(source, rows)
    generate(mod, monkeypatch, source, pack)
    before = {p: p.read_bytes() for p in pack.rglob('*.csv')}
    original = mod._write_csv

    def corrupt(path, rows, fields):
        original(path, rows, fields)
        path.write_text('wrong\ncontents\n')

    monkeypatch.setattr(mod, '_write_csv', corrupt)
    with pytest.raises(ValueError, match='staged fixture validation'):
        generate(mod, monkeypatch, source, pack)
    assert {p: p.read_bytes() for p in pack.rglob('*.csv')} == before


def test_partial_previous_generation_unlink_rollback_recovery(tmp_path, monkeypatch):
    mod, rows = load_builder(), source_rows()
    source, pack = tmp_path / 'source.zip', tmp_path / 'pack'
    write_source(source, rows)
    generate(mod, monkeypatch, source, pack)
    for path in (pack / 'fixtures').rglob('*.csv'):
        path.unlink()
    old_labels = {p: p.read_bytes() for p in (pack / 'verify').glob('*.csv')}
    replace, unlink = mod.os.replace, Path.unlink
    calls = 0

    def fail_replace(src, dst):
        nonlocal calls
        calls += 1
        if calls == 3:
            raise OSError('publication failure')
        return replace(src, dst)

    def fail_unlink(path, *args, **kwargs):
        if path.name in ('train_offers.csv', 'test_offers.csv'):
            raise OSError('unlink failure')
        return unlink(path, *args, **kwargs)

    with monkeypatch.context() as patch:
        patch.setattr(mod.os, 'replace', fail_replace)
        patch.setattr(Path, 'unlink', fail_unlink)
        with pytest.raises(RuntimeError, match='recovery files retained at') as exc:
            generate(mod, monkeypatch, source, pack, seed=9)
    recovery = Path(str(exc.value).split(' at ', 1)[1])
    manifest = json.loads((recovery / 'manifest.json').read_text())
    assert [entry['existed'] for entry in manifest] == [False, False, False, True, True]
    # Follow the documented recovery contract using only retained evidence.
    for i, entry in enumerate(manifest):
        target = pack / entry['path']
        backup = recovery / 'backup' / f'{i}.csv'
        if not entry['existed']:
            target.unlink(missing_ok=True)
        elif backup.exists():
            replace(backup, target)
    assert {p: p.read_bytes() for p in pack.rglob('*.csv') if recovery not in p.parents} == old_labels
    mod.shutil.rmtree(recovery)
    generate(mod, monkeypatch, source, pack, seed=9)
    assert_joins(pack, rows)
