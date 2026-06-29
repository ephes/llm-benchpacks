# Product Matching Literature And Benchmark Redesign Notes

Status: initial literature repository, created after the 2026-06-27
`product-offer-matching` GPT-5.5/Qwen runs showed that the current compact
pairwise task mostly rewards shallow lexical heuristics and threshold tuning.

## Diagnosis

The current `product-offer-matching` task is useful as a smoke test for whether
an agent can write and run a deterministic matcher, but it is not yet a strong
test of product matching as an algorithmic problem.

The GPT-5.5 solution mostly did this:

- normalize text;
- extract brand/category/color/model-code features;
- compute a weighted pair score;
- tune one threshold on visible training rows;
- write binary labels for hidden pair rows.

That is not enough. In particular, exact SKU/model-code matching should be
treated as a baseline or leakage-like shortcut. If an identifier is exact and
reliable, matching is a lookup problem, not a product-resolution problem. The
next benchmark should either strip exact identifiers or put them in a separate
baseline lane, then evaluate whether agents can build an actual resolution
pipeline:

1. create candidate pairs with blocking or approximate nearest-neighbor search;
2. score candidate pairs with learned or semi-supervised similarity;
3. construct a weighted graph over offers;
4. cluster the graph into product entities;
5. calibrate thresholds or cluster cuts without hidden-label access;
6. evaluate entity-level quality, not only isolated pair labels.

## Relevance-Ranked Reading List

### Tier 1: Read Before Redesigning The Benchmark

