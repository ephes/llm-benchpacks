# Product Offer Matcher Fixture

Implement one matcher program for WDC-derived product-offer pairs.

Input files:

- `data/train.csv`: labeled offer pairs with `label` equal to `1` for the same
  product and `0` otherwise.
- `data/test_pairs.csv`: unlabeled offer pairs to predict.

Output contract:

- Write a CSV with header `pair_id,label`.
- Include exactly one row for each `pair_id` in `data/test_pairs.csv`.
- Use labels `0` and `1` only.

The benchmark verifier owns the hidden labels.
