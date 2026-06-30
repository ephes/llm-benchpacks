# Billiger Pack Replacement — Design

Date: 2026-06-30
Status: design, pending implementation plan.

## Goal

Make the billiger fixture the runnable `product-offer-matching` benchmark by
**replacing** the PriceRunner fixture, cases, prompts, and hidden labels with
billiger equivalents. The PriceRunner lane is retired from the live pack but
preserved in git history and under `results/` as the title-only predecessor
(see decision D-034). The verifier's scoring logic is reused unchanged.

## Decisions (from brainstorming)

- **Replace** PriceRunner (not a parallel pack) — billiger becomes *the* pack.
- **Both lanes** retained: `cluster-billiger-python`, `cluster-billiger-rust`,
  each shipping the same trivial singleton-baseline clusterer stub the agent must
  replace. The matching is the benchmark.
- **Lightly-guided prompts**: fully specify task, schema, I/O contract,
  constraints, scale, and scoring; name the sub-problems at a high level; give NO
  techniques, token lists, thresholds, or clustering method.
- **Builder writes into the pack layout**: public files → fixture-repo `data/`,
  hidden labels → pack `verify/`.
- **Verifier logic unchanged**; pass thresholds kept as-is for the MVP
  (recalibrate after real runs).
- **Out of scope** (separate later projects): the D-036 amplified scale-set
  system-metric lane, the warm-start (catalog-linkage) lane, and threshold
  recalibration.

## Why no verifier logic change

`verify/score_clusters.py` reads hidden labels via
`Path(__file__).with_name("hidden_test_clusters.csv")` /
`hidden_eval_pair_labels.csv` (i.e. from the pack `verify/` dir, outside the
copied fixture — correct for anti-leakage), reads `clusters.csv`/`pair_scores.csv`
from the workspace, reads `data/test_offers.csv` only for `offer_id`s, and
computes B-cubed, pairwise-cluster, the PR curve / average precision, system
metrics (peak RSS, offers/sec), the combined score, and the hard gates. Billiger's
hidden-label schema (`offer_id,cluster_id` and `pair_id,label`) and output
contracts are identical to PriceRunner's, so **only the data and hidden labels
change, not the code.**

## Builder change

`scripts/build-fixture-from-billiger.py` currently writes all six files under one
`--out-dir`. Change `main()` to write to the pack layout:

- public → `fixtures/billiger-matcher-repo/data/{train_offers,test_offers,eval_pairs}.csv`
- hidden → `verify/{hidden_test_clusters,hidden_eval_pair_labels}.csv`
- `build-report.json` → `fixtures/billiger-matcher-repo/build-report.json`

`build()` gains two output roots in place of the single `out_dir`: `data_dir`
(the three public `train/test/eval` CSVs) and `verify_dir` (the two hidden-label
files). `build-report.json` is written to the fixture-repo root, i.e.
`data_dir.parent`, matching the target layout (`fixtures/billiger-matcher-repo/build-report.json`).
`main()` exposes `--data-dir` (default
`benchpacks/product-offer-matching/fixtures/billiger-matcher-repo/data`) and
`--verify-dir` (default `benchpacks/product-offer-matching/verify`). Regenerating
thus updates the live pack directly. The standalone `fixtures/billiger/` directory
created by the earlier task is removed once the pack layout is the source of
truth.

This `build()` signature change updates the existing build integration tests in
`tests/test_build_fixture_from_billiger.py` (`test_build_writes_all_outputs_with_anti_leakage`,
`test_build_is_deterministic`) to pass the two roots and read hidden labels from
`verify_dir`; the per-function unit tests (`clean_offers`, `choose_split`,
`anonymize`, `sample_eval_pairs`, token extractors) are unaffected.

## Target pack structure (after)

```text
benchpacks/product-offer-matching/
  benchpack.toml                       # billiger cases + fixture
  README.md                            # billiger description
  prompts/
    cluster-billiger-python.md         # lightly-guided
    cluster-billiger-rust.md           # lightly-guided
  fixtures/billiger-matcher-repo/
    README.md                          # billiger schema
    clusterer.py                       # trivial singleton stub (agent edits)
    clusterer.rs                       # trivial singleton stub (agent edits)
    data/{train_offers,test_offers,eval_pairs}.csv
    build-report.json
  verify/
    score_clusters.py                  # unchanged logic
    hidden_test_clusters.csv           # billiger
    hidden_eval_pair_labels.csv        # billiger
  scripts/
    build-fixture-from-billiger.py     # active builder (writes pack layout)
    build-fixture-from-pricerunner.py  # kept, historical
  pilot-data/billiger-pilot-offers.csv # raw snapshot
```

Removed: `prompts/cluster-pricerunner-{python,rust}.md`, `fixtures/matcher-repo/`
(PriceRunner data + stubs), and the PriceRunner content of `verify/hidden_*.csv`
(overwritten with billiger). `fixtures/billiger/` (the earlier standalone output)
is deleted.

## Fixture repo (`fixtures/billiger-matcher-repo/`)

