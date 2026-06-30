# Billiger Fixture Builder — Design

Date: 2026-06-30
Status: design, pending implementation plan.

## Goal

Turn the committed raw billiger.de scrape into a benchmark-grade **cold-start
(batch dedup)** product-matching fixture with a **clean** gold set, mirroring the
structure of the existing PriceRunner pack while adding the price and image
signals the PriceRunner data lacks (decision D-034). This builder produces only
the fixture; wiring it into `benchpack.toml`, prompts, and the verifier is a
separate later step.

Scope decisions (agreed during brainstorming):

- **Cold-start only** — train/test products disjoint; warm-start (catalog-linkage)
  is a later, separate builder.
- **Clean lane** — drop confidently-noisy offers, report the residual rate.
- **Sizing mirrors PriceRunner** — ~30% of offers to train, ~70% to test; ~20k
  eval pairs at 1:3 positive:negative.
- **Keep eval pairs** — for the threshold-independent ranking lane (PR curve /
  average precision) and hard-negative-specific reporting.

## Input

`benchpacks/product-offer-matching/pilot-data/billiger-pilot-offers.csv`
(31,330 offers, 4,653 clusters, 50 categories, 100% price+image). Columns:
`offer_id, title, shop_name, price_eur, brand, category_label, image_url,
cluster_id, cluster_label, source_query`. The cluster key is billiger's variant
`product_id`. **No GTIN/EAN exists in the scrape**, so the D-035 identifier-strip
is a no-op here.

The committed CSV is the regenerable snapshot; this builder is deterministic
source, so fixture + builder + snapshot together are reproducible
(benchmark-constraints.md).

## Pipeline

### 1. Clean-lane validation pass

Goal: remove the *dangerous* label noise (genuinely different products sharing a
gold cluster) while keeping the *hard cases* (which are the point of the task).
Each pass flags; the policy decides drop vs keep.

- **Model-token disjointness (DROP, conservative).** Per cluster, derive the
  dominant model-token signature (the family/generation/model-code tokens shared
  by most of its offers). Drop an offer whose title carries a *strong* model
  token that conflicts with the cluster's dominant one (e.g. `S25` in an `S26`
  cluster, `RTX 5080` in an `RTX 5070` cluster, `A55` in an `S24` cluster). Only
  high-confidence conflicts are dropped, to avoid removing legitimate hard cases.
  This is a first heuristic implementation with thresholds surfaced in the build
  report; the exact extraction recipe (cf. signals.md LCS) is tunable.
- **Unit-conflict (DROP).** Drop offers whose storage/size token conflicts with
  the cluster's dominant unit (a `256GB` offer in an otherwise-`512GB` cluster),
  since billiger variant clusters are storage/colour-specific.
- **Price-outlier (FLAG, keep).** Flag offers far from the cluster's robust price
  center (> k·MAD from the median). Kept — usually real market variance, and the
  signal an algorithm should learn, not a label error.
- **Degenerate-title (FLAG, keep).** Flag titles too short / lacking a
  distinguishing token (bare `iPhone 17`). Kept — these are the hard cases.

After dropping, clusters that fall to 0 offers vanish; singletons remain.
Emit a `build-report.json` with per-pass flag/drop counts and the **estimated
residual noise rate** (so the achievable metric ceiling is documented).

### 2. Cold-start split (by cluster, seeded)

- Deterministically shuffle clusters with a fixed `SEED`.
- Accumulate clusters into **train** until ~30% of (post-clean) offers are
  reached; the rest are **test**. Splitting whole clusters keeps train/test
  products **disjoint** (the generalization property).
- Reassign opaque sequential local ids **after** shuffling within each split:
  `offer_id` → `oNNNNN`, `cluster_id` → `cNNNNN`. Public row order and id
  sequence must not encode the source cluster order (anti-leakage, as in the
  PriceRunner builder).

### 3. Eval-pair sampling (from test offers)

- Target ~20,000 pairs, ~5,000 positive / ~15,000 negative (1:3), seeded.
- **Positives:** two offers from the same test cluster (clusters with ≥2 offers).
- **Hard negatives:** two test offers, same `brand`+`category_label`, different
  cluster — drawn from the dense blocks (200–344 sibling products) so the lane
  stresses confusable cases.
- **Easy negatives:** two test offers from different categories.
- Mix hard and easy negatives (proportion recorded in the build report).
- Pair labels are verifier-owned (hidden).

## Outputs

Written under a new billiger fixture directory (exact path finalized in the plan;
parallel to the PriceRunner `fixtures/matcher-repo/data/`):

Public (workspace) files:

- `train_offers.csv` — `offer_id, title, shop_name, price_eur, category_label,
  image_url, cluster_id, cluster_label` (visible labels).
- `test_offers.csv` — same columns **minus** `cluster_id, cluster_label`.
- `eval_pairs.csv` — `pair_id, offer_id_left, offer_id_right`.

Verifier-owned files:

- `verify/hidden_test_clusters.csv` — `offer_id, cluster_id` for every test offer.
- `verify/hidden_eval_pair_labels.csv` — `pair_id, label` (1/0).

Audit:

- `build-report.json` — flat/structured: input counts, per-pass flag/drop counts,
  residual noise rate, train/test offer+cluster counts, eval-pair pos/neg and
  hard/easy counts, seed.

Schema notes:

- `shop_name`, `price_eur`, `image_url` are kept as offer features — `price_eur`
  and `image_url` are the new signals the whole effort is about; `shop_name` is a
  legitimate (non-leaking) merchant feature. `brand`/`category_label` are billiger
  classifier outputs kept as labels/features, never as gold (D-035 / data-quality).
- `cluster_label` is exposed only in `train_offers.csv` (it is a per-product gold
  name; test must not see it).

## Cross-cutting

- **Determinism:** single `SEED`; deterministic shuffle, split, and sampling;
  sorted/stable output. Same input → same fixture.
- **Anti-leakage:** gold cluster ids and pair labels live only under `verify/`;
  test offers carry no cluster columns; ids reassigned post-shuffle so public
  order/ids do not encode cluster structure.
- **Image URLs may rot.** `image_url` points at billiger's CDN; URLs can expire
  over time. Acceptable for a research fixture; the durable image-storage policy
  (hashes/embeddings vs URLs) remains open question 6 in the sourcing analysis.

## Out of scope (YAGNI)

- Warm-start / catalog-linkage split.
- Realistic (noise-kept) lane.
- `benchpack.toml` cases, prompts, the verifier, the amplified scale set for
  system metrics — all separate later steps.

## Open parameters (defaults; finalize in plan)

- Train offer fraction (default 0.30), eval-pair total (20k) and pos:neg (1:3),
  hard:easy negative split.
- Price-outlier `k·MAD` multiplier, minimum title length, model-token match
  strictness — tunable, reported per build (data-quality.md open questions).