| Rank | Source | Why It Matters | Benchmark Implication |
|------|--------|----------------|-----------------------|
| 1 | WDC Products: A Multi-Dimensional Entity Matching Benchmark, Peeters, Der, Bizer, 2023. [Project page](https://webdatacommons.org/largescaleproductcorpus/wdc-products/), [arXiv](https://arxiv.org/abs/2301.09521) | This is the source family we already use, and it explicitly varies corner cases, unseen entities, and development-set size. It evaluates Ditto, HierGAT, and R-SupCon and provides both pairwise and multi-class formulations. | Stop using a tiny pair-only sample as the main claim. Add an entity/grouping lane from WDC's multi-class formulation or reproduce its harder unseen-entity dimensions. |
| 2 | An Overview of End-to-End Entity Resolution for Big Data, Christophides et al., ACM CSUR 2020. [ACM](https://dl.acm.org/doi/abs/10.1145/3418896), [arXiv](https://arxiv.org/abs/1905.06397) | Good end-to-end map of modern ER: indexing/blocking, matching, clustering, distributed execution, and workflow tradeoffs. | Future prompts should ask agents for a pipeline, not one scorer. The benchmark should inspect blocking recall, candidate count, pair scoring, and clustering separately. |
| 3 | Blocking and Filtering Techniques for Entity Resolution: A Survey, Papadakis et al., ACM CSUR 2020. [ACM](https://dl.acm.org/doi/10.1145/3377455), [arXiv](https://arxiv.org/abs/1905.06167) | Blocking is central because all-pairs matching is quadratic. The survey organizes blocking, filtering, hybrid methods, schema-aware vs schema-agnostic settings, and meta-blocking. | Add a medium/large fixture where naive all-pairs is expensive enough that agents must choose blocking or ANN retrieval. Report pair completeness / reduction ratio. |
| 4 | Magellan: Toward Building Entity Matching Management Systems, Konda et al., PVLDB 2016. [PVLDB PDF](https://www.vldb.org/pvldb/vol9/p1197-pkonda.pdf), [ACM](https://dl.acm.org/doi/10.14778/2994509.2994535) | Magellan treats EM as a workflow: blocking, matching, sampling, labeling, debugging, estimating accuracy, and iteration. | The benchmark should reward workflow design and diagnostics. A strong agent should generate reports on blocker coverage, uncertain pairs, and error analysis. |
| 5 | Deep Entity Matching with Pre-Trained Language Models / Ditto, Li et al., PVLDB 2020. [PVLDB PDF](https://www.vldb.org/pvldb/vol14/p50-li.pdf), [arXiv](https://arxiv.org/abs/2004.00584), [GitHub](https://github.com/megagonlabs/ditto) | Ditto is the core transformer cross-encoder baseline for pairwise EM. It serializes record pairs, fine-tunes PLMs, and adds domain knowledge, summarization, and data augmentation. | If dependencies are allowed, a realistic agent should consider cross-encoder scoring or at least write an interface compatible with such scoring. For local-only lanes, use Ditto as an upper-baseline reference. |
| 6 | Deep Learning for Entity Matching: A Design Space Exploration / DeepMatcher, Mudgal et al., SIGMOD 2018. [PDF](https://pages.cs.wisc.edu/~anhai/papers1/deepmatcher-sigmod18.pdf), [GitHub](https://github.com/anhaidgroup/deepmatcher) | Useful pre-PLM neural EM design space: attribute summarization, comparison, aggregation, and when deep models help or fail. | Agent prompts can provide the design-space summary and ask for a non-neural approximation when dependencies are restricted. |
| 7 | Supervised Contrastive Learning for Product Matching / R-SupCon, Peeters and Bizer, 2022. [arXiv PDF](https://arxiv.org/pdf/2202.02098) | Important specifically for product matching. WDC Products reports contrastive models as training-data-efficient compared with cross-encoders. | Add a representation-learning lane or at least a prompt section describing contrastive embeddings and nearest-neighbor candidate generation. |
| 8 | Shopee - Price Match Guarantee Kaggle competition. [Competition](https://www.kaggle.com/competitions/shopee-product-matching), [Top solution writeups](https://www.kaggle.com/competitions/shopee-product-matching/discussion/240667), [1st-place writeup](https://www.kaggle.com/competitions/shopee-product-matching/writeups/upstage-making-ai-beneficial-1st-place-solution-fr), [2nd-place writeup](https://www.kaggle.com/competitions/shopee-product-matching/writeups/lyaka-tkm-2nd-place-solution-matching-prediction-b) | Practical product matching at scale with images and titles. Top solutions use embeddings, ArcFace-style metric learning, nearest neighbors, thresholding, graph/GAT/LGB-style post-processing, and ensembling. | For a serious product benchmark, include image/title multimodal retrieval or at least text-embedding nearest-neighbor retrieval and graph clustering. Treat this as the practical competition reference. |
| 9 | Collective Entity Resolution in Relational Data, Bhattacharya and Getoor, TKDD 2007. [PDF](https://linqs.org/assets/resources/bhattacharya-tkdd07.pdf), [Semantic Scholar](https://www.semanticscholar.org/paper/Collective-entity-resolution-in-relational-data-Bhattacharya-Getoor/814f90ef27bfe5a90e118a1df0e24488e75b7939) | Formalizes ER as clustering where decisions interact, instead of isolated pair classification. | Add graph clustering and transitivity-aware scoring. Penalize pair predictions that produce impossible or inconsistent clusters. |
| 10 | Transforming Pairwise Duplicates to Entity Clusters for High-quality Entity Resolution, Draisbach et al., 2019. [PDF](https://hpi.de/oldsite/fileadmin/user_upload/fachgebiete/naumann/publications/PDFs/2019_draisbach_transforming.pdf) | Directly addresses the problem of converting pairwise duplicate decisions into consistent entity clusters. | Pairwise F1 should not be the only metric. Add cluster quality metrics and test how agents handle transitive closure errors. |

### Tier 2: Foundations And Classical Methods

| Source | Why It Matters | Benchmark Implication |
|--------|----------------|-----------------------|
| Fellegi and Sunter, A Theory for Record Linkage, 1969. [Taylor & Francis](https://www.tandfonline.com/doi/abs/10.1080/01621459.1969.10501049), [PDF copy](https://www.cs.cornell.edu/~shmat/courses/cs6434/fellegi-sunter.pdf) | The probabilistic record-linkage foundation: match/non-match decisions from comparison vectors and error tradeoffs. | Useful as a dependency-free baseline: learn m/u-style weights from labeled pairs, then calibrate thresholds. |
| Hernandez and Stolfo, The Merge/Purge Problem for Large Databases, SIGMOD 1995. [SIGMOD Record](https://sigmodrecord.org/1995/06/06/the-merge-purge-problem-for-large-databases/), [Springer article](https://link.springer.com/article/10.1023/A%3A1009761603038) | Introduces large-scale merge/purge and sorted-neighborhood-style thinking. | Add a sorted-neighborhood baseline and require agents to explain why their blocking is better. |
| Bilenko and Mooney, Adaptive Duplicate Detection Using Learnable String Similarity Measures, KDD 2003. [PDF](https://www.cs.utexas.edu/~ml/papers/marlin-kdd-03.pdf) | Learns string similarity functions and uses active learning; bridges hand-written similarity and learned matchers. | A good dependency-free agent could implement trainable per-field similarity weights rather than fixed SKU heuristics. |
| Entity Resolution Tutorial, Getoor and Machanavajjhala, VLDB 2012 tutorial materials. [PDF](https://home.cse.ust.hk/~leichen/courses/mscit6000d/notes/entityresolution.pdf) | Compact orientation covering duplicate detection names, imbalance, active learning, relational/collective methods, and clustering. | Good source to include in agent context when asking for a principled design. |
| Data Matching: Concepts and Techniques for Record Linkage, Entity Resolution, and Duplicate Detection, Christen, 2012. [Springer DOI via citation](https://doi.org/10.1007/978-3-642-31164-2) | Standard book-length reference for blocking, comparison, classification, and evaluation. | Use as background, especially for metric and evaluation definitions. |

### Tier 3: Modern Neural, LLM, And Heterogeneous Matching

| Source | Why It Matters | Benchmark Implication |
|--------|----------------|-----------------------|
| Entity Resolution with Hierarchical Graph Attention Networks / HierGAT, 2022. [ACM](https://dl.acm.org/doi/10.1145/3514221.3517872), [GitHub](https://github.com/CGCL-codes/HierGAT) | Graph-attention approach for pairwise and collective ER. WDC Products uses it as one evaluated SOTA system. | Include as a high-end graph/neural baseline, but probably too heavy for default agent-generated code. |
| Entity Matching with Transformer Architectures, Brunner and Stockinger, EDBT 2020. [PDF](https://openproceedings.org/2020/conf/edbt/paper_205.pdf) | Early transformer EM paper before Ditto became the standard reference. | Useful for explaining why simple token overlap is inadequate. |
| Hierarchical Matching Network for Heterogeneous Entity Resolution, IJCAI 2020. [PDF](https://www.ijcai.org/proceedings/2020/0507.pdf) | Token/attribute/entity-level matching for heterogeneous schemas. | Relevant if future fixtures include missing or schema-shifted attributes across sources. |
| Neural Networks for Entity Matching: A Survey, Barlaug and Gulla, ACM TKDD 2021. [ACM](https://dl.acm.org/doi/10.1145/3442200), [PDF](https://www.dit.unitn.it/~pavel/OM/articles/BARLAUG_ACM_TKDD21.pdf) | Survey of neural EM pipeline components. | Use to choose dependency-enabled baselines and decide what agents are allowed to import. |
| Entity Matching using Large Language Models, Peeters and Bizer, 2023/2025. [arXiv HTML](https://arxiv.org/html/2310.11244v4), [Semantic Scholar](https://www.semanticscholar.org/paper/Entity-Matching-using-Large-Language-Models-Peeters-Bizer/13c2ae7831c0f1579bc8c6f1a31c9aa8689e24a8) | Tests LLMs for EM as matchers, including explanation-oriented prompting. | Relevant for a separate direct-LLM matcher lane, not for the coding-agent lane unless the agent can call an LLM during inference. |
| Fine-tuning Large Language Models for Entity Matching, 2024. [arXiv HTML](https://arxiv.org/html/2409.08185v2) | Studies fine-tuning LLMs for EM and generalization across datasets/domains. | Useful background if we add a trainable LLM baseline outside the deterministic benchmark runner. |
| A Deep Dive Into Cross-Dataset Entity Matching with Large and Small Language Models, EDBT 2025. [PDF](https://openproceedings.org/2025/conf/edbt/paper-224.pdf) | Compares large and small language models in cross-dataset EM and highlights cost/performance issues. | Reinforces that small specialized models may be a stronger benchmark baseline than general LLM calls. |
| Heterogeneity in Entity Matching: A Survey and Experimental Analysis, 2025. [arXiv HTML](https://arxiv.org/html/2508.08076v1) | Recent survey focused on schema and format heterogeneity. | Relevant once the benchmark stops exposing a clean symmetric CSV and includes heterogeneous feeds. |

### Tier 4: Product-Specific And Multimodal References

| Source | Why It Matters | Benchmark Implication |
|--------|----------------|-----------------------|
| Tailoring Entity Resolution for Matching Product Offers, Köpcke et al., EDBT 2012. [PDF](https://openproceedings.org/2012/conf/edbt/KopckeTTR12.pdf) | Product matching is harder than generic ER because many products are similar but different, and category-specific attributes matter. | Use this to define domain-specific hard negatives and avoid rewarding exact identifier matching. |
| Towards Multi-Modal Entity Resolution for Product Matching, Wilke and Rahm, 2021. [PDF](https://ceur-ws.org/Vol-3075/paper10.pdf) | Extends product ER with image data and reports that images can improve recall/quality. | Add an image-enabled lane if we want to model real e-commerce product matching. |
| A Machine Learning Approach for Product Matching and Categorization, 2017. [PDF](https://www.semantic-web-journal.net/system/files/swj1664.pdf) | Pipeline with feature extraction, similarity vectors, and classification over product data. | Useful as a classical ML product-specific system design before PLMs. |
| Shopee practical writeups and repos. [Competition](https://www.kaggle.com/competitions/shopee-product-matching), [1st place](https://www.kaggle.com/competitions/shopee-product-matching/writeups/upstage-making-ai-beneficial-1st-place-solution-fr), [solution index](https://www.kaggle.com/competitions/shopee-product-matching/discussion/240667), [example repo](https://github.com/cr21/Shopee-Product-Matching) | Real competition solutions emphasize metric learning, image/text embeddings, KNN/FAISS, thresholding, graph post-processing, and ensembling. | A serious agent benchmark should ask for embedding retrieval and clustering. A standard-library-only toy lane should be clearly labeled as a toy. |
| Home Depot Product Search Relevance Kaggle. [Competition](https://www.kaggle.com/competitions/home-depot-product-search-relevance) | Related e-commerce text matching/search relevance, but not entity resolution. | Useful for text feature engineering, but do not confuse query-product relevance with product-entity matching. |

## Approach Families To Represent In Future Benchmarks

### 1. Identifier Baselines

Exact SKU/GTIN/model-code matching belongs here. It should be implemented as a
baseline and then either stripped from the real task or evaluated separately.

Useful metrics:

- exact-id precision and recall;
- fraction of pairs/entities where the identifier is present;
- conflict rate when identifiers disagree.

### 2. Blocking And Candidate Generation

Representative methods:

- sorted neighborhood / canopy-like blocking;
- token-prefix or q-gram blocking;
- schema-agnostic token blocking;
- LSH or ANN over text/image embeddings;
- meta-blocking to prune dense candidate graphs.

Useful metrics:

- pair completeness / blocking recall;
- reduction ratio;
- candidate pair count;
- maximum and median block size;
- runtime and memory.

### 3. Pair Scoring

Representative methods:

- Fellegi-Sunter-style learned comparison weights;
- learned string similarity;
- feature-vector classifier over field similarities;
- transformer cross-encoder;
- contrastive or metric-learning embedding similarity.

Useful metrics:

- PR curve and average precision over candidate pairs;
- calibration curve;
- selected threshold vs best hidden threshold;
- separate performance on hard negatives, unseen entities, and low-attribute rows.

### 4. Graph Construction And Clustering

Representative methods:

- thresholded weighted graph plus connected components;
- correlation clustering or constrained clustering;
- hierarchical clustering with cut selection;
- spectral clustering on a similarity graph;
- graph neural post-processing when dependencies are allowed.

Useful metrics:

- pairwise precision/recall/F1;
- cluster purity and inverse purity;
- B-cubed precision/recall/F1;
- number of over-merged and split gold entities;
- transitivity violation count before clustering.

### 5. Semi-Supervised, Active, And Human-In-The-Loop Learning

Representative methods:

- active pair selection near the decision boundary;
- cluster-aware active learning;
- pseudo-labeling high-confidence pairs;
- contrastive self-supervision over product titles/images;
- weak supervision rules as labeling functions.

Useful metrics:

- F1 vs number of labels;
- active-learning label efficiency;
- performance under unseen-entity splits;
- robustness to class imbalance.

## Suggested Source Pack For Implementing Agents

For the next serious agent prompt, do not give agents the entire bibliography.
Give a short source pack with explicit design requirements:

1. WDC Products benchmark page/paper for the task dimensions and data shape.
2. End-to-end ER survey for pipeline steps.
3. Blocking/filtering survey for candidate generation.
4. Magellan for workflow and diagnostics.
5. Ditto or DeepMatcher for learned pair scoring.
6. Collective ER or pair-to-cluster paper for graph clustering.
7. Shopee top-solution writeup for practical embedding/KNN/product matching.

Then require the agent to produce:

- a blocker or ANN candidate generator;
- a pair scorer that does not rely on exact IDs;
- a graph clustering stage;
- an ablation report with identifier-only, lexical-only, and learned/graph
  variants;
- PR curves and cluster metrics;
- explicit notes on where exact identifiers were unavailable or withheld.

## Benchmark Redesign Sketch

Replace or supplement the current pairwise-only compact pack with a grouped
entity-resolution pack:

```text
product-offer-entity-resolution
  train_offers.csv            # labeled product/entity groups, identifiers stripped
  train_pairs.csv             # optional labels for pair scorer training
  predict_offers.csv          # unlabeled offers to cluster
  hidden_entity_labels.csv    # verifier-owned group labels
```

Agent output:

```text
offer_id,entity_id
```

Verifier:

- validates every offer is assigned to one entity;
- computes pairwise precision/recall/F1;
- computes B-cubed or purity/inverse-purity style cluster metrics;
- computes over-merge and split diagnostics;
- optionally computes pair-scoring PR curves if the agent also writes scores.

Fixture lanes:

- `ids-visible-baseline`: exact identifiers available, should be near lookup.
- `ids-stripped-text-only`: exact identifiers removed, text/attributes only.
- `hard-negative-unseen-entity`: high corner-case rate, unseen entities.
- `multimodal-shopee-style`: title plus image path/embedding if assets are
  practical to ship or generate.

The current pairwise pack can remain as a smoke test, but it should not be used
as evidence that a model can solve product matching.

## Scale And Systems Metrics

The next benchmark needs substantially more data. A 120-pair hidden set is too
small to estimate quality reliably, and it says almost nothing about whether an
approach scales past toy all-pairs scoring. Product matching is partly an
algorithmic systems problem: quality matters, but so do candidate generation,
memory, runtime, and throughput.

### Minimum Useful Scale

Use multiple fixture sizes instead of one compact sample:

| Lane | Offers | Approx all-pairs count | Purpose |
|------|--------|------------------------|---------|
| `tiny-debug` | 200-500 | 20K-125K | Fast local debugging and deterministic unit tests. |
| `small-quality` | 2K-5K | 2M-12.5M | Enough entities and hard negatives for meaningful PR/cluster metrics. |
| `medium-systems` | 20K-50K | 200M-1.25B | Forces blocking/ANN; all-pairs scoring should be impractical or fail budget. |
| `large-systems` | 100K+ | 5B+ | Optional campaign lane for throughput and memory stress, not default CI. |

For each lane, record:

- number of offers;
- number of gold entities/products;
- entity-size distribution;
- number and percentage of singleton entities;
- category/source/brand distribution;
- exact identifier availability rate before stripping;
- train/dev/test split policy;
- known hard-negative rate.

### Runtime Measurements

The verifier should time stages separately when the submitted program exposes
them, or at least record coarse end-to-end timing:

| Metric | Definition |
|--------|------------|
| `wall_s_total` | Total time from process start to validated output. |
| `wall_s_load` | Input parsing/loading time, when reported. |
| `wall_s_blocking` | Candidate generation / blocking / ANN retrieval time. |
| `wall_s_scoring` | Pair scoring time. |
| `wall_s_clustering` | Graph clustering / entity assignment time. |
| `offers_per_second_total` | `n_offers / wall_s_total`. |
| `candidate_pairs_per_second` | `n_candidate_pairs / wall_s_scoring`. |
| `comparisons_per_offer` | `n_candidate_pairs / n_offers`. |
| `candidate_reduction_ratio` | `1 - n_candidate_pairs / all_pairs_possible`. |
| `blocking_pair_completeness` | Gold duplicate-pair recall after blocking, before scoring. |

The implementation should write an optional `metrics.json` next to its
predictions. If absent, the verifier can still compute total wall time and
quality metrics, but the row should receive no stage-level systems credit.

Suggested submitted metrics schema:

```json
{
  "schema_version": 1,
  "n_offers": 50000,
  "n_candidate_pairs": 4200000,
  "wall_s_load": 1.42,
  "wall_s_blocking": 8.31,
  "wall_s_scoring": 22.9,
  "wall_s_clustering": 3.8,
  "peak_rss_mb_observed_by_program": 1840,
  "notes": "token blocking + weighted graph connected components"
}
```

The verifier should compute and validate derived values instead of trusting all
submitted numbers. For example, `n_offers` and output row counts are verifier
owned; `n_candidate_pairs` can be checked if the program writes an optional
candidate edge file.

### Memory Measurements

Main memory must be recorded because bad product-matching approaches often
materialize too many pairs or dense matrices.

Record at minimum:

- peak resident set size (`peak_rss_mb`);
- memory per offer (`peak_rss_mb / n_offers`);
- memory per candidate edge, if edge counts are reported;
- whether the program attempted all-pairs materialization;
- whether the program spilled temporary files to disk;
- output file size and optional candidate-edge file size.

On macOS and Linux, the verifier can wrap the program with a small sampler that
polls RSS for the process tree. For Linux campaign lanes, also record cgroup
memory peaks when available. The benchmark should enforce a memory cap per
lane, e.g.:

| Lane | Suggested memory cap |
|------|----------------------|
| `tiny-debug` | 512 MB |
| `small-quality` | 2 GB |
| `medium-systems` | 8-16 GB |
| `large-systems` | campaign-specific |

Dense `n x n` score matrices should only be acceptable in `tiny-debug`, and
even there they should be called out in diagnostics.

### Quality Metrics

For entity-clustering output, compute:

- pairwise precision, recall, and F1;
- B-cubed precision, recall, and F1;
- cluster purity and inverse purity;
- over-merge count: predicted clusters spanning multiple gold entities;
- split count: gold entities split across multiple predicted clusters;
- singleton precision/recall where relevant;
- hard-negative false-positive rate;
- exact-identifier-only baseline delta.

For pair-score output, compute:

- PR curve;
- average precision;
- ROC-AUC only as secondary, because class imbalance can make it misleading;
- selected operating threshold vs best hidden threshold;
- calibration error if probabilities are claimed.

### Combined Score

Use a combined score for headline ranking, but always report the components.
The combined score should not let a fast bad matcher beat a useful matcher, and
it should not hide a memory-exploding algorithm behind good F1.

Recommended first combined score:

```text
quality = 0.55 * pairwise_f1
        + 0.35 * bcubed_f1
        + 0.10 * hard_negative_precision

throughput = clamp(log10(offers_per_second_total / baseline_offers_per_second) / 2 + 0.5, 0, 1)

memory = clamp(1 - log2(max(peak_rss_mb, memory_floor_mb) / memory_target_mb) / 4, 0, 1)

blocking = 0.7 * blocking_pair_completeness
         + 0.3 * candidate_reduction_ratio

combined = 100 * (
    0.70 * quality
  + 0.10 * throughput
  + 0.10 * memory
  + 0.10 * blocking
)
```

Interpretation:

- quality dominates;
- throughput and memory matter enough to penalize impractical systems;
- blocking gets explicit credit only when it preserves gold pairs while
  reducing candidate explosion;
- all components remain visible in reports.

`baseline_offers_per_second` and `memory_target_mb` should be lane-specific and
derived from simple reference implementations:

- exact-id lookup baseline, when identifiers are visible;
- token-blocking plus connected-components baseline;
- all-pairs lexical baseline for `tiny-debug` only;
- embedding/ANN reference baseline for dependency-enabled lanes.

Hard gates should apply before combined scoring:

- invalid output: score `0`;
- quality below a minimum floor, e.g. pairwise F1 `< 0.50`: score capped at
  `30`, regardless of speed;
- blocking pair completeness below a minimum, e.g. `< 0.85` on non-tiny lanes:
  score capped at `60`;
- memory cap exceeded: fail or score capped at `50`;
- timeout exceeded: fail.

### Reporting Tables

The report should include separate quality and systems tables.

Quality:

| run | pairwise P | pairwise R | pairwise F1 | B3 P | B3 R | B3 F1 | over-merges | splits |
|-----|------------|------------|-------------|------|------|-------|-------------|--------|

Systems:

| run | offers | candidate pairs | reduction | blocking recall | wall s | offers/s | peak RSS MB | MB/1K offers |
|-----|--------|-----------------|-----------|-----------------|--------|----------|-------------|--------------|

Combined:

| run | quality | throughput | memory | blocking | combined | caps/gates |
|-----|---------|------------|--------|----------|----------|------------|

This makes tradeoffs explicit. A model-generated implementation that gets high
F1 by doing all-pairs scoring on 500 offers should not look comparable to a
pipeline that clusters 50K offers under memory and time budgets.
