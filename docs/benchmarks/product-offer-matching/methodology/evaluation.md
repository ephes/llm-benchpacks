# Evaluation Metrics

## Problem

The benchmark outputs a clustering (`offer_id → cluster_id`) plus, optionally,
pair scores. Scoring it well is subtle: a single F1 number can hide over-merging,
splitting, or a system that only works on easy entities. This document defines
the metric families, their pros and cons, and the recommended headline set, so
the benchmark measures what we actually care about — correct *entities*, under a
realistic cost budget.

Three metric families:

1. **Cluster quality** — did we recover the right product groups?
2. **Pair ranking** — is the scorer's ordering good (an evaluation aid)?
3. **Systems** — throughput, memory, blocking cost.

## Cluster-quality metrics

Notation: predicted clusters partition the offers; gold clusters are the true
products. A *pair* is two offers; a pair is a true-positive if both offers are in
the same predicted cluster *and* the same gold cluster.

### Pairwise precision / recall / F1

Over all offer pairs:

- precision = TP / (predicted same-cluster pairs)
- recall = TP / (gold same-cluster pairs)
- F1 = harmonic mean.

**Pros:** intuitive, directly tied to pair decisions, standard in EM.
**Cons:** dominated by large clusters — a cluster of size `m` contributes
`m(m−1)/2` pairs, so getting a few big clusters right swamps many small ones.
With many singletons (typical for products), pairwise recall is brittle.

### B-cubed precision / recall / F1

Per *offer*, not per pair. For offer `o` let `P` be its predicted cluster and `G`
its gold cluster:

- B-cubed precision of `o` = `|P ∩ G| / |P|`
- B-cubed recall of `o` = `|P ∩ G| / |G|`

Average over all offers; F1 is their harmonic mean. B-cubed weights every offer
equally regardless of cluster size, so it does not let big clusters dominate, and
it degrades gracefully (each offer contributes independently).

**Pros:** the recommended primary entity metric; handles size skew and
singletons sensibly; widely used in coreference/ER. **Cons:** less immediately
intuitive than pairwise; still a single number that blends over-merge and split
errors.

### Purity and inverse purity

- **Purity:** for each predicted cluster, take the fraction belonging to its
  majority gold cluster; average (offer-weighted). Measures "are predicted
  clusters internally pure?" — penalizes over-merge.
- **Inverse purity:** symmetric, with predicted/gold swapped. Measures "is each
  gold cluster gathered together?" — penalizes splitting.

**Pros:** the two directions cleanly separate the two error types. **Cons:**
purity alone is gamed by making every offer its own cluster (perfect purity,
terrible inverse purity), so the two must always be reported together; their
harmonic mean approximates B-cubed-style balance but is less standard.

### Micro vs macro F1

- **Micro F1:** pool TP/FP/FN across all clusters/classes, then compute F1.
  Big clusters dominate (pair-count weighting again).
- **Macro F1:** compute F1 per gold cluster, then average unweighted. Every
  product counts equally, so performance on the many small clusters is visible.

**Pros:** macro surfaces small-cluster performance the benchmark cares about;
micro reflects aggregate pair-level success. **Cons:** in a pure clustering
setting (no fixed class list, clusters are unlabeled), "per-class F1" needs a
gold↔predicted cluster alignment first, which is itself a choice; B-cubed and
pairwise avoid that alignment problem, which is why they are preferred as the
primary surface here. Report micro/macro mainly when a class/category structure
is available.

### Over-merge and split counts

- **Over-merge count:** predicted clusters spanning >1 gold product.
- **Split count:** gold products spread across >1 predicted cluster.

**Pros:** the most *actionable* diagnostic — they name the failure mode
(threshold too low / chaining vs threshold too high / weak recall). **Cons:**
raw counts depend on dataset size; normalize (per gold cluster) for
cross-dataset comparison.

### Cluster-metric summary

| Metric | Weights | Penalizes over-merge | Penalizes split | Robust to size skew | Role |
|---|---|---|---|---|---|
| Pairwise P/R/F1 | pairs | yes (P) | yes (R) | no | secondary headline |
| B-cubed P/R/F1 | offers | yes (P) | yes (R) | yes | **primary headline** |
| Purity / inverse purity | offers | purity | inv. purity | partly | diagnostic pair |
| Micro F1 | pairs/instances | yes | yes | no | secondary |
| Macro F1 | clusters | yes | yes | yes (over-weights small) | small-cluster check |
| Over-merge / split | clusters | direct | direct | normalize first | **diagnostic** |

## Pair-ranking metrics (evaluation aid)

Computed from the optional `pair_scores` over a fixed eval-pair sample:

- **PR curve + average precision (AP)** — primary; robust to the heavy
  non-match imbalance.
- **ROC-AUC** — secondary; imbalance makes it optimistic.
- **Best hidden-threshold F1** — a diagnostic ceiling for the scorer.
- **Operating-point pair metrics induced by the submitted clusters** — ties the
  scorer back to the actual clustering decision.

Pair ranking measures the scorer in isolation; it is not the headline because
the deliverable is the clustering (clustering.md).

