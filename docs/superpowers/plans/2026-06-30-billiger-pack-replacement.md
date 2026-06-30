# Billiger Pack Replacement Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Replace the PriceRunner fixture/cases/prompts/hidden-labels with the billiger lane so `product-offer-matching` becomes the runnable price+image benchmark, reusing the verifier unchanged.

**Architecture:** Rewire the builder to emit the pack layout (public → fixture-repo `data/`, hidden → pack `verify/`), generate the billiger fixture there, ship trivial schema-agnostic clusterer stubs, swap cases/prompts/docs, and update the pack test. The 663-line verifier (`score_clusters.py`) is reused with no logic change — only data and hidden labels differ.

**Tech Stack:** Python 3.11 stdlib, `uv`/`pytest`, TOML pack manifest, Rust stub (compiled by the verifier with `rustc`).

Spec: `docs/superpowers/specs/2026-06-30-billiger-pack-replacement-design.md`.

---

## File Structure

- Modify: `benchpacks/product-offer-matching/scripts/build-fixture-from-billiger.py` (two-root output)
- Modify: `tests/test_build_fixture_from_billiger.py` (two-root build tests)
- Create: `benchpacks/product-offer-matching/fixtures/billiger-matcher-repo/{clusterer.py,clusterer.rs,README.md}` + generated `data/*.csv` + `build-report.json`
- Modify (generated): `benchpacks/product-offer-matching/verify/hidden_test_clusters.csv`, `hidden_eval_pair_labels.csv`
- Create: `benchpacks/product-offer-matching/prompts/cluster-billiger-{python,rust}.md`
- Modify: `benchpacks/product-offer-matching/benchpack.toml`
- Modify: `tests/test_product_offer_matching_pack.py`
- Modify: `benchpacks/product-offer-matching/README.md`, `docs/benchmarks/product-offer-matching/index.md`, `docs/decisions.md`
- Delete: `prompts/cluster-pricerunner-{python,rust}.md`, `fixtures/matcher-repo/`, `fixtures/billiger/`

---

## Task 1: Rewire the builder to a two-root output

**Files:**
- Modify: `benchpacks/product-offer-matching/scripts/build-fixture-from-billiger.py`
- Modify: `tests/test_build_fixture_from_billiger.py`

- [ ] **Step 1: Update the two build integration tests** (replace the existing `test_build_writes_all_outputs_with_anti_leakage` and `test_build_is_deterministic` in `tests/test_build_fixture_from_billiger.py` with these):

```python
def test_build_writes_all_outputs_with_anti_leakage(tmp_path):
    mod = load_builder()
    raw = tmp_path / "raw.csv"
    fields = ["offer_id", "title", "shop_name", "price_eur", "brand", "category_label",
              "image_url", "cluster_id", "cluster_label", "source_query"]
    write_csv(raw, _synthetic_raw(), fields)
    data_dir = tmp_path / "fixture" / "data"
    verify_dir = tmp_path / "verify"

    mod.build(raw, data_dir, verify_dir, train_fraction=0.30, n_pos=20, n_hard_neg=20,
              n_easy_neg=10, seed=1)

    train = mod.read_offers(data_dir / "train_offers.csv")
    test = mod.read_offers(data_dir / "test_offers.csv")
    hidden = mod.read_offers(verify_dir / "hidden_test_clusters.csv")
    pair_labels = mod.read_offers(verify_dir / "hidden_eval_pair_labels.csv")
    report = json.loads((data_dir.parent / "build-report.json").read_text())

    assert "cluster_id" not in test[0] and "cluster_label" not in test[0]
    assert set(train[0]) == {"offer_id", "title", "shop_name", "price_eur", "brand",
                             "category_label", "image_url", "cluster_id", "cluster_label"}
    assert {r["offer_id"] for r in hidden} == {r["offer_id"] for r in test}
    assert {r["cluster_id"] for r in train}.isdisjoint({r["cluster_id"] for r in hidden})
    pairs = mod.read_offers(data_dir / "eval_pairs.csv")
    assert {p["pair_id"] for p in pairs} == {p["pair_id"] for p in pair_labels}
    assert report["kept_offers"] <= report["input_offers"]


def test_build_is_deterministic(tmp_path):
    mod = load_builder()
    raw = tmp_path / "raw.csv"
    fields = ["offer_id", "title", "shop_name", "price_eur", "brand", "category_label",
              "image_url", "cluster_id", "cluster_label", "source_query"]
    write_csv(raw, _synthetic_raw(), fields)
    mod.build(raw, tmp_path / "a" / "data", tmp_path / "a" / "verify", 0.30, 20, 20, 10, seed=1)
    mod.build(raw, tmp_path / "b" / "data", tmp_path / "b" / "verify", 0.30, 20, 20, 10, seed=1)
    assert (tmp_path / "a" / "data" / "train_offers.csv").read_text() == \
           (tmp_path / "b" / "data" / "train_offers.csv").read_text()
    assert (tmp_path / "a" / "data" / "eval_pairs.csv").read_text() == \
           (tmp_path / "b" / "data" / "eval_pairs.csv").read_text()
```

