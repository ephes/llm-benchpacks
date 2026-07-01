# billiger-matcher-repo

Direct-edit fixture for the `product-offer-matching` benchmark. The measured
agent edits one clusterer implementation (`clusterer.py` or `clusterer.rs`); the
verifier runs it against hidden billiger.de product clusters.

The shipped Python clusterer is the `offerweave` reference matcher: a
dependency-trained package that uses public-train-derived coefficients, writes
cluster predictions, and writes eval-pair scores. It is intentionally still
below the final clustering target so future agents have a meaningful bar to
beat.

## Data (`data/`)

- `train_offers.csv` — visible labeled offers:
  `offer_id,title,shop_name,price_eur,brand,category_label,cluster_id,cluster_label`
- `test_offers.csv` — unlabeled offers to cluster (same columns minus
  `cluster_id,cluster_label`).
- `eval_pairs.csv` — `pair_id,offer_id_left,offer_id_right`.

Offers with the same `cluster_id` are the same real product. Data is derived from
billiger.de; `category_label` is an aggregator classifier output rather than a
raw merchant field. Realistic matchers should not depend on it; the bundled
`offerweave` reference infers product family/category from title and brand,
then blocks by brand and capped title-token candidate blocks. No structured
GTIN/EAN is present. `image_url` is excluded because the only image available is
the canonical product image, which is a cluster-id proxy (D-038). Training and
test products are disjoint.