## Blocking metrics

Defined in blocking.md (pair completeness, reduction ratio, pairs quality).
Reported in the systems table because blocking is a recall ceiling and a cost
lever at once.

## Catalog-linkage metrics (warm-start regime)

The cluster metrics above score a *partition* and are the right surface for batch
deduplication. The warm-start regime (index.md) instead assigns each incoming
offer to a known product **or** declares it new, so it is scored like an
open-world classification/retrieval task.

**Output convention (required).** Each offer is assigned an id that is either an
existing catalog product id or a **fresh predicted new-product id**. A system
that declares an offer new must still *group* the novel offers it believes are
the same product under a shared predicted id — a single `"new"` sentinel for all
novel offers is invalid, because it collapses unrelated new products into one
cluster, while making each novel offer its own singleton splits repeated offers
of the same new product. Requiring predicted new-product ids makes both the
linkage metrics and the cluster metrics below well-defined.

The metrics:

- **Assignment accuracy.** Fraction of offers given the correct decision —
  linked to their true catalog product, or correctly flagged new.
- **Link precision@1 / top-1 accuracy** over offers whose true product *is* in
  the catalog: did the top candidate point to the right product?
- **New-entity detection (open-world).** Precision/recall of the known-vs-new
  decision. The actionable confusion breakdown:
  - *known→correct*: linked to the right catalog product;
  - *known→wrong*: linked to the wrong catalog product (false link);
  - *known→missed*: should have linked, but flagged new (misses a known product);
  - *new→correct*: novel product correctly flagged new;
  - *new→mislinked*: novel product wrongly linked to a known product.
- **Macro vs micro** over catalog products, as in the cluster metrics, so a few
  popular products do not dominate.

After assignment, the offers form clusters — every offer sharing an assigned id,
whether an existing catalog id or a predicted new-product id (per the output
convention above) — so **B-cubed and pairwise can be computed on the result
too**, useful for comparing a warm-start system against a cold-start one on the
same data. The predicted-new-id convention is what keeps this well-defined:
distinct novel products stay separate and repeated offers of one novel product
stay together. Report both: the linkage metrics describe the decision the system
actually made; the cluster metrics make it comparable across regimes.

## Systems metrics

From `../literature.md`: wall time (total and per stage when reported),
offers/second, eval-pairs/second, peak RSS, MB per 1K offers, candidate count,
comparisons per offer. These keep a fast-but-wrong or memory-exploding matcher
from looking comparable to a real pipeline.

## Recommended headline set

- **Primary quality:** B-cubed F1 (with its P/R), pairwise cluster F1.
- **Diagnostics:** over-merge / split counts, purity / inverse purity, AP over
  eval pairs, hard-negative false-positive rate.
- **Systems:** offers/second, peak RSS, blocking pair completeness + reduction
  ratio.
- **Combined score:** the transparent weighted formula in `../literature.md`
  (quality-dominant, with throughput/memory/blocking terms), always reported
  alongside its components and behind hard gates (invalid output → 0; quality
  floor; blocking-recall floor; memory/timeout caps).

Never reduce a run to pass/fail for model comparison — inspect the component
tables (quality / systems / combined) as in `../literature.md`.

## Benchmark implications

- Make B-cubed the primary entity metric; keep pairwise as the familiar
  secondary; always show over-merge/split.
- Report purity and inverse purity *as a pair*, never purity alone.
- Use macro F1 only where category/class structure exists; otherwise rely on
  B-cubed to avoid the cluster-alignment problem.
- Keep pair ranking as a diagnostic surface, not the target.

## Open questions

- Exact combined-score weights and lane-specific baselines/caps — inherited from
  `../literature.md`, to be re-tuned once real distributions are measured.
- Whether to add B-cubed variants that adjust for singletons explicitly.
- Whether to report a CEAF or V-measure-style metric as an additional
  cross-check, or keep the surface minimal (B-cubed + pairwise + over-merge/
  split).

## References

- Christen, *Data Matching*, 2012 — metric definitions; `../literature.md`
  Tier 2.
- Draisbach et al., 2019; Bhattacharya & Getoor, 2007 — cluster-quality framing;
  `../literature.md` Tier 1.
- Bagga & Baldwin, *Algorithms for Scoring Coreference Chains*, 1998 — origin of
  the B-cubed metric; the MUC/B-cubed/CEAF family carries over from coreference
  evaluation.
- WDC Products (pairwise + multi-class formulations) — `../literature.md`
  Tier 1. Its **unseen-entities** axis (test products absent from training)
  measures generalization, not memorization — the right stress test, and the
  reason to prefer it over the partly-saturated Magellan sets
  ([critical re-evaluation](https://arxiv.org/pdf/2307.01231); `resources.md`).
- SIGMOD2020/Alaska — F-measure-on-pairs protocol over product specs
  (`resources.md`).
- Metric implementations: `bcubed` (PyPI), scikit-learn `v_measure_score` and
  related, RunOrVeith/BCUBED (fast) — see `resources.md`.
