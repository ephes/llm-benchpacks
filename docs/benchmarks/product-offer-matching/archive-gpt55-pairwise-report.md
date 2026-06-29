# GPT-5.5 Product-Offer Matching Report

Date: 2026-06-27
Run directory: `results/product-offer-pi-gpt55-20260627/`
Pack: `product-offer-matching` 0.1.0
Agent route: Pi direct-edit wrapper with `openai-codex/gpt-5.5 --thinking off`

## Executive Summary

GPT-5.5 produced two full-file matcher replacements, one in Python and one in
Rust. Both were deterministic standard-library implementations that learned a
score threshold from visible training rows, then emitted binary predictions for
hidden test pairs.

The Python implementation passed the benchmark. It reached F1 `0.754098` at its
train-calibrated threshold, above the `0.70` pass threshold. The Rust
implementation compiled and ran, but missed the threshold with F1 `0.690909`.
Its precision was higher than Python's, but recall was lower.

| Case | Patch bytes | Agent duration | Pass | Precision | Recall | F1 | Accuracy | TP | FP | TN | FN |
|------|-------------|----------------|------|-----------|--------|----|----------|----|----|----|----|
| Python | 11,373 | 114.886690s | yes | 0.741935 | 0.766667 | 0.754098 | 0.875000 | 23 | 8 | 82 | 7 |
| Rust | 10,532 | 93.596577s | no | 0.760000 | 0.633333 | 0.690909 | 0.858333 | 19 | 6 | 84 | 11 |

## Data And Split

The fixture is a compact derived slice of WDC Products 20pair
`wdcproducts20cc80rnd000un`.

- Source archive:
  `https://data.dws.informatik.uni-mannheim.de/largescaleproductcorpus/data/wdc-products/20pair.zip`
- Visible training source:
  `wdcproducts20cc80rnd000un_train_small.json.gz`
- Hidden evaluation source:
  `wdcproducts20cc80rnd000un_gs.json.gz`
- Deterministic fixture seed: `20260627`
- Training rows: 200 total, 50 positive, 150 negative
- Hidden test rows: 120 total, 30 positive, 90 negative
- Hidden positive prevalence: 25%
- Train sampling: 50 positive, 75 hard negative, 75 easy negative
- Test sampling: 30 positive, 60 hard negative, 30 easy negative

The model saw `data/train.csv` with labels and `data/test_pairs.csv` without
labels. The verifier owned `verify/hidden_labels.csv`. Raw WDC offer ids and
cluster ids were stripped; `pair_id` values are local sequential ids. Exposed
features were brand, title, description, price, and price currency for each side
of the pair.

## Python Approach

GPT-5.5 wrote a weighted similarity scorer around product-specific feature
extraction.

Main components:

- Unicode and punctuation normalization, including accent stripping, trademark
  symbol cleanup, inch/foot normalization, and `f/1.8`-style lens normalization.
- Stopword filtering and tokenization over title and description.
- Brand canonicalization with an explicit alias table, plus brand inference from
  title/description when the brand field is blank.
- Model/code extraction for alphanumeric SKU-like tokens, with separate handling
  for capacity/spec tokens so sizes do not become model codes.
- Numeric/spec extraction for `tb`, `gb`, `mb`, `ml`, `mm`, `inch`, `w`, `mah`,
  `rpm`, `mhz`, `ghz`, gear ratios, and speeds.
- Category and color vocabularies used for boosts and penalties.
- Composite score using title Jaccard, title containment, all-token Jaccard,
  `SequenceMatcher` title similarity, brand match/conflict, code match/conflict,
  spec match/conflict, category agreement, color conflict, and low-overlap
  penalties.
- Threshold selection by maximizing F1 over visible training scores, then
  subtracting `0.015` to bias slightly toward recall.

The selected Python threshold was `0.566761`. On hidden labels this produced 31
positive predictions: 23 true positives and 8 false positives.

## Rust Approach

GPT-5.5 wrote a simpler standard-library ranker in Rust.

Main components:

- Custom CSV parser.
- Manual deaccenting for common Latin characters.
- Tokenization and stopword filtering.
- Brand normalization and fallback brand inference from a fixed known-brand
  list.
- Model-token detection based on alphanumeric tokens containing digits.
- Numeric-unit extraction for `tb`, `gb`, `mb`, `mm`, `mah`, and watts.
- Composite score with a base offset plus weighted title Jaccard, title
  containment, all-token Jaccard, brand match/conflict, model-token
  match/conflict, numeric-unit conflict, and a few product-specific penalties
  such as `mono`/`duo` and some color conflicts.
