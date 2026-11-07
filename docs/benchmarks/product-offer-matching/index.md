# Product Offer Clustering Benchmark

Status: current implementation lives in `benchpacks/product-offer-matching/`
as a direct-edit external-agent benchmark over a billiger.de-derived
cluster-labeled offer fixture.

Related material for this benchmark:

- [Methodology knowledge base](methodology/index.md) — dataset-agnostic
  pipeline methodology (blocking, signals, scoring, clustering, evaluation,
  data quality, constraints, resources)
- [OfferWeave reference matcher](offerweave-reference.md) —
  dependency-trained reference implementation report, including hidden verifier
  metrics and failure analysis
- [Literature and redesign notes](literature.md)
- [Dataset sourcing analysis (price + image sources)](dataset-sourcing-analysis.md)
- [PriceRunner rerun, 2026-06-28](pricerunner-rerun-20260628.md)
- [Archived WDC large pairwise rerun, 2026-06-27](archive-large-pairwise-rerun-20260627.md)
- [Archived GPT-5.5 pairwise report](archive-gpt55-pairwise-report.md)

## Goal

Measure whether a coding agent can write deterministic product entity-resolution
software: given many merchant offers, assign offers that represent the same real
product to the same cluster.

This is not an LLM-as-judge benchmark and not a direct chat-labeling task. The
agent writes normal code, the verifier runs that code on hidden labels, and the
runner records deterministic metrics.

The benchmark should answer:

- Can the agent write a runnable offer-clustering program from a real schema?
- Does the program generalize from visible labeled product clusters to disjoint
  hidden product clusters?
- What cluster precision/recall/F1 and pairwise precision/recall curve does it
  achieve?
- How much memory does it use, how many offers per second does it cluster, and
  what transparent combined score results when quality, throughput, and memory
  are considered together?

## Dataset

The implemented fixture is derived from billiger.de product offers and lives at
`benchpacks/product-offer-matching/fixtures/billiger-matcher-repo`. Each offer
carries multiple signals: title, shop name, price (`price_eur`), brand, and a
classifier-produced `category_label`, plus product cluster id/label on visible
training rows. The data has no GTIN, and `image_url` is excluded (see below).

Visible training offers have columns:

```text
offer_id,title,shop_name,price_eur,brand,category_label,cluster_id,cluster_label
```

Prediction (test) offers carry the same columns minus the two cluster columns,
which are hidden.

Unlike the title-only PriceRunner predecessor (decision D-034), which carried no
price or image fields, the billiger fixture adds a genuine **price** signal, so it
supports a multi-signal product-matching benchmark rather than a title-only
entity-matching lane. An image signal would help only as real per-merchant
photos; the canonical product image in the scrape is a cluster-id proxy and is
excluded from the published offers (decision D-038, like GTIN in D-035).

The fixture builder is:

```text
benchpacks/product-offer-matching/scripts/build-fixture-from-billiger.py
```

It consumes the raw billiger offer export outside git and writes a deterministic
derived fixture. Raw source ids are replaced with local `offer_id` values after
train and test rows are deterministically shuffled. Training and test splits are
disjoint by true product cluster, and public row order plus sequential local ids
must not encode source product-cluster order.

Current derived fixture shape (from 31,330 input offers, 31,187 kept):

- `data/train_offers.csv`: 9,362 visible labeled offers from 1,385 product
  clusters.
- `data/test_offers.csv`: 21,825 unlabeled prediction offers from 3,265 hidden
  product clusters.
- `data/eval_pairs.csv`: 20,000 unlabeled eval pairs sampled from hidden test
  offers, with 5,000 positive and 15,000 negative pairs.
- `verify/hidden_test_clusters.csv`: verifier-owned hidden product cluster for
  every test offer.
- `verify/hidden_eval_pair_labels.csv`: verifier-owned labels for eval pairs.

## Task

The generated program reads:

- visible labeled training offers;
- unlabeled test offers to cluster;
- a fixed unlabeled eval-pair sample used only for score/ranking output.

The generated program writes:

- `clusters.csv` with `offer_id,cluster_id`, exactly one row for every test
  offer;
- `pair_scores.csv` with `pair_id,score`, exactly one finite score for every
  eval pair, where higher means more likely same product;
- optional flat scalar `metrics.json` with timing, blocking, candidate-count, or
  other implementation counters.

Pair scoring is an evaluation aid, not the target deliverable. The primary task
is clustering a set of offers into inferred products.

## Pack Shape

Implemented case ids:

