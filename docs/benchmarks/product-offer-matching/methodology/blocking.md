# Blocking and Candidate Generation

## Problem

Comparing every pair of offers is quadratic. For `n` offers there are
`n·(n−1)/2` pairs: 5,000 offers is ~12.5M pairs, 50,000 offers is ~1.25B. Pair
scoring (signals.md, pair-scoring.md) is the expensive stage, so we cannot score
all pairs at non-trivial scale. Blocking (a.k.a. indexing or candidate
generation) selects a small candidate set that is supposed to contain almost all
true-match pairs while discarding most non-matches.

Blocking sets the ceiling on recall for the whole pipeline: a true pair dropped
at blocking can never be recovered by scoring or clustering. So blocking is
evaluated on a recall-vs-cost trade-off, not on precision alone.

> **Example.** A naive all-pairs lexical matcher on a few hundred offers looks
> fine, but the same approach on 50,000 offers must either block or blow the
> time/memory budget. A serious benchmark lane should be large enough that
> all-pairs is impractical, forcing a real candidate generator.

## Methods

The blocking survey (Papadakis et al., CSUR 2020) organizes these into
schema-aware vs schema-agnostic, and block-building vs block-cleaning. The
practical families:

### Key-based blocking

- **Standard/token blocking.** Build a key per offer (e.g. brand, first token,
  a normalized model token) and only compare offers sharing a key. Schema-
  agnostic token blocking puts every offer in a block for each of its tokens.
  Simple and high-recall, but produces large, skewed blocks for common tokens.
- **Q-gram / character-n-gram blocking.** Key on overlapping character n-grams
  so near-spellings still collide. More robust to the spacing/dash noise that
  breaks word tokens (see signals.md identifier extraction), at the cost of
  larger candidate sets.
- **Prefix / suffix blocking.** Key on a sorted token prefix; cheap, recall
  depends on consistent leading tokens.

### Sorted neighborhood

Sort offers by a key (e.g. normalized title) and slide a fixed window,
comparing only offers within the window (Hernandez & Stolfo, SIGMOD 1995).
Multi-pass sorted neighborhood with different keys recovers pairs a single sort
order misses. Window size trades recall for candidate count directly.

### Canopy clustering

Use a cheap similarity (e.g. TF-IDF cosine over titles) to form overlapping
canopies with a loose threshold, then only score within a canopy. Bridges
key-based blocking and similarity-based retrieval.

### Similarity-based retrieval (LSH / ANN)

- **MinHash + LSH** for set/Jaccard similarity over token or shingle sets.
- **ANN over embeddings** (HNSW, IVF/PQ) for dense title or image embeddings.
  Retrieve each offer's top-k nearest neighbors as candidates. This is the
  practical product-matching path at scale and what the Shopee solutions use
  (KNN over ArcFace embeddings; resources.md).

ANN turns "all pairs" into "k candidates per offer", making candidate count
`O(n·k)` instead of `O(n^2)`.

### Meta-blocking

When the candidate graph from block-building is still too dense, prune it.
Weight candidate edges by how many blocks two offers co-occur in (and how large
those blocks are), then drop low-weight edges. Useful as a second stage on top
of schema-agnostic token blocking.

### Identifier-dictionary matching (catalog-linkage regime)

This blocker exists only in the **warm-start regime** (index.md): when an
established catalog of products is available, candidate generation becomes a
dictionary lookup instead of an all-pairs reduction.

Build, offline, a dictionary `code → {product_id}` of canonical model codes
mined from each catalog product's member offers (signals.md, *catalog-side
canonical codes*). Then, for each incoming offer title, find which dictionary
codes occur in it. Because the codes are short patterns and a title is a short
text, this is the classic **multi-pattern substring matching** problem, solved by
an **Aho-Corasick automaton**: build one automaton over all codes
(`O(Σ code lengths)`), then scan each title once in `O(title length + matches)`.
A 10k-code dictionary is trivial to build and scans at hundreds of MB/s.

Aho-Corasick matches *exactly*, so the spacing/dash robustness does not come for
free — it comes from canonicalizing first. Apply the same normalization to
**both** the dictionary codes and the incoming title (signals.md: strip
separators, lowercase, canonicalize units) before building and scanning. On that
shared canonical stream, AC's word-boundary-free matching then lets a code hit
even though the raw titles wrote it differently (`S928B/DS` vs `S928B` both
reduce to `s928b`). If codes and titles are *not* reduced to the same form, exact
matching will miss the intended variants — the robustness is in the
canonicalization, not in AC.

