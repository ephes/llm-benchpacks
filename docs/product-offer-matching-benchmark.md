# Product Offer Matching Program Benchmark

Status: initial implementation landed in `benchpacks/product-offer-matching/`
with Python and Rust direct-edit external-agent cases. Live GPT-5.5 versus
Qwen3.6 Pi benchmark results are tracked separately in `docs/run-log.md`.

This document specifies an opt-in benchmark direction for evaluating coding
agents on product-offer matching. The central trick is deliberate: the model is
not asked to label products directly. It must write normal deterministic code
that uses labeled examples to infer matching rules, then the runner scores that
program on hidden real-data examples with deterministic metrics such as F1.

## Goal

Measure whether a model/runtime/agent combination can produce useful matching
software for messy e-commerce offer data.

The benchmark should answer:

- Can the model inspect a real dataset schema and write a runnable matcher?
- Can it learn useful normalization and matching rules from labeled examples
  without using a heavyweight ML dependency or an external service?
- Does the generated code generalize to held-out product offers instead of only
  satisfying visible tests?
- What precision/recall/F1 does the generated matcher achieve, and how long
  does it take to run?

This is a coding-agent benchmark, not a direct product-classification prompt and
not an LLM-as-judge benchmark.

## Non-Goals

- Do not ask the benchmarked model to directly answer every match decision in
  chat output.
- Do not start from an invented synthetic schema. Version 1 hidden scoring rows
  must be real-derived. Synthetic rows are permitted only after a real dataset
  has been inspected, and only for verifier/unit-test coverage or prompt
  examples that preserve the observed real schema.
- Do not depend on network access during a benchmark run.
- Do not require a full machine-learning stack for the first version. The first
  Python lane should run with the standard library, and the first Rust lane
  should compile with `rustc` using only the standard library unless a later
  design explicitly adds a Cargo/dependency lane.
- Do not make this part of the default benchmark matrix until real runs show it
  adds stable signal.

## Dataset Posture

Use a real dataset first. The first implementation should inspect and derive its
fixture shape from an actual public product matching/clustering dataset before
writing prompts, schemas, or verifiers.

The current preferred first inspection pass should compare two practical real
sources rather than committing to one before looking at the files:

- **Kaggle product matching/clustering leads**, because the operator has
  indicated that Kaggle license terms are acceptable for this work and a compact
  real-data fixture may be easier to redistribute. Candidate leads include
  `lakritidis/product-clustering-matching-classification` and
  `pooriamst/product-classification-and-clustering`.
- **WDC Products**, because it is a compact entity-matching benchmark rather
  than the much larger WDC Product Data Corpus. The public WDC Products pages
  describe pair-wise and multi-class formulations, train/validation/test
  variants, hard cases, unseen-entity dimensions, product attributes, and
  reported F1/micro-F1 metrics. It should be inspected alongside Kaggle and may
  be the better first source if Kaggle lacks clean matching labels or
  redistributable fixtures.

Separate these from the **WDC Product Data Corpus and Gold Standard for
Large-Scale Product Matching**, which is valuable but much larger and should not
be the default first implementation target unless a small official fold proves
straightforward. WDC categorization resources are also interesting, but they
should become a separate product-categorization benchmark, not be confused with
offer matching.

The initial implementation selected WDC Products 20pair because the public page
documents real-world product entity matching, pairwise train/validation/test
sets, offer-disjoint splitting, and the exact pairwise JSONL fields. The
implemented fixture uses `20pair.zip`, `wdcproducts20cc80rnd000un_train_small`
for visible training rows, and `wdcproducts20cc80rnd000un_gs` for hidden
labels. Raw WDC offer ids and cluster ids are stripped from matcher inputs.

For later fixture revisions or additional lanes, inspect the actual downloaded
files or official fold metadata and record:

- license and attribution requirements;
- file names, encodings, row counts, and column names;
- whether rows represent offers, products, pairs, clusters, or categories;
- the field or combination of fields that gives ground-truth matching signal,
  such as product id, cluster id, duplicate group id, or pair label;
- whether price, currency, brand, merchant, title, description, category, image,
  URL, source-site, or other identifier fields exist;
- whether redistribution of a small derived fixture is allowed, or whether the
  repo must ship only a fixture builder plus checksums.