```text
cluster-billiger-python
cluster-billiger-rust
```

Implemented layout:

```text
benchpacks/product-offer-matching/
  benchpack.toml
  README.md
  prompts/
    cluster-billiger-python.md
    cluster-billiger-rust.md
  fixtures/
    billiger-matcher-repo/
      README.md
      clusterer.py
      clusterer.rs
      data/
        train_offers.csv
        test_offers.csv
        eval_pairs.csv
  verify/
    score_clusters.py
    hidden_test_clusters.csv
    hidden_eval_pair_labels.csv
  scripts/
    build-fixture-from-billiger.py
```

Both cases use `harness = { id = "external-agent", timeout_s = 3600 }` because
local Pi/Qwen runs may need long prefill and generation time. The Pi wrapper
uses bounded CSV previews and requires a JSON full-file replacement for the
single prompt-allowed implementation file.

## Program Interface

Python verifier command:

```sh
python clusterer.py \
  --train data/train_offers.csv \
  --predict data/test_offers.csv \
  --output clusters.csv \
  --pair-input data/eval_pairs.csv \
  --pair-scores pair_scores.csv
```

Rust verifier command:

```sh
rustc clusterer.rs -O -o <verifier-temp>/clusterer-rust
<verifier-temp>/clusterer-rust \
  --train data/train_offers.csv \
  --predict data/test_offers.csv \
  --output clusters.csv \
  --pair-input data/eval_pairs.csv \
  --pair-scores pair_scores.csv
```

The bundled Python reference uses the project `uv` environment for dependencies
such as `numpy`, `scipy`, `scikit-learn`, and `rapidfuzz`, while keeping the
verifier runtime path deterministic with embedded coefficients. The first Rust
lane still uses one `clusterer.rs` file compiled directly with `rustc`.

## Scoring

Primary clustering metrics:

- B-cubed precision, recall, and F1.
- Pairwise cluster precision, recall, and F1 induced by the predicted clusters.

Ranking metrics:

- Full precision/recall curve over `data/eval_pairs.csv` from
  `pair_scores.csv`.
- Average precision.
- Hidden-best F1 point for diagnostics.
- Operating-point pair metrics induced by the submitted clusters.

System metrics:

- program wall time;
- test offers per second;
- eval pairs per second;
- peak process RSS;
- optional implementation-owned metrics from `metrics.json`.

Current combined-score formula:

```text
100 * (0.35*bcubed_f1 + 0.25*pairwise_cluster_f1
       + 0.25*average_precision
       + 0.10*min(offers_per_second/10000,1)
       + 0.05*min(1024/peak_rss_mb,1))
```

Pass thresholds:

- B-cubed F1 must be at least `0.70`.
- Pairwise cluster F1 must be at least `0.20`.

The thresholds are deliberately not the main interpretation surface. For model
comparisons, inspect the metric JSON, PR curve CSV, throughput, memory, and
failure mode instead of reducing the result to pass/fail.

## Anti-Leakage Rules

Hidden labels stay in `verify/` and are not copied into the prepared workspace.
The prompt prohibits editing data, reading verifier files, network access, and
hardcoding test ids or labels. The verifier fails malformed CSVs, missing ids,
duplicates, unknown ids, non-finite scores, process failures, timeouts, empty
patches, and metrics below threshold.

External-agent runs are benchmark-grade only when the wrapper prevents broad
filesystem access or the result is documented as weaker anti-cheat evidence.
The bundled Pi wrapper runs Pi without filesystem tools and only applies JSON
replacements for prompt-allowed paths.

## Archived PriceRunner fixture tooling

`build-fixture-from-pricerunner.py` retains the whole-cluster split policy:
shuffle clusters, then take complete clusters until the training offer target
is reached (the final cluster may overshoot). Seeded row shuffling and local IDs
are reproducible; public test offers contain no cluster labels. Synthetic tests
check all five public/hidden joins and prevent row-level split leakage.

Pair requests must be nonnegative and feasible. Positives share a source cluster;
hard negatives share a category but differ in cluster; easy negatives come from
all remaining cross-cluster pairs, excluding selected hard negatives. Hard negatives are uniform over eligible pairs (larger categories therefore
contribute more), replacing the old category-first weighting. Sampling
is without replacement and produces the exact requested counts, or raises before
writing output. The corrected sampler changes seeded pair selections relative
to the earlier attempt-capped sampler; regenerate all labels together.

