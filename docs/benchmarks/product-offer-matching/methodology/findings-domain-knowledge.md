# Findings: Practitioner Domain Knowledge

Status: **primary-source domain knowledge** from building a real billiger.de
product matcher / category classifier. This is practitioner experience, not a
controlled experiment, but it is evidence no paper or public dataset provides —
and it independently corroborates (and in places tempers) the data findings in
[findings-pilot.md](findings-pilot.md). Generalizable lessons are flagged; the
billiger specifics stay as context.

## Signal reliability (practitioner ranking)

In descending order of how useful each signal proved in practice:

1. **Longest common substring / subsequence** over titles — *the most reliable
   signal*. Structural overlap of the raw strings (not tokens) carried the
   matching. Directly vindicates signals.md's identifier-extraction approach
   (LCS over normalized titles, robust to spacing/dash noise) and the
   Aho-Corasick dictionary direction in blocking.md.
2. **TF-IDF cosine similarity** — solid. Matches the pilot result that
   IDF-weighted text (AUC 0.890) beats raw token Jaccard.
3. **Price** — helpful, *but conditional* (see hard categories below).
4. **Brand** and **shop category** — only mildly useful. (Category is itself a
   classifier output, consistent with treating it as an auxiliary feature, not
   ground truth.)

## Hardest categories (where matching broke)

- **Phones with vs without contract.** A subsidized contract phone is listed at a
  near-zero or heavily discounted price, so **price decouples from product
  identity** — the same handset is cheap-with-contract and expensive
  without. Price, the otherwise-strong signal, becomes misleading here.
- **Phones vs phone accessories.** A cover, case, or battery *for* a phone is
  hard to separate from the phone itself — and when the phone carries a contract
  (low price), an accessory and a phone can sit at similar prices, so **price
  cannot disambiguate them**. This is a classic product-ER hard negative
  (Köpcke et al.): similar-but-different items in the same category.

These are the concrete failure structures behind "price is strong on average":
its discriminative power collapses exactly where pricing is decoupled from the
physical product (subsidies, bundles, accessories). A price feature must be
**category-conditional**, not global.

## What did not work

- **Hand-built linguistic heuristics.** Regexes and lemmatization were tried and
  *did not help much*. The win came from **structural string matching (LCS)**,
  not linguistic preprocessing. This tempers any methodology enthusiasm for
  elaborate normalization rules: keep normalization light (unit/case/separator
  canonicalization for the LCS/AC step) and let structural and learned-text
  similarity do the work, rather than investing in lemmatizers or large
  rule sets.

## GTIN / EAN

Too unreliable to be used as a matching *key*; in practice they were included
only as ordinary **tokens in the TF-IDF cosine**, never as an identifier lookup.
This independently confirms the premise of **D-035** (strip GTIN/EAN as a
structured identifier — a reliable one would trivialize matching, and real ones
are not reliable). The benchmark forgoes even the weak token-level GTIN signal to
prevent the leakage shortcut a *reliable* identifier would otherwise create.

## Lessons for the methodology

| Lesson | Effect on the methodology |
|---|---|
| LCS/subsequence was most reliable | Strengthens signals.md identifier extraction + blocking.md Aho-Corasick dictionary as primary, not optional. |
| TF-IDF solid; hand heuristics (regex/lemmatization) did not help | signals.md: keep normalization light; prefer structural + learned-text similarity over linguistic rule-building. |
| Price decouples for contract phones & accessories | signals.md price section + pair-scoring.md: price weight must be category-conditional; data-quality.md / benchmark-constraints.md: add these as canonical hard cases. |
| Brand / category only mildly useful | Confirms their blocking-grade (not decisive) role in signals.md. |
| GTIN/EAN unreliable, used only as cosine tokens | Confirms D-035 (strip as identifier). |

## Where this feeds back

- signals.md — LCS as top signal; light-normalization lesson; the
  contract/accessory price-decoupling caveat.
- pair-scoring.md — category-conditional price weighting.
- benchmark-constraints.md — phone-with/without-contract and phone-vs-accessory
  as canonical hard-case fixture entries.
- data-quality.md — accessory-vs-product and contract-pricing as a price-outlier
  blind spot.
