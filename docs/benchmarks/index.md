# Benchmarks

This repository currently tracks two benchmark families.

## Product-Offer Matching

[`product-offer-matching`](product-offer-matching/index.md) is a real-data
coding-agent benchmark where the agent writes deterministic code to cluster
merchant offers into products. The current fixture is derived from the
PriceRunner Product Classification and Clustering dataset.

This benchmark is a `benchpack run` pack under:

```text
benchpacks/product-offer-matching/
```

## Django Resume Electron Wrap

[`django-resume-electron-wrap`](django-resume-electron-wrap/index.md) is a hard
one-shot agent benchmark where an agent wraps a real `django-resume` checkout
in an Electron shell from scratch and the harness verifies the generated app.

This benchmark is currently driven by:

```text
scripts/run-agent-wrap-oneshot
```

It is not yet a `benchpack run` pack because it operates on an arbitrary
external source checkout rather than a pack-owned fixture.