PriceRunner source ZIPs must contain exactly the seven source columns: Product
ID, Product Title, Merchant ID, Category ID, Category Label, Cluster ID and
Cluster Label. Rows must have seven cells and unique nonblank Product IDs.
Cluster IDs must consist only of ASCII digits (0–9) and convert to integers; numeric aliases are normalized before
splitting. UTF-8/BOM and quoted multiline CSV are accepted; embedded newlines
are normalized to spaces. Diagnostics identify row/column contracts without
including source values.

All five CSVs are staged and read back before replacing any fixture. Caught
publication failures restore the previous files (or remove the partial first
generation). Serialize builds to a pack directory, and do not read fixtures
during publication: this is recoverable publication, not an atomic concurrent
reader snapshot or a crash-durable transaction. If rollback itself fails, the
error reports a retained `.pricerunner-*` directory. Its `backup/0.csv` through
`backup/4.csv` correspond, in order, to train offers, test offers, eval pairs,
hidden test clusters and hidden pair labels. Use `manifest.json` to identify each target and whether it existed before the
build. Delete any target marked `existed: false`; restore remaining backups for
targets marked `existed: true`. For those existing targets only, a missing backup
means rollback already restored it.
Retain the directory until all five files are coherent, then remove it and retry.

## Pilot baseline contracts

`baseline-clusterer.py` links Jaccard scores at or above the threshold within
(normalized brand, exact category) blocks and returns connected components,
including transitive links. Duplicate offer identities fail before clustering;
an empty CSV returns no clusters, comparisons or blocks. Empty-domain scores
are zero. An all-singleton prediction has B-cubed precision of one and pairwise F1
of zero (there are no predicted positive pairs). Its B-cubed recall and F1 are
also one when gold is all singletons; otherwise they decrease. Scoring uses only the prediction domain;
gold must contain every predicted identity. Synthetic fraction oracles cover
perfect, merged, split and asymmetric partitions and label renaming. Scoring
remains outside the measured clusterer work; resource measurement is CLI-only.

## Signal-analysis contracts

The pilot, TF-IDF and Amazon–Google analyzers compute ROC-AUC using average
ranks for ties and average precision at whole equal-score thresholds. Synthetic
hand-derived fractions and every ordering of tied observations protect these
independent implementations. ROC-AUC is NaN for empty or single-class inputs;
AP is NaN without positives, and one for positive-only input. Importing metric
helpers does not read datasets or import optional scientific libraries.

Pilot blocking keys retain normalized brand and exact category semantics;
first-title-token blocks use title order. Model-code candidates mix letters and
digits and exclude pure storage/power/other unit tokens. Character n-grams are
counted, not deduplicated. Token, block-pair and connected-component oracles run
without pilot datasets or model calls; no methodology results were remeasured.

## Offline scraper contracts

The pilot scraper admits each clickout separately: a JSON mapping must hold a
nonempty LeadEvent list whose first row has at least nine cells. Cluster IDs
are nonblank strings or integers; consumed text is string/null, and price is
string, finite number or null. Invalid siblings are skipped with one aggregate
rejection count per page, without logging payloads. Deduplication includes
cluster identity so recommendations cannot evict target offers.

Synthetic HTML/fetch/sleep tests forbid network transport. They protect hard
per-search request limits and the shared seen-set rule: mark a variant only
after a successful fetch, leaving failed and queued-but-unfetched variants
retryable. Repeated successful variants are skipped across searches. Offer
budgets remain soft and keep complete clusters, so the last cluster may
overshoot; only the page target's offers enter that cluster.

## Generated pilot viewer contracts

`build-billiger-viewer.py` treats CSV fields as untrusted text. Category options
use DOM text/value properties, grouping dictionaries have no prototype keys,
and card text/attributes are HTML-escaped. Embedded JSON escapes all HTML-sensitive characters and Unicode line
separators as well as script closers, preventing HTML script escape states. Images accept only absolute HTTP(S) URLs. Synthetic tests execute the
actual generated JavaScript under Node.js with a fake DOM and parse the rendered
HTML to check literal hostile values and intact grouping/filtering.

Only complete finite decimal price strings (trimmed, with optional exponent) enter ranges or medians; empty,
invalid, NaN and infinite values display `—`. Missing ranges/medians are null,
distinct from a finite zero price. Empty or nonpositive medians disable relative
outlier detection/spread; otherwise outliers retain the >1.8× / <0.55× median
rules. Overflowing relative spreads saturate at the largest finite JS number so
sorting stays finite. Even medians avoid overflowing the sum. Filter, sort,
median and outlier tests need no network or platform-specific browser.
