# Benchmark Research Backlog

Status date: 2026-05-09.

This is a research backlog, not an implemented benchmark contract. It records
candidate directions for stronger coding-agent benchmarks after live evidence
showed that the public external-agent path works mechanically but copied
fenced-diff task prompts were the wrong benchmark surface for direct
workspace-editing agents. The first direct-edit prompt slice for the existing
external-agent coding-task packs has now landed and has local M5 real-agent
evidence: two fixtures passed deterministically and one larger dashboard
fixture failed from no workspace mutation.

No datasets were downloaded. Generated `results/*`, metadata, raw payloads,
workspaces, patches, task logs, verify artifacts, model-call logs, or secrets
should not be committed for this research track unless explicitly curated.

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
- The 2026-05-07 local M5 direct-edit validation with Codex OSS through Ollama
  produced meaningful deterministic outcomes: `fix-greeting` and
  `fix-task-summary` passed with non-empty workspace diffs, while
  `fix-dashboard-regressions` failed with an empty diff after Codex emitted a
  plan but made no edits.
- Current task logs plus patch and verifier artifacts were enough to classify
  the dashboard failure, but the aggregate row status alone was not. A compact
  report/status summary for empty-vs-nonempty workspace diffs landed on
  2026-05-08 as report-only repo-task outcome tables in `summary.md` and
  `benchpack report`.
- The `endpoint-python-correctness` pack now provides a simpler endpoint-only
  deterministic correctness lane: normal chat adapter, fenced unified diff or
  explicit path-marked replacement block, tiny committed Python fixture, and
  verifier-only hidden edge checks. The first local M5 Ollama validation
  reached the endpoint with `ok=true` but failed at the `0.1.0` patch contract:
  `qwen3-coder:latest` returned replacement Python content inside a `diff`
  fence, the executor rejected it as having no unified-diff file paths, the
  captured patch was empty, and the verifier failed all visible and hidden
  checks against the unchanged fixture. Version `0.2.0` adds the explicit
  replacement block fallback; this still needs live validation before it counts
  as broad correctness success.
- Broader M4/M5/NVIDIA direct-edit comparison is now reasonable as exploratory
  evidence, provided the pack set stays opt-in and generated artifacts remain
  local/ignored unless curated explicitly.

## Next Work Ordering

1. Keep this research backlog and implementation plan current.
2. Treat `endpoint-python-correctness` helper/default-matrix promotion as
   premature after the first local Ollama apply/format failure. The first
   follow-up has now deliberately added an explicit path-marked replacement
   block fallback and bumped the pack to `0.2.0`; a later live validation
   against an already-available endpoint is still required before any
   helper/default recommendation changes.
3. Broaden to M4/M5/NVIDIA comparison as exploratory direct-edit evidence,
   keeping `coding-tasks-external-agent` opt-in and preserving the current
   artifact policy.
4. Keep the result-schema question open until repeated live evidence shows
   which repo-task status fields are worth making durable.

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

Concrete platform details from the upstream README at the 2026-05-08 review:
20 problems across 8 categories (data structures, management systems,
interpreters, storage systems, algorithms, assembly, game/simulation,
optimization), difficulty ranging from easy partial-codebase tasks to
from-scratch hard tasks, an average of about 138 interaction turns and about
4.81M tokens per problem, and a combined score of
`0.8 * execution + 0.2 * code-review`. That per-problem cost shape is
materially different from the current single-case fenced-patch packs and would
need its own opt-in lane before any default-matrix consideration. The 0.8/0.2
execution/review weighting is informative but is not adopted by this repo:
existing deterministic `verify-script` semantics should not be diluted with
LLM-judged components by default.

Backlog item: prototype a small project-construction or project-completion pack
for this repo that keeps deterministic execution scoring first. Optional review
or compliance checks may be researched later, but they must be explicitly
separate from deterministic scoring and should not become an implicit
LLM-as-judge default.

Design questions:

