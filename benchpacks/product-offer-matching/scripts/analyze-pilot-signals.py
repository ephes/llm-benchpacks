#!/usr/bin/env python3
"""Tier-1 evidence pass over the billiger pilot offers: dataset shape, blocking
recall (pair completeness), per-signal separability (ROC-AUC / average
precision), error analysis of the title-Jaccard baseline, and signal ablations.

Stdlib only, deterministic (seeded sampling). Companion to baseline-clusterer.py;
where that scores one matcher, this explains *why* it scores what it does and
which signals would move it. Findings are written up in
docs/benchmarks/product-offer-matching/methodology/findings-pilot.md.

Usage:
  python analyze-pilot-signals.py [offers.csv]
"""
import csv, re, sys, math, random, collections
from itertools import combinations
from pathlib import Path

random.seed(0)
DEFAULT_CSV = Path(__file__).resolve().parent.parent / "pilot-data" / "billiger-pilot-offers.csv"
CSV = sys.argv[1] if len(sys.argv) > 1 else str(DEFAULT_CSV)

UNIT = re.compile(r"^\d+(gb|tb|mb|kb|ghz|mhz|hz|mah|wh|kw|w|mm|cm|zoll|inch|in|k|p|fps|nm|ml|l|g|m)$")
WORD = re.compile(r"[^a-z0-9äöüß ]")


def toks(s):
    return frozenset(t for t in WORD.sub(" ", s.lower()).split() if len(t) > 1)


def first_tok(s):
    """The genuine first usable token of the title (in title order)."""
    for t in WORD.sub(" ", s.lower()).split():
        if len(t) > 1:
            return t
    return ""


def codes(s):
    """Per-offer candidate model codes: alnum tokens mixing letters+digits, len>=4,
    not a pure unit. Token-level (a lower bound; LCS/Aho-Corasick over a separator-
    stripped stream would also catch codes split by spaces/dashes)."""
    out = set()
    for t in WORD.sub(" ", s.lower()).split():
        if len(t) >= 4 and re.search(r"[a-z]", t) and re.search(r"\d", t) and not UNIT.match(t):
            out.add(t)
    return frozenset(out)


def ngrams(s, n=3):
    s = re.sub(r"\s+", " ", WORD.sub(" ", s.lower())).strip()
    return collections.Counter(s[i:i+n] for i in range(len(s)-n+1)) if len(s) >= n else collections.Counter()


def cos(a, b):
    if not a or not b:
        return 0.0
    dot = sum(a[k]*b[k] for k in a if k in b)
    na = math.sqrt(sum(v*v for v in a.values()))
    nb = math.sqrt(sum(v*v for v in b.values()))
    return dot/(na*nb) if na and nb else 0.0


def jac(a, b):
    return len(a & b)/len(a | b) if a and b else 0.0


def auc(scores_labels):
    """ROC-AUC via rank-sum (average ranks for ties)."""
    xs = sorted(scores_labels, key=lambda t: t[0])
    n = len(xs)
    ranks = [0.0]*n
    i = 0
    while i < n:
        j = i
        while j < n and xs[j][0] == xs[i][0]:
            j += 1
        avg = (i + j - 1)/2 + 1
        for k in range(i, j):
            ranks[k] = avg
        i = j
    npos = sum(1 for _, l in xs if l)
    nneg = n - npos
    if npos == 0 or nneg == 0:
        return float("nan")
    spos = sum(r for r, (_, l) in zip(ranks, xs) if l)
    return (spos - npos*(npos+1)/2)/(npos*nneg)


def ap(scores_labels):
    """Average precision, tie-aware (groups equal scores at one threshold, like
    sklearn average_precision_score). A naive per-row AP would be biased by tie
    order — fatal for binary/discrete signals."""
    xs = sorted(scores_labels, key=lambda t: -t[0])
    npos = sum(1 for _, l in xs if l)
    if not npos:
        return float("nan")
    n = len(xs)
    tp = fp = 0
    prev_recall = 0.0
    out = 0.0
    i = 0
    while i < n:
        j = i
        while j < n and xs[j][0] == xs[i][0]:
            if xs[j][1]:
                tp += 1
            else:
                fp += 1
            j += 1
        recall = tp/npos
        precision = tp/(tp+fp)
        out += (recall-prev_recall)*precision
        prev_recall = recall
        i = j
    return out


def bcubed_f1(pred, gold):
    bp_ = collections.defaultdict(list)
    bg_ = collections.defaultdict(list)
    for oid in pred:
        bp_[pred[oid]].append(oid)
        bg_[gold[oid]].append(oid)
    ps = {oid: len(bp_[pred[oid]]) for oid in pred}
    gs = {oid: len(bg_[gold[oid]]) for oid in pred}
    bp = br = 0.0
    for m in bp_.values():
        gc = collections.Counter(gold[o] for o in m)
        for o in m:
            c = gc[gold[o]]
            bp += c/ps[o]
            br += c/gs[o]
    n = len(pred)
    bp /= n
    br /= n
    return 2*bp*br/(bp+br) if bp+br else 0.0