- [ ] **Step 2: Run the tests to verify they fail**

Run: `uv run pytest tests/test_build_fixture_from_billiger.py -k build -q`
Expected: FAIL (the current `build()` takes a single `out_dir`, so the 3-positional-arg call raises `TypeError`).

- [ ] **Step 3: Replace `build()` and `main()`** in `build-fixture-from-billiger.py` with these (leave `TRAIN_FIELDS`, `TEST_FIELDS`, `write_fixture_csv`, and all earlier functions unchanged):

```python
def build(in_path: Path, data_dir: Path, verify_dir: Path, train_fraction: float,
          n_pos: int, n_hard_neg: int, n_easy_neg: int, seed: int = SEED) -> dict:
    rng = random.Random(seed)
    raw = read_offers(in_path)
    kept, report = clean_offers(raw)

    train_clusters, test_clusters = choose_split(kept, train_fraction, rng)
    train_src = [r for r in kept if r["cluster_id"] in train_clusters]
    test_src = [r for r in kept if r["cluster_id"] in test_clusters]

    # Train and test share one global id namespace so their offer/cluster ids never
    # collide (test ids start above train's), keeping the splits unambiguously disjoint.
    train = anonymize(train_src, rng)
    train_cluster_count = len({r["cluster_id"] for r in train})
    test = anonymize(test_src, rng, offer_start=len(train), cluster_start=train_cluster_count)

    pair_rows, label_rows = sample_eval_pairs(test, n_pos, n_hard_neg, n_easy_neg, rng)

    write_fixture_csv(data_dir / "train_offers.csv", train, TRAIN_FIELDS)
    write_fixture_csv(data_dir / "test_offers.csv", test, TEST_FIELDS)
    write_fixture_csv(data_dir / "eval_pairs.csv", pair_rows,
                      ["pair_id", "offer_id_left", "offer_id_right"])
    write_fixture_csv(verify_dir / "hidden_test_clusters.csv",
                      [{"offer_id": r["offer_id"], "cluster_id": r["cluster_id"]} for r in test],
                      ["offer_id", "cluster_id"])
    write_fixture_csv(verify_dir / "hidden_eval_pair_labels.csv", label_rows,
                      ["pair_id", "label"])

    report.update({
        "train_offers": len(train), "test_offers": len(test),
        "train_clusters": len(train_clusters), "test_clusters": len(test_clusters),
        "eval_pairs": len(pair_rows),
        "eval_pos": sum(1 for r in label_rows if r["label"] == "1"),
        "eval_neg": sum(1 for r in label_rows if r["label"] == "0"),
        "seed": seed, "train_fraction": train_fraction,
    })
    data_dir.parent.mkdir(parents=True, exist_ok=True)
    (data_dir.parent / "build-report.json").write_text(json.dumps(report, indent=2) + "\n",
                                                       encoding="utf-8")
    return report


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--in", dest="in_path", type=Path,
                    default=Path("benchpacks/product-offer-matching/pilot-data/billiger-pilot-offers.csv"))
    ap.add_argument("--data-dir", type=Path,
                    default=Path("benchpacks/product-offer-matching/fixtures/billiger-matcher-repo/data"))
    ap.add_argument("--verify-dir", type=Path,
                    default=Path("benchpacks/product-offer-matching/verify"))
    ap.add_argument("--train-fraction", type=float, default=0.30)
    ap.add_argument("--pos", type=int, default=5000)
    ap.add_argument("--hard-neg", type=int, default=9000)
    ap.add_argument("--easy-neg", type=int, default=6000)
    ap.add_argument("--seed", type=int, default=SEED)
    args = ap.parse_args()
    report = build(args.in_path, args.data_dir, args.verify_dir, args.train_fraction,
                   args.pos, args.hard_neg, args.easy_neg, args.seed)
    print(json.dumps(report, indent=2))
    return 0
```

