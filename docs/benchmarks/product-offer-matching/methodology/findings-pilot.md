# Findings: Billiger Pilot Signal & Baseline Analysis

Status: **dataset-specific empirical findings** (not stable methodology). This is
the first `evaluated` output of the auto-research pass, run on the billiger.de
pilot (10,825 offers). It instruments the title-only baseline to explain *why* it
scores what it does and which signals would move a solution. Methodology claims
live in the stage docs; these numbers are evidence *for* them, on one concrete
dataset, and will shift if the dataset changes.

Reproduce:

```sh
# stdlib-only: shape, blocking recall, separability, error analysis, ablations
python benchpacks/product-offer-matching/scripts/analyze-pilot-signals.py
# TF-IDF separability comparison (sklearn, no project-dep pollution)
uv run --with scikit-learn --with numpy \
  python benchpacks/product-offer-matching/scripts/analyze-pilot-tfidf.py
```

## TL;DR — what the evidence says for a solution

1. **Blocking is not the bottleneck on this data.** `(brand, category)` blocking
   has pair completeness **1.000** (loses zero gold pairs) at reduction ratio
   0.976. Effort belongs in matching, not candidate generation.
2. **The failure mode is splits, not over-merges.** The title-Jaccard baseline
   splits **71% of gold clusters**, because same-product offers share only a
   **median 0.34 token Jaccard** — titles for one product are lexically very
   different. This is a recall problem.
3. **Price is the single strongest signal** (ROC-AUC **0.905**), above every text
   similarity, and the title-only baseline ignores it. Adding a price guard alone
   lifts B-cubed F1 from 0.409 to **0.463** (+13%).
4. **IDF weighting is a cheap text win.** TF-IDF word cosine (AUC **0.890**) beats
   raw token Jaccard (0.826); swapping Jaccard → TF-IDF cosine costs little.
5. **Identifier codes are high-precision but low-coverage and noisy at token
   level.** Only 54.7% of offers expose an extractable code, and 21.4% of true
   matches look like "code conflicts" under naive token extraction — direct
   evidence for the LCS/Aho-Corasick *normalization* the methodology prescribes.
   Naive shared-code OR-linking *hurts* (0.400); a code-conflict **veto** helps
   (0.463).
6. **The win is multi-signal.** No single signal solves it; TF-IDF/embedding text
   **+** price **+** normalized-identifier veto, tuned together, is the indicated
   direction.

## Section A — dataset shape

| Quantity | Value |
|---|---|
| Offers | 10,825 |
| Gold clusters | 1,485 (mean 7.29, median 9, max 10) |
| Singletons | 63 (4.2%) |
| Price coverage | 100% |
| Offers with ≥1 extractable model code (token-level) | 5,918 (54.7%) |
| Brands / categories | 85 / 18 |
| Gold positive pairs | 40,892 |

Note the **max cluster size of 10**: billiger's initial HTML lazy-loads ~8–10
offers per product, so cluster sizes are capped and the size distribution is
partly an artifact of the scrape, not the market.

## Section B — blocking recall (pair completeness) and cost

| Scheme | PC (recall) | Candidate pairs | RR | Max block |
|---|---|---|---|---|
| (brand, category) | **1.000** | 1,396,950 | 0.976 | 783 |
| brand only | 1.000 | 5,085,631 | 0.913 | 2,540 |
| category only | 1.000 | 5,409,115 | 0.908 | 1,808 |
| first title token | 0.779 | 4,004,095 | 0.932 | 2,251 |