The hit set *is* the candidate set: an offer whose title contains product X's
code yields candidates `{X}` (often size 0 or 1), so reduction ratio is extreme
and downstream scoring is nearly free. Caveats that keep it from being brittle:

- **Substring false positives** (`A31` inside `A310`; `S928B` inside
  `S928B/DS`): require a minimum code length/specificity and prefer
  longest-match; optionally check word-ish boundaries.
- **Ambiguous codes** that map to many products are non-discriminating; keep the
  value a *set* and down-weight high-fan-out codes.
- **No hit** (terse titles, genuinely new products): fall through to a
  recall-oriented fallback blocker (ANN / q-gram) and the new-entity path
  (evaluation.md). Identifier-dictionary matching is a high-precision *first*
  pass, not the whole blocker.

A generalized **suffix automaton / suffix tree built over the titles** is the
dual structure (index the text, query arbitrary patterns) and supports general
substring/q-gram blocking; for the specific "which of my N codes is in this
title" question, Aho-Corasick over the codes is simpler and faster.

## How we measure it

Blocking is measured on the candidate set *before* scoring, against gold pairs.
Let gold duplicate pairs be the set of all same-product offer pairs.

| Metric | Definition | Reading |
|---|---|---|
| Pair completeness (PC) / blocking recall | `(gold pairs in candidates) / (all gold pairs)` | The recall ceiling. Most important. |
| Reduction ratio (RR) | `1 − (candidate pairs) / (all possible pairs)` | How much work was avoided. |
| Pairs quality (PQ) / blocking precision | `(gold pairs in candidates) / (candidate pairs)` | Density of true matches in candidates. |
| F-of-PC-and-PQ | harmonic mean of PC and PQ | Single-number summary; secondary. |
| Candidate count | `|candidates|` | Drives downstream scoring cost. |
| Comparisons per offer | `|candidates| / n` | Scale-normalized cost. |
| Max / median block size | size distribution | Detects skewed giant blocks. |

The recall–cost trade-off is a curve, not a point: sweep the blocking parameter
(window size, k, threshold, n-gram length) and plot PC against RR (or against
candidate count). A good blocker dominates: higher PC at equal RR.

Diagnostics worth recording:

- the largest blocks and their keys (giant blocks are usually a common brand or
  a stopword-like token that should be down-weighted);
- gold pairs missed by blocking, bucketed by why (no shared token, unit/spacing
  mismatch, cross-language title) — this feeds back into signals.md
  normalization;
- whether the candidate generator materialized all pairs internally (a hidden
  `O(n^2)` step defeats the purpose even if the output set is small).

## Benchmark implications

- **Provide a lane where all-pairs is impractical.** Tiny lanes can allow
  all-pairs as a baseline, but at least one lane should have enough offers that
  blocking or ANN is required to fit the time/memory budget.
- **Score blocking explicitly.** Give credit for high PC at high RR; do not let
  a matcher claim quality while silently scoring all pairs. The combined score
  in `../literature.md` already includes a blocking term
  (`0.7·PC + 0.3·RR`).
- **Gate on a recall floor.** Below a minimum PC (literature.md suggests `0.85`
  on non-tiny lanes), cap the score: a matcher that cannot even surface the true
  pairs cannot be rescued downstream.
- **Ask for a candidate-edge file.** If the implementation writes its candidate
  pairs, the verifier can compute PC/RR directly instead of trusting a reported
  number.

## Open questions

- Which blocking metric(s) belong in the headline vs the diagnostic table —
  PC+RR pair, or the F-of-PC-PQ single number? (Coordinate with evaluation.md.)
- Default blocking baselines per lane: token-blocking + connected components for
  standard-library lanes; ANN/HNSW for dependency-enabled lanes. Exact reference
  parameters to be set by the auto-research pass.
- Whether to require a reported peak candidate count to detect hidden all-pairs
  materialization, or to infer it from memory sampling alone.

## References

- Papadakis et al., *Blocking and Filtering Techniques for Entity Resolution: A
  Survey*, ACM CSUR 2020 — see `../literature.md` Tier 1.
- Christophides et al., *An Overview of End-to-End Entity Resolution for Big
  Data*, ACM CSUR 2020 — `../literature.md` Tier 1.
- Hernandez & Stolfo, *The Merge/Purge Problem*, SIGMOD 1995 — `../literature.md`
  Tier 2.
- Aho & Corasick, *Efficient String Matching: An Aid to Bibliographic Search*,
  CACM 1975 — the multi-pattern automaton behind identifier-dictionary matching.
- Shopee top solutions (ANN over metric-learned embeddings) — see
  `resources.md`.
