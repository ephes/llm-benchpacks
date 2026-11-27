# product-offer-matching

Opt-in direct-edit `repo-task` benchmark for product-offer clustering programs.
The measured agent edits one clusterer implementation, then the verifier runs it
against hidden billiger.de-derived product clusters and eval-pair labels.

Pack version: `0.1.0`.

The Python fixture now includes `offerweave`, a dependency-trained reference
matcher package invoked by `clusterer.py`. It clears the hidden eval-pair
average-precision target and now passes the pack's B-cubed and pairwise
clustering thresholds. It clears the reference pairwise cluster F1 target of
`0.80`, but it is still below the B-cubed reference goal of `0.95`. See
`docs/benchmarks/product-offer-matching/offerweave-reference.md` for the
paper-style report and current metrics.

## Cases

- `cluster-billiger-python`: implement `clusterer.py`; the bundled
  `offerweave` reference uses the project `uv` environment and embedded
  coefficients trained with `numpy`/`scikit-learn`.
- `cluster-billiger-rust`: implement `clusterer.rs` as a single file that
  compiles with `rustc` and uses only the Rust standard library.

Both cases use the public `external-agent` harness. The normal adapter call is
kept as a runner compatibility step; benchmark interpretation should use the
external-agent model-call telemetry and verifier output.
The harness timeout is 3600 seconds per case to accommodate long-context local
Pi/Qwen runs that prefill the embedded real-data fixture.

The bundled Pi wrapper, `examples/external-agent/pi-agent.py`, runs Pi without
file-system tools. It embeds the prompt-allowed editable file and a bounded
preview of visible workspace data files in the prompt, requires a JSON full-file
replacement response, and applies only paths listed in the benchmark prompt's
allowed edit section. The generated program must read the full CSV files from
the workspace at runtime.

## Fixture

The fixture is a cluster-labeled CSV task derived from billiger.de product
offers. It lives at `fixtures/billiger-matcher-repo` and is built by
`scripts/build-fixture-from-billiger.py` from a raw offer export outside git.

Each offer carries multiple signals beyond the title. Visible training offers
have columns:

```text
offer_id,title,shop_name,price_eur,brand,category_label,cluster_id,cluster_label
```

Prediction (test) offers carry the same columns minus the two cluster columns
(`cluster_id` and `cluster_label`), which are hidden. `category_label` is a
classifier output rather than a verbatim source field; do not treat it as a
production-realistic input. The bundled reference does not read it at runtime:
it infers product family/category from title and brand, then blocks by brand
plus capped token/code/unit candidate blocks. The data has no GTIN.
`image_url` is **excluded** from the published offers: the scrape only has the
canonical billiger product image (one per cluster), so it leaks the gold cluster
id like a reliable identifier and is stripped, the same way GTIN is (decisions
D-035 and D-038).

Raw source ids are replaced with local `offer_id` values after deterministically
shuffling train and test rows. The deterministic split is by true product
cluster, so visible training products and hidden test products are disjoint.
Public row order and sequential `offer_id` assignment must not encode source
product-cluster order.

Derived fixture shape (from 31,330 input offers, 31,187 kept):

- `data/train_offers.csv`: 9,362 visible labeled offers from 1,385 product
  clusters.
- `data/test_offers.csv`: 21,825 unlabeled prediction offers from 3,265 hidden
  product clusters.
- `data/eval_pairs.csv`: 20,000 unlabeled eval pairs sampled from hidden test
  offers, with 5,000 positive and 15,000 negative pairs.
- `verify/hidden_test_clusters.csv`: verifier-owned hidden product cluster for
  every test offer.
- `verify/hidden_eval_pair_labels.csv`: verifier-owned labels for
  `data/eval_pairs.csv`.

Unlike the title-only PriceRunner predecessor (decision D-034), the billiger
fixture adds a genuine **price** (`price_eur`) signal alongside title, shop,
brand, and classifier category metadata, so it supports multi-signal product
matching. The category metadata is retained for transparency and comparison,
but the reference implementation treats it as non-production metadata. An image
signal would also help, but only as real per-merchant photos; the canonical
product image we have is a cluster-id proxy and is excluded (D-038).