- [ ] **Step 4: Run the tests to verify they pass**

Run: `uv run pytest tests/test_build_fixture_from_billiger.py -q`
Expected: PASS (13 tests).

- [ ] **Step 5: Commit**

```bash
git add benchpacks/product-offer-matching/scripts/build-fixture-from-billiger.py tests/test_build_fixture_from_billiger.py
git commit -m "Rewire billiger fixture builder to two-root pack output"
```

---

## Task 2: Build the fixture repo and generate the billiger fixture into the pack

**Files:**
- Create: `benchpacks/product-offer-matching/fixtures/billiger-matcher-repo/{clusterer.py,clusterer.rs,README.md}`
- Create (generated): `.../billiger-matcher-repo/data/{train_offers,test_offers,eval_pairs}.csv`, `.../billiger-matcher-repo/build-report.json`, `verify/hidden_{test_clusters,eval_pair_labels}.csv`
- Delete: `benchpacks/product-offer-matching/fixtures/billiger/`

- [ ] **Step 1: Create the fixture-repo skeleton (copy the schema-agnostic stubs, write the README)**

```bash
cd /Users/jochen/projects/llm-benchpacks
mkdir -p benchpacks/product-offer-matching/fixtures/billiger-matcher-repo
cp benchpacks/product-offer-matching/fixtures/matcher-repo/clusterer.py \
   benchpacks/product-offer-matching/fixtures/matcher-repo/clusterer.rs \
   benchpacks/product-offer-matching/fixtures/billiger-matcher-repo/
```

Then create `benchpacks/product-offer-matching/fixtures/billiger-matcher-repo/README.md`:

```markdown
# billiger-matcher-repo

Direct-edit fixture for the `product-offer-matching` benchmark. The measured
agent edits one clusterer implementation (`clusterer.py` or `clusterer.rs`); the
verifier runs it against hidden billiger.de product clusters.

The shipped clusterer is a trivial baseline (each offer in its own cluster, every
eval pair scored 0.0). Replace it with a real product matcher.

## Data (`data/`)

- `train_offers.csv` — visible labeled offers:
  `offer_id,title,shop_name,price_eur,brand,category_label,image_url,cluster_id,cluster_label`
- `test_offers.csv` — unlabeled offers to cluster (same columns minus
  `cluster_id,cluster_label`).
- `eval_pairs.csv` — `pair_id,offer_id_left,offer_id_right`.

Offers with the same `cluster_id` are the same real product. Data is derived from
billiger.de; `category_label` is an aggregator classifier output (a feature, not
ground truth), and no structured GTIN/EAN is present. Training and test products
are disjoint.
```

- [ ] **Step 2: Generate the fixture into the pack layout**

Run (from repo root):
```bash
uv run python benchpacks/product-offer-matching/scripts/build-fixture-from-billiger.py
```
Expected: prints the build report; writes `fixtures/billiger-matcher-repo/data/*.csv`, `fixtures/billiger-matcher-repo/build-report.json`, and `verify/hidden_{test_clusters,eval_pair_labels}.csv`.

- [ ] **Step 3: Sanity-check and remove the obsolete standalone output**

```bash
python3 - <<'PY'
import csv, json
base="benchpacks/product-offer-matching/"
def n(f): return sum(1 for _ in open(base+f))-1
rep=json.load(open(base+"fixtures/billiger-matcher-repo/build-report.json"))
print("test_offers", rep["test_offers"], "eval_pairs", rep["eval_pairs"],
      "eval_pos", rep["eval_pos"])
assert n("fixtures/billiger-matcher-repo/data/test_offers.csv") == rep["test_offers"]
assert n("verify/hidden_test_clusters.csv") == rep["test_offers"]
assert n("fixtures/billiger-matcher-repo/data/eval_pairs.csv") == n("verify/hidden_eval_pair_labels.csv") == 20000
hdr=open(base+"fixtures/billiger-matcher-repo/data/test_offers.csv").readline().strip()
assert "cluster_id" not in hdr and "cluster_label" not in hdr, hdr
print("OK; test_offers count =", rep["test_offers"])
PY
rm -rf benchpacks/product-offer-matching/fixtures/billiger
```
Note the printed `test_offers` value — Task 4 hardcodes it in the pack test (it is 21825 with the committed scrape + seed 20260630, but use the value printed here).

