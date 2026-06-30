#!/usr/bin/env python3
"""Tier-3 comparability anchor: run the same per-signal separability analysis as
analyze-pilot-signals.py on the independent Amazon-Google entity-matching
benchmark (price-bearing), to test whether the pilot's signal findings and our
ROC-AUC / average-precision machinery generalize off our own data.

The benchmark data is third-party and not redistributed here. Fetch the serialized
labeled pairs (Ditto's mirror of the ER-Magellan Structured/Amazon-Google split):

  D=https://raw.githubusercontent.com/megagonlabs/ditto/master/data/er_magellan/Structured/Amazon-Google
  mkdir -p amazon-google && cd amazon-google
  for f in train.txt valid.txt test.txt; do curl -fsSLO "$D/$f"; done

Then:  python analyze-amazon-google-signals.py <dir-with-the-txt-files>

Each line is `recordA \t recordB \t label`, each record serialized as
`COL <field> VAL <value> ...` with fields title / manufacturer / price.
"""
import re, sys, math, glob, collections
from pathlib import Path

WORD = re.compile(r"[^a-z0-9 ]")
DATADIR = sys.argv[1] if len(sys.argv) > 1 else "."


def toks(s):
    return frozenset(t for t in WORD.sub(" ", s.lower()).split() if len(t) > 1)


def ngrams(s, n=3):
    s = re.sub(r"\s+", " ", WORD.sub(" ", s.lower())).strip()
    return collections.Counter(s[i:i+n] for i in range(len(s)-n+1)) if len(s) >= n else collections.Counter()


def cos(a, b):
    if not a or not b:
        return 0.0
    dot = sum(a[k]*b[k] for k in a if k in b)
    na = math.sqrt(sum(v*v for v in a.values())); nb = math.sqrt(sum(v*v for v in b.values()))
    return dot/(na*nb) if na and nb else 0.0


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
    """Tie-aware average precision."""
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


def parse_rec(rec):
    fields = {}
    for piece in rec.split("COL "):
        piece = piece.strip()
        if " VAL " in piece:
            f, _, v = piece.partition(" VAL ")
            fields[f.strip()] = v.strip()
    return fields


def to_price(s):
    try:
        return float(s)
    except (ValueError, TypeError):
        return None


def main():
    pairs = []
    for path in sorted(glob.glob(str(Path(DATADIR) / "*.txt"))):
        if path.endswith((".balance", ".jsonl")):
            continue
        for line in open(path, encoding="utf-8"):
            parts = line.rstrip("\n").split("\t")
            if len(parts) != 3:
                continue
            pairs.append((parse_rec(parts[0]), parse_rec(parts[1]), int(parts[2])))
    if not pairs:
        sys.exit(f"no pairs found under {DATADIR!r} — see the download instructions in this file's docstring")

    npos = sum(l for _, _, l in pairs)
    print(f"Amazon-Google: {len(pairs):,} labeled pairs, {npos} positive ({npos/len(pairs):.1%} match rate)")
    pa = sum(1 for a, b, _ in pairs if to_price(a.get('price')) and to_price(b.get('price')))
    print(f"pairs with price on both sides: {pa:,} ({pa/len(pairs):.1%})")

    sig = {"title token Jaccard": [], "title char-3gram cosine": [], "price similarity 1/(1+relgap)": []}
    for a, b, l in pairs:
        ta, tb = a.get("title", ""), b.get("title", "")
        sig["title token Jaccard"].append((jac(toks(ta), toks(tb)), l))
        sig["title char-3gram cosine"].append((cos(ngrams(ta), ngrams(tb)), l))
        pap, pbp = to_price(a.get("price")), to_price(b.get("price"))
        if pap and pbp:
            sig["price similarity 1/(1+relgap)"].append((1/(1+abs(pap-pbp)/min(pap, pbp)), l))

    print(f"\n{'signal':>32} {'ROC-AUC':>8} {'avg-prec':>9} {'n pairs':>9}")
    for name, sl in sig.items():
        print(f"{name:>32} {auc(sl):>8.3f} {ap(sl):>9.3f} {len(sl):>9,}")


if __name__ == "__main__":
    main()
