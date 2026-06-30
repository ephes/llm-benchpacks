# Signals and Feature Extraction

## Problem

Once blocking produces candidate pairs, each pair needs a comparison vector: a
set of features that a scorer (pair-scoring.md) turns into a match decision. The
quality of matching is bounded by how *separating* these features are — how well
their distribution over true matches differs from their distribution over
non-matches.

This document covers the signals available for product offers, how to extract
them robustly, and the **separability analysis** that tells us which signals
carry information and where to put thresholds. It is dataset-agnostic: which
signals exist depends on the source, so each is flagged with its availability
assumption.

## The signals

| Signal | Availability | Strength | Failure mode |
|---|---|---|---|
| Title / name text | Always | High | Per-merchant wording noise; cross-language |
| Identifier tokens (model no., MPN) | Often in title | Very high when present | Spacing/dash/case noise; absent on terse titles |
| Price | Only price-bearing sources | Medium | Same-price different variants; promotions, used items |
| Brand / category | Often (may be classifier output) | Medium (blocking-grade) | Inconsistent vocab; classifier labels are not ground truth |
| Image | Only if **per-offer** images exist | High (multimodal) | Useless if one image per product (see below) |
| GTIN / EAN | Sometimes | High when correct | **Filtered out before the benchmark** (see below) |

A key design rule: a signal that is the **output of another model** (a category
label from a text classifier, a GTIN copied from a feed) is a noisy auxiliary
feature, never ground truth.

### GTIN / EAN are filtered out before the benchmark

Structured catalog identifiers — GTIN, EAN, and any reliable MPN *field* — are
**removed from the offer data the matcher sees**. The reason is the same one the
literature notes flag (`../literature.md` Diagnosis): when a reliable identifier
is present, matching collapses to a `GROUP BY identifier` lookup, not an entity-
resolution problem. Leaving it in lets a matcher shortcut to the answer and
measures nothing about resolution.

Two clarifications:

- **This is a structured-field rule, not a title rule.** The in-title model
  tokens the LCS extractor digs out of noisy merchant titles (below) stay — they
  are the matching challenge, not a shortcut. We strip the clean catalog field,
  not the messy string a human wrote.
- **GTIN is used only verifier-side, before stripping.** During fixture building
  it serves as a cross-check signal in the label-noise cleanup
  (`data-quality.md`, GTIN-vs-key disagreement), then it is dropped from the
  published offers. It is never a gold label (the cluster key is the reliable
  product id, not GTIN, which merchant feeds frequently get wrong).

If a lookup ceiling is ever wanted for reference, it belongs in a clearly
labeled, separate identifier-baseline lane — explicitly *not* the real task — not
in the matching lanes.

## Title similarity

Per-merchant titles describe the same product differently, so exact match is
useless and token overlap is fragile. Useful representations:

- **TF-IDF cosine** over word or character n-grams. Character n-grams (e.g.
  3–5 grams) are robust to the spacing/dash noise that breaks word tokens and to
  minor spelling variation.
- **Jaccard / overlap** over token sets or shingles — cheap, pairs well with
  MinHash blocking.
- **Edit-distance family** (Levenshtein, Jaro-Winkler) — good for short strings,
  too slow for long titles at scale.
- **Learned embeddings** (sentence encoders, contrastive product encoders) —
  strongest, but a dependency; see pair-scoring.md and metric learning.

### Normalization (shared with identifier extraction)

Before any title comparison, normalize: lowercase; unify unicode; collapse
whitespace; and canonicalize **measurement units** so `32 GB`, `32gb`,
`32-GB`, `32 gigabyte` map to one token. The same applies to other units
(`6.3"`, `6,3 Zoll`, `6.3 inch`; `5G`; `1 TB`). Unit canonicalization is high
leverage because storage/size/generation tokens are exactly what distinguish
variants of the same model.

## Identifier extraction (per-offer model codes + LCS alignment)

The strongest text signal is usually a model number or part code buried in the
title (`S928B`, `A3105`, `MQ6L3`). Tokenizing to find it fails because merchants
insert or drop spaces and dashes inconsistently, so the "token" is not stable.

Extraction needs **two complementary mechanisms**, because they answer different
questions. Per-offer extraction asks "what model code(s) does *this* title
carry?" (needed to detect conflict and to flag mislabels); pairwise alignment
asks "do these two titles share a code despite formatting noise?" (needed to
confirm agreement robustly). A shared-substring method alone cannot see a
conflicting code that appears in only one title, so per-offer extraction is not
optional.