- [ ] **Step 4: Commit**

```bash
git add benchpacks/product-offer-matching/fixtures/billiger-matcher-repo \
        benchpacks/product-offer-matching/verify/hidden_test_clusters.csv \
        benchpacks/product-offer-matching/verify/hidden_eval_pair_labels.csv
git rm -r --cached benchpacks/product-offer-matching/fixtures/billiger 2>/dev/null || true
git add -A benchpacks/product-offer-matching/fixtures
git commit -m "Generate billiger fixture into the pack layout"
```

---

## Task 3: Write the billiger prompts; remove the PriceRunner prompts

**Files:**
- Create: `benchpacks/product-offer-matching/prompts/cluster-billiger-python.md`
- Create: `benchpacks/product-offer-matching/prompts/cluster-billiger-rust.md`
- Delete: `benchpacks/product-offer-matching/prompts/cluster-pricerunner-python.md`, `cluster-pricerunner-rust.md`

- [ ] **Step 1: Create `cluster-billiger-python.md`** with exactly this content:

```markdown
You are running inside the prepared repository workspace for this benchmark
case. Implement the Python product-offer clusterer by editing the workspace file
directly.

Allowed repo-root path to edit:

- `clusterer.py`

Do not edit data files, README files, verifier files, prompts, generated
artifacts, or the Rust clusterer.

Task:

Write a deterministic product-offer clustering program. Read visible labeled
training offers from `data/train_offers.csv`, read unlabeled prediction offers
from `data/test_offers.csv`, and write `clusters.csv` with exactly one
`offer_id,cluster_id` row for every prediction offer. Offers with the same output
`cluster_id` are predicted to be the same real product.

Also read `data/eval_pairs.csv` and write `pair_scores.csv` with header
`pair_id,score`, one row for every eval pair, where a higher score means the two
offers are more likely to be the same product. If your implementation tracks
stage timing, candidate-pair counts, or memory counters, you may also write an
optional flat-scalar `metrics.json`.

The offers carry several fields; which of them to use is your decision.

`data/train_offers.csv` columns:

```text
offer_id,title,shop_name,price_eur,brand,category_label,image_url,cluster_id,cluster_label
```

`data/test_offers.csv` columns:

```text
offer_id,title,shop_name,price_eur,brand,category_label,image_url
```

`data/eval_pairs.csv` columns:

```text
pair_id,offer_id_left,offer_id_right
```

The data is derived from billiger.de. `category_label` is an aggregator
classifier output, not ground truth. Training and test true product clusters are
disjoint.

Constraints:

- Use only the Python standard library.
- No network access or external services.
- The program must be deterministic: the same input must produce the same output.
- Do not hardcode test `offer_id`, `pair_id`, labels, or cluster ids. Do not read
  verifier files.

Scale: the hidden test set has roughly 21,800 offers. Your approach must finish
within the time and memory budget; throughput and peak memory are scored.

You will need to decide which offers are worth comparing, how to judge whether
two offers are the same product, and how to group offers into products. The
approach is yours.

Local command the verifier will run:

```sh
python clusterer.py --train data/train_offers.csv --predict data/test_offers.csv --output clusters.csv --pair-input data/eval_pairs.csv --pair-scores pair_scores.csv
```

Verifier contract:

- `clusters.csv` must have header `offer_id,cluster_id`.
- Every `offer_id` from `data/test_offers.csv` must appear exactly once.
- `pair_scores.csv` must have header `pair_id,score` and one finite numeric score
  for every row in `data/eval_pairs.csv`.
- No unknown or duplicate ids are allowed.
- The verifier records B-cubed cluster precision/recall/F1, pairwise cluster
  precision/recall/F1, a full pair-score precision/recall curve, program runtime,
  offers per second, peak RSS, and a combined score.

Edit `clusterer.py` directly and exit when done.
```

