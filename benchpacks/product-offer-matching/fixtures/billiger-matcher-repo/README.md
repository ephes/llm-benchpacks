# billiger-matcher-repo

Direct-edit fixture for the `product-offer-matching` benchmark. The measured
agent edits one clusterer implementation (`clusterer.py` or `clusterer.rs`); the
verifier runs it against hidden billiger.de product clusters.

The shipped clusterer is a trivial baseline (each offer in its own cluster, every
eval pair scored 0.0). Replace it with a real product matcher.

## Data (`data/`)

- `train_offers.csv` — visible labeled offers:
  `offer_id,title,shop_name,price_eur,brand,category_label,cluster_id,cluster_label`
- `test_offers.csv` — unlabeled offers to cluster (same columns minus
  `cluster_id,cluster_label`).
- `eval_pairs.csv` — `pair_id,offer_id_left,offer_id_right`.

Offers with the same `cluster_id` are the same real product. Data is derived from
billiger.de; `category_label` is an aggregator classifier output (a feature, not
ground truth), and no structured GTIN/EAN is present. `image_url` is excluded
because the only image available is the canonical product image, which is a
cluster-id proxy (D-038). Training and test products are disjoint.
