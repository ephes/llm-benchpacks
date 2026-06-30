You are running inside the prepared repository workspace for this benchmark
case. Implement the Rust product-offer clusterer by editing the workspace file
directly.

Allowed repo-root path to edit:

- `clusterer.rs`

Do not edit data files, README files, verifier files, prompts, generated
artifacts, or the Python clusterer.

Task:

Write a deterministic product-offer clustering program. Read visible labeled
training offers from `data/train_offers.csv`, read unlabeled prediction offers
from `data/test_offers.csv`, and write `clusters.csv` with exactly one
`offer_id,cluster_id` row for every prediction offer. Offers with the same output
`cluster_id` are predicted to be the same real product.

Also read `data/eval_pairs.csv` and write `pair_scores.csv` with header
`pair_id,score`, one row for every eval pair, where a higher score means the two
offers are more likely to be the same product. If your implementation tracks
stage timing, candidate-pair counts, or memory counters, you may also write an
optional flat-scalar `metrics.json`.

The offers carry several fields; which of them to use is your decision.

`data/train_offers.csv` columns:

```text
offer_id,title,shop_name,price_eur,brand,category_label,cluster_id,cluster_label
```

`data/test_offers.csv` columns:

```text
offer_id,title,shop_name,price_eur,brand,category_label
```

`data/eval_pairs.csv` columns:

```text
pair_id,offer_id_left,offer_id_right
```

The data is derived from billiger.de. `category_label` is an aggregator
classifier output, not ground truth. Training and test true product clusters are
disjoint.

Constraints:

- Use only the Rust standard library and a single `clusterer.rs` file that
  compiles with `rustc`.
- No network access or external services.
- The program must be deterministic: the same input must produce the same output.
- Do not hardcode test `offer_id`, `pair_id`, labels, or cluster ids. Do not read
  verifier files.

Scale: the hidden test set has roughly 21,800 offers. Your approach must finish
within the time and memory budget; throughput and peak memory are scored.

You will need to decide which offers are worth comparing, how to judge whether
two offers are the same product, and how to group offers into products. The
approach is yours.

Local command the verifier will run:

```sh
rustc clusterer.rs -O -o <verifier-temp>/clusterer-rust
<verifier-temp>/clusterer-rust --train data/train_offers.csv --predict data/test_offers.csv --output clusters.csv --pair-input data/eval_pairs.csv --pair-scores pair_scores.csv
```

Verifier contract:

- `clusters.csv` must have header `offer_id,cluster_id`.
- Every `offer_id` from `data/test_offers.csv` must appear exactly once.
- `pair_scores.csv` must have header `pair_id,score` and one finite numeric score
  for every row in `data/eval_pairs.csv`.
- No unknown or duplicate ids are allowed.
- The verifier records B-cubed cluster precision/recall/F1, pairwise cluster
  precision/recall/F1, a full pair-score precision/recall curve, program runtime,
  offers per second, peak RSS, and a combined score.

Edit `clusterer.rs` directly and exit when done.
