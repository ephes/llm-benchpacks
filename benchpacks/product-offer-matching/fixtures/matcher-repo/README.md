# Product Offer Clustering Fixture

Implement one clusterer program for PriceRunner-derived product offers.

Input files:

- `data/train_offers.csv`: labeled training offers with product `cluster_id`
  and `cluster_label`.
- `data/test_offers.csv`: unlabeled offers to cluster into products.
- `data/eval_pairs.csv`: unlabeled pair sample for score calibration and
  precision/recall curve generation.

Output contract:

- Write `clusters.csv` with header `offer_id,cluster_id`.
- Include exactly one row for each `offer_id` in `data/test_offers.csv`.
- Write `pair_scores.csv` with header `pair_id,score`, one finite numeric score
  for each `pair_id` in `data/eval_pairs.csv`.

The benchmark verifier owns the hidden test cluster labels and hidden eval-pair
labels.
