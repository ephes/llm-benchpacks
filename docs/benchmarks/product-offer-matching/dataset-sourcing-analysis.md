# Dataset Sourcing Analysis: Price- and Image-Bearing Product Matching

Status: analysis / decision input. No implementation committed. Companion to
decision [D-034](../../decisions.md) (PriceRunner data lacks price and image
signals).

## Problem statement

The current `product-offer-matching` pack is derived from the PriceRunner
Product Classification and Clustering dataset. That dataset is **text-only**:
its offer fields are product title, merchant id, and category id/label, plus a
gold cluster id/label. It carries no price and no image, and neither is
recoverable from the source (see D-034).

Price and images are two of the strongest signals real product-matching systems
use:

- **Price**: offers for the same physical product cluster tightly in price; a
  large price gap is strong evidence two offers are *not* the same item.
- **Images**: visual similarity disambiguates variants (colour, bundle,
  storage size, generation) that inconsistent titles describe poorly.

To benchmark price-aware or multimodal matching we need a dataset that carries
both. This document compares the candidate ways to obtain one and recommends a
direction. It assumes the intended use is a **research/benchmark sample**, not a
production price-comparison service, and that the raw third-party data is **not
redistributed** — only derived, anonymised fixtures and the generating scripts
live in the repo (the same pattern the current PriceRunner pack already uses).

## Candidate sources

1. **Scrape a price-comparison site** (idealo.de, billiger.de, geizhals.at, or
   similar). These sites have already matched merchant offers onto product
   pages, so a product page is effectively a labelled cluster with price and
   image per offer.
2. **Extract from WebDataCommons (WDC) / Common Crawl** schema.org
   `Product`/`Offer` markup. This is the provenance of the WDC Products
   benchmark the literature already cites.
3. **Reuse an existing entity-matching benchmark with price** (Abt-Buy,
   Amazon-Google). Text + price, but no images.
