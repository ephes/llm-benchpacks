# Product Offer Clustering Benchmark

Status: current implementation lives in `benchpacks/product-offer-matching/`
as a direct-edit external-agent benchmark over a billiger.de-derived
cluster-labeled offer fixture.

Related material for this benchmark:

- [Methodology knowledge base](methodology/index.md) — dataset-agnostic
  pipeline methodology (blocking, signals, scoring, clustering, evaluation,
  data quality, constraints, resources)
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

The first Python lane uses only the Python standard library. The first Rust lane
uses one `clusterer.rs` file compiled directly with `rustc`.

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