## Verification

`verify/score_clusters.py` runs the implementation with:

```sh
python clusterer.py --train data/train_offers.csv --predict data/test_offers.csv --output clusters.csv --pair-input data/eval_pairs.csv --pair-scores pair_scores.csv
```

or, for Rust:

```sh
rustc clusterer.rs -O -o <verifier-temp>/clusterer-rust
<verifier-temp>/clusterer-rust --train data/train_offers.csv --predict data/test_offers.csv --output clusters.csv --pair-input data/eval_pairs.csv --pair-scores pair_scores.csv
```

`clusters.csv` must contain `offer_id,cluster_id` with one prediction for every
test offer. `pair_scores.csv` must contain `pair_id,score` with one finite
numeric score for every eval pair. The verifier fails on malformed output,
missing ids, duplicate ids, unknown ids, extra ids, non-zero process exit,
timeout, empty patch, or cluster metrics below the thresholds.

Implementations may also write:

- `metrics.json` as a flat scalar object with implementation-owned timing or
  count fields.

The verifier records B-cubed cluster precision/recall/F1, pairwise cluster
precision/recall/F1, eval-pair operating point from the final clusters, a full
precision/recall curve from `pair_scores.csv`, wall time, offers per second,
eval pairs per second, and sampled peak owned-process-group RSS. With valid
predictions and complete memory evidence it also emits a transparent combined score:

```text
100 * (0.35*bcubed_f1 + 0.25*pairwise_cluster_f1
       + 0.25*average_precision
       + 0.10*min(offers_per_second/10000,1)
       + 0.05*min(1024/peak_rss_mb,1))
```

This score is quality-dominant and should not be treated as a production
business metric. It exists to keep memory and throughput visible in benchmark
comparisons.

Primary pass threshold:

- B-cubed F1 must be at least `0.70`.
- Pairwise cluster F1 must be at least `0.20`.

The scorer compares exact cluster F1 values against these inclusive minima.
The published metrics round to six decimal places.

The verifier writes cluster metrics, eval-pair metrics, precision/recall curve
metadata, runtime seconds, system metrics, and combined score details into its
JSON artifact.

## Example Command

```sh
BENCHPACK_EXTERNAL_AGENT_ARGV='["/abs/path/to/examples/external-agent/pi-agent.py", "--model", "openai-codex/gpt-5.5", "--thinking", "off", "--timeout-s", "3600"]' \
  uv run benchpack run product-offer-matching --adapter ollama-generate --model qwen3-coder:latest --host-label product-offer-pi-gpt55 --force
```

Generated result directories remain under `results/` and are ignored by
default. Commit only curated summaries or documentation updates.

### Candidate execution and memory evidence

The cluster scorer drains stdout/stderr while the candidate runs and retains at
most 64 KiB per stream. Each candidate runs in a new POSIX process group; the
scorer kills remaining group members and reaps the leader on completion, timeout
or interruption, with a bounded cleanup wait. SIGTERM or SIGHUP to the scorer
(for example from the outer verifier timeout) records a stop request: a running
candidate is retired through the same cleanup, then the scorer exits with
status 128 + signal number.
Each sample drains up to 1 MiB per output stream. This is lifecycle ownership, not
a security sandbox; candidates must not detach from the owned group.

`system_metrics.memory_scope = "owned_process_group_sampled_rss"` identifies the
sum of RSS sampled across the owned group via psutil. Shared resident pages may
be counted for each process. `memory_samples` records successful observations;
`memory_complete` requires nonzero evidence and no failed observations. Missing
accounting permissions, all-missed/zero observations or sampling failures yield
null `peak_rss_mb` and an unavailable combined score (`value: null`), never zero
memory evidence. Normal exits are not failed observations: a group member that
exits during a sample is skipped, and a sample that finds no member because the
leader just exited ends the run. Sampling may miss brief allocation peaks. Historical scores
using only the leader PID have a different scope and must not be compared as
though the memory methodology were unchanged. Candidate `program_metrics`
remain self-reported and separate from independently observed system metrics.