def union_find_cluster(blocks, link_fn, thr):
    par = {}
    for ids in blocks.values():
        for oid in ids:
            par.setdefault(oid, oid)

    def f(x):
        while par[x] != x:
            par[x] = par[par[x]]
            x = par[x]
        return x

    for ids in blocks.values():
        for a, b in combinations(ids, 2):
            if link_fn(a, b, thr):
                ra, rb = f(a), f(b)
                if ra != rb:
                    par[ra] = rb
    return {oid: f(oid) for oid in par}


def main():
    rows = list(csv.DictReader(open(CSV, encoding="utf-8")))
    for r in rows:
        r["price"] = float(r["price_eur"]) if r["price_eur"] else None
    gold = {r["offer_id"]: r["cluster_id"] for r in rows}
    tok = {r["offer_id"]: toks(r["title"]) for r in rows}
    cd = {r["offer_id"]: codes(r["title"]) for r in rows}
    ng = {r["offer_id"]: ngrams(r["title"]) for r in rows}
    price = {r["offer_id"]: r["price"] for r in rows}
    by_gold = collections.defaultdict(list)
    for r in rows:
        by_gold[r["cluster_id"]].append(r["offer_id"])

    print("="*70, "\nSECTION A — dataset shape\n", "="*70, sep="")
    sizes = sorted(len(v) for v in by_gold.values())
    singles = sum(1 for s in sizes if s == 1)
    print(f"offers: {len(rows)}  gold clusters: {len(by_gold)}  mean size: {len(rows)/len(by_gold):.2f}")
    print(f"singletons: {singles} ({singles/len(by_gold):.1%})  median size: {sizes[len(sizes)//2]}  max size: {sizes[-1]}")
    print(f"price coverage: {sum(1 for p in price.values() if p):,}/{len(rows)} ({sum(1 for p in price.values() if p)/len(rows):.1%})")
    code_cov = sum(1 for c in cd.values() if c)
    print(f"offers with >=1 extractable model code: {code_cov:,} ({code_cov/len(rows):.1%})")
    print(f"brands: {len(set(r['brand'].lower().strip() for r in rows))}  categories: {len(set(r['category_label'] for r in rows))}")

    gold_pairs = set()
    for ids in by_gold.values():
        for a, b in combinations(sorted(ids), 2):
            gold_pairs.add((a, b))
    print(f"total gold positive pairs: {len(gold_pairs):,}")

    print("\n", "="*70, "\nSECTION B — blocking recall (pair completeness) & cost\n", "="*70, sep="")
    schemes = {
        "(brand, category)": lambda r: (r["brand"].lower().strip(), r["category_label"]),
        "brand only": lambda r: (r["brand"].lower().strip(),),
        "category only": lambda r: (r["category_label"],),
        "first title token": lambda r: (first_tok(r["title"]),),
    }
    allpairs = len(rows)*(len(rows)-1)//2
    print(f"{'scheme':>20} {'PC(recall)':>11} {'cand pairs':>12} {'RR':>7} {'maxblk':>7}")
    for name, key in schemes.items():
        blocks = collections.defaultdict(list)
        for r in rows:
            blocks[key(r)].append(r["offer_id"])
        cand = sum(len(v)*(len(v)-1)//2 for v in blocks.values())
        keyof = {r["offer_id"]: key(r) for r in rows}
        kept = sum(1 for (a, b) in gold_pairs if keyof[a] == keyof[b])
        print(f"{name:>20} {kept/len(gold_pairs):>11.3f} {cand:>12,} {1-cand/allpairs:>7.3f} {max(len(v) for v in blocks.values()):>7}")

    print("\n", "="*70, "\nSECTION C — signal separability over (brand,category) candidate pairs\n", "="*70, sep="")
    blocks = collections.defaultdict(list)
    for r in rows:
        blocks[(r["brand"].lower().strip(), r["category_label"])].append(r["offer_id"])
    pos, neg = [], []
    for ids in blocks.values():
        for a, b in combinations(ids, 2):
            (pos if gold[a] == gold[b] else neg).append((a, b))
    random.shuffle(neg); neg = neg[:min(len(neg), 60000)]
    random.shuffle(pos); pos = pos[:min(len(pos), 60000)]
    pairs = [(p, 1) for p in pos] + [(p, 0) for p in neg]
    print(f"candidate pairs sampled: {len(pos):,} pos / {len(neg):,} neg (match rate {len(pos)/(len(pos)+len(neg)):.1%})")

    def relprice(a, b):
        pa, pb = price[a], price[b]
        return abs(pa-pb)/min(pa, pb) if pa and pb else None

    sig = {"title token Jaccard": [], "title char-3gram cosine": [],
           "price similarity 1/(1+relgap)": [], "shared model code (0/1)": []}
    for (a, b), l in pairs:
        sig["title token Jaccard"].append((jac(tok[a], tok[b]), l))
        sig["title char-3gram cosine"].append((cos(ng[a], ng[b]), l))
        rp = relprice(a, b)
        if rp is not None:
            sig["price similarity 1/(1+relgap)"].append((1/(1+rp), l))
        sig["shared model code (0/1)"].append((1.0 if (cd[a] & cd[b]) else 0.0, l))
    print(f"{'signal':>32} {'ROC-AUC':>8} {'avg-prec':>9}")
    for name, sl in sig.items():
        print(f"{name:>32} {auc(sl):>8.3f} {ap(sl):>9.3f}")

    cp = sum(1 for (a, b), l in pairs if l and cd[a] and cd[b] and not (cd[a] & cd[b]))
    cn = sum(1 for (a, b), l in pairs if not l and cd[a] and cd[b] and not (cd[a] & cd[b]))
    bpos = sum(1 for (a, b), l in pairs if l and cd[a] and cd[b])
    bneg = sum(1 for (a, b), l in pairs if not l and cd[a] and cd[b])
    print("\ncode-conflict (both have codes, disjoint):")
    print(f"  among MATCH pairs w/ both codes:     {cp}/{bpos} ({cp/bpos:.1%} conflicts — token-level noise; should be ~0)")
    print(f"  among NON-MATCH pairs w/ both codes: {cn}/{bneg} ({cn/bneg:.1%} conflicts — useful negative signal)")

    print("\n", "="*70, "\nSECTION D — error analysis of the title-Jaccard baseline (thr 0.5)\n", "="*70, sep="")
    pred = union_find_cluster(blocks, lambda a, b, t: jac(tok[a], tok[b]) >= t, 0.5)
    by_pred = collections.defaultdict(list)
    for oid in pred:
        by_pred[pred[oid]].append(oid)
    overmerge = sum(1 for m in by_pred.values() if len(set(gold[o] for o in m)) > 1)
    g2p = collections.defaultdict(set)
    for oid in pred:
        g2p[gold[oid]].add(pred[oid])
    splits = sum(1 for v in g2p.values() if len(v) > 1)
    print(f"predicted {len(by_pred)} clusters vs {len(by_gold)} gold")
    print(f"over-merged predicted clusters (span >1 gold): {overmerge}")
    print(f"split gold clusters (across >1 predicted): {splits} ({splits/len(by_gold):.1%} of gold)")
    same, below, jvals = 0, 0, []
    for ids in blocks.values():
        for a, b in combinations(ids, 2):
            if gold[a] == gold[b]:
                same += 1
                j = jac(tok[a], tok[b]); jvals.append(j)
                if j < 0.5:
                    below += 1
    jvals.sort()
    print(f"\nsplit cause — same-gold in-block pairs scoring < 0.5: {below}/{same} ({below/same:.1%})")
    print(f"  title-Jaccard of same-gold in-block pairs: median {jvals[len(jvals)//2]:.2f}, p25 {jvals[len(jvals)//4]:.2f}, p10 {jvals[len(jvals)//10]:.2f}")
    keyof = {r["offer_id"]: (r["brand"].lower().strip(), r["category_label"]) for r in rows}
    sbb = sum(1 for (a, b) in gold_pairs if keyof[a] != keyof[b])
    print(f"split cause — same-gold pairs in DIFFERENT (brand,category) blocks: {sbb}/{len(gold_pairs)} ({sbb/len(gold_pairs):.1%})")

    print("\n", "="*70, "\nSECTION E — ablations (best B-cubed F1 per variant)\n", "="*70, sep="")
    base = lambda a, b, t: jac(tok[a], tok[b]) >= t
    price_guard = lambda a, b, t: jac(tok[a], tok[b]) >= t and (relprice(a, b) is None or relprice(a, b) <= 0.25)
    code_or = lambda a, b, t: bool(cd[a] & cd[b]) or jac(tok[a], tok[b]) >= t
    code_veto = lambda a, b, t: jac(tok[a], tok[b]) >= t and not (cd[a] and cd[b] and not (cd[a] & cd[b]))
    for name, fn in [("baseline (title Jaccard)", base), ("+ price guard (relgap<=25%)", price_guard),
                     ("+ shared-code OR link", code_or), ("+ code-conflict veto", code_veto)]:
        best = max((bcubed_f1(union_find_cluster(blocks, fn, t), gold), t) for t in (0.3, 0.4, 0.5, 0.6))
        print(f"{name:>32}: best B-cubed F1 {best[0]:.3f} (thr {best[1]})")


if __name__ == "__main__":
    main()
