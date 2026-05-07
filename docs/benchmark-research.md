# Benchmark Research Backlog

Status date: 2026-05-07.

This is a research backlog, not an implemented benchmark contract. It records
candidate directions for stronger coding-agent benchmarks after live evidence
showed that the public external-agent path works mechanically but copied
fenced-diff task prompts were the wrong benchmark surface for direct
workspace-editing agents. The first direct-edit prompt slice for the existing
external-agent coding-task packs has now landed; real-agent validation remains
the next evidence step.

No live benchmarks were run for this note. No datasets were downloaded. No
generated `results/*`, metadata, raw payloads, workspaces, task logs, model-call
logs, or secrets should be committed for this research track.

## Current Evidence Boundary

- Gemma 4 strict same-GGUF evidence is complete enough for the selected
  `google_gemma-4-E2B-it-Q4_K_M.gguf` artifact and current four-pack lane
  across M5, M4, and Hetzner. That does not make the tiny repo-task pack broad
  coding-agent evidence.
- The public `external-agent` path is mechanically validated for the current
  M5 Codex OSS/Ollama slice: adapter calls, tmux environment injection,
  metadata, external subprocess routing, and model-call telemetry worked.
- The external-agent verifiers failed because the reused fenced-diff prompts
  caused Codex to emit unified diffs to stdout instead of editing the prepared
  workspace. Captured workspace diffs were empty.
- The external-agent coding-task packs now have direct-edit prompts that ask
  the agent to edit the prepared workspace directly while preserving existing
  verifier semantics.
- The next useful work is local real-agent validation of that direct-edit slice.
  More broad M4/M5/Hetzner live rows should wait until the benchmark surface
  produces meaningful deterministic task outcomes.

## Next Work Ordering

1. Keep this research backlog and implementation plan current.
2. Validate the direct-edit slice locally on M5 with a real external agent.
3. Broaden to M4/M5/NVIDIA comparison only after the direct-edit benchmark
   surface produces meaningful deterministic task outcomes.

## Candidate Benchmark Tracks

### Project-Level Coding Tasks

[ProjDevBench](https://arxiv.org/html/2602.01655v2) is the main design
reference. It evaluates agents on end-to-end repository construction from
project-level requirements, expects complete executable repositories, and uses
execution-based scoring with diagnostic verdicts such as wrong answer, compile
error, runtime error, time limit exceeded, and memory limit exceeded. Its
[repository](https://github.com/zsworld6/projdevbench) also exposes a concrete
platform shape with containerized execution, multi-agent support, execution
score analysis, code-review score analysis, and combined score analysis.

Backlog item: prototype a small project-construction or project-completion pack
for this repo that keeps deterministic execution scoring first. Optional review
or compliance checks may be researched later, but they must be explicitly
separate from deterministic scoring and should not become an implicit
LLM-as-judge default.

### Direct-Edit External-Agent Tasks

Backlog item: the first slice has landed by updating the existing
external-agent-specific variants of the bundled repo-task fixtures so their
prompts tell the agent to edit files in the prepared workspace and stop, not to
produce a fenced patch. Keep the existing fenced-patch packs as
compatibility/default evidence and do not promote the direct-edit slice into
the default matrix until it has local M5 evidence.

Design questions:

- Should direct-edit variants reuse the same verifiers first, or introduce a
  slightly larger fixture where direct editing is materially different from a
  patch-output task?
- Should task stdout be expected to contain a short summary only, or should
  agents be allowed to leave it arbitrary while scoring only workspace state?
- Do current task logs and `repo_task.status` give enough failure signal, or is
  a later richer task-status row field justified by live evidence?

### Product Classification And Matching Programs

Candidate data leads:

- [WDC Product Data Corpus and Gold Standard for Large-Scale Product Matching](https://webdatacommons.org/largescaleproductcorpus/v2/index.html):
  public product matching corpus and gold standard with 26 million offers,
  16 million clusters, and 4,400 manually verified offer pairs, plus
  pre-assembled training and validation sets. License, fixture size, and
  offline reproducibility need validation before implementation.
- [WDC Products](https://webdatacommons.org/largescaleproductcorpus/wdc-products/index.html):
  multi-dimensional entity-matching benchmark with pair-wise and multi-class
  formulations, train/validation/test variants, product attributes such as
  brand/title/description/price/currency, and reported F1 or micro-F1 metrics.
  This is a strong candidate for coding-agent-written matcher pipelines.
- [WDC-24 Gold Standard for Product Categorization](https://webdatacommons.org/largescaleproductcorpus/wdc-products/categorization/):
  product categorization lead with over 17,000 manually labeled offers across
  24 non-hierarchical categories and published train/validation/test downloads.
  It supports deterministic classification metrics such as micro-F1 and
  macro-F1, but its schema is not hierarchical.
- [Shopify product-catalogue](https://huggingface.co/datasets/Shopify/product-catalogue):
  Apache-2.0 Hugging Face dataset with product title, description, image,
  candidate categories, brand, secondhand flag, and ground-truth category. The
  category strings are hierarchical, making it a candidate for hierarchical F1
  or path-aware scoring after split and fixture design are validated.
- [Kaggle Product Classification and Clustering](https://www.kaggle.com/datasets/pooriamst/product-classification-and-clustering)
  and [Kaggle Product Clustering, Matching & Classification](https://www.kaggle.com/datasets/lakritidis/product-clustering-matching-classification):
  candidate leads only. The current browser path did not expose inspectable
  page content, so access, license, fields, sizes, and splits require manual
  validation before any implementation decision.

Benchmark idea: do not ask the model to classify products directly. Ask a
coding agent to write a program or pipeline under fixed constraints, then run
that program on held-out data and score deterministic metrics such as F1,
weighted F1, macro/micro F1, hierarchical F1 for taxonomy paths, or matching
metrics for pairwise/entity-cluster tasks.

Research questions:

- Which datasets allow a small committed fixture versus an external fetch step?
- What license and attribution terms apply to derived fixtures?
- Can train/test splits be made deterministic and portable without committing
  large corpora?
- Should the benchmark allow training during the run, or require a fixed
  no-network inference-only program over supplied data?
- Which metrics should be primary for each task type: match-class F1,
  micro-F1, macro-F1, weighted F1, hierarchical F1, pairwise precision/recall,
  or cluster-level metrics?

### Resource-Aware Program Scoring

Backlog item: design resource-aware scoring before changing result schemas.
Candidate fields and verdicts include wall-clock runtime, peak process memory,
peak GPU memory when observable, deterministic timeout, deterministic memory
limit exceeded, and possibly compile/runtime error classes for agent-written
programs.

Design questions:

- Should runtime and memory be reported as separate metrics only, or combined
  into an explicit weighted score?
- Should per-task resource limits be pack-local manifest fields, verifier
  fields, or runner-level execution policy?
- How should resource use from an agent-written training phase be separated
  from scoring/inference resource use?
- When GPU memory is unavailable or not relevant, should score aggregation
  ignore it or mark a resource dimension as missing?