- [ ] **Step 2: Create `cluster-billiger-rust.md`** with exactly this content:

```markdown
You are running inside the prepared repository workspace for this benchmark
case. Implement the Rust product-offer clusterer by editing the workspace file
directly.

Allowed repo-root path to edit:

- `clusterer.rs`

Do not edit data files, README files, verifier files, prompts, generated
artifacts, or the Python clusterer.

Task:

Write a deterministic product-offer clustering program. Read visible labeled
training offers from `data/train_offers.csv`, read unlabeled prediction offers
from `data/test_offers.csv`, and write `clusters.csv` with exactly one
`offer_id,cluster_id` row for every prediction offer. Offers with the same output
`cluster_id` are predicted to be the same real product.

Also read `data/eval_pairs.csv` and write `pair_scores.csv` with header
`pair_id,score`, one row for every eval pair, where a higher score means the two
offers are more likely to be the same product. If your implementation tracks
stage timing, candidate-pair counts, or memory counters, you may also write an
optional flat-scalar `metrics.json`.

The offers carry several fields; which of them to use is your decision.

`data/train_offers.csv` columns:

```text
offer_id,title,shop_name,price_eur,brand,category_label,image_url,cluster_id,cluster_label
```

`data/test_offers.csv` columns:

```text
offer_id,title,shop_name,price_eur,brand,category_label,image_url
```

`data/eval_pairs.csv` columns:

```text
pair_id,offer_id_left,offer_id_right
```

The data is derived from billiger.de. `category_label` is an aggregator
classifier output, not ground truth. Training and test true product clusters are
disjoint.

Constraints:

- Use only the Rust standard library and a single `clusterer.rs` file that
  compiles with `rustc`.
- No network access or external services.
- The program must be deterministic: the same input must produce the same output.
- Do not hardcode test `offer_id`, `pair_id`, labels, or cluster ids. Do not read
  verifier files.

Scale: the hidden test set has roughly 21,800 offers. Your approach must finish
within the time and memory budget; throughput and peak memory are scored.

You will need to decide which offers are worth comparing, how to judge whether
two offers are the same product, and how to group offers into products. The
approach is yours.

Local command the verifier will run:

```sh
rustc clusterer.rs -O -o <verifier-temp>/clusterer-rust
<verifier-temp>/clusterer-rust --train data/train_offers.csv --predict data/test_offers.csv --output clusters.csv --pair-input data/eval_pairs.csv --pair-scores pair_scores.csv
```

Verifier contract:

- `clusters.csv` must have header `offer_id,cluster_id`.
- Every `offer_id` from `data/test_offers.csv` must appear exactly once.
- `pair_scores.csv` must have header `pair_id,score` and one finite numeric score
  for every row in `data/eval_pairs.csv`.
- No unknown or duplicate ids are allowed.
- The verifier records B-cubed cluster precision/recall/F1, pairwise cluster
  precision/recall/F1, a full pair-score precision/recall curve, program runtime,
  offers per second, peak RSS, and a combined score.

Edit `clusterer.rs` directly and exit when done.
```

- [ ] **Step 3: Remove the PriceRunner prompts and commit**

```bash
cd /Users/jochen/projects/llm-benchpacks
git rm benchpacks/product-offer-matching/prompts/cluster-pricerunner-python.md \
       benchpacks/product-offer-matching/prompts/cluster-pricerunner-rust.md
git add benchpacks/product-offer-matching/prompts/cluster-billiger-python.md \
        benchpacks/product-offer-matching/prompts/cluster-billiger-rust.md
git commit -m "Add lightly-guided billiger prompts; remove PriceRunner prompts"
```

---

## Task 4: Rewire benchpack.toml, update the pack test, remove the PriceRunner fixture

**Files:**
- Modify: `benchpacks/product-offer-matching/benchpack.toml`
- Modify: `tests/test_product_offer_matching_pack.py`
- Delete: `benchpacks/product-offer-matching/fixtures/matcher-repo/`

- [ ] **Step 1: Update the pack-loading and stub-verifier assertions** in `tests/test_product_offer_matching_pack.py`:

