# Graph Clustering

## Problem

Pair scoring (pair-scoring.md) yields a weighted graph: nodes are offers, edges
carry a match score. The final task is to partition this graph into product
entities — clusters where every offer refers to the same real product. This is
where the benchmark is actually scored (evaluation.md), because the deliverable
is `offer_id → cluster_id`, not pair labels.

The hard part is that pairwise decisions are *not independent*. Three offers
A, B, C with edges A–B and B–C above threshold but A–C below imply a
**transitivity violation**: pairwise scoring says A≈B and B≈C but A≉C. Entity
resolution is collective — the cluster assignment must reconcile these
inconsistencies rather than trust each edge in isolation (Bhattacharya & Getoor,
TKDD 2007; Draisbach et al., 2019).

## Methods

### Threshold + connected components (baseline)

Keep edges above a threshold, take connected components as clusters. Simple,
fast, dependency-free, and a legitimate baseline. Its weakness is exactly
transitivity: a single bad high-score edge chains two true products into one
giant cluster (the classic over-merge cascade). Sensitive to the threshold;
no notion of cluster cohesion beyond connectivity.

### Correlation clustering

Built for exactly this signal: given edges labeled "same" (positive weight) or
"different" (negative weight), find the partition minimizing disagreement
(positive edges cut + negative edges kept). Maps cleanly onto a similarity graph
where scores are centered around the decision threshold (above → +, below → −).
NP-hard in general but with good practical approximations (e.g. pivot-based).
The principled choice when scores can be signed around a threshold, and it
handles transitivity violations natively by paying a cost for each one.

### Hierarchical agglomerative clustering (HAC)

Merge the closest clusters repeatedly; cut the dendrogram to get a flat
partition. Linkage choice matters: single-linkage reproduces the connected-
components chaining problem; **average** or **complete** linkage resist
over-merge by requiring broad cohesion before merging. Cutting requires a
distance threshold or a stopping rule; the cut height is the main knob and can
be selected on visible labels. Good quality/control balance; cost is the
distance computations, mitigated by only operating on candidate edges.

### Spectral clustering

Embed offers using the top eigenvectors of the (normalized) graph Laplacian,
then cluster in that space. Captures global graph structure that local methods
miss and handles non-convex cluster shapes. Drawbacks: classic spectral
clustering needs the number of clusters `k`, which is unknown and large here
(thousands of products); eigendecomposition is expensive on large graphs; and it
assumes a reasonably connected similarity structure. Usable on a blocked,
sparsified graph, but `k`-selection (eigengap heuristic) is fragile at this
scale.

### Markov clustering (MCL) and community detection

MCL (random-walk flow simulation) and modularity-based community detection
(Louvain/Leiden) find clusters without a preset `k` and scale to sparse graphs.
Worth evaluating as `k`-free alternatives to spectral; they are common in
practical large-scale ER post-processing.

### Graph neural post-processing

GNN/GAT refinement of the edge graph (HierGAT) is SOTA-adjacent but heavy;
relegate to a dependency-enabled high-end reference, not a default lane.

### Why k-means is a poor fit

k-means is tempting but mismatched here, and the methodology should say so
plainly:

- It needs `k` up front. The number of products is unknown and very large
  (potentially one cluster per few offers), so there is no good `k`.
- It minimizes Euclidean distance to centroids in a feature space. Our signal is
  a *pairwise similarity graph*, not points with meaningful centroids; "the mean
  of three offers" is not a product.
- It assumes roughly balanced, convex clusters. Product clusters are tiny,
  highly imbalanced (many singletons, a few large), and defined by relational
  agreement, not geometric compactness.

If embeddings exist (metric learning, signals.md/pair-scoring.md), clustering
*in embedding space* is reasonable — but even then prefer HDBSCAN or
threshold/agglomerative methods that infer cluster count and tolerate noise over
flat k-means. k-means belongs in the "considered and rejected" record, not the
default pipeline.

### Handling transitivity explicitly

Independent of clustering algorithm, two practical moves:

- **Count violations before clustering** as a diagnostic: how many A–B, B–C
  high / A–C low triangles exist. High counts mean the scorer is locally
  inconsistent and the clusterer will have to absorb the cost.
- **Pair-to-cluster reconciliation** (Draisbach et al., 2019): convert pairwise
  duplicate decisions into a consistent partition deliberately (e.g. via
  correlation clustering or a max-agreement merge) rather than naive transitive
  closure, which propagates every false-positive edge.

## How we measure it

Clustering is scored with the cluster-quality metrics defined in evaluation.md:
B-cubed P/R/F1, pairwise P/R/F1 induced by the clusters, purity / inverse
purity, plus **over-merge count** (predicted clusters spanning multiple gold
products) and **split count** (gold products split across predicted clusters).
The over-merge/split pair is the most actionable diagnostic: over-merge points
at chaining / too-low threshold / single-linkage; split points at too-high
threshold or weak recall upstream.

Always report the transitivity-violation count of the input graph next to the
cluster metrics, so a clusterer's quality is read in light of how inconsistent
its input was.

## Benchmark implications

- The deliverable is the clustering, so cluster metrics — not pair F1 — are the
  headline (`../literature.md` redesign).
- Provide connected-components as the documented baseline; reward methods that
  beat it on over-merge without sacrificing recall.
- Penalize pair predictions that imply impossible/inconsistent clusters: a
  scorer + naive transitive closure that over-merges should score worse than a
  transitivity-aware clusterer on the same edges.
- k-means submissions are allowed but should not be presented as appropriate;
  expect them to under-perform and be visible as such.

## Open questions

- Default clusterer per lane: connected components (standard-library) vs
  correlation clustering / average-linkage HAC (dependency-enabled). Choose
  after measuring over-merge/split on a representative sample.
- Whether to require the agent to emit candidate edges so the verifier can
  recompute transitivity violations and re-cluster with a reference algorithm
  for comparison.
- `k`-free vs `k`-based methods (MCL/Louvain vs spectral) at our cluster-count
  scale — to be benchmarked.

## References

- Bhattacharya & Getoor, *Collective Entity Resolution in Relational Data*,
  TKDD 2007 — `../literature.md` Tier 1.
- Draisbach et al., *Transforming Pairwise Duplicates to Entity Clusters*, 2019
  — `../literature.md` Tier 1.
- HierGAT, 2022 — `../literature.md` Tier 3.
- `resources.md` for clustering implementations (scikit-learn agglomerative/
  spectral, `markov_clustering`, igraph/Leiden).
