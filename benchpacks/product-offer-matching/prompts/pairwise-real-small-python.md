You are running inside the prepared repository workspace for this benchmark
case. Implement the Python product-offer matcher by editing the workspace file
directly.

Allowed repo-root path to edit:

- `matcher.py`

Do not edit data files, README files, verifier files, prompts, generated
artifacts, or the Rust matcher.

Task:

Write a deterministic product-offer matcher. The program must read visible
labeled training pairs from `data/train.csv`, read unlabeled prediction pairs
from `data/test_pairs.csv`, and write `predictions.csv` with exactly one
`pair_id,label` row for every prediction pair. Label `1` means the two offers
refer to the same product; label `0` means they do not.

Use only the Python standard library. Do not use network access or external
services. Do not hardcode test `pair_id` values or labels.

CSV schemas:

`data/train.csv` columns:

```text
pair_id,brand_left,title_left,description_left,price_left,priceCurrency_left,brand_right,title_right,description_right,price_right,priceCurrency_right,label
```

`data/test_pairs.csv` columns:

```text
pair_id,brand_left,title_left,description_left,price_left,priceCurrency_left,brand_right,title_right,description_right,price_right,priceCurrency_right
```

Current file: `matcher.py`

```python
from __future__ import annotations

import argparse
import csv


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--train", required=True)
    parser.add_argument("--predict", required=True)
    parser.add_argument("--output", required=True)
    args = parser.parse_args()

    with open(args.predict, newline="", encoding="utf-8") as predict_file:
        rows = list(csv.DictReader(predict_file))

    with open(args.output, "w", newline="", encoding="utf-8") as output_file:
        writer = csv.DictWriter(output_file, fieldnames=["pair_id", "label"])
        writer.writeheader()
        for row in rows:
            writer.writerow({"pair_id": row["pair_id"], "label": "0"})

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
```

Useful implementation ideas:

- Normalize text case, punctuation, whitespace, and simple Unicode variants.
- Compare title, brand, and description tokens.
- Extract model-like tokens such as capacities, part numbers, hyphenated
  identifiers, and alphanumeric product codes.
- Use visible `label` values in `data/train.csv` to tune a threshold or simple
  weighted rule.
- Treat matching brands, model identifiers, and high title-token overlap as
  positive evidence.
- Treat conflicting capacities, product families, or very low overlap as
  negative evidence.

Local command the verifier will run:

```sh
python matcher.py --train data/train.csv --predict data/test_pairs.csv --output predictions.csv
```

Verifier contract:

- `predictions.csv` must have header `pair_id,label`.
- Every `pair_id` from `data/test_pairs.csv` must appear exactly once.
- No unknown or duplicate ids are allowed.
- Labels must be exactly `0` or `1`.
- Positive-class F1 against hidden labels must be at least `0.70`.

Edit `matcher.py` directly and exit when done.
