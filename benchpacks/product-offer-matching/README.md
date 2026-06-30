# product-offer-matching

Opt-in direct-edit `repo-task` benchmark for product-offer clustering programs.
The measured agent edits one clusterer implementation, then the verifier runs it
against hidden PriceRunner-derived product clusters and eval-pair labels.

Pack version: `0.1.0`.

## Cases

- `cluster-pricerunner-python`: implement `clusterer.py` using the Python
  standard library.
- `cluster-pricerunner-rust`: implement `clusterer.rs` as a single file that
  compiles with `rustc` and uses only the Rust standard library.

Both cases use the public `external-agent` harness. The normal adapter call is
kept as a runner compatibility step; benchmark interpretation should use the
external-agent model-call telemetry and verifier output.
The harness timeout is 3600 seconds per case to accommodate long-context local
Pi/Qwen runs that prefill the embedded real-data fixture.

The bundled Pi wrapper, `examples/external-agent/pi-agent.py`, runs Pi without
file-system tools. It embeds the prompt-allowed editable file and a bounded
preview of visible workspace data files in the prompt, requires a JSON full-file
replacement response, and applies only paths listed in the benchmark prompt's
allowed edit section. The generated program must read the full CSV files from
the workspace at runtime.

## Fixture

The fixture is a cluster-labeled CSV task derived from the PriceRunner Product
Classification and Clustering dataset, also mirrored on Kaggle as:

- `https://www.kaggle.com/datasets/lakritidis/product-clustering-matching-classification/data`

The same data can be downloaded without Kaggle credentials from the UCI Machine
Learning Repository:

- `https://archive.ics.uci.edu/dataset/837/product%2Bclassification%2Band%2Bclustering`

Raw source product ids are replaced with local `offer_id` values after
deterministically shuffling train and test rows. Visible training offers keep
`cluster_id` and `cluster_label`; prediction offers hide the cluster labels.
The deterministic split is by true product cluster, so visible training
products and hidden test products are disjoint. Public row order and sequential
`offer_id` assignment must not encode source product-cluster order.

Derived fixture shape:

- `data/train_offers.csv`: 10,003 visible labeled offers from 3,709 product
  clusters.
- `data/test_offers.csv`: 25,308 unlabeled prediction offers from 9,524 hidden
  product clusters.
- `data/eval_pairs.csv`: 20,000 unlabeled eval pairs sampled from hidden test
  offers, with 5,000 positive and 15,000 negative pairs.
- `verify/hidden_test_clusters.csv`: verifier-owned hidden product cluster for
  every test offer.
- `verify/hidden_eval_pair_labels.csv`: verifier-owned labels for
  `data/eval_pairs.csv`.

The upstream PriceRunner data contains 35,311 offers, 13,233 product clusters,
306 merchants, and 10 product categories. It is explicitly intended for product
classification, clustering, and entity matching.

### Limitation: title-only, no price or images

This dataset is text-only. Its sole offer columns are product title, merchant
id, and category id/label. It carries **no price and no image fields**, and
neither can be recovered — they are absent at the source, not dropped by the
fixture builder. Price (same-product offers cluster tightly; large gaps are
strong negative evidence) and images (visual disambiguation of variants) are
central signals for realistic product matching, so this pack is a **title-only
entity-matching lane**, not a faithful multi-signal product-matching benchmark.
A price- and image-bearing dataset is required for any price-aware or multimodal
lane. See decision D-034.

## Verification

`verify/score_clusters.py` runs the implementation with:

```sh
python clusterer.py --train data/train_offers.csv --predict data/test_offers.csv --output clusters.csv --pair-input data/eval_pairs.csv --pair-scores pair_scores.csv
```

or, for Rust:

```sh
rustc clusterer.rs -O -o <verifier-temp>/clusterer-rust
<verifier-temp>/clusterer-rust --train data/train_offers.csv --predict data/test_offers.csv --output clusters.csv --pair-input data/eval_pairs.csv --pair-scores pair_scores.csv
```

`clusters.csv` must contain `offer_id,cluster_id` with one prediction for every
test offer. `pair_scores.csv` must contain `pair_id,score` with one finite
numeric score for every eval pair. The verifier fails on malformed output,
missing ids, duplicate ids, unknown ids, extra ids, non-zero process exit,
timeout, empty patch, or cluster metrics below the thresholds.

Implementations may also write:

- `metrics.json` as a flat scalar object with implementation-owned timing or
  count fields.

The verifier records B-cubed cluster precision/recall/F1, pairwise cluster
precision/recall/F1, eval-pair operating point from the final clusters, a full
precision/recall curve from `pair_scores.csv`, wall time, offers per second,
eval pairs per second, and peak process RSS. It also emits a transparent
combined score:

```text
100 * (0.35*bcubed_f1 + 0.25*pairwise_cluster_f1
       + 0.25*average_precision
       + 0.10*min(offers_per_second/10000,1)
       + 0.05*min(1024/peak_rss_mb,1))
```

This score is quality-dominant and should not be treated as a production
business metric. It exists to keep memory and throughput visible in benchmark
comparisons.

Primary pass threshold:

- B-cubed F1 must be at least `0.70`.
- Pairwise cluster F1 must be at least `0.20`.

The verifier writes cluster metrics, eval-pair metrics, precision/recall curve
metadata, runtime seconds, system metrics, and combined score details into its
JSON artifact.

## Example Command

```sh
BENCHPACK_EXTERNAL_AGENT_ARGV='["/abs/path/to/examples/external-agent/pi-agent.py", "--model", "openai-codex/gpt-5.5", "--thinking", "off", "--timeout-s", "3600"]' \
  uv run benchpack run product-offer-matching --adapter ollama-generate --model qwen3-coder:latest --host-label product-offer-pi-gpt55 --force
```

Generated result directories remain under `results/` and are ignored by
default. Commit only curated summaries or documentation updates.