## Task Formulation

Prefer pairwise offer matching for the first pack because it has a simple,
deterministic scoring surface.

Input to the generated program:

- labeled training examples;
- unlabeled prediction examples;
- a documented command-line interface.

Output from the generated program:

- one row per prediction example;
- stable id plus binary label: `1` for same underlying product, `0` otherwise.

If the real source dataset already contains labeled offer pairs, preserve that
shape where practical. If it contains offer rows with product or cluster ids,
derive pairwise examples from those ids:

- positive pair: two offers with the same product/cluster id;
- negative pair: two offers from different product/cluster ids, preferably
  sampled from similar categories or brands so negatives are not trivial.

A future lane can evaluate full offer-to-product assignment or clustering, but
pairwise matching should come first because positive-class F1 is easy to
understand and implement in a verifier.

## Pack Shape

Initial pack id:

```text
product-offer-matching
```

Implemented case ids:

```text
pairwise-real-small-python
pairwise-real-small-rust
```

Initial case kind:

```text
repo-task
```

Expected pack layout:

```text
benchpacks/product-offer-matching/
  benchpack.toml
  README.md
  prompts/
    pairwise-real-small-python.md
    pairwise-real-small-rust.md
  fixtures/
    matcher-repo/
      README.md
      matcher.py
      matcher.rs
      data/
        train.csv
        dev.csv                 # optional, visible validation split
        test_pairs.csv          # hidden labels are not included here
  verify/
    score_pairwise.py
    hidden_labels.csv           # verifier-owned, not copied to workspace
  scripts/
    build-fixture-from-kaggle.py # optional, if raw data is not committed
```

Implemented manifest shape:

```toml
[pack]
id = "product-offer-matching"
version = "0.1.0"
description = "Coding-agent task: write a real-data product offer matcher scored by F1"

[defaults]
temperature = 0
max_tokens = 4096
stream = false
warmup = 0
repetitions = 1

[[cases]]
id = "pairwise-real-small-python"
kind = "repo-task"
prompt_file = "prompts/pairwise-real-small-python.md"
fixture_refs = ["matcher-repo"]
harness = { id = "external-agent", timeout_s = 1200 }
scoring = { mode = "verify-script", script = "verify/score_pairwise.py", timeout_s = 30 }

[[cases]]
id = "pairwise-real-small-rust"
kind = "repo-task"
prompt_file = "prompts/pairwise-real-small-rust.md"
fixture_refs = ["matcher-repo"]
harness = { id = "external-agent", timeout_s = 1200 }
scoring = { mode = "verify-script", script = "verify/score_pairwise.py", timeout_s = 30 }

[[fixtures]]
id = "matcher-repo"
kind = "repo"
path = "fixtures/matcher-repo"
description = "Small real-data product offer matching repository fixture"
```

This pack is the direct-edit external-agent lane used for Pi-hosted agent
comparisons, including GPT-5.5 versus Qwen3.6, so both models edit the same
prepared workspace fixture and are judged by the same deterministic verifier.
If a fenced-patch endpoint-only variant becomes useful, add it as a separate
explicit pack or case rather than changing this lane's direct-edit semantics.

## Fixture-Building Requirements

The fixture builder must be deterministic and must document the source dataset
version. It should take raw downloaded data outside git and write a compact
benchmark fixture.

Implemented first compact real fixture:

- 200 visible training pairs: 50 positive, 75 hard negative, and 75 easy
  negative rows sampled from WDC Products `20cc80rnd000un_train_small`;
- 120 hidden test pairs: 30 positive, 60 hard negative, and 30 easy negative
  rows sampled from WDC Products `20cc80rnd000un_gs`;
- evaluation positive prevalence is `0.25`;
- deterministic seed `20260627`;
- local sequential `pair_id` values that do not expose raw WDC offer ids;
- hidden labels remain verifier-owned in `verify/hidden_labels.csv`.

Recommended properties for future compact real fixtures:

- hundreds to a few thousand training pairs;
- hundreds to a few thousand hidden test pairs;
- evaluation prevalence documented explicitly, so the pack does not pretend a
  deliberately balanced sample has production class prevalence;