- Which one or two ProjDevBench-shaped problems are small enough to fit a
  committed fixture and a bounded runner timeout, given the 138-turn /
  4.81M-token per-problem averages?
- Should diagnostic verdicts (TLE, MLE, RE, CE, WA) be lifted into a
  structured `repo_task` field, or remain captured only in `verify-script`
  stdout/stderr as today?
- Container-isolated execution gives reproducibility but adds a Docker
  dependency the runner does not currently require; should a project-level
  pack inherit container isolation, or stay within the existing run-owned
  workspace boundary with stricter resource limits?

### Direct-Edit External-Agent Tasks

Backlog item: the first slice has landed by updating the existing
external-agent-specific variants of the bundled repo-task fixtures so their
prompts tell the agent to edit files in the prepared workspace and stop, not to
produce a fenced patch. Keep the existing fenced-patch packs as
compatibility/default evidence and do not promote the direct-edit slice into
the default matrix. The first local M5 validation produced 2/3 verifier passes,
which is enough to treat the surface as meaningful exploratory evidence but not
enough to make it a default matrix.

Design questions:

- Should direct-edit variants reuse the same verifiers first, or introduce a
  slightly larger fixture where direct editing is materially different from a
  patch-output task?
- Should task stdout be expected to contain a short summary only, or should
  agents be allowed to leave it arbitrary while scoring only workspace state?
- Do current task logs and `repo_task.status` give enough failure signal, or is
  a later richer task-status row field justified by live evidence?

Current evidence answer: stdout/stderr logs, patch bytes, and verifier JSON were
enough to classify the no-mutation dashboard failure, but `repo_task.status` by
itself only said `failed`. A report-facing task summary landed on 2026-05-08;
a result-schema change can wait until repeated evidence shows the exact field
shape needed.

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

### Runtime And Serving Coverage Gaps

