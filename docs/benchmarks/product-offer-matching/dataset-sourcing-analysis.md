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
| Per-merchant title variance | Confirmed (billiger) | Yes | Limited (2 sources) |
| Gold cluster labels | Pre-solved per page (billiger product_id) | From identifiers, variable | Yes |
| Popularity/category control | Yes (decisive) | No | No |
| Extraction effort to first sample | Low–moderate | Moderate–high | Very low |
| Anti-bot / access friction | High (idealo/geizhals); low (billiger) | Low | None |
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

## Feasibility probe: billiger.de (2026-06-30)

A single-page probe (a handful of polite, unauthenticated `curl` requests)
tested the scrape route against the candidate aggregators.

**Access.** `geizhals.at` is behind a Cloudflare managed challenge
(`cf-mitigated: challenge`); plain HTTP requests are blocked and a real headless
browser would be required. `billiger.de` serves full HTML to a plain request
(HTTP 200, no challenge) and is the practical target.

**Structure.** billiger.de maps almost directly onto the existing pack shape:

- `/baseproducts/<id>` is the product model (schema.org `ProductGroup`) holding
  variant `Product`s; each variant carries a normalised name, brand, a CDN image
  URL, a stable billiger **product_id**, a GTIN13, and an `AggregateOffer` with
  low price and `offerCount`.
- `/products/<id>` and `/pricelist/<id>` expose the individual merchant offers.
- A base64 `data-econda-clickout-params` payload per offer decodes to structured
  fields: product id, normalised name, category id + hierarchical category path,
  brand, shop id, shop name, and per-offer price.

**Key confirmation — the matching signal is present.** For one identical variant
(Galaxy S24 Ultra, 512 GB, Titanium Black) merchants wrote genuinely different
titles, e.g. `Samsung Galaxy S24 Ultra 512GB 12RAM S928B/DS Titanium Black`
vs. `Samsung Galaxy S24 Ultra S928B 5G 512GB titanium black EU - Schwarz/Silber`
vs. an Amazon listing packing camera/S-Pen/warranty text. Per-offer prices for
that same variant ranged roughly €819–€1439. Titles are not normalised to one
canonical string, so the clustering task is not trivialised.

**Recoverable per-offer fields** (versus a typical merchant feed CSV):

| Feed field | Recoverable | Source |
|---|---|---|
| Merchant title (raw, varied) | Yes | offer rows — the matching signal |
| Price (per merchant) | Yes | clickout payload + offer row |
| Shipping cost | Yes | offer row |
| Shop name + id | Yes | `/shops/<id>`, clickout payload |
| Condition (new/used) | Yes | offer-list attribute |
| Brand | Yes | clickout payload + JSON-LD |
| GTIN/EAN | Yes (variant level) | JSON-LD `gtin13` — noisy auxiliary attribute, not the cluster key |
| Image | Yes (variant level) | JSON-LD CDN URL |
| billiger category | Yes | clickout payload: hierarchical path + ids |
| Cluster label | Yes | billiger `product_id` (variant) — the reliable key |
| Offer description (separate field) | Partial | no distinct field; titles are description-rich |
| Merchant raw category (pre-classification) | No | consumed internally, not re-exposed |
| Merchant deeplink (real shop URL) | No | behind a tokenised clickout redirect |

**Caveats.**