- Threshold selection by grid-searching visible training rows from `0.20` to
  `1.29` in `0.01` increments.
- A prediction-time boost for very high title containment when brand or model
  evidence agrees.

The selected Rust threshold was `1.25`. It produced 25 positive predictions: 19
true positives and 6 false positives. The ranking was useful, but the threshold
was too conservative for the hidden split.

## Precision/Recall Curves

These curves were reconstructed from each implementation's continuous score on
the hidden 120-row test set. The selected operating point is the threshold
learned from the visible training set. The best hidden-test point is shown only
as diagnostic information; it was not available to the model.

Python average precision over the hidden ranking was `0.824802`.

| Python threshold | Precision | Recall | F1 | TP | FP | FN | Predicted positive | Note |
|------------------|-----------|--------|----|----|----|----|--------------------|------|
| 0.919471 | 1.000 | 0.367 | 0.537 | 11 | 0 | 19 | 11 | high precision |
| 0.820797 | 0.867 | 0.433 | 0.578 | 13 | 2 | 17 | 15 |  |
| 0.700755 | 0.833 | 0.667 | 0.741 | 20 | 4 | 10 | 24 |  |
| 0.627821 | 0.786 | 0.733 | 0.759 | 22 | 6 | 8 | 28 |  |
| 0.566761 | 0.742 | 0.767 | 0.754 | 23 | 8 | 7 | 31 | selected by training |
| 0.447112 | 0.714 | 0.833 | 0.769 | 25 | 10 | 5 | 35 | best hidden F1 |
| 0.200810 | 0.500 | 0.900 | 0.643 | 27 | 27 | 3 | 54 | high recall |
| 0.017979 | 0.476 | 1.000 | 0.645 | 30 | 33 | 0 | 63 | full recall |

Rust average precision over the hidden ranking was `0.772573`.

| Rust threshold | Precision | Recall | F1 | TP | FP | FN | Predicted positive | Note |
|----------------|-----------|--------|----|----|----|----|--------------------|------|
| 2.461496 | 1.000 | 0.200 | 0.333 | 6 | 0 | 24 | 6 | high precision |
| 1.994395 | 0.900 | 0.300 | 0.450 | 9 | 1 | 21 | 10 |  |
| 1.557436 | 0.812 | 0.433 | 0.565 | 13 | 3 | 17 | 16 |  |
| 1.250000 | 0.760 | 0.633 | 0.691 | 19 | 6 | 11 | 25 | selected by training |
| 1.008125 | 0.733 | 0.733 | 0.733 | 22 | 8 | 8 | 30 | best hidden F1 |
| 0.808788 | 0.632 | 0.800 | 0.706 | 24 | 14 | 6 | 38 |  |
| 0.489444 | 0.538 | 0.933 | 0.683 | 28 | 24 | 2 | 52 | high recall |
| 0.351606 | 0.492 | 1.000 | 0.659 | 30 | 31 | 0 | 61 | full recall |

## Error Pattern

Python's highest-scoring false positives were generally same-brand or
same-category alternatives where the products are related but not identical:

- New Era Yankees cap variants with different colors/styles.
- ASUS ROG Strix RTX 2060 Super vs RTX 2070.
- Jabra Evolve headset variants.

Python's high-scoring false negatives were genuine matches with weak or
language-shifted evidence:

- Epson 18/T1803 magenta ink cartridge.
- Epson T0792 cyan ink cartridge with multilingual/catalog wording.
- Citizen Eco-Drive watch title mismatch.

Rust showed the same broad pattern but had lower recall. Its selected threshold
missed plausible true matches such as a Neff oven, iPhone 6s replacement
battery kit, and Canon PGI-9PBK ink cartridge. Lowering the threshold to the
hidden-optimal region would have passed F1, but that threshold was not selected
from training.

## Interpretation

GPT-5.5 did not solve this with memorized labels or direct classification. It
wrote conventional matching software: normalize fields, extract brands/SKUs,
compare titles/descriptions/specs, learn a decision threshold from labels, and
emit deterministic predictions.

The Python implementation had a better precision/recall tradeoff and more
domain-specific extraction logic. The Rust implementation was operational and
reasonably ranked the examples, but the training-calibrated threshold landed on
the wrong side of the benchmark's pass/fail boundary. In practical terms, the
Rust failure was a calibration/generalization miss rather than a compile,
runtime, or output-contract failure.
