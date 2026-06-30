# Data Quality and Label Noise

## Problem

Every metric in evaluation.md is computed against gold cluster labels. If those
labels are noisy, the benchmark partly measures agreement with mistakes. Scraped
or aggregated product data always carries some label noise, because the gold
clusters are themselves the output of an upstream matching system (an
aggregator's pipeline) plus merchant-feed errors. A representative sample needs a
documented cleanup pass before it becomes a fixture, and the residual noise rate
needs to be reported.

> **Example (billiger.de pilot).** A crude title-vs-label model-token heuristic
> over 10,825 offers flags ~0.44% as possible cross-model mismatches; manual
> inspection shows a mix of genuine source mislabels (e.g. an ebay offer titled
> `Samsung Galaxy S25 Ultra - 256 GB - Titanium Black` in the
> `Galaxy S26 Ultra 256 GB Black` cluster) and heuristic false positives, so true
> label noise is well under 0.5%. Price-outlier checks miss the real cases because
> sibling-model prices nearly coincide — a model-identifier check catches them
> where a price check cannot.

## Label-noise taxonomy

| Noise type | Description | Detection signal |
|---|---|---|
| Cross-model mislabel | Offer for product X placed in product Y's cluster | Model-identifier token disjoint from cluster's other offers |
| Variant collapse | Distinct variants (storage/color/generation) merged into one gold cluster | Conflicting unit tokens (`256GB` vs `512GB`) within a cluster |
| Variant over-split | One product split into several gold clusters | Near-identical titles across clusters |
| Wrong identifier | Merchant feed carries a wrong GTIN/MPN | GTIN disagrees with the reliable cluster key |
| Junk / placeholder offer | Accessory, bundle, or listing with a degenerate title | Very short title, no model token, price far off cluster |
| Cross-language description | Same product, different-language title | High char-n-gram sim but low token overlap (not noise, but stresses signals) |

The first two (cross-model mislabel, variant collapse) are the dangerous ones:
they put genuinely different products in the same gold cluster, which punishes a
*correct* matcher and rewards an over-merging one.

## Cleanup passes

A reusable validation pipeline, run when building a fixture from raw scraped
data. Each pass *flags*; the drop-vs-keep policy (below) decides the action.

1. **Model-token disjointness.** Extract candidate model codes per offer
   (signals.md per-offer model-code extraction, step 1). Flag any offer whose
   model code is disjoint from the cluster's dominant model code. Catches
   cross-model mislabels.
2. **Unit-conflict scan.** Within each gold cluster, flag conflicting
   storage/size/generation unit tokens. Catches variant collapse.
3. **Price-outlier check.** Flag offers whose price is far from the cluster's
   robust center (e.g. > k·MAD from the median). Catches some junk offers and
   wrong placements — but note its blind spot: it misses mislabels between
   similarly priced products (the S25/S26 case).
4. **Degenerate-title filter.** Flag offers with titles too short or lacking any
   distinguishing token to be matchable (bare `iPhone 17` across color variants).
   These are not necessarily noise — they are the hard cases — so flag, don't
   auto-drop.
5. **GTIN-vs-key disagreement.** Where a GTIN exists, flag disagreement with the
   reliable cluster key as evidence the GTIN (not the cluster) is wrong. This is
   a fixture-build-time check only: GTIN/EAN are used here as a verifier-side
   cross-check and then **filtered out of the published offers** before the
   benchmark (signals.md), because a reliable identifier would trivialize
   matching into a lookup. GTIN is never a gold label.
6. **Singleton audit.** Inspect singleton clusters; some are real, some are
   split fragments of a larger product.

The passes are deliberately multi-signal: no single check is sufficient (price
misses same-price mislabels; model-token misses junk). Run them together and
record per-pass flag counts.

## Drop-vs-keep policy

Flagged offers can be **dropped** (clean fixture) or **kept** (realistic noise).
The policy is a design choice, and the benchmark should make it explicit per
lane rather than silently picking one:

- **Clean lane.** Drop confidently-noisy offers (cross-model mislabels, unit
  conflicts) so the gold labels are trustworthy and the metric ceiling is ~1.0.
  Best for measuring algorithm quality without label-noise confounds.
- **Realistic lane.** Keep a known, measured amount of noise to test robustness;
  report the noise rate so the achievable ceiling is understood (a perfect
  matcher cannot score 1.0 against noisy labels).
- **Raw provenance.** The raw scrape is kept faithful (noise included); cleanup
  produces the derived fixture. Document which offers were dropped/flagged and
  why, so the fixture is regenerable and auditable.

Whatever the policy, **measure and report the residual noise rate** so results
are interpreted against the real ceiling.

## How we measure it

- Per-pass flag counts and the union flag rate (the estimated noise rate).
- A small manually-audited sample to estimate precision of the flags (are flagged
  offers actually mislabeled?) and to spot-check unflagged offers (recall of the
  cleanup).
- The gap between achievable metric ceiling and 1.0 implied by residual noise.
- Stability of the noise rate across categories/sources (some categories are
  noisier).

## Benchmark implications

- A fixture is not benchmark-grade until its cleanup pass is run and its residual
  noise rate is documented.
- Offer both a clean lane (trustworthy ceiling) and, optionally, a realistic
  lane (measured noise) — and never compare scores across lanes without noting
  the ceiling difference.
- Keep the raw scrape and the cleanup script committed so the derived fixture is
  reproducible (`../dataset-sourcing-analysis.md` reproducibility contract).
- Do not use an aggregator's category label as gold; it is a classifier output
  (auxiliary feature only).

## Open questions

- Flag thresholds (price MAD multiplier, minimum title length, model-token
  matching strictness) — tune on a representative sample.
- Whether the default fixture is clean, realistic, or ships both lanes.
- How much manual auditing is needed to certify a noise-rate estimate, and
  whether to automate part of it with a held-out high-precision check.

## References

- `../dataset-sourcing-analysis.md` — the billiger.de pilot noise finding and
  reproducibility contract.
- Köpcke et al., EDBT 2012 — product hard-negatives and why similar-but-different
  products are the core difficulty; `../literature.md` Tier 4.
- Christen, *Data Matching*, 2012 — data quality and evaluation; `../literature.md`
  Tier 2.