### Fixture identity checks

Before launching the candidate, the scorer checks that public and hidden CSVs
have unique offer or pair IDs, that the hidden labels cover exactly the public
IDs, and that both endpoints of each eval pair are test offers. A failed check
produces `passed: false` with `error` and `fixture_errors` in the JSON artifact.

### Candidate file admission

Predictions and optional metrics are opened once with no-follow, nonblocking
regular-file admission. Reads reject changes to the opened file's size or
metadata. Each CSV is limited to 16 MiB and 100,000 rows; metrics.json to 64 KiB.
One run shares 32 MiB and 200,000 CSV rows across all candidate evidence.
Exact-limit files are admitted. Headers and row widths must match the schema;
errors retain only bounded row diagnostics, never candidate file contents.

Optional metrics require unique JSON members at every depth and finite numbers
(including exponent overflow rejection). At most 128 top-level fields are
accepted, with keys up to 128 UTF-8 bytes and scalar strings up to 4096 bytes;
invalid Unicode scalar strings are refused. Only scalar extensions are retained.
Missing metrics are optional; present but malformed metrics invalidate evidence.

### Precision/recall methodology

The scorer sorts pair scores once, then accumulates confusion counts in a single
sweep over equal-score threshold groups (O(n log n) time, O(n) retained rows).
Threshold rows retain the `score >= threshold` convention. Average precision is
noninterpolated: sum each group's recall increment times precision after the
whole group is admitted. A positive and a negative tied at the same score have
AP 0.5 in either CSV order. AP is zero with no positives. The best-hidden row
is selected by the exact F1 ratio from the confusion counts, with the highest
threshold winning exact ties. Published F1 is rounded to six decimal places.
Older per-item AP can differ for tied scores and must be identified accordingly.

### Valid quality evidence and result publication

All prediction schema, coverage and optional-metrics errors are collected before
quality calculation. Invalid evidence fails with bounded `prediction_errors`,
null `metrics`/`pr_curve` and an unavailable combined score. Measured program and
system execution data remain available. Complete but wrong predictions receive
normal numeric quality scores, including genuine low scores.

The scorer stages a complete generation-specific PR CSV and strictly serialized
JSON before publication. It installs the immutable curve first, then atomically
replaces the JSON with a reference to that exact generation. A failure before
the JSON rename preserves the previous JSON and its curve. If the rename
lands before an interruption is reported, the visible JSON's curve remains
readable. Installed curves are retained, including complete generations left
unreferenced by an interrupted publication. Consumers locate the curve using
`pr_curve.path`. Atomic visibility applies during publication. Durability
across power loss is outside this contract. Outer verifier normalization
preserves the generation reference.

### Billiger fixture rebuilding

Positive pairs are sampled uniformly without replacement from the range of
within-cluster pair indices. Compact cluster counts plus binary-search unranking
avoid a quadratic tuple pool, even for zero or one requested pair. Seeds remain
reproducible with this algorithm; the RNG sequence intentionally changes versus
the old shuffled pool, so future deliberate fixture regeneration can change
sampled rows for the same seed. No committed dataset is regenerated by this
change. Negative-pair sampling and label/ID contracts are unchanged.

The builder serializes cooperating writers with stable POSIX locks in every
output directory. It serializes and validates all five CSVs plus the report,
stages bytes and backups beside their destinations, then replaces them. Any
catchable publication failure restores the previous generation (or removes newly
created files). Failed compensation retains stages and a recovery manifest with
target and backup paths. Do not remove the retained lock files. Readers must
consume a finished build; multi-file replacement does not provide snapshot reads
during publication or automatic recovery after an uncatchable process/power loss.