In `test_product_offer_matching_pack_loads_with_external_agent_cases`, change the case-id list to:
```python
    assert [case.id for case in pack.cases] == [
        "cluster-billiger-python",
        "cluster-billiger-rust",
    ]
```

In `test_product_offer_python_stub_verifier_writes_cluster_metrics`, change the copytree source, the `--case`, and the `--source-fixture-id`, and the two count assertions:
```python
    shutil.copytree(PACK_DIR / "fixtures" / "billiger-matcher-repo", workspace)
```
```python
            "--case",
            "cluster-billiger-python",
```
```python
            "--source-fixture-id",
            "billiger-matcher-repo",
```
```python
    assert payload["system_metrics"]["test_offers"] == 21825
    assert payload["system_metrics"]["eval_pairs"] == 20000
```
(Use the `test_offers` value printed in Task 2 Step 3 if it differs from 21825.)

In `test_product_offer_hidden_clusters_are_not_public_order_contiguous`, change the length assertion:
```python
    assert len(cluster_ids) == 21825
```

In `test_pi_agent_previews_pricerunner_cluster_data_files`, rename it to
`test_pi_agent_previews_billiger_cluster_data_files` and replace the two synthetic
CSV headers/rows with the billiger schema:
```python
    (data / "train_offers.csv").write_text(
        "offer_id,title,shop_name,price_eur,brand,category_label,image_url,cluster_id,cluster_label\n"
        "o00001,alpha,shopA,100.00,BrandA,Phones,http://img,c00001,Alpha\n"
        "o00002,beta,shopB,110.00,BrandB,Phones,http://img,c00002,Beta\n",
        encoding="utf-8",
    )
    (data / "test_offers.csv").write_text(
        "offer_id,title,shop_name,price_eur,brand,category_label,image_url\n"
        "o00003,gamma,shopC,120.00,BrandC,Phones,http://img\n",
        encoding="utf-8",
    )
```

- [ ] **Step 2: Run the pack test to verify it fails**

Run: `uv run pytest tests/test_product_offer_matching_pack.py -q`
Expected: FAIL (pack still declares pricerunner cases / fixture `matcher-repo`).

- [ ] **Step 3: Rewire `benchpack.toml`** — replace the `[[fixtures]]` and both `[[cases]]` blocks (and the `[pack]` description) so the file reads:

```toml
[pack]
id = "product-offer-matching"
version = "0.1.0"
description = "Direct-edit coding-agent benchmark for billiger.de product-offer clustering in Python and Rust"

[defaults]
temperature = 0
max_tokens = 64
stream = false
warmup = 0
repetitions = 1

[[fixtures]]
id = "billiger-matcher-repo"
kind = "repo"
path = "fixtures/billiger-matcher-repo"
description = "billiger.de-derived product-offer clustering repo fixture"

[[cases]]
id = "cluster-billiger-python"
kind = "repo-task"
prompt_file = "prompts/cluster-billiger-python.md"
fixture_refs = ["billiger-matcher-repo"]
harness = { id = "external-agent", timeout_s = 3600 }
scoring = { mode = "verify-script", script = "verify/score_clusters.py", timeout_s = 90 }

[[cases]]
id = "cluster-billiger-rust"
kind = "repo-task"
prompt_file = "prompts/cluster-billiger-rust.md"
fixture_refs = ["billiger-matcher-repo"]
harness = { id = "external-agent", timeout_s = 3600 }
scoring = { mode = "verify-script", script = "verify/score_clusters.py", timeout_s = 90 }
```

- [ ] **Step 4: Remove the PriceRunner fixture, run the pack test to verify it passes**

```bash
cd /Users/jochen/projects/llm-benchpacks
git rm -r benchpacks/product-offer-matching/fixtures/matcher-repo
uv run pytest tests/test_product_offer_matching_pack.py -q
```
Expected: PASS (pack loads billiger cases; the stub verifier runs against the billiger fixture and scores it; hidden labels load).

- [ ] **Step 5: Commit**

```bash
git add benchpacks/product-offer-matching/benchpack.toml tests/test_product_offer_matching_pack.py
git add -A benchpacks/product-offer-matching/fixtures
git commit -m "Switch product-offer-matching pack to the billiger cases and fixture"
```

---

## Task 5: Update docs, add the decision record, full-suite verification

