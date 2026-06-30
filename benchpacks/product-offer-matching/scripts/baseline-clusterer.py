#!/usr/bin/env python3
"""Simple baseline clusterer + scorer over the billiger pilot offers.

Blocking: (brand, category) blocks. Matching: within each block, union-find link
any offer pair whose title-token Jaccard >= threshold. Connected components are
the predicted clusters. Scores B-cubed + pairwise F1 vs the gold cluster_id, and
reports end-to-end wall time, offers/s, and peak RSS. Title-only on purpose (no
price/image) to read the difficulty of the text-only lane.

The reported throughput is end-to-end (CSV load + tokenize + block + match — the
work a clusterer program does); scoring is verifier-side and excluded.
"""
import csv, re, sys, time, resource, subprocess, collections
from itertools import combinations
from pathlib import Path

DEFAULT_CSV = Path(__file__).resolve().parent.parent / "pilot-data" / "billiger-pilot-offers.csv"
CSV = sys.argv[1] if len(sys.argv) > 1 else str(DEFAULT_CSV)


def toks(s):
    s = re.sub(r"[^a-z0-9äöüß ]", " ", s.lower())
    return frozenset(t for t in s.split() if len(t) > 1)


def jaccard(a, b):
    if not a or not b:
        return 0.0
    return len(a & b) / len(a | b)


def cluster(rows, tok, threshold):
    """Block by (brand, category), link within-block pairs over the Jaccard
    threshold via union-find, return (pred, comparisons, n_blocks, biggest_block)."""
    parent = {r["offer_id"]: r["offer_id"] for r in rows}

    def find(x):
        while parent[x] != x:
            parent[x] = parent[parent[x]]
            x = parent[x]
        return x

    def union(a, b):
        ra, rb = find(a), find(b)
        if ra != rb:
            parent[ra] = rb

    blocks = collections.defaultdict(list)
    for r in rows:
        blocks[(r["brand"].lower().strip(), r["category_label"])].append(r["offer_id"])
    comparisons = 0
    for ids in blocks.values():
        for a, b in combinations(ids, 2):
            comparisons += 1
            if jaccard(tok[a], tok[b]) >= threshold:
                union(a, b)
    pred = {oid: find(oid) for oid in parent}
    return pred, comparisons, len(blocks), max(len(v) for v in blocks.values())


def score(pred, gold):
    """B-cubed precision/recall/F1 and pairwise cluster F1 vs gold."""
    by_pred = collections.defaultdict(list)
    by_gold = collections.defaultdict(list)
    for oid in pred:
        by_pred[pred[oid]].append(oid)
        by_gold[gold[oid]].append(oid)
    gsize = {oid: len(by_gold[gold[oid]]) for oid in pred}
    psize = {oid: len(by_pred[pred[oid]]) for oid in pred}
    bp = br = 0.0
    for members in by_pred.values():
        gc = collections.Counter(gold[o] for o in members)
        for o in members:
            correct = gc[gold[o]]
            bp += correct / psize[o]
            br += correct / gsize[o]
    n = len(pred)
    bp /= n
    br /= n
    bf = 2 * bp * br / (bp + br) if bp + br else 0.0

    def npairs(c):
        return c * (c - 1) // 2

    tp = sum(npairs(c) for m in by_pred.values()
             for c in collections.Counter(gold[o] for o in m).values())
    pp = sum(npairs(len(m)) for m in by_pred.values())
    gp = sum(npairs(len(m)) for m in by_gold.values())
    prec = tp / pp if pp else 0.0
    rec = tp / gp if gp else 0.0
    pf = 2 * prec * rec / (prec + rec) if prec + rec else 0.0
    return dict(bp=bp, br=br, bf=bf, pf=pf, npred=len(by_pred), ngold=len(by_gold))


def load(path):
    rows = list(csv.DictReader(open(path, encoding="utf-8")))
    tok = {r["offer_id"]: toks(r["title"]) for r in rows}
    return rows, tok


def _rss_mb(ru_maxrss):
    return ru_maxrss / (1024 * 1024) if sys.platform == "darwin" else ru_maxrss / 1024  # mac bytes, linux KB


def main():
    # Isolated-run measurement path: load + tokenize + block + match once, then
    # exit. Invoked as a subprocess so peak RSS / wall time are for a single
    # clusterer run only, uncontaminated by the threshold sweep and scoring.
    if "--measure" in sys.argv:
        thr = float(sys.argv[sys.argv.index("--measure") + 1])
        t0 = time.perf_counter()
        rows_m, tok_m = load(CSV)
        cluster(rows_m, tok_m, thr)
        # Report the in-child elapsed so the parent excludes interpreter startup.
        print(f"MEASURE_ELAPSED {time.perf_counter() - t0}")
        return

    rows, tok = load(CSV)
    gold = {r["offer_id"]: r["cluster_id"] for r in rows}
    print(f"loaded {len(rows)} offers, {len(set(gold.values()))} gold clusters\n")

    print(f"{'thr':>4} {'Bcubed-F1':>10} {'B-P':>6} {'B-R':>6} {'pair-F1':>8} {'#pred':>6}")
    results = {}
    for thr in (0.3, 0.4, 0.5, 0.6, 0.7):
        pred, comps, nblk, bigblk = cluster(rows, tok, thr)
        s = score(pred, gold)
        results[thr] = (s, comps, nblk, bigblk)
        print(f"{thr:>4} {s['bf']:>10.3f} {s['bp']:>6.3f} {s['br']:>6.3f} {s['pf']:>8.3f} {s['npred']:>6}")

    best = max(results, key=lambda t: results[t][0]["bf"])
    s, comps, nblk, bigblk = results[best]

    # End-to-end system metrics for one clusterer run at the reported threshold,
    # measured in a clean subprocess (CSV load + tokenize + block + match; scoring
    # is verifier-side and excluded). RUSAGE_CHILDREN gives that child's peak RSS.
    proc = subprocess.run([sys.executable, str(Path(__file__).resolve()), CSV, "--measure", str(best)],
                          check=True, capture_output=True, text=True)
    elapsed = next(float(line.split()[1]) for line in proc.stdout.splitlines()
                   if line.startswith("MEASURE_ELAPSED"))
    rss_mb = _rss_mb(resource.getrusage(resource.RUSAGE_CHILDREN).ru_maxrss)

    print(f"\nbest threshold = {best}: B-cubed F1 {s['bf']:.3f}, pairwise F1 {s['pf']:.3f}")
    print(f"predicted {s['npred']} clusters vs {s['ngold']} gold")
    print("\n--- system metrics (one isolated clusterer run, subprocess) ---")
    print(f"blocks: {nblk}, largest block: {bigblk} offers, within-block comparisons: {comps:,}")
    print(f"end-to-end wall time (load+tokenize+block+match): {elapsed * 1000:.0f} ms")
    print(f"offers/sec: {len(rows) / elapsed:,.0f}")
    print(f"peak RSS: {rss_mb:.0f} MB  (combined-score memory term min(1024/rss,1) = {min(1024 / rss_mb, 1):.3f})")


if __name__ == "__main__":
    main()
