#!/usr/bin/env python3
"""Does a better text representation close the split gap? Compare TF-IDF word/char
cosine separability against token-Jaccard on the SAME candidate pairs (seed 0,
identical sampling to analyze-pilot-signals.py). Requires scikit-learn; run via
uv without polluting project deps:

  uv run --with scikit-learn --with numpy \
    python benchpacks/product-offer-matching/scripts/analyze-pilot-tfidf.py
"""
import csv, re, sys, random, collections
from itertools import combinations
from pathlib import Path
from sklearn.feature_extraction.text import TfidfVectorizer

random.seed(0)
DEFAULT_CSV = Path(__file__).resolve().parent.parent / "pilot-data" / "billiger-pilot-offers.csv"
CSV = sys.argv[1] if len(sys.argv) > 1 else str(DEFAULT_CSV)
WORD = re.compile(r"[^a-z0-9äöüß ]")


def toks(s):
    return frozenset(t for t in WORD.sub(" ", s.lower()).split() if len(t) > 1)


def jac(a, b):
    return len(a & b)/len(a | b) if a and b else 0.0


def auc(sl):
    xs = sorted(sl, key=lambda t: t[0]); n = len(xs); ranks = [0.0]*n; i = 0
    while i < n:
        j = i
        while j < n and xs[j][0] == xs[i][0]:
            j += 1
        avg = (i+j-1)/2+1
        for k in range(i, j):
            ranks[k] = avg
        i = j
    npos = sum(1 for _, l in xs if l); nneg = n-npos
    if not npos or not nneg:
        return float("nan")
    return (sum(r for r, (_, l) in zip(ranks, xs) if l)-npos*(npos+1)/2)/(npos*nneg)


def ap(sl):
    """Tie-aware average precision (sklearn semantics)."""
    xs = sorted(sl, key=lambda t: -t[0]); npos = sum(1 for _, l in xs if l)
    if not npos:
        return float("nan")
    n = len(xs); tp = fp = 0; prev = 0.0; out = 0.0; i = 0
    while i < n:
        j = i
        while j < n and xs[j][0] == xs[i][0]:
            if xs[j][1]:
                tp += 1
            else:
                fp += 1
            j += 1
        recall = tp/npos; precision = tp/(tp+fp)
        out += (recall-prev)*precision; prev = recall; i = j
    return out


rows = list(csv.DictReader(open(CSV, encoding="utf-8")))
oid = [r["offer_id"] for r in rows]
idx = {o: i for i, o in enumerate(oid)}
gold = {r["offer_id"]: r["cluster_id"] for r in rows}
tok = {r["offer_id"]: toks(r["title"]) for r in rows}
titles = [r["title"] for r in rows]

# identical pair sampling to analyze-pilot-signals.py
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
print(f"pairs: {len(pos):,} pos / {len(neg):,} neg")


def pair_cos(M):
    return [(float(M[idx[a]].multiply(M[idx[b]]).sum()), l)  # rows L2-normalized
            for (a, b), l in pairs]


configs = {
    "token Jaccard (baseline)": None,
    "TF-IDF word (1,2)": TfidfVectorizer(lowercase=True, ngram_range=(1, 2), min_df=2),
    "TF-IDF char_wb (3,5)": TfidfVectorizer(lowercase=True, analyzer="char_wb", ngram_range=(3, 5), min_df=2),
}
print(f"{'representation':>28} {'ROC-AUC':>8} {'avg-prec':>9}")
for name, vec in configs.items():
    sl = ([(jac(tok[a], tok[b]), l) for (a, b), l in pairs] if vec is None
          else pair_cos(vec.fit_transform(titles)))
    print(f"{name:>28} {auc(sl):>8.3f} {ap(sl):>9.3f}")
