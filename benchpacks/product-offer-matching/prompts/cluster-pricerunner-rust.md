You are running inside the prepared repository workspace for this benchmark
case. Implement the Rust product-offer clusterer by editing the workspace file
directly.

Allowed repo-root path to edit:

- `clusterer.rs`

Do not edit data files, README files, verifier files, prompts, generated
artifacts, or the Python clusterer.

Task:

Write a deterministic product-offer clustering program. The program must read
visible labeled training offers from `data/train_offers.csv`, read unlabeled
prediction offers from `data/test_offers.csv`, and write `clusters.csv` with
exactly one `offer_id,cluster_id` row for every prediction offer. Offers with
the same output `cluster_id` are predicted to be the same real product.

Also read `data/eval_pairs.csv` and write `pair_scores.csv` with header
`pair_id,score`, one row for every eval pair, where higher scores mean the two
offers are more likely to be the same product. The verifier uses this to produce
a full precision/recall curve. If your implementation has stage timing,
candidate-pair counts, blocking counts, or memory-relevant counters, also write
an optional `metrics.json` object with simple scalar fields.

Use only the Rust standard library. Do not use network access or external
services. Do not hardcode test `offer_id`, `pair_id`, labels, or cluster ids.

CSV schemas:

`data/train_offers.csv` columns:

```text
offer_id,title,merchant_id,category_id,category_label,cluster_id,cluster_label
```

`data/test_offers.csv` columns:

```text
offer_id,title,merchant_id,category_id,category_label
```

`data/eval_pairs.csv` columns:

```text
pair_id,offer_id_left,offer_id_right
```

The data is derived from the PriceRunner product classification and clustering
dataset. Training and test true product clusters are disjoint.

Useful implementation ideas:

- Normalize case, punctuation, whitespace, and simple Unicode variants.
- Block by category and product-code tokens before comparing offers.
- Extract model-like tokens such as capacities, part numbers, slash-separated
  codes, hyphenated identifiers, screen sizes, CPU models, appliance model
  numbers, and alphanumeric product codes.
- Use visible training clusters to calibrate thresholds, token weights, and
  rules for each category.
- Build a similarity graph over candidate pairs and output connected
  components, union-find clusters, or another deterministic clustering result.
- Avoid all-pairs scoring across all test offers; the hidden test set has more
  than 25,000 offers.

Local command the verifier will run:

```sh
rustc clusterer.rs -O -o <verifier-temp>/clusterer-rust
<verifier-temp>/clusterer-rust --train data/train_offers.csv --predict data/test_offers.csv --output clusters.csv --pair-input data/eval_pairs.csv --pair-scores pair_scores.csv
```

Verifier contract:

- `clusters.csv` must have header `offer_id,cluster_id`.
- Every `offer_id` from `data/test_offers.csv` must appear exactly once.
- `pair_scores.csv` must have header `pair_id,score` and one finite numeric
  score for every row in `data/eval_pairs.csv`.
- No unknown or duplicate ids are allowed.
- The verifier records B-cubed cluster precision/recall/F1, pairwise cluster
  precision/recall/F1, a full pair-score precision/recall curve, program
  runtime, offers per second, eval pairs per second, peak RSS, and a combined
  score.

Edit `clusterer.rs` directly and exit when done.