**1. Per-offer model-code extraction (single title → code set).** From each
normalized title independently, extract candidate model codes by shape, not by a
shared comparison: alphanumeric runs that mix letters and digits (`S928B`,
`A3105`, `MQ6L3`), pass length/digit/alphanumeric-density filters, and are not a
brand, common word, or pure unit token (`512GB`, `5G` are units, not model
codes). This yields each offer's own code set, which is what conflict detection,
the `data-quality.md` model-token-disjointness pass, and per-offer blocking keys
all consume.

**2. Pairwise alignment (two titles → shared code, formatting-robust).** To
decide whether two offers' codes *agree* despite inserted/removed spaces and
dashes, use the **longest common substring (LCS-substring)** over the normalized
character streams (separators stripped). It ignores word boundaries, so it
matches `s928b` even when one title wrote `S928B/DS` and the other `S928B`.
LCS-subsequence (gaps allowed) recovers a code that is itself split (`S928 B`)
but produces more spurious hits, so it needs a stricter length/density filter.
This step robustly confirms agreement; it does **not** by itself reveal a
non-shared conflicting code — that comes from step 1.

**Feature construction.** Compare the two offers' code sets from step 1, using
step 2's formatting-robust equality so trivial separator differences don't read
as a conflict:

- **Agreement** — a code shared by both (length-weighted) → strong match signal.
- **Conflict** — each offer carries a code, but no pair of them aligns → strong
  *non-match* signal.
- **One-sided / absent** — only one offer (or neither) exposes a code → weak /
  no signal; fall back to title similarity.

Conflict is as valuable as agreement: two titles that each contain a distinct
model code are likely different products even if the rest of the text is similar.
This catches the hard negatives (same brand/category, adjacent models) that
lexical similarity alone merges — and it depends on step 1, since the conflicting
code lives in only one title.

> **Example.** `Samsung Galaxy S24 Ultra 512GB ... S928B/DS Titanium Black` and
> `Samsung Galaxy S24 Ultra S928B 5G 512GB titanium black EU`: step 1 extracts
> `s928b` (and `s928bds`) from the first and `s928b` from the second; step 2
> aligns them across the `S928B/DS` vs `S928B` formatting difference → agreement.
> An S25 offer instead yields `s938b` in step 1, which aligns with neither →
> conflict, flagging a non-match even though the rest of the title is nearly
> identical.

Note the difference from a structured catalog identifier. A reliable identifier
*field* (GTIN/EAN/MPN) is a leakage shortcut and is filtered out before the
benchmark (above): if it is present, matching is a lookup, not a resolution
problem (see `../literature.md` Diagnosis). An in-title model token recovered by
LCS is the opposite — a noisy signal the matcher must work to extract and
reconcile — so it stays. The benchmark strips the clean field and keeps the
messy string.

### Catalog-side canonical codes (warm-start regime)

In the catalog-linkage regime (index.md) the codes can be mined offline from the
*known* products and turned into a reusable index — the precompute the cold-start
regime cannot do:

1. **Per-offer extraction** (step 1 above) over every member offer of a known
   product.
2. **Aggregate to a per-product canonical code.** Take the consensus across the
   product's member offers: a code that appears in several members is
   high-confidence; a code in only one terse outlier title is not. This
   cross-member vote *denoises* the per-single-title extraction — exactly what a
   flat regime lacks. LCS across pairs of member titles is a good discovery
   method for the shared canonical string when no single title is clean.
3. **Build the dictionary** `code → {product_id}` over all products (keep a *set*
   value: a platform code may map to several products, and such high-fan-out
   codes are down-weighted).

A new offer is then linked by finding which dictionary codes occur in its title —
a multi-pattern scan (Aho-Corasick), which is both a high-precision blocker and a
strong link signal (blocking.md, *identifier-dictionary matching*). This is not
the GTIN/EAN shortcut D-035 strips: the dictionary is derived from the
catalog/training clusters, not from hidden test labels, and the codes are the
noisy in-title strings the matcher had to extract — a legitimate production
technique.

## Price

For price-bearing sources, price is a medium-strength signal best used as a
*non-match* filter rather than a positive one:

- Same physical product clusters tightly in price; a large gap is evidence
  *against* a match.
- Use a scale-free comparison: relative gap `|p1−p2| / min(p1,p2)` or absolute
  log-ratio `|log(p1/p2)|`. Raw difference is dominated by product price level.
- Price overlaps across distinct nearby variants (adjacent storage tiers,
  generations) and is distorted by promotions, bundles, and used/refurbished
  condition. So price disambiguates *within* a candidate set; it rarely confirms
  a match alone.

> **Example.** Adjacent phone generations can have nearly identical street
> prices, so a price-only check cannot separate them — but a conflicting model
> identifier can.

## Image