- `data/train_offers.csv` — `offer_id,title,shop_name,price_eur,brand,category_label,image_url,cluster_id,cluster_label`
- `data/test_offers.csv` — same minus the two cluster columns.
- `data/eval_pairs.csv` — `pair_id,offer_id_left,offer_id_right`.
- `clusterer.py` / `clusterer.rs` — the existing trivial singleton stubs
  (assign each offer a unique cluster, score every pair `0.0`). They are
  schema-agnostic (only read `offer_id`), so they tolerate the new columns
  unchanged; copy them across from the PriceRunner fixture.
- `README.md` — describes the billiger schema and that the agent edits the
  clusterer.

## benchpack.toml

- `[pack]` description → billiger.
- `[[fixtures]]` id `billiger-matcher-repo`, path `fixtures/billiger-matcher-repo`,
  billiger description.
- Two `[[cases]]`: `cluster-billiger-python`, `cluster-billiger-rust`, each with
  `prompt_file = prompts/cluster-billiger-<lang>.md`, `fixture_refs =
  ["billiger-matcher-repo"]`, the same `harness` (external-agent, 3600s) and
  `scoring` (verify-script `verify/score_clusters.py`, 90s).

## Prompts (lightly guided)

Each prompt (`cluster-billiger-{python,rust}.md`) **includes**:

- Workspace framing; the single allowed edit path (`clusterer.py` or
  `clusterer.rs`); the do-not-edit list.
- Task: read `data/train_offers.csv` (visible labeled) and `data/test_offers.csv`
  (unlabeled), write `clusters.csv` (`offer_id,cluster_id`, one row per test
  offer; same cluster_id ⇒ same product). Read `data/eval_pairs.csv`, write
  `pair_scores.csv` (`pair_id,score`, one finite score per pair, higher ⇒ more
  likely same product). Optional flat-scalar `metrics.json`.
- The full CSV schemas (incl. `price_eur`, `brand`, `category_label`,
  `image_url`, `shop_name`), stated as available signals with **no instruction on
  which to use**.
- Constraints: Python stdlib only / single-file `rustc` + Rust std only;
  deterministic; no network; do not hardcode `offer_id`/`pair_id`/labels/cluster
  ids; do not read verifier files.
- Scale: the hidden test set has ~21,800 offers (so the chosen approach must
  scale within the time/memory budget — efficiency is scored).
- A high-level naming of the sub-problems, no techniques: *"You will need to
  decide which offers are worth comparing, how to judge whether two offers are
  the same product, and how to group offers into products."*
- The exact verifier command and the verifier contract (headers, one row per id,
  no unknown/duplicate ids) and the scored metrics (B-cubed, pairwise-cluster,
  PR curve / average precision, offers/sec, peak RSS, combined score).

Each prompt **excludes** (the deliberate omission): normalization recipes,
blocking strategy, model-token type lists, threshold-calibration recipe, the
clustering algorithm (union-find/connected-components), and any "avoid all-pairs"
style technique hint. Scale is stated as a constraint, not a solution.

## Test updates

`tests/test_product_offer_matching_pack.py` asserts the PriceRunner case ids and
copies `fixtures/matcher-repo` into a workspace to run the stub verifier. Update:

- expected case ids → `["cluster-billiger-python", "cluster-billiger-rust"]`.
- fixture copy source → `fixtures/billiger-matcher-repo`.
- any PriceRunner-specific paths/strings → billiger equivalents.
- the stub-verifier test must still pass (the trivial clusterer produces valid
  output the verifier scores), confirming the swapped hidden labels load.

## Docs

- Pack `README.md`: rewrite for billiger (schema, price/image signals, fixture
  shape, verification, example command). Note PriceRunner as the title-only
  predecessor.
- `docs/benchmarks/product-offer-matching/index.md`: update "current
  implementation" / Dataset / Pack Shape / Program Interface sections to billiger;
  keep the dataset-sourcing-analysis and D-034/D-035/D-036 references.
- Reconcile any methodology references that name the PriceRunner fixture as
  current.
- Add a decision record noting the replacement (PriceRunner → billiger as the
  live pack).

## Out of scope

- D-036 amplified scale-set system-metric lane (system metrics run on the real
  ~21.8k test set for now).
- Warm-start (catalog-linkage) lane.
- Pass-threshold recalibration (kept at B-cubed ≥ 0.70, pairwise ≥ 0.20 for the
  MVP; a title-only baseline cannot pass, which is intended — multi-signal
  matching is required).

## Verification

- `uv run pytest tests/test_product_offer_matching_pack.py
  tests/test_build_fixture_from_billiger.py` passes.
- Regenerating the fixture from the repo root (`uv run python
  benchpacks/product-offer-matching/scripts/build-fixture-from-billiger.py`)
  writes the pack layout and the build report reconciles. All `main()` defaults
  are repo-root-relative, so the canonical cwd is the repository root.
- A dry run of the verifier against the trivial stub in a copied workspace
  produces a valid metrics JSON (singleton clustering scores low but is valid),
  confirming hidden labels load and the contract holds end to end.
