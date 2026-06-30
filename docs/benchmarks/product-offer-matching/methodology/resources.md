# Resources: Code, Libraries, Datasets

Reusable code, libraries, and datasets for the product-matching pipeline, plus
the landing zone for the deeper auto-research pass. This is **seeded** — web
passes on 2026-06-30 (a general sweep, a per-stage code-first pass, and a
solved-instances deep-read of product-ER competitions) collected the entries
below; the auto-research phase will evaluate (not just list) them and record
results in the relevant stage docs. Every entry answers one question: *would we
reuse this, and for what stage/decision?*

Status legend: `listed` = found, not yet evaluated; `evaluated` = run/assessed by
the auto-research pass with notes; `in-use` = referenced by an actual benchmark
lane.

## Entity-resolution libraries (general)

| Tool | What it gives | Pipeline stage | Status |
|---|---|---|---|
| [pyJedAI](https://github.com/AI-team-UoA/pyJedAI) | End-to-end ER workflows in Python: blocking, block-cleaning/meta-blocking, matching, **and clustering** in one toolkit; has a product-focused track (INFORMS JoC 2024). Strongest single candidate for an end-to-end baseline. | blocking, pair-scoring, clustering | listed |
| [py_entitymatching](https://github.com/anhaidgroup/py_entitymatching) (Magellan) | Blocking + rule-based and ML matchers, sampling, labeling, debugging; the workflow reference. No built-in clustering. | blocking, pair-scoring | listed |
| [dedupe](https://github.com/dedupeio/dedupe) | Fellegi-Sunter + active learning; learns thresholds; includes clustering of matched pairs. | pair-scoring, clustering | listed |
| [recordlinkage](https://github.com/J535D165/recordlinkage) | Prototyping toolkit: indexing/blocking, comparison, classification. | blocking, signals, pair-scoring | listed |
| [Awesome-Entity-Resolution](https://github.com/OlivierBinette/Awesome-Entity-Resolution) | Curated index of ER software and resources; a discovery hub for the auto-research pass. | all | listed |
| [BigGorilla](https://www.biggorilla.org/) | Data-integration/ER ecosystem (home of Magellan). | all | listed |

## Blocking / candidate generation

| Tool | What it gives | Reuse for | Status |
|---|---|---|---|
| [pyahocorasick](https://github.com/WojciechMula/pyahocorasick) | C-extension Aho-Corasick automaton; multi-pattern matching, picklable. | The **identifier-dictionary blocker** (blocking.md) — scan a title against 10k canonical codes in one pass. | listed |
| [datasketch](https://github.com/ekzhu/datasketch) | MinHash, MinHashLSH, LSH Forest. | Jaccard/shingle blocking over token sets without all-pairs. | listed |
| [faiss](https://github.com/facebookresearch/faiss) | Optimized ANN (IVF/PQ/HNSW), C++ + Python. | Embedding ANN blocking at scale (dependency lane). | listed |
| [hnswlib](https://github.com/nmslib/hnswlib) | Lightweight HNSW ANN index. | Lighter-weight embedding ANN blocker than faiss. | listed |

## Signals / feature extraction

| Tool | What it gives | Reuse for | Status |
|---|---|---|---|
| [quantulum3](https://github.com/nielstron/quantulum3) | Extracts quantities + units from free text, disambiguates similar units. | Unit canonicalization in signals.md (storage/size/generation tokens: `32 GB` vs `32gb`). | listed |
| [pint](https://github.com/hgrecco/pint) | Unit representation and conversion. | Normalizing extracted quantities to a canonical unit. | listed |

## Pair scoring / neural EM

| Tool | What it gives | Stage | Status |
|---|---|---|---|
| [Ditto](https://github.com/megagonlabs/ditto) | Transformer cross-encoder EM; serializes pairs, fine-tunes a PLM; evaluated on WDC product matching. | pair-scoring | listed |
| [DeepMatcher](https://github.com/anhaidgroup/deepmatcher) | Pre-PLM neural EM (attribute summarization/comparison/aggregation); design-space reference. | pair-scoring | listed |
| [WDC / R-SupCon](https://github.com/wbsg-uni-mannheim/contrastive-product-matching) | Supervised contrastive learning for product matching (metric learning). | pair-scoring, signals | listed |
| [Jellyfish](https://huggingface.co/NECOUDBFM/Jellyfish-13B) ([paper](https://aclanthology.org/2024.emnlp-main.497.pdf)) | Instruction-tuned local LLM (Llama-2-13B) for data prep incl. entity matching; runs on one GPU, competitive with GPT-4 on EM. | Reference for a direct-LLM matcher lane; supports the "fine-tuned small model > general LLM" finding. | listed |

## Product matching at scale (Shopee competition)

Practical image+text product matching: metric-learned embeddings (ArcFace),
KNN/ANN retrieval, thresholding, graph/transitive post-processing, ensembling.
Official 1st/2nd-place writeups are linked from `../literature.md` Tier 1 #8.

| Repo | Notes | Status |
|---|---|---|
| [kiccho1101/kaggle-shopee-6th-place-solution](https://github.com/kiccho1101/kaggle-shopee-6th-place-solution) | Gold-medal solution; image+text embeddings + KNN. | listed |
| [Edyanakov/Shopee-Price-Match-Guarantee](https://github.com/Edyanakov/Shopee-Price-Match-Guarantee) | ArcMargin image+text heads, cosine-similarity thresholding. | listed |
| [mfalfafa/shopee-price-match-guarantee](https://github.com/mfalfafa/shopee-price-match-guarantee) | Silver-medal solution. | listed |
| [cr21/Shopee-Product-Matching](https://github.com/cr21/Shopee-Product-Matching) | Already cited in `../literature.md`; ML pipeline writeup. | listed |
| [jingxuanyang/Shopee-Product-Matching](https://github.com/jingxuanyang/Shopee-Product-Matching) | Documented pattern-recognition project. | listed |

## Techniques from solved instances

Concrete, reusable techniques extracted from the top solutions of two product-ER
competitions. (Provenance: Shopee specifics are from two corroborating recap
write-ups — [GO Inc.](https://techblog.goinc.jp/entry/2021/05/27/090000),
[Shiwagi](https://masatakashiwagi.com/blog/kaggle-shopee-solution/) — because the
Kaggle discussion pages and ACM full text were not directly fetchable; treat as
secondary but cross-checked. The SIGMOD2020 winner row is verified against the
primary paper.)

| Technique | What it is | Reuse for | Status |
|---|---|---|---|
| Iterative Neighborhood Blending (INB) | Shopee 1st: build a cosine-KNN graph (faiss, k≈51), re-aggregate each item's embedding as a similarity-weighted blend of its neighbors, re-run KNN, iterate ~2×. Query-expansion / label-propagation over the graph. | signals/pair-scoring — embedding refinement that lifts any KNN matcher before clustering. | listed |
| Two-stage embed → re-rank | Shopee 1st–3rd: ArcFace/CurricularFace/Triplet embeddings → cosine-KNN candidates → 2nd-stage **LightGBM / GAT / CatBoost** over ~500 pair features (top-K cosine stats, PageRank/graph metrics, text edit-distance). | pair-scoring — the proven product image+text architecture. | listed |
| Graph cluster cleanup | Shopee 2nd: drop non-reciprocal (non-mutual-KNN) edges, threshold-vote edges, recursively prune highest-**betweenness** edges to split over-merges; 3rd: agglomerative merge to a target cluster size. | clustering — turning a noisy KNN graph into clean clusters; controls over-merge. | listed |
| Union-find + transitive closure | SIGMOD2020: labels are transitively closed, so clustering = connected components over predicted-match edges; **self-training** folds high-confidence pairs back in. | clustering — the baseline pair→cluster step; matches clustering.md. | listed |
| Mock labels + sorted-integer-set matching | SIGMOD2020 **winner** ([paper](https://ceur-ws.org/Vol-2726/paper2.pdf)): build a catalog of ~2,800 "mock labels" (per-entity keyword sets, mainly brand+model tokens) offline, then represent each label and each offer title as a **sorted integer set** and assign an offer to a label by a set-**subset** test (dropping subset-labels to disambiguate `eos 7d` vs `eos 7d mark ii`). Set intersections are extremely fast — 0.61s for ~30k offers, the tiebreaker since all finalists hit F=0.99. | **catalog-linkage matching (warm-start regime)** + fast set-ops; the "mock labels" map onto our catalog-side canonical codes (signals.md, index.md regimes). | listed |
| Unit-mismatch filtering | Shopee + SIGMOD: rule-based reject when quantity/unit tokens disagree (50ml vs 100ml). | signals — the negative-veto our pilot evidence also supports (`findings-pilot.md`). | listed |

## Clustering

| Tool | What it gives | Status |
|---|---|---|
| scikit-learn (`AgglomerativeClustering`, `SpectralClustering`) | Hierarchical and spectral baselines. | listed |
| [markov_clustering](https://github.com/GuyAllard/markov_clustering) | MCL for sparse similarity graphs (`k`-free). | listed |
| igraph / [leidenalg](https://github.com/vtraag/leidenalg) | Community detection (Louvain/Leiden), `k`-free, scalable. | listed |
| [scikit-network](https://github.com/sknetwork-team/scikit-network) | Graph algorithms on SciPy CSR sparse matrices: clustering, ranking, embedding. Lightweight for the offer similarity graph. | listed |
| [hdbscan](https://github.com/scikit-learn-contrib/hdbscan) | Density clustering in embedding space; infers cluster count, tolerates noise. | listed |
| [HierGAT](https://github.com/CGCL-codes/HierGAT) | Graph-attention collective ER; high-end reference. | listed |

## Evaluation metrics

| Tool | What it gives | Reuse for | Status |
|---|---|---|---|
| [bcubed](https://pypi.org/project/bcubed/) | B-cubed precision/recall/F1 for (non-)overlapping clustering. | The primary cluster metric (evaluation.md); cross-check our own impl. | listed |
| scikit-learn `metrics` | `v_measure_score`, homogeneity/completeness, adjusted Rand, etc. | Secondary cluster cross-checks (evaluation.md open question on V-measure/CEAF). | listed |
| [RunOrVeith/BCUBED](https://github.com/RunOrVeith/BCUBED) | Faster single-class B-cubed implementation. | Scaling B-cubed to the large quality lane. | listed |

## Datasets / benchmarks

| Dataset | Signals | Use here | Status |
|---|---|---|---|
| [WDC Products](https://webdatacommons.org/largescaleproductcorpus/wdc-products/) ([paper](https://arxiv.org/abs/2301.09521)) | title/brand/desc, numeric price; no image | Best off-the-shelf eval harness: 27 variants over corner-cases / **unseen-entities** / dev-size; pairwise + multi-class. The unseen-entity axis measures generalization, not memorization. | listed |
| [WDC LSPM v2](http://webdatacommons.org/largescaleproductcorpus/v2/) ([paper](https://www.uni-mannheim.de/media/Einrichtungen/dws/Files_Research/Web-based_Systems/pub/ECNLP_19_PrimpeliPeetersBizer.pdf)) | title (raw+norm), desc, brand, GTIN/MPN, specTableContent; sparse price; no image | Large real web offers keyed by **GTIN/MPN clusters** — mirrors our "product_id as cluster key". 4,400-pair hand-verified gold standard; training sets Small→XLarge. | listed |
| [Magellan / DeepMatcher datasets](https://sites.google.com/site/anhaidgroup/useful-stuff/the-magellan-data-repository) (Abt-Buy, Amazon-Google, Walmart-Amazon) | title, desc, brand, **price**, model; hand-labeled candidate pairs; no image | Ready gold pairs *with price* to validate a scorer; standard EM numbers exist for calibration. **But** some sets are saturated/leaky ([re-eval](https://arxiv.org/pdf/2307.01231)) — prefer WDC unseen-entity splits for a stress test. | listed |
| [SIGMOD2020 / Alaska](https://transactional.blog/sigmod-contest/2020) ([Alaska paper](https://arxiv.org/abs/2101.11259), [starter](https://github.com/transactionalblog/sigmod-contest-2020)) | ~30k camera specs as (attr, value) lists from 24 sources; labeled match pairs; no image | Spec-style product ER for a third validation domain; F-measure-on-pairs protocol; accessories as known hard non-matches. | listed |
| [Shopee Price Match](https://www.kaggle.com/competitions/shopee-product-matching) | per-offer image + title | The multimodal reference (per-offer images). | listed |
| PriceRunner (UCI/Kaggle) | title-only | Current title-only pack (`../index.md`). | in-use |
| billiger.de pilot | title + price + product-level image | Current scrape pilot (`../dataset-sourcing-analysis.md`, `findings-pilot.md`). | in-use |

## Auto-research landing zone

The deeper auto-research pass (run when a representative sample is collected)
fills this in. For each candidate approach it should record:

- **Approach** and which stage doc it belongs to (blocking / signals /
  pair-scoring / clustering / evaluation).
- **Source** (paper + code) and license.
- **Result on our sample** — the metric(s) from evaluation.md, on our data, not
  the source's numbers.
- **Cost** — throughput/memory (systems metrics).
- **Verdict** — adopt as baseline / candidate lane / reference-only / reject,
  with one line of reasoning.

Template:

| Approach | Stage | Source | Result (our sample) | Cost | Verdict |
|---|---|---|---|---|---|
| _e.g._ token-blocking + CC | blocking + clustering | Papadakis CSUR 2020 | _PC/RR/B3-F1 TBD_ | _TBD_ | _baseline_ |

When an entry graduates from `listed` to `evaluated`, copy its verdict into the
*Methods* section of the relevant stage doc so the methodology stays the source
of truth and this file stays the catalog.

## References

- Approach families and the reading list: `../literature.md`.
- Pipeline and stage docs: `index.md`, `blocking.md`, `signals.md`,
  `pair-scoring.md`, `clustering.md`, `evaluation.md`.