Whether images help depends entirely on **granularity**:

- **Per-offer images** (each merchant's own photo): a real, strong multimodal
  signal. Visual similarity disambiguates color/bundle/storage/generation
  variants that titles describe inconsistently. Features: perceptual hashes
  (pHash/dHash) for near-duplicate detection; CNN/ViT embeddings with ANN for
  visual KNN; metric-learned embeddings (ArcFace-style, as in the Shopee
  solutions) for fine-grained similarity.
- **Per-product images** (one image shared by all offers in a cluster, as
  aggregator product pages typically expose): **not usable** as a matching
  feature. Every offer in a cluster carries the *same* image, so image
  similarity is 1.0 within a cluster and lower across clusters by construction —
  that is the gold label leaking through the image field, not an independent
  signal. Using it would inflate scores and measure nothing real.

So the rule is: **images are a signal only when each offer carries the
merchant's own image.** Document the source's image granularity before building
an image lane. The image-feature methodology above is recorded so it is ready
the moment a per-offer-image source is available; until then, the image lane
stays unbuilt rather than built on a leaking signal.

> **Example (billiger.de pilot).** billiger exposes one image per *variant*
> (product), not per offer, so its image field is product-level and cannot serve
> as a matching feature. The pilot still motivates multimodal work: some
> merchants list a bare `iPhone 17` identically across blue/white/lavender
> clusters, which title-only matching cannot separate but per-offer images
> could.

## Separability analysis (how we measure signal quality)

Before trusting any signal, measure how well it separates matches from
non-matches. This is the analysis to run on a representative sample (deferred to
the auto-research pass); here is the method.

For each candidate signal `s` (title cosine, price relative-gap, shared-
identifier length, image distance):

1. Sample candidate pairs and label them with gold (match / non-match).
2. Plot **two overlaid histograms** of `s`: one over matches, one over
   non-matches. Visual overlap = how separating the signal is.
3. Quantify separation without eyeballing:
   - **ROC-AUC** of `s` as a one-feature classifier (chance = 0.5);
   - **average precision** (PR-AUC), which respects the heavy class imbalance
     better than ROC;
   - distribution-distance measures (KS statistic, or the histogram-overlap
     coefficient) between the match and non-match distributions.
4. Read a **candidate threshold** off the curves: the crossover region of the
   two histograms, or the operating point that maximizes F1 / Youden's J on a
   held-out split. Record the chosen threshold *and* the best-achievable hidden
   threshold so we can see the calibration gap (see pair-scoring.md).
5. Repeat on **hard slices** — same-brand pairs, adjacent-model pairs, terse
   titles, cross-language pairs — because a signal that separates easy pairs may
   collapse on the cases that actually matter.

Two cautions:

- **Class imbalance.** Non-matches vastly outnumber matches, so prefer PR-based
  measures over ROC, and always report the base match rate alongside.
- **Blocking conditioning.** Separability measured on *candidate* pairs (post-
  blocking) is the relevant quantity, since those are the only pairs the scorer
  sees. Measuring on all pairs overstates how easy the job is.

The output of this analysis is a per-signal table: AUC / AP / chosen threshold /
behavior on hard slices. That table tells pair-scoring.md which features to
weight and which thresholds to seed.

## Benchmark implications

- Provide normalization and identifier-extraction as *described capabilities*,
  not as exact-ID shortcuts; strip or sandbox reliable identifiers.
- Build an image lane only against a per-offer-image source; never against
  product-level images.
- Expect price as a within-candidate disambiguator, scored via a scale-free
  transform, not as a standalone matcher.
- The separability table is a deliverable of the auto-research pass and a
  diagnostic a strong agent submission should be able to produce.

## Open questions

- Default normalization spec (unit canonicalization rules, separator handling) —
  to be fixed once measured against a representative sample.
- Identifier-extraction filter thresholds (minimum length, digit requirement,
  stopword/brand lists) — tune on real titles.
- Whether to ship a per-offer-image source at all, given the legal/storage notes
  in `../dataset-sourcing-analysis.md` (store URLs / hashes / embeddings, not raw
  images).

## References

- Köpcke et al., *Tailoring Entity Resolution for Matching Product Offers*, EDBT
  2012 — product-specific hard negatives; `../literature.md` Tier 4.
- Bilenko & Mooney, *Adaptive Duplicate Detection Using Learnable String
  Similarity Measures*, KDD 2003 — `../literature.md` Tier 2.
- Wilke & Rahm, *Towards Multi-Modal Entity Resolution for Product Matching*,
  2021 — image signal; `../literature.md` Tier 4.
- Shopee top solutions (image+text metric learning, KNN) — `resources.md`.
