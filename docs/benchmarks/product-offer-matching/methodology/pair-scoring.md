# Pair Scoring and Metric Learning

## Problem

Blocking gives candidate pairs (blocking.md); signals give each pair a
comparison vector (signals.md). Pair scoring turns that vector into a number —
ideally a calibrated probability — that two offers are the same product. Those
scores become the weighted edges that clustering (clustering.md) operates on.

The scorer must work from noisy signals, not exact identifiers, and it must
generalize from visible labeled products to disjoint hidden products. A scorer
that memorizes seen entities or leans on a leaked identifier is not solving the
resolution problem.

## Methods

Ordered roughly from dependency-free to dependency-heavy.

### Fixed-weight similarity (baseline)

A hand-weighted sum of field similarities with a tuned threshold. This is what a
shallow agent submission produces, and it is a legitimate baseline — but it is
also the thing the redesign wants to push past, because it mostly rewards
threshold tuning (`../literature.md` Diagnosis). Keep it as a reference floor.

### Fellegi-Sunter probabilistic linkage

The classical record-linkage foundation (Fellegi & Sunter, 1969). For each
comparison feature, estimate `m = P(agree | match)` and `u = P(agree |
non-match)`; the per-feature log-likelihood ratio `log(m/u)` for agreement (and
`log((1−m)/(1−u))` for disagreement) sums to a match weight. Decision thresholds
follow from target error rates. `m`/`u` can be learned from labeled pairs or via
EM when labels are scarce. Dependency-free and interpretable; a strong baseline
that learns weights instead of hardcoding them.

### Learned per-field similarity

Rather than fixed string metrics, learn the similarity function itself
(Bilenko & Mooney, KDD 2003): trainable string-similarity weights, optionally
with active learning to label the most informative pairs. Bridges hand-written
similarity and fully learned matchers.

### Feature-vector classifier

Assemble the comparison vector (title cosine, price log-ratio, shared-identifier
length, identifier-conflict flag, brand agreement, …) and train a standard
classifier (logistic regression, gradient-boosted trees, random forest) on
labeled pairs. Logistic regression gives calibrated-ish probabilities and
interpretable coefficients; gradient-boosted trees capture interactions (e.g. "high
title similarity *and* identifier conflict → non-match"). This is the workhorse
for tabular ER and a good dependency-enabled default. Interactions matter for
**category-conditional** weighting: practitioner experience
(findings-domain-knowledge.md) shows price is decisive for most goods but
*misleading* for subsidized contract phones and accessories, so the price
feature should be conditioned on category (a tree learns this; a single global
price weight cannot).

### Transformer cross-encoder

Serialize the pair into one sequence and fine-tune a pretrained LM to classify
match/non-match (Ditto, Li et al., PVLDB 2020; DeepMatcher, Mudgal et al.,
SIGMOD 2018). Strongest pairwise accuracy on EM benchmarks; heavy dependency and
compute. Use as an upper-baseline reference for local-only lanes, or an allowed
approach in dependency-enabled lanes.

### Metric learning / contrastive embeddings

Instead of scoring pairs directly, learn an embedding space where same-product
offers are close (R-SupCon, Peeters & Bizer, 2022; ArcFace-style heads in the
Shopee solutions). Then similarity = embedding distance, and candidate
generation = ANN in that space (blocking.md). Advantages: training-data
efficient, scales via ANN, unifies blocking and scoring, and extends naturally
to images (signals.md). This is the practical product-matching path at scale.

## Calibration and thresholding

Clustering needs a meaningful edge weight, so a calibrated score matters:

- **Calibration.** If the scorer claims probabilities, check them: reliability
  curve (predicted vs empirical match rate per bin) and expected calibration
  error. Recalibrate with Platt scaling or isotonic regression if needed.
- **Threshold selection without hidden labels.** The agent must pick an
  operating threshold using only visible/training labels. Record the chosen
  threshold and compare it to the best-achievable hidden threshold (the
  *calibration gap*); a large gap means the scorer's score distribution shifts
  between visible and hidden products — a generalization failure, not just a
  tuning miss.
- **Class imbalance.** Non-matches dominate, so optimize and report PR-based
  operating points (max-F1, or precision at a target recall), not accuracy.

## How we measure it

Pair scoring is measured over the candidate pairs, with gold pair labels:

- **PR curve and average precision (AP)** — the primary ranking metric;
  robust to imbalance.
- **ROC-AUC** — secondary only; imbalance makes it look optimistic.
- **Selected threshold vs best hidden threshold** — the calibration/
  generalization gap above.
- **Calibration error** — only if probabilities are claimed.
- **Sliced performance** — AP on hard negatives (same brand, adjacent model),
  unseen entities, and low-attribute/terse rows, so a high overall AP cannot
  hide failure on the cases that matter.

Pair scoring is an *evaluation aid*, not the headline deliverable: the benchmark
target is the clustering, and pair scores let us inspect the scorer in
isolation. See evaluation.md for how pair metrics sit alongside cluster metrics.

## Benchmark implications

- Reward scorers that **learn** weights/probabilities over those that hardcode a
  single threshold; the Fellegi-Sunter and classifier baselines are the bar to
  beat. Cross-dataset evidence (findings-pilot.md) shows the *strongest* signal
  shifts between datasets — price on the billiger pilot, text on Amazon-Google —
  so per-dataset learned weights matter rather than a fixed signal priority.
- Require an operating threshold chosen without hidden labels, and report the
  calibration gap as a generalization diagnostic.
- Keep exact-identifier matching in a separate baseline lane; do not let it leak
  into the learned-scorer lane (signals.md).
- Allow cross-encoder / embedding approaches only in dependency-enabled lanes;
  keep a standard-library lane honest as a from-scratch test.

## Open questions

- Default dependency-free scorer baseline: Fellegi-Sunter vs logistic regression
  over engineered features — pick after measuring both on a representative
  sample.
- Whether to require the agent to emit per-pair probabilities (enabling
  calibration metrics) or allow unnormalized scores (ranking metrics only).
- How aggressively to strip identifiers so the scorer is tested without making
  the task unrealistically hard.

## References

- Fellegi & Sunter, *A Theory for Record Linkage*, 1969 — `../literature.md`
  Tier 2.
- Bilenko & Mooney, KDD 2003 — `../literature.md` Tier 2.
- Li et al., *Ditto*, PVLDB 2020; Mudgal et al., *DeepMatcher*, SIGMOD 2018 —
  `../literature.md` Tier 1.
- Peeters & Bizer, *R-SupCon*, 2022 — `../literature.md` Tier 1.
- Zhang et al., *Jellyfish: Instruction-Tuning Local LLMs for Data Preprocessing*,
  EMNLP 2024. [ACL](https://aclanthology.org/2024.emnlp-main.497.pdf) — a local
  fine-tuned LLM matcher competitive with GPT-4 on EM; relevant if a direct-LLM
  matcher lane is added. Recent work reports fine-tuned *small* models beat
  general LLMs on EM, reinforcing the small-specialized-model framing in
  `../literature.md` Tier 3.
- `resources.md` for `dedupe` (Fellegi-Sunter + active learning),
  `py_entitymatching` (rule + ML matchers), Ditto/DeepMatcher repos, Jellyfish,
  and Shopee metric-learning solutions.
- Solved-instance pipeline (`resources.md`, *Techniques from solved instances*):
  the Shopee two-stage recipe — ArcFace/CurricularFace embeddings → cosine-KNN
  candidates → 2nd-stage LightGBM/GAT re-ranker over ~500 pair features — is the
  proven product image+text scoring architecture.
