# Product-Matching Methodology

A stable, dataset-agnostic knowledge base for the product entity-resolution
benchmark. It records *how* to match offers to products and *how* to measure
each stage, independent of which dataset currently feeds the benchmark.

## Stability contract

These documents must survive a dataset swap. We currently source from
billiger.de and from the PriceRunner UCI/Kaggle dump, and we may move to
WebDataCommons or another aggregator later. The contract applies to
**methodology claims** — the problem framing, method descriptions, metric
definitions, and benchmark rules that make up the body of these docs:

- No methodology claim names a concrete dataset.
- Concrete datasets appear in methodology prose **only** inside fenced *example*
  callouts, like:

  > **Example (billiger.de pilot).** Per-offer titles for one Galaxy S24 Ultra
  > 512 GB variant ranged from `Samsung Galaxy S24 Ultra 512GB 12RAM S928B/DS
  > Titanium Black` to `... titanium black EU - Schwarz/Silber`.

  Swapping the dataset means editing the callouts, not the claims around them.

When a concrete dataset detail leaks into a methodology claim, treat it as a
defect to fix, not as content.

**Exempt surfaces.** Some sections exist precisely to track the current concrete
setup, and they name datasets by design — that is not a contract violation:

- `resources.md` — the code/dataset catalog, including which dataset is `in-use`.
- The status tables in this document.
- Provenance pointers to [`../dataset-sourcing-analysis.md`](../dataset-sourcing-analysis.md).

These catalog/status surfaces are updated on a dataset swap alongside the example
callouts; the methodology claims stay unchanged.

## The pipeline

Product matching is an entity-resolution (ER) pipeline, not a single scorer.
Each document below owns one stage or one cross-cutting concern.

```text
            offers
              │
   ┌──────────▼───────────┐
   │ 1. Blocking /        │  reduce O(n^2) pairs to a candidate set
   │    candidate gen     │  → blocking.md
   └──────────┬───────────┘
              │ candidate pairs
   ┌──────────▼───────────┐
   │ 2. Signals /         │  per-pair comparison features
   │    feature extraction│  (price, title sim, identifiers, image)
   └──────────┬───────────┘  → signals.md
              │ feature vectors
   ┌──────────▼───────────┐
   │ 3. Pair scoring      │  feature vector → match probability/score
   │                      │  → pair-scoring.md
   └──────────┬───────────┘
              │ weighted edges
   ┌──────────▼───────────┐
   │ 4. Graph clustering  │  similarity graph → product entities
   │                      │  → clustering.md
   └──────────┬───────────┘
              │ offer → cluster assignment
   ┌──────────▼───────────┐
   │ 5. Evaluation        │  cluster + ranking + systems metrics
   │                      │  → evaluation.md
   └──────────────────────┘
```

Cross-cutting concerns wrap every stage:

- **[data-quality.md](data-quality.md)** — label-noise taxonomy and the cleanup
  passes that protect the gold labels every stage is measured against.
- **[benchmark-constraints.md](benchmark-constraints.md)** — constraints on the
  *submitted implementations* we test: rule-level unit tests, determinism,
  anti-leakage, stage decomposition, and resource budgets.
- **[resources.md](resources.md)** — reusable code, libraries, datasets, and the
  landing zone for the deeper auto-research pass.

## Document skeleton

Every stage/concern document follows the same skeleton so later auto-research
and found code have an obvious slot:

1. **Problem** — what this stage must accomplish and why it is hard.
2. **Methods** — the families of approaches, with trade-offs.
3. **How we measure it** — the metrics and diagnostics for this stage.
4. **Benchmark implications** — what we require, reward, or withhold.
5. **Open questions** — unresolved decisions, flagged for the auto-research pass.
6. **References** — pointers into `../literature.md` and external sources.

## Status

`grounded` = written from collected literature + prior internal analysis.
`seeded` = initial content plus a landing zone for the deeper auto-research pass.
`open` = scaffolded, awaiting the auto-research phase.

| Document | Stage / concern | Status |
|---|---|---|
| [blocking.md](blocking.md) | Candidate generation | grounded |
| [signals.md](signals.md) | Feature extraction (price, title, identifier, image) | grounded |
| [pair-scoring.md](pair-scoring.md) | Pair scoring + metric learning | grounded |
| [clustering.md](clustering.md) | Graph clustering | grounded |
| [evaluation.md](evaluation.md) | Metrics (cluster, ranking, systems) | grounded |
| [data-quality.md](data-quality.md) | Label noise + cleanup | grounded |
| [benchmark-constraints.md](benchmark-constraints.md) | Implementation constraints | grounded |
| [resources.md](resources.md) | Code / datasets / auto-research | seeded |

## How this feeds the auto-research phase

When a representative sample is collected, the auto-research pass will:

- run the empirical analyses these docs *describe* (separability histograms,
  blocking recall curves, label-noise rates) on real data;
- benchmark candidate approaches per stage and record results back into the
  relevant document's *Methods* and *How we measure it* sections;
- populate `resources.md` with evaluated, not just listed, code.

Until then, the empirical sections specify the method and leave the numbers to
that pass.

## Related material

- [Literature and redesign notes](../literature.md) — the reading list and the
  original redesign sketch this methodology builds on.
- [Dataset sourcing analysis](../dataset-sourcing-analysis.md) — price/image
  source comparison and the billiger.de pilot.
- [Benchmark index](../index.md) — the current implemented pack.
