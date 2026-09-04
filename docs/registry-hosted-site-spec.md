# Registry Hosted Site Spec

Status date: 2026-05-12.

Update 2026-05-13: this static-only spec is no longer the preferred hosted
architecture. It remains as a temporary read-only fallback and local/offline
publication path. The preferred direction is the dynamic Django service in
[`registry-hosted-django-spec.md`](registry-hosted-django-spec.md), deployed
through `ops-library` and `ops-control`.

Update 2026-09-02: the temporary static fallback is deployed at
<https://benchmarks.staging.django-cast.com/>. The current published snapshot has
108 runs, including 43 Django/Electron-wrap rows and 17 Hetzner RTX
4000 Gemma/Qwen strict-GGUF runs, and is served as exactly
`index.html`, `report.md`, and `snapshot.json` by a loopback-only service behind
Traefik HTTPS. The dynamic Django service remains the preferred hosted target.
The static view keeps all filter state in the URL, includes a direct Django
Resume one-shot view, renders explicit outcomes, uses canonical human-readable
host/model facets, retains raw identifiers in `snapshot.json`, and links the
raw Markdown report without duplicating it below the rendered tables.

This spec defines the first hosted consumption path for `llm-benchpacks`
benchmark results. The goal is a small public or semi-public benchmark archive
published at the v1 staging hostname
`benchmarks.staging.django-cast.com` without turning result submission, trust
review, or leaderboard ranking into the first slice.

## Context

The repository already has the local substrate for a hosted archive:

- `benchpack registry import` indexes compact result directories into SQLite.
- `benchpack registry report` renders registry-backed Markdown reports.
- `benchpack registry site` exports `index.html`, `report.md`, and
  `snapshot.json` from indexed rows.
- `benchpack registry bundle create`, `validate`, and `import` provide compact
  bundle export and offline ingestion with hash checks, provenance labels, and
  bounded artifact selection.

This spec defined the original static sharing workflow. The dynamic Django
service in [`registry-hosted-django-spec.md`](registry-hosted-django-spec.md)
is now the preferred hosted sharing workflow; this static path remains a
temporary operator-curated fallback.

## Naming

Use `benchmarks.staging.django-cast.com` as the v1 staging hostname. It is
clearer for a result archive than an `llm.*` name, which can be confused with an
inference API. The existing deployment environment already uses
`*.staging.django-cast.com` hostnames such as
`homepage.staging.django-cast.com`, so staging under that domain fits current
ops conventions.

For a later stable public hostname, prefer a benchmark-specific name such as
`benchmarks.wersdoerfer.de` or `llm-bench.wersdoerfer.de` over
`llm.wersdoerfer.de`, unless the site becomes a broader LLM service landing
page rather than a benchmark archive.

## Version 1 Scope

Version 1 is a static, curated registry site:

1. Select result directories that are already safe to summarize.
2. Create compact bundles when results need to cross machine or repo
   boundaries.
3. Validate bundles before ingestion.
4. Import result dirs or bundles into a local SQLite registry.
5. Export the static site with `benchpack registry site`.
6. Deploy the static site output to the staging hostname.

The generated site should be read-only. It should not require a database,
running Python service, user accounts, background workers, or direct access to
raw benchmark artifacts on the public host.

Representative local build flow:

```sh
uv run benchpack registry bundle create \
  --out bundles/<campaign-slug> \
  --provenance operator-curated \
  <result-dir> [<result-dir> ...]

uv run benchpack registry bundle validate bundles/<campaign-slug>

uv run benchpack registry bundle import \
  --db registry/llm-benchpacks.sqlite \
  bundles/<campaign-slug>

uv run benchpack registry site \
  --db registry/llm-benchpacks.sqlite \
  --out registry/site \
  --force
```

Direct local imports are also acceptable when the source result directories are
already on the same machine:

```sh
uv run benchpack registry import \
  --db registry/llm-benchpacks.sqlite \
  <result-dir> [<result-dir> ...]
```

## Content Policy

Version 1 should publish only compact, report-facing artifacts:

- normalized `run.jsonl` rows;
- optional `hardware.json`;
- optional `run-metadata.json`;
- safe patch/model-call summary artifacts only when the existing bundle
  validator accepts them;
- generated static `index.html`, `report.md`, and `snapshot.json`.

Do not publish raw request/response payloads, workspaces, task logs, verifier
artifacts, credentials, bearer tokens, private prompts, or ignored
`metadata/*.json` files. Result dirs under `results/*` remain generated local
artifacts unless a separate curation decision intentionally publishes their
compact bundle or static registry projection.

## Deployment Alignment

`~/projects/homepage` deploys through ops-control:

- staging: `just deploy-staging`;
- production: `just deploy-production`;
- the deploy recipes call `../ops-control` Ansible playbooks.

The hosted registry site should not initially be embedded in the homepage
Django/Wagtail app. It is a static artifact produced by this repository and
served by deployment infrastructure. The v1 deployment path belongs in
`ops-control` and should provide:

- a static document root behind the existing staging reverse proxy;
- a small service directory owned by a dedicated user;
- HTTPS hostname routing for `benchmarks.staging.django-cast.com`;
- an operator-only deploy command that syncs a local generated `registry/site/`.

The deployment slice belongs in `ops-control`. This repository owns the
registry data contract, bundle/static-site generation, and curation workflow.
For operator ergonomics, this repository may expose homepage-style Justfile
shortcuts that prefer an already complete `registry/site/` static export, fall
back to regenerating it from the local SQLite registry when available, and then
delegate to the ops-control static-site deploy target. If neither a complete
static export (`index.html`, `report.md`, and `snapshot.json`) nor the local
registry DB exists, the shortcut should fail with registry import and bundle
import instructions instead of starting a deployment. Those shortcuts must keep
the deployment input as generated static files only.

## Explicit Non-Goals For Version 1

- No public upload form.
- No unauthenticated bundle submission endpoint.
- No hosted database or API.
- No object storage for raw artifacts.
- No automatic import of arbitrary user-provided bundles.
- No leaderboard ranking.
- No claim that unrelated runs are comparable just because they appear on the
  same site.
- No mutation of benchmark result directories during publication.

## Relationship To Dynamic Service

The dynamic Django service is now the path for hosted submission, quarantine,
review, public browse pages, and APIs. If the static archive is used before
that service exists, treat it as a temporary read-only publication path only.
Do not extend the static archive into upload, moderation, hosted API, or
leaderboard behavior.

## Static Fallback Requirements

When the static fallback is used:

- A local operator must be able to produce `registry/site/` from curated results
  without contacting benchmark endpoints or reading raw artifacts.
- The static site must include enough provenance to distinguish self-reported,
  operator-curated, and independently reproduced bundles.
- Static filters must round-trip through URL query parameters so filtered views
  are shareable. Django Resume one-shot results must have a direct quick link,
  and pass/fail/interrupted outcomes must be visible without horizontal
  scrolling.
- Host/model facets must use canonical indexed identities and readable labels;
  raw hostname, platform, model, artifact, and quantization values remain
  available for provenance. Wide tables must use the full viewport and retain
  accessible horizontal overflow at narrow widths.
- Deployment work must remain separate from the homepage Django app.
- Hosted upload/review, APIs, and leaderboard policy remain out of scope for
  the static fallback and belong to the dynamic Django service track.