Notes derived from a 2026-05-08 review of
[bench360](https://github.com/slinusc/bench360), an NVIDIA-CUDA-focused local
LLM benchmarking suite covering vLLM, TGI, SGLang, and LMDeploy. bench360 has
no overlap on workload philosophy with this repo's coding-agent direction, but
it captures several runtime/serving dimensions that are currently missing or
weakly represented here. None of these are committed work; they are research
items to weigh against the existing coding-agent direction.

#### Concurrent / Multi-User Serving

The current `runtime-sweep` pack is sequential streaming only: one in-flight
request per measured execution, no concurrency. bench360 distinguishes
single-stream, offline batch, and multi-user server mode with
Poisson-distributed query arrivals, which exposes scheduler and queueing
behavior that sequential sweeps cannot. A candidate research direction is a
separate concurrent-load pack that records per-request latency distributions
under a fixed arrival rate, without changing the existing sequential pack
semantics.

Design questions:

- Should concurrent load be a new pack kind, a new `defaults` field on
  existing packs, or a runner-level option independent of pack manifests?
- What concurrency primitives does the runner need? `openai-chat` currently
  issues one request per measured execution; a load pack needs at least a
  scheduled arrival generator and per-request timing capture.
- Which percentile fields deserve `run.jsonl` row support (p50/p95/p99 wall
  and TTFT), and is that worth a result-schema change before live evidence?
- How does concurrent measurement interact with the existing prefill/cache
  parity gates, since shared prompt-cache state across concurrent requests
  changes prefill semantics?

#### Energy And Cost-Per-Request

`run-metadata.json` currently has free-text `operating_conditions.power` and
`operating_conditions.thermal` fields, but the runner does not autodiscover
energy or cost. bench360 captures power and reports amortized GPU cost per
request, which is meaningful for the "is the Hetzner GEX44 worth it vs an
M-class Mac" comparison the spec calls out as a core question. Energy capture
is platform-specific (NVML on CUDA, `powermetrics`/IOReport on Apple Silicon),
so any implementation needs a platform abstraction similar to the existing
`hardware.json` shape.

Design questions:

- Should energy be a normalized `run.jsonl` field, a separate optional
  `energy.json` per run, or only an auxiliary artifact alongside
  `hardware.json`?
- Cost-per-request requires a price input; should this repo own a price table
  or treat cost as user-supplied metadata applied at report time?
- Can platform-specific power capture be opt-in without making it a hard
  runtime dependency on macOS or Linux?
- How are energy samples reconciled with the existing measured-repetition
  shape, where each repetition is short and the sampling window may be
  coarser than a single request?

#### Quantization As A First-Class Axis

Quantization is currently captured only as `run-metadata.model.quantization`
free text. bench360 sweeps FP16/INT8/INT4 across GPTQ/AWQ/GGUF as a structured
axis. Treating quantization as a structured axis would let `benchpack compare`
and `benchpack report` group results by quantization explicitly rather than
relying on user-typed metadata strings, and would make matrix planning across
runtimes easier.

Design questions:

- Should quantization be promoted into a normalized `run.jsonl` row field, or
  remain in `run-metadata.json` with stricter validation?
- What is the canonical quantization label set across MLX, GGUF, GPTQ, and
  AWQ, and who owns it?
- Should pack manifests be allowed to declare expected or required
  quantization, or is quantization strictly an operating-condition concern?

#### Native CUDA Server Adapters

`openai-chat` already reaches vLLM, and through the same path can reach TGI,
SGLang, or LMDeploy when they expose OpenAI-compatible endpoints. Native
adapters would expose engine-specific telemetry (vLLM `usage` extensions,
TGI/SGLang scheduling metrics) that the OpenAI-compat shape hides. This is
strictly opportunistic: only worth doing when a real measurement question
requires server-native fields, not as a coverage exercise. Default position
is to keep using `openai-chat` until a concrete missing metric forces the
issue.

Design questions:

- Which engine-specific metrics are actually missing today, given that
  `tokens.cached_prompt` and the streaming TTFT/decode estimates already
  cover most cross-runtime needs?
- Should engine-specific adapters subclass `openai-chat` and add fields, or
  remain separate adapters with their own request paths?

### Single-Model Runtime Watch Items

#### DeepSeek V4 Flash via ds4

[ds4](https://github.com/antirez/ds4) is an alpha, Metal-focused,
DeepSeek-V4-Flash-specific inference engine. It exposes OpenAI-compatible HTTP
at `/v1/chat/completions`, so the existing `openai-chat` adapter reaches it
without code changes. It loads custom GGUF artifacts from
[`antirez/deepseek-v4-gguf`](https://huggingface.co/antirez/deepseek-v4-gguf),
requires roughly 128 GB RAM (M3 Ultra / M5 Max class), and treats KV cache as
a disk-resident first-class artifact.

A separate llama.cpp fork by the same author,
[antirez/llama.cpp-deepseek-v4-flash](https://github.com/antirez/llama.cpp-deepseek-v4-flash),
loads the same `antirez/deepseek-v4-gguf` artifact, so a same-artifact
cross-runtime comparison on DeepSeek V4 Flash is in principle possible between
ds4 and that fork. Both sides are alpha and specialized, and neither has the
broad cross-host evidence that strict-GGUF Gemma 4 already has, so the watch
item stands on alpha/specialization grounds rather than absence of a second
runtime.

Watch item, not committed work: if DeepSeek V4 Flash is added to
`docs/model-targets.md` as its own model target, ds4 plus the llama.cpp fork
become the natural runtime pair for it on M-class hardware. Until that model
target lands and at least one of the two runtimes stabilizes past alpha, ds4
is a curiosity-run endpoint, not a runtime-comparison lane. Disk-resident
compressed KV cache also means a `prefill parity = comparable` status cannot
be assumed: the existing gate is driven by normalized prompt-token and
cached-prompt-token medians, so parity for ds4 case rows would only hold if
those medians actually match in practice. Until that is shown,
`prefill_tps med` should be expected to render as `—` for ds4 case rows.

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
