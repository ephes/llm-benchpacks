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