**Files:**
- Modify: `benchpacks/product-offer-matching/README.md`
- Modify: `docs/benchmarks/product-offer-matching/index.md`
- Modify: `docs/decisions.md`

- [ ] **Step 1: Update the pack `README.md`** — replace PriceRunner-specific text (dataset name, fixture path `matcher-repo`, the title-only column schema, the example command, the case ids) with billiger equivalents: the billiger schema (incl. `price_eur`, `image_url`, `brand`, `shop_name`), fixture path `fixtures/billiger-matcher-repo`, case ids `cluster-billiger-{python,rust}`, and a note that PriceRunner was the title-only predecessor (D-034). Keep the Verification and combined-score sections (they are unchanged). Read the file first and edit the specific PriceRunner mentions; do not rewrite unrelated sections.

- [ ] **Step 2: Update `docs/benchmarks/product-offer-matching/index.md`** — the `## Dataset`, `## Pack Shape`, `## Program Interface`, and the status line at the top currently describe the PriceRunner fixture as the current implementation. Update them to billiger (fixture `fixtures/billiger-matcher-repo`, billiger schema, case ids `cluster-billiger-{python,rust}`, builder `build-fixture-from-billiger.py`). Keep the existing D-034 limitation note as historical context and the dataset-sourcing-analysis / methodology links. Read the file first; edit only the sections that name the PriceRunner fixture/cases as current.

- [ ] **Step 3: Add a decision record** — append to `docs/decisions.md` (use the next free `D-0NN` number after the current highest):

```markdown
## D-0NN: Billiger Replaces PriceRunner As The Product-Offer-Matching Pack

The runnable `product-offer-matching` pack uses the billiger.de-derived fixture
(`fixtures/billiger-matcher-repo`, cases `cluster-billiger-{python,rust}`) instead
of the title-only PriceRunner fixture. The PriceRunner lane is removed from the
live pack but preserved in git history and under `results/`. The verifier
(`verify/score_clusters.py`) is reused unchanged; only the data, hidden labels,
cases, prompts, and docs differ.

Reason: PriceRunner is text-only (no price or images — D-034), while the benchmark
should test multi-signal product matching. Billiger adds price and image signals
on a harder, denser fixture (decision D-036), so it supersedes PriceRunner as the
primary lane. Prompts are lightly guided so the benchmark measures programming
ability, not entity-resolution recall.
```

- [ ] **Step 4: Full-suite verification**

Run: `uv run pytest tests/test_product_offer_matching_pack.py tests/test_build_fixture_from_billiger.py -q`
Expected: PASS (all). Also confirm no stale references remain:
```bash
grep -rnE "cluster-pricerunner|fixtures/matcher-repo|fixtures/billiger/" benchpacks/product-offer-matching/benchpack.toml tests/test_product_offer_matching_pack.py || echo "no stale references in wiring"
```
Expected: prints "no stale references in wiring".

- [ ] **Step 5: Commit**

```bash
git add benchpacks/product-offer-matching/README.md docs/benchmarks/product-offer-matching/index.md docs/decisions.md
git commit -m "Document billiger as the product-offer-matching pack (D-0NN)"
```

---

## Self-Review Notes (completed)

- **Spec coverage:** builder two-root output (Task 1), fixture repo + generation + standalone removal (Task 2), lightly-guided prompts + PriceRunner-prompt removal (Task 3), benchpack.toml + pack-test update + PriceRunner-fixture removal (Task 4), docs + decision record + verification (Task 5). Verifier logic unchanged (used as-is in Task 4's stub run). Pass thresholds kept (asserted unchanged in the pack test). Hidden labels stay in `verify/` outside the copied fixture (Task 1 builder).
- **Schema-agnostic stubs confirmed:** both `clusterer.py` and `clusterer.rs` locate `offer_id`/`pair_id` by header name, so they run unchanged on the billiger schema.
- **Name/value consistency:** fixture id `billiger-matcher-repo`, cases `cluster-billiger-{python,rust}`, `build(in_path, data_dir, verify_dir, ...)`, `--source-fixture-id billiger-matcher-repo`, and the `test_offers == 21825` assertion (verified against Task 2's printed value) are used identically across tasks.
- **Out of scope (per spec):** D-036 amplifier, warm-start lane, threshold recalibration.
```