- non-trivial negative pairs, sampled from nearby categories/brands/tokens when
  the source data supports that, or from official hard-negative folds when the
  dataset provides them;
- stable random seed;
- no duplicate `pair_id` values;
- no duplicate or reversed duplicate pairs across train/dev/test;
- no hidden labels copied into the workspace fixture;
- raw source files and large generated intermediates ignored by git.

Split policy should be chosen after inspecting the real schema. Version 1 should
prefer an offer-disjoint and, where possible, unseen-entity/group split. If a
seen-group lane is intentionally useful, make it a separate case with a clear
name and do not mix it with the harder unseen lane.

Fixture-builder audits should fail or loudly report:

- train/dev/test overlap by raw offer id, URL, source-site id, product id, or
  cluster id when those identifiers exist;
- duplicate or reversed duplicate pairs;
- `pair_id` values that encode labels, product ids, cluster ids, source row
  offsets, or other leakage-prone information;
- product/cluster/duplicate-group ids accidentally exposed as matcher input
  features;
- suspicious exact normalized-title overlap across splits when the intended
  lane is unseen-entity generalization.

The first implemented case should state which split lane it uses. If both are
useful, make them separate cases rather than mixing semantics.

## Generated Program Contract

The repository fixture should expose small executable stubs for the language
lanes. The Python lane should document an interface similar to:

```sh
python matcher.py \
  --train data/train.csv \
  --predict data/test_pairs.csv \
  --output predictions.csv
```

The Rust lane should document an equivalent interface, for example:

```sh
rustc matcher.rs -O -o matcher-rust
./matcher-rust \
  --train data/train.csv \
  --predict data/test_pairs.csv \
  --output predictions.csv
```

The generated program must:

- read the visible training data;
- read unlabeled prediction pairs;
- write exactly one prediction for every `pair_id`;
- output only allowed labels, normally `0` or `1`;
- use deterministic behavior unless a fixed seed is documented;
- avoid network access and external services;
- avoid hardcoding prediction ids or labels;
- complete within the verifier timeout.

For the endpoint/fenced-patch lane, remember that the model sees the prompt and
adapter output, not an interactive file browser. The prompt should therefore
include the allowed edit path, the CLI contract, the CSV schemas, the current
`matcher.py` stub, and a small sample of train/predict rows, and it must request
the current fenced unified-diff or replacement-file output contract rather than
direct workspace edits. The generated program should still read the full
`train.csv` at runtime and tune rules from that visible data; the prompt sample
is only for schema comprehension.

For the external-agent lane, the agent can inspect the prepared workspace when
its harness allows that, but it remains a separate explicit benchmark lane.

For the first Python lane, allow only the standard library. For the first Rust
lane, prefer a single `matcher.rs` that compiles with `rustc` alone; use a
Cargo fixture only if the chosen source data or parser contract makes that
necessary. Both lanes should encourage normal matching software: text
normalization, tokenization, brand/model-number extraction, title similarity,
description overlap, price/currency handling, category-aware thresholds, and
simple threshold tuning over visible training or dev data.

## Scoring

Primary metric:

```text
positive-class F1 for label = 1
```

Secondary metrics:

- precision for label `1`;
- recall for label `1`;
- accuracy;
- macro F1 when useful;
- confusion matrix counts: true positives, false positives, true negatives,
  false negatives;
- verifier/runtime seconds;
- output-contract errors.

Initial `verify-script` scoring can remain pass/fail for runner compatibility.
The verifier should write F1, precision, recall, confusion counts, prevalence,
thresholds, and diagnostic status into the runner-provided verifier JSON
artifact. Stdout can remain human-readable diagnostics. A later runner slice may
promote numeric verifier metrics into `run.jsonl` and report tables once this
benchmark has live evidence.

The first pass threshold should be chosen only after a trivial baseline is run
on the real fixture. Suggested policy:

- compute naive baselines such as always-negative, always-positive, normalized
  exact title match, and token Jaccard;
- report test-set positive prevalence and any artificial sampling ratio;
- set the pass threshold above the strongest trivial baseline by a meaningful
  margin;
- document the baseline scores in the pack README;
- never set the threshold so low that always-negative or exact-title-only code
  passes.

Example verifier summary shape:

