# Product-Offer Large Pairwise Rerun

Date: 2026-06-27

This rerun uses a larger WDC Products 20pair-derived pairwise fixture than the
initial compact pack. It is useful for threshold curves, ranking quality,
implementation throughput, and process RSS. It is not a valid blocking or
clustering benchmark because the hidden set is still only about 1,000 unique
offers. Blocking must be evaluated on at least tens of thousands of offers.

## Fixture

- Source archive: WDC Products `20pair.zip`
- Visible training: `wdcproducts20cc80rnd000un_train_large.json.gz`
- Hidden test: `wdcproducts20cc80rnd000un_gs.json.gz`
- Training pairs: 19,015 total, 7,963 positive, 11,052 negative
- Hidden test pairs: 4,500 total, 500 positive, 4,000 negative
- Hidden prevalence: 11.111%
- Generated pack: `results/product-offer-matching-large-pairwise-pack-20260627`

## Results

| Run | Case | Agent result | F1 | Precision | Recall | AP | Best hidden F1 | Pairs/s | Peak RSS MB | Combined |
|-----|------|--------------|----|-----------|--------|----|----------------|---------|-------------|----------|
| GPT-5.5 | Python | edited, failed threshold | 0.510 | 0.369 | 0.826 | 0.562 | 0.555 | 319 | 89.0 | 50.25 |
| GPT-5.5 | Rust | edited, failed threshold | 0.476 | 0.337 | 0.810 | 0.489 | 0.515 | 3,974 | 63.8 | 49.82 |
| Qwen3.6 llama.cpp high | Python | no mutation / timeout failures | 0.000 | 0.000 | 0.000 | n/a | n/a | n/a | n/a | n/a |
| Qwen3.6 llama.cpp high | Rust | edited, failed threshold | 0.322 | 0.194 | 0.946 | 0.443 | 0.457 | 5,592 | 23.8 | 41.62 |

Combined score formula:

```text
100 * (0.55*f1 + 0.30*average_precision
       + 0.10*min(pairs_per_second/10000,1)
       + 0.05*min(512/peak_rss_mb,1))
```

The formula is quality-dominant and should be read as a sorting aid, not a
business KPI.

## PR Curves

Generated curve artifacts:

- GPT-5.5 Python: 4,202 PR points,
  `results/product-offer-pi-gpt55-large-pairwise-20260627/verify/pairwise-real-small-python/rep-001.pr-curve.csv`
- GPT-5.5 Rust: 2,777 PR points,
  `results/product-offer-pi-gpt55-large-pairwise-20260627/verify/pairwise-real-small-rust/rep-001.pr-curve.csv`
- Qwen3.6 Rust: 1,688 PR points,
  `results/product-offer-pi-qwen36-llamacpp-high-large-pairwise-20260627/verify/pairwise-real-small-rust/rep-001.pr-curve.csv`

Qwen3.6 Python did not produce a usable curve. The initial full run produced an
almost-valid JSON replacement payload that the wrapper rejected. A subsequent
Python-only rerun produced prose plus fenced JSON, which led to wrapper
hardening. The final Python-only rerun then ran until the external subprocess
timeout at 3,600s after llama.cpp had decoded about 45.6K tokens, and produced
no applied edit. Treat this as an agent/harness failure, not as matcher-quality
evidence.

## Interpretation

No run passed the existing `0.70` F1 threshold on the larger hidden set. The
best evidence came from GPT-5.5 Python, with AP 0.562 and hidden-best F1 0.555,
but that is still weak product-matching performance. The large-pairwise rerun
therefore confirms the earlier concern: current approaches are rough heuristic
matchers, not a convincing product entity-resolution solution.

The Qwen3.6 llama.cpp high-thinking path is especially problematic for this
direct-edit harness. Rust produced a fast but low-precision matcher. Python
failed to produce a bounded, applied edit under the current 3,600s subprocess
timeout. Future local-Qwen runs need a stricter output budget or a different
agent protocol before they are useful for this pack.

## Next Benchmark Work

- Add a real entity-resolution lane with tens of thousands of offers and
  clustering/blocking metrics.
- Measure blocking separately from pairwise scoring: candidate-pair reduction,
  pair completeness, pair quality, memory, and offers/s.
- Keep the current pairwise lane as a quality/ranking smoke test, not as
  empirical evidence about production-scale blocking.
