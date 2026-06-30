from __future__ import annotations

import argparse
import csv


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--train", required=True)
    parser.add_argument("--predict", required=True)
    parser.add_argument("--output", required=True)
    parser.add_argument("--pair-input", required=True)
    parser.add_argument("--pair-scores", required=True)
    args = parser.parse_args()

    with open(args.predict, newline="", encoding="utf-8") as predict_file:
        offers = list(csv.DictReader(predict_file))

    with open(args.output, "w", newline="", encoding="utf-8") as output_file:
        writer = csv.DictWriter(output_file, fieldnames=["offer_id", "cluster_id"])
        writer.writeheader()
        for row in offers:
            writer.writerow(
                {"offer_id": row["offer_id"], "cluster_id": f"singleton:{row['offer_id']}"}
            )

    with open(args.pair_input, newline="", encoding="utf-8") as pair_file:
        pairs = list(csv.DictReader(pair_file))
    with open(args.pair_scores, "w", newline="", encoding="utf-8") as score_file:
        writer = csv.DictWriter(score_file, fieldnames=["pair_id", "score"])
        writer.writeheader()
        for row in pairs:
            writer.writerow({"pair_id": row["pair_id"], "score": "0.0"})

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