- The category billiger exposes is the **output of billiger's own text
  classifier**, not a raw merchant signal. It is usable as a clean `category_label`
  (as PriceRunner's is), but it must not be treated as ground truth; using it as a
  feature means feeding models another model's predictions.
- **GTIN is not a reliable cluster key.** Merchant-feed GTIN/EAN values are often
  wrong, so they should be treated as a noisy auxiliary attribute, not the gold
  label. billiger's own variant `product_id` — the output of billiger's matching
  pipeline — is the reliable cluster key and is what the fixture should use.
- There is **no distinct offer-description field**; merchant titles carry
  description-like content but a separate description is not publicly rendered.
- The full offer list is **lazy-loaded** (≈4–8 offers in the initial HTML versus
  an `offerCount` of 13–19), so recovering every offer per product needs the
  segment endpoint. For a benchmark sample this is likely unnecessary — even 4–8
  offers per cluster exceeds PriceRunner's ≈2.7 average.

**Net.** billiger.de yields **more than the PriceRunner CSV had** — it adds price,
image, GTIN, shipping, condition, and per-offer shop on top of varied titles and a
category. The two fields that cannot be cleanly recovered are the merchant's
separate description and the merchant's raw (pre-classification) category.

## Pilot result (2026-06-30)

A pilot scraper
(`benchpacks/product-offer-matching/scripts/scrape-billiger-pilot.py`) ran across
five categories — smartphones, TVs, headphones, laptops, and coffee machines
(`--searchstrings`, 12 baseproducts × 3 variants each, polite per-category request
cap). Sample output:
`benchpacks/product-offer-matching/pilot-data/billiger-pilot-offers.csv`. A
companion viewer (`scripts/build-billiger-viewer.py`) renders the clusters as a
static HTML page for visual inspection.

Results:

- **1,280 offers across 158 clusters (3 singletons), ~8.1 offers/cluster, 100%
  price and image coverage.** The initial HTML carries ~8–10 offers per variant,
  so the lazy-load segment endpoint (open question 3) is **not needed** for a
  useful fixture.
- Each row has: raw merchant title, shop, price, brand, category label, image URL,
  the source search term, and the billiger variant `product_id` as the cluster key.
- **Cluster quality is high but not perfect.** A title-vs-label model-token scan
  found exactly one cross-model mislabel in the whole sample (~0.08%): an ebay
  offer titled `Samsung Galaxy S25 Ultra - 256 GB - Titanium Black` sits in the
  `Galaxy S26 Ultra 256 GB Black` cluster (`cluster_id` 5566514751). Billiger's
  matching (or the merchant feed) attached an S25 offer to the S26 product, and
  this propagates into the gold label. Price-based outlier checks miss it because
  S25/S26 prices nearly coincide. Takeaway: billiger gold clusters carry rare but
  real label noise, so a production fixture builder needs a validation/filter pass
  (e.g. flag offers whose model token is disjoint from the cluster label); the
  pilot CSV is left as a faithful raw scrape and deliberately keeps this case.
- **Title noise is real and useful.** For the iPhone 17 256 GB Nebelblau cluster,
  titles range from a terse `iPhone 17` (Moblify) to
  `Apple iPhone 17 256GB Blau Blue Nebelblau NEU nur E-SIM, kein Sim-Kartenschacht`
  (ebay) to `Apple iPhone 17 (256 GB, Mist Blue, 6.30", Dual SIM, 5G)` (Galaxus,
  using "Mist Blue" where billiger says "Nebelblau").
- **Concrete evidence for the multimodal motivation.** Some merchants (e.g.
  Moblify) list a bare `iPhone 17` identically across the blue/white/lavender
  clusters; title-only matching cannot disambiguate these, but price and image can.

Sourcing caveat: broad appliance search terms (e.g. `waschmaschine`, `kühlschrank`)
resolve to a category-overview page with few `/baseproducts/` links; concrete
product terms (`smartphone`, `laptop`, `kaffeevollautomat`, …) return flat product
lists and are the ones to use.

This confirms the scrape route end-to-end and validates that real billiger.de data
makes a harder, signal-richer matching task than the title-only PriceRunner fixture.

## Open questions (resolve before building)

1. ~~**Per-merchant title variance**~~ — *resolved by the probe: present and
   genuinely noisy on billiger.de.*
2. ~~**JSON-LD / markup completeness**~~ — *resolved: price, image, GTIN, brand,
   shop, and category are all recoverable from billiger.de (see table above).*
3. ~~**Full offer-list extraction**~~ — *resolved by the pilot: initial HTML
   carries ~10 offers per cluster, enough for a fixture; the lazy-load segment
   endpoint is only needed if much deeper offer coverage is later required.*
4. **WDC price/image coverage** — what fraction of WDC product offers actually
   carry a usable price and image? (Decides whether option 2 remains a fallback.)
5. **Reproducibility contract** — confirm the fixture (not just scripts) is
   committed, and define the snapshot/manifest format that pins a regenerable
   sample.
6. **Image storage policy** — store URLs only, perceptual hashes, or derived
   embeddings rather than raw images.
7. **Gold-label validation pass** — the pilot found ~0.08% cross-model label noise
   in billiger gold clusters (an S25 offer in an S26 cluster). The production
   fixture builder should validate/flag offers whose model token is disjoint from
   the cluster label, and decide whether to drop them or keep them as realistic
   label noise.

## Recommendation

1. **Pilot the scrape route on billiger.de** — the probe confirmed it as the
   practical target (geizhals.at is behind a Cloudflare challenge; idealo is the
   most defended). The remaining build-blocker is open question 3: confirm the
   lazy-load offer-segment endpoint, or accept the initial-HTML 4–8 offers per
   cluster.
2. **Commit the derived, anonymised fixture plus a snapshot/manifest**, never raw
   HTML or images — mirroring the existing PriceRunner pack so reproducibility is
   preserved despite a live source.
3. **Use billiger's variant `product_id` as the cluster key** — it is the output
   of billiger's matching pipeline and far more reliable than merchant-feed GTINs,
   which are often wrong (keep GTIN only as a noisy auxiliary attribute). Keep
   billiger's category only as a `category_label`, not as ground truth (it is a
   classifier output).
4. **Time-box a parallel WDC coverage check** (open question 4) as the
   reproducible, license-clean fallback if the scrape route is later abandoned.
5. **Keep Abt-Buy / Amazon-Google in reserve** as a low-effort price-aware *text*
   lane if the multimodal goal is deferred.

Net: scraping is the lower-effort path to the specific signals we want and the
only one giving popularity/category control, provided the derived fixture is
committed for reproducibility; WDC is the safer, reproducible fallback whose
viability hinges entirely on measured price/image coverage.
