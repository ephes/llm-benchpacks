# Product-Offer PriceRunner Rerun - 2026-06-28

This rerun replaced the old WDC pairwise fixture with a PriceRunner-derived
offer-clustering fixture from the Kaggle
`lakritidis/product-clustering-matching-classification` dataset mirror and the
equivalent UCI archive.

Fixture shape:

- 10,003 visible labeled training offers from 3,709 product clusters.
- 25,308 hidden-test offers from 9,524 product clusters.
- 20,000 hidden eval pairs for precision/recall curves: 5,000 positive and
  15,000 negative.

Post-review note: these completed GPT-5.5 metrics were produced before the
fixture generator was tightened to shuffle train/test rows before local
`offer_id` assignment. Treat the numbers below as pre-fix calibration evidence,
not the current comparable baseline.

Validation:

- `uv run pytest`: 613 passed in 35.09s.

Completed benchmark:

- Result directory: `results/2026-06-28-product-offer-pricerunner-pi-gpt55`
- Agent path: Pi direct-edit external-agent wrapper.
- Model: `openai-codex/gpt-5.5`, `--thinking off`.
- Both cases returned valid source edits and verifier artifacts, but neither
  passed the cluster thresholds.

| case | pass | B-cubed P/R/F1 | pairwise cluster P/R/F1 | eval-pair AP | best eval-pair F1 | PR points | offers/s | peak RSS MB | combined |
|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| `cluster-pricerunner-python` | no | 0.427 / 0.795 / 0.556 | 0.004 / 0.717 / 0.008 | 0.923 | 0.837 | 11,290 | 823.0 | 385.2 | 48.554 |
| `cluster-pricerunner-rust` | no | 0.124 / 0.938 / 0.219 | 0.002 / 0.929 / 0.004 | 0.915 | 0.858 | 12,477 | 1,457.1 | 234.2 | 37.077 |

Interpretation:

- The pair-score rankings are strong on the fixed eval-pair sample.
- The submitted clusters are not usable: both implementations merge far too
  many offers into very large clusters, yielding high recall but extremely low
  pairwise cluster precision.
- This confirms the new benchmark exposes the gap between pair scoring and
  actual product clustering.

Qwen3.6 high-thinking attempt:

- Started a local `llama-server` with Qwen3.6 27B Q4_K_M, 131k context, q8 KV
  cache, reasoning enabled, and Pi `--thinking high`.
- The first `cluster-pricerunner-python` case was interrupted after about 22
  minutes because the model had decoded more than 25,000 tokens and was still
  streaming without returning the required JSON edit payload.
- No verifier artifact was produced for the Qwen attempt.

Pi goal judgment:

```text
REACHED

The benchmark now uses Product Classification/Clustering data equivalent to the
requested Kaggle dataset, was converted into the new clustering task, tests
passed, and benchmark runs completed for Python and Rust with reported results.

Must-do remaining items: none.
```