```json
{
  "schema_version": 1,
  "case_id": "pairwise-real-small-python",
  "passed": true,
  "exit_code": 0,
  "metrics": {
    "f1": 0.812,
    "precision": 0.790,
    "recall": 0.835,
    "accuracy": 0.902,
    "tp": 167,
    "fp": 44,
    "tn": 735,
    "fn": 33,
    "positive_prevalence": 0.20
  },
  "thresholds": {
    "f1_min": 0.70
  }
}
```

## Hidden-Data And Anti-Leakage Rules

Hidden labels must be verifier-owned and must not be copied into the prepared
workspace. The default fenced-patch harness only sends the model the prompt and
workspace-relevant context, so the hidden verifier files are not part of the
normal task input.

External-agent runs need extra care because an unrestricted local agent may be
able to read files outside the prepared workspace. Benchmark-grade external
runs should either use a read-restricted harness or be documented as weaker
anti-cheat evidence. Do not place hidden labels in the workspace fixture.

The prompt and fixture should explicitly prohibit:

- reading verifier files;
- using network access;
- hardcoding test `pair_id` values;
- writing predictions by exploiting fixture order rather than feature data;
- modifying data files instead of implementing matcher logic.

The verifier should fail on missing predictions, duplicate predictions, unknown
ids, invalid labels, extra rows, malformed CSV, non-zero subprocess exit, or
runtime timeout.

## Dataset Inspection Checklist

Before implementing the pack, run a short research pass and record the answer in
the pack README or a follow-up docs note:

1. Which dataset was selected, with URL, version/date, and license?
2. Is redistribution of a compact derived fixture allowed?
3. What are the exact raw file names and columns?
4. Which column or relation is the ground truth matching signal?
5. Is the task naturally pairwise, clustered, categorical, or mixed?
6. What fields should be exposed to the generated matcher, and which identifier
   fields must be stripped to avoid leakage?
7. How are train/dev/test pairs sampled?
8. Is the split offer-disjoint, seen-group, unseen-group, or based on an
   official dataset fold?
9. What class prevalence and trivial baseline scores were measured?
10. What F1 threshold makes sense for a pass/fail `verify-script` result?

## Implementation Slices

1. **Dataset inspection only**
   - Download candidate Kaggle data outside git and inspect WDC Products fold
     metadata/source files.
   - Inspect schema, license, size, labels, splits, and task fit.
   - Decide whether the first pack uses official pair labels directly or
     derives pairs from product/cluster ids.

2. **Fixture builder**
   - Add a deterministic builder if raw data cannot be committed directly.
   - Generate compact real-data train/test files and hidden labels.
   - Record source attribution and checksums.

3. **Repo-task pack**
   - Add `product-offer-matching` as an opt-in `repo-task` pack.
   - Add Python and Rust prompts, fixture repository, verifier, and README.
   - Keep standard-library Python and stdlib-only Rust as the first
     implementation languages.

4. **Baseline and calibration**
   - Run naive baselines against the fixture.
   - Set or adjust the pass threshold.
   - Document baseline metrics and known failure modes.

5. **Live benchmark validation**
   - Run the Python and Rust cases against GPT-5.5 and Qwen3.6 through the Pi
     external-agent harness.
   - Review captured patches, verifier JSON, and summary output.
   - Ask Pi to judge whether the benchmark goal has been reached and to compare
     GPT-5.5 with Qwen3.6 using the deterministic verifier output as the
     authority.
   - Keep generated results out of git unless explicitly curated.

6. **Reporting follow-up, if useful**
   - If live evidence shows that numeric F1 is valuable in comparisons, add a
     narrow result/reporting extension for verifier-emitted metrics rather than
     overloading the current pass/fail field.

## Open Questions

- Which inspected source, Kaggle or WDC Products, has the cleanest
  offer-to-product or offer-pair matching signal and redistribution story?
- Can a compact derived real-data fixture be committed, or must users build it
  locally from authenticated downloads?
- Should the first lane be offer-disjoint unseen-group only, or should a
  separate seen-group lane also exist?
- Is standard-library-only Python sufficient to produce a useful spread between
  weak and strong models, or should a later lane allow small dependencies such
  as rapidfuzz or scikit-learn?
- Should full clustering or offer-to-product assignment become a second pack
  after pairwise F1 is validated?