`(brand, category)` is the clear winner: perfect recall at the highest reduction.
First-title-token blocking still loses ~22% of gold pairs (PC 0.779) at a *worse*
reduction — terse and brand-led titles split true matches across keys. Caveat:
the 783-offer max block already hints that brand+category will need a finer key
or ANN at larger scale (D-036's amplified systems lane).

## Section C — signal separability (over (brand,category) candidate pairs)

Sampled 40,892 positive / 60,000 negative candidate pairs (match rate 40.5%).

| Signal | ROC-AUC | Avg precision |
|---|---|---|
| **price similarity** `1/(1+relgap)` | **0.905** | 0.833 |
| TF-IDF word cosine (1–2 gram) | 0.890 | 0.834 |
| TF-IDF char_wb cosine (3–5 gram) | 0.862 | 0.790 |
| title char-3gram cosine | 0.838 | 0.768 |
| title token Jaccard (baseline) | 0.826 | 0.760 |
| shared model code (0/1, token-level) | 0.648 | 0.555 |

Reading: price separates best; IDF-weighted text is a clear step up from raw
Jaccard; shared-code has low AUC and modest AP (binary + 55% coverage), but high
*precision when present* — ~85% of pairs that share a code are true matches. It
is a strong positive *when available* and a poor blanket ranker, which is why it
belongs as a feature/veto rather than a standalone signal.

**Code-conflict signal** (both offers carry a code, disjoint):

- among **match** pairs with both codes: 21.4% flagged conflict — should be ~0;
  this is token-level extraction noise (variant tokens, split codes), the exact
  failure LCS/Aho-Corasick normalization is meant to remove.
- among **non-match** pairs with both codes: 89.2% flagged conflict — a strong
  negative signal.

## Section D — error analysis of the title-Jaccard baseline (threshold 0.5)

- Predicted 1,814 clusters vs 1,485 gold.
- Over-merged predicted clusters (span >1 gold): **537**.
- Split gold clusters (across >1 predicted): **1,055 (71.0%)** — the dominant
  error.
- Split cause: **76.2%** of same-gold in-block pairs score below 0.5 Jaccard;
  the median same-gold in-block Jaccard is **0.34** (p25 0.24, p10 0.17).
- Blocking loses **0%** of gold pairs — confirms splits are a matching failure,
  not a blocking failure.

## Section E — ablations (best B-cubed F1 per variant)

| Variant | Best B-cubed F1 | Δ vs baseline |
|---|---|---|
| baseline (title Jaccard) | 0.409 | — |
| + price guard (relgap ≤ 25%) | **0.463** | +0.054 |
| + code-conflict veto | **0.463** | +0.054 |
| + shared-code OR link | 0.400 | −0.009 |

Price guard and code-conflict veto each add ~13%; naive shared-code OR-linking
slightly *hurts* (it links wrong pairs through noisy token codes). The two
helpful signals are largely independent (one prunes by price, the other by code
disagreement), so stacking them — on top of TF-IDF text — is the obvious next
matcher to measure.

## Caveats

- **Electronics-heavy.** 18 categories, model-number-rich titles; generalization
  to non-electronics (appliances, cosmetics) is untested (Tier 3 / cross-domain).
- **Cluster size capped ~10** by the scrape, so size-weighted metrics (pairwise)
  are affected; B-cubed is more robust here.
- **Token-level code extraction is a lower bound.** LCS/Aho-Corasick over a
  separator-stripped stream would raise the 54.7% coverage and cut the 21.4%
  false-conflict rate — expect identifier signals to improve once implemented as
  the methodology prescribes.
- **Single-run point estimates** on one fixture with sampled negatives; this is
  evidence, not the full bake-off.
- **Price=100% coverage is a billiger property**, not guaranteed for other
  sources; a price-dependent matcher must degrade gracefully when price is absent.

## Where this feeds back

- blocking.md — confirms `(brand, category)` PC on real data; flags block-size
  growth for the scale lane.
- signals.md — separability ranking (price > IDF-text > Jaccard > token-code) and
  the token-level identifier-noise evidence for the LCS/AC normalization.
- pair-scoring.md — multi-signal (price + text + identifier veto) over single-
  signal; the price guard / code veto as concrete features.
- evaluation.md — splits-vs-over-merge as the actionable diagnostic; B-cubed over
  pairwise given the capped cluster sizes.
