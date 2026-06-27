# product-offer-matching

Opt-in direct-edit `repo-task` benchmark for product-offer matching programs.
The measured agent edits one matcher implementation, then the verifier runs it
against hidden WDC-derived labels and scores positive-class F1.

Pack version: `0.1.0`.

## Cases

- `pairwise-real-small-python`: implement `matcher.py` using the Python
  standard library.
- `pairwise-real-small-rust`: implement `matcher.rs` as a single file that
  compiles with `rustc` and uses only the Rust standard library.

Both cases use the public `external-agent` harness. The normal adapter call is
kept as a runner compatibility step; benchmark interpretation should use the
external-agent model-call telemetry and verifier output.

The bundled Pi wrapper, `examples/external-agent/pi-agent.py`, runs Pi without
file-system tools. It embeds the prompt-allowed editable file and visible
workspace data files in the prompt, requires a JSON full-file replacement
response, and applies only paths listed in the benchmark prompt's allowed edit
section.

## Fixture

The fixture is a compact CSV task derived from WDC Products 20pair
`wdcproducts20cc80rnd000un`, downloaded from:

`https://data.dws.informatik.uni-mannheim.de/largescaleproductcorpus/data/wdc-products/20pair.zip`

The derived files use:

- `wdcproducts20cc80rnd000un_train_small.json.gz` for visible training rows.
- `wdcproducts20cc80rnd000un_gs.json.gz` for hidden test labels.

Raw WDC offer ids and cluster ids are stripped from matcher inputs. `pair_id`
values are local sequential ids, not WDC ids. The fixture keeps WDC offer
attributes such as brand, title, description, price, and currency.

Derived fixture shape:

- `data/train.csv`: 200 visible labeled pairs, 50 positive and 150 negative.
- `data/test_pairs.csv`: 120 unlabeled prediction pairs.
- `verify/hidden_labels.csv`: 120 verifier-owned labels, 30 positive and 90
  negative.

The WDC Products page describes the upstream benchmark as real-world product
entity matching with pairwise splits and offer-disjoint train/validation/test
records. This pack is a small derived benchmark fixture, not a reproduction of
the full WDC Products benchmark.

## Verification

`verify/score_pairwise.py` runs the implementation with:

```sh
python matcher.py --train data/train.csv --predict data/test_pairs.csv --output predictions.csv
```

or, for Rust:

```sh
rustc matcher.rs -O -o <verifier-temp>/matcher-rust
<verifier-temp>/matcher-rust --train data/train.csv --predict data/test_pairs.csv --output predictions.csv
```

The output CSV must contain `pair_id,label` with one prediction for every test
pair and labels limited to `0` or `1`. The verifier fails on malformed output,
missing ids, duplicate ids, unknown ids, extra ids, non-zero process exit,
timeout, empty patch, or F1 below the threshold.

Primary pass threshold:

- positive-class F1 must be at least `0.70`.

Calibration notes from the generated fixture:

- Always-negative F1: `0.000`.
- Always-positive F1: `0.400`.
- Best simple token-Jaccard threshold over hidden rows: about `0.645`.
- Best simple token-Jaccard threshold selected on visible training rows and
  evaluated on hidden rows: about `0.657`.

The verifier writes precision, recall, accuracy, confusion counts, prevalence,
runtime seconds, and threshold details into its JSON artifact.

## Example Command

```sh
BENCHPACK_EXTERNAL_AGENT_ARGV='["/abs/path/to/examples/external-agent/pi-agent.py", "--model", "openai-codex/gpt-5.5", "--thinking", "off"]' \
  uv run benchpack run product-offer-matching --adapter ollama-generate --model qwen3-coder:latest --host-label product-offer-pi-gpt55 --force
```

Generated result directories remain under `results/` and are ignored by
default. Commit only curated summaries or documentation updates.