4. **Synthesise price/images onto the existing PriceRunner fixture.** Listed for
   completeness; rejected up front (a fabricated signal measures "can the model
   use the synthetic field", not real-world matching) and not analysed further.

The substantive comparison is between option 1 (scrape) and option 2 (WDC),
because only those two plausibly deliver price *and* images at the needed shape.

## Evaluation dimensions

Each option is judged against:

- **Signal completeness** — does it carry price AND image AND varied per-merchant
  titles (the matching difficulty)?
- **Label quality** — are gold clusters available, and how trustworthy?
- **Popularity / category control** — can we target popular products per category
  deterministically?
- **Extraction effort** — engineering work to a first usable sample.
- **Anti-bot / access friction** — how hard is it to actually fetch the data?
- **Reproducibility** — can the fixture be regenerated identically later?
- **Legal / ToS exposure** — redistribution and database-right considerations.
- **Maintenance** — how fast does the pipeline rot?

## Option 1 — Scrape a price-comparison site

### Pros

- **Matching is pre-solved.** Each product page is a ready-made gold cluster; the
  merchant offer list gives cluster members for free. No need to build or trust a
  separate labelling process.
- **All target signals on one page.** Product pages typically expose title, an
  offer/price list per merchant, a product image, brand, and a category
  breadcrumb — exactly the schema we want.
- **Structured extraction.** These sites generally emit schema.org JSON-LD
  (`Product`, `Offer`, `AggregateOffer`, `Brand`, `BreadcrumbList`), so parsing
  can target structured markup rather than brittle HTML. *Must be verified per
  site* — see open questions.
- **Popularity and category control — the decisive advantage.** Category listing
  pages are sorted by popularity/bestseller, so "top N products per category"
  falls out automatically and deterministically. WDC cannot offer this.
- **Small scale is enough.** A few hundred to a few thousand products across ~10
  categories is plenty for a benchmark sample; this keeps request volume low.
- **Fresh, real-world messiness.** Live merchant data reflects current
  title/price noise, which is what the benchmark is meant to stress.

### Cons

- **Anti-bot friction is real and rising.** These are commercial sites with bot
  detection, rate limiting, Cloudflare-style challenges, and increasingly
  JS-gated content. idealo (Axel Springer) is the most aggressively defended;
  geizhals and billiger are reportedly somewhat lighter but still defended.
  Low-rate, polite fetching at sample scale mitigates but does not eliminate this.
- **Reproducibility is weak.** Scraper output is not stable: site markup,
  pagination, and anti-bot behaviour change, so a re-run later yields different or
  empty results. A benchmark fixture regenerated from a live scrape silently
  drifts. **Mitigation:** commit the derived, anonymised fixture (as the
  PriceRunner pack already does) plus a captured snapshot/manifest, so the
  committed fixture is the stable artifact and the scraper is only the
  provenance. "Scripts only, no data" would *break* the reproducibility the repo
  currently has.
- **Per-merchant title variance is unverified.** The core matching signal depends
  on offers carrying *different* merchant-written titles. If the site normalises
  every offer to one canonical title, the clustering task becomes trivial and the
  dataset is weak. This must be checked on a real page before building anything.
- **Legal / ToS exposure (acknowledged, accepted by stakeholder for this use).**
  ToS prohibit automated access; the EU sui generis **database right** (German
  UrhG §87a–e; Austrian equivalent) protects exactly the matched offer→product
  aggregation. The chosen mitigation is: sample only, do not redistribute raw
  content, commit only derived/anonymised fixtures and scripts, and do not build a
  competing price-comparison service. Risk is reduced, not zero; this is a
  stakeholder-accepted residual risk, not a clean bill of health.
- **Maintenance cost.** The scraper is coupled to each site's markup and defences
  and will need upkeep to keep running; treat it as provenance, not a load-bearing
  pipeline.
- **Image handling.** Images carry separate copyright; storing/redistributing
  them is more exposed than storing image URLs or derived embeddings/hashes.

## Option 2 — WebDataCommons / Common Crawl schema.org extraction

### Pros

- **License-clean provenance.** Common Crawl is a public web snapshot; WDC
  publishes pre-extracted product data. No live-site anti-bot war and far less
  database-right exposure. This is the established academic path for this task.
- **Reproducible.** WDC/Common Crawl artifacts are frozen public files, so a
  re-run regenerates the same sample — the property the scrape route lacks.
- **Scale and breadth.** Far more products, merchants, and categories than a
  hand-scoped scrape, drawn from across the web rather than one aggregator.
- **Already in the literature.** WDC Products is cited in `literature.md`, so
  using it keeps provenance consistent with prior benchmark framing.

### Cons

- **Price/image coverage is incidental, not first-class.** The curated WDC
  Products matching tables are built around title/brand/description/spec-table.
  Price and image are not the focus and are **sparsely populated**, so the curated
  benchmark may not actually deliver the two signals we need. *Coverage must be
  measured, not assumed.*
- **Raw extraction is heavy.** To get price + image reliably you likely drop to
  the raw WDC schema.org Product extraction — large gzipped n-quads at
  terabyte-ish scale. You download tens of GB, parse, filter by language, group by
  product identifier, and dedup before you have a usable sample. Significant data
  engineering up front.
- **No popularity signal.** WDC/Common Crawl has no notion of "most popular
  product"; you get whatever was crawled. Targeting popular items per category is
  effectively impossible.
- **No clean category taxonomy.** schema.org `category` is freeform merchant
  text, inconsistent across sites; building a clean 10-category split is its own
  normalisation problem.
- **Label quality varies.** Clusters depend on shared product identifiers
  (GTIN/MPN/sku) which are unevenly present and sometimes wrong, so gold-cluster
  quality is more variable than an aggregator's curated product page.

## Option 3 — Existing benchmark with price (Abt-Buy / Amazon-Google)

- **Pros:** Ready-made, clean, reproducible, license-clear, has price, widely
  used and comparable to prior work. Lowest effort of all options.
- **Cons:** **No images** (text + price only), so it cannot support a multimodal
  lane; small and somewhat saturated; two-source structure differs from the
  many-merchant clustering shape of the current pack. Good as a *price-aware
  text* lane, insufficient for the multimodal goal.

## Comparison summary

| Dimension | Scrape (idealo/geizhals/billiger) | WDC / Common Crawl | Abt-Buy / Amazon-Google |
|---|---|---|---|
| Price signal | Yes, per offer | Sparse / incidental | Yes |
| Image signal | Yes, per product | Sparse / incidental | No |
| Per-merchant title variance | Likely (verify) | Yes | Limited (2 sources) |
| Gold cluster labels | Pre-solved per page | From identifiers, variable | Yes |
| Popularity/category control | Yes (decisive) | No | No |
| Extraction effort to first sample | Low–moderate | Moderate–high | Very low |
| Anti-bot / access friction | High | Low | None |
| Reproducibility | Weak (needs snapshot) | Strong | Strong |
| Legal / ToS exposure | Higher (accepted) | Low | Low |
| Maintenance | Higher | Low | Low |

## Key tensions

- **Signal completeness vs reproducibility.** Scraping is the only option that
  cleanly delivers price + image + popularity, but it is the weakest on
  reproducibility and access. WDC inverts this. The reproducibility gap is
  *closable* by committing the derived fixture + snapshot; the WDC signal-coverage
  gap may not be closable at all if price/image are too sparse.
- **Effort is non-obvious.** Intuition says "use the public dataset, scraping is
  hard." But for *this* goal (price + image + popular-per-category, small sample)
  WDC's wrangling and missing popularity can make it *more* total work to a usable
  result than a low-rate scrape of a JSON-LD-emitting aggregator.
- **The legal concern shifted, not vanished.** Stakeholder accepts the risk for a
  non-redistributed research sample. That makes scraping viable to *consider*, but
  the residual risk and maintenance cost remain real cons, not zeros.

## Open questions (resolve before building)

1. **Per-merchant title variance** on a real product page — is the matching
   signal actually present, or are offers normalised to one title? (Single-page
   probe answers this.)
2. **JSON-LD completeness** per candidate site — do `Product`/`Offer` blocks
   include price, image, merchant, and breadcrumb category as structured fields?
3. **WDC price/image coverage** — what fraction of WDC product offers actually
   carry a usable price and image? (Decides whether option 2 is even feasible.)
4. **Reproducibility contract** — confirm the fixture (not just scripts) is
   committed, and define the snapshot/manifest format that pins a regenerable
   sample.
5. **Image storage policy** — store URLs only, perceptual hashes, or derived
   embeddings rather than raw images.

## Recommendation

1. **Pilot the scrape route** on the friendliest aggregator first (**geizhals.at**
   or **billiger.de** — cleaner JSON-LD and lighter defences than idealo). Start
   with a single-page probe to settle open questions 1 and 2 before any build.
2. **Commit the derived, anonymised fixture plus a snapshot/manifest**, never raw
   HTML or images — mirroring the existing PriceRunner pack so reproducibility is
   preserved despite a live source.
3. **Time-box a parallel WDC coverage check** (open question 3). If WDC price+image
   coverage turns out to be dense enough, prefer it — it is reproducible and
   license-clean. If it is as sparse as expected, the scrape pilot is the path.
4. **Keep Abt-Buy / Amazon-Google in reserve** as a low-effort price-aware *text*
   lane if the multimodal goal is deferred.

Net: scraping is the lower-effort path to the specific signals we want and the
only one giving popularity/category control, provided the derived fixture is
committed for reproducibility; WDC is the safer, reproducible fallback whose
viability hinges entirely on measured price/image coverage.
