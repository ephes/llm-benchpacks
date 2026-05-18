# Hosted Registry PRD

Status date: 2026-05-18.

This document is the product and implementation direction for the hosted
`llm-benchpacks` registry. It supersedes the static-only hosted archive as the
preferred hosted path. The static `benchpack registry site` export remains a
local/offline review tool and possible temporary read-only fallback, but the
target hosted product is a dynamic Django service.

`homepage` and `nyxmon` are reference implementations for local development and
deployment mechanics only. They are not product dependencies, and their content
models should not shape this service.

## Product Goal

Provide a small curated benchmark registry at
`benchmarks.staging.django-cast.com` where operators can ingest compact
benchmark result bundles, validate them, review them, approve them for
publication, and expose approved results through public web pages and read-only
JSON APIs.

The product should make accumulated local and remote benchmark evidence easier
to inspect and share without turning the service into a raw artifact host, a
benchmark runner, or an unconditional public leaderboard.

## Users

- Operator: imports or uploads compact bundles, inspects validation output,
  approves or rejects submissions, and manages published results.
- Registered submitter: creates an account, verifies email ownership, submits
  compact bundles, and tracks review status for their own submissions.
- Public reader: browses approved benchmark runs, filters rows, reads
  comparison caveats, and downloads compact JSON views.

## First Release Scope

The first dynamic release should prove the ingestion and review loop:

1. Run a local Django development server from this repo.
2. Deploy the Django service to staging with SQLite-backed app state.
3. Let users register accounts, sign in, verify email ownership, and reset
   passwords through normal Django web flows.
4. Send transactional email for account verification, password reset, and
   submission/review notifications.
5. Accept compact bundle uploads from registered users. A web upload may be an
   archive of the existing directory-style bundle format; the server can unpack
   it into temporary process-local storage for validation, then persist compact
   payloads and validation results in SQLite.
6. Validate pending bundles server-side with the existing bundle validator.
7. Store validation state, provenance, run labels, row counts, and compact
   metadata for review.
8. Provide Django admin or a small operator UI for pending submissions.
9. Approve or reject submissions.
10. Publish only approved compact run and result-row data.
11. Serve public browse pages with basic filters.
12. Serve read-only JSON APIs over approved compact data.
13. Expose a health endpoint for local and deployment checks.

Unauthenticated uploads should stay disabled. Self-registration creates a
submitter account, but publication still requires operator approval.

## Non-Goals

- No hosted benchmark execution.
- No raw request/response payload hosting.
- No workspace, task log, verifier artifact, ignored metadata, credential, or
  private prompt hosting.
- No object storage in the first release.
- No unauthenticated upload in the first release.
- No leaderboard ranking until comparability policy is explicit.
- No dependency on the homepage Wagtail app.
- No requirement to deploy PostgreSQL for the first staging release.

## Functional Requirements

### Accounts And Email

- Users can self-register with email and password.
- Email verification is required before a user can submit benchmark results.
- Password reset must work through email.
- Operators can disable or suspend submitter accounts.
- Local development should use Django's console email backend so account and
  submission emails are visible in the dev-server logs. Tests should use the
  in-memory email backend. Neither path should require real SMTP/API
  credentials.
- Staging/production email provider is configurable through deployment secrets.
  Mailgun via AnyMail is an acceptable starting point because existing Django
  deployments already use that pattern, but the product should not hard-code a
  provider into the domain model.
- Transactional email should cover account verification, password reset,
  submission received, validation failed, approved, and rejected events.

### Submission And Validation

- Accept compact bundles, not raw result trees.
- The current CLI bundle is directory-based because it is meant for
  local/offline inspection, diffing, and hash validation. The web submission
  surface does not need users to upload a bare directory; it can accept an
  archive that preserves the bundle directory contents.
- Reuse `benchpack registry bundle validate` semantics for manifest, hash,
  row-shape, metadata-shape, role/path, UTF-8, unlisted-file, and conservative
  secret-scan checks.
- Store validation output in a reviewable form.
- Reject invalid bundles before they can be approved.
- Preserve provenance labels: `self-reported`, `operator-curated`, and
  `independently-reproduced`.
- Detect and surface duplicate hints based on compact run identity and
  `run.jsonl` hashes.
- Associate every non-operator submission with the registered submitter account.
- After successful validation, store approved queryable benchmark data in
  SQLite. The submitted compact JSON payloads, validation results, hashes, and
  row summaries should also be stored in SQLite JSON/text fields where
  practical.

### Review And Publication

- Keep pending submissions private.
- Require an authenticated operator action before publication.
- Publish compact run, row, hardware, run-metadata, comparison, and case-metric
  fields only after approval.
- Preserve enough metadata for readers to understand model artifact, runtime,
  quantization, context/cache settings, pack version, scoring state, and
  provenance.
- Allow rejection without deleting the original pending validation record.

### Public Browse

- List approved runs.
- Filter result rows by pack, case, adapter, model, host, runtime,
  quantization, adapter success, and deterministic scoring state.
- Show comparison caveats when runs differ in comparability anchors.
- Avoid presenting a single global leaderboard in the first release.

### Public API

Initial read-only APIs should cover:

- published run list;
- filtered result rows equivalent to `benchpack registry query`;
- single run summary;
- comparison or case-metric rows for selected runs.

Write APIs should start authenticated only:

- upload a compact bundle archive;
- validate a pending bundle;
- approve or reject a pending submission.

User-facing submission endpoints should require an authenticated, email-verified
account. Do not expose unauthenticated write APIs.

## Local Development

The repo should provide a normal local development workflow for the web app:

- `just dev` should start the Django development server.
- `just migrate` should run Django migrations.
- `just test` should run the repo test suite, including web-app tests once the
  app exists.
- Local development should use SQLite by default.
- Local development should use the console email backend by default; tests
  should use the in-memory email backend.
- Local SQLite state and any transient upload extraction directories should
  live under ignored runtime paths, not under committed `results/*`,
  `registry/site/*`, bundles, or raw artifacts.
- The development server must not require Ollama, llama.cpp, MLX, a benchmark
  endpoint, SSH access, or staging secrets.

Reference only: `homepage` shows one style of project-level Justfile dev/deploy
commands, and `nyxmon` shows a SQLite-backed Django app with local and deployed
settings. The `llm-benchpacks` web app should choose names and layout that fit
this repo instead of copying those projects wholesale.

## Project Layout

Keep the benchmark runner and hosted web app in the same repository, but make
their boundaries explicit.

Proposed layout:

```text
manage.py                    # Django management entrypoint for local/dev/admin use
src/
  benchpack/                 # existing CLI, runner, registry, bundle logic
  benchpack_web/             # Django project package: settings, urls, wsgi/asgi
  benchpack_registry_web/    # Django app: models, admin, views, forms, APIs
templates/
  benchpack_registry_web/
static/
  benchpack_registry_web/
web_runtime/                 # ignored local SQLite/cache/temp extraction, if needed
```

Use `benchpack_web.settings` as the base Django settings package unless an
implementation slice finds a clearer project-local name. The existing Python
package layout already uses `src/`, so the Django project and app should live
under `src/` and be importable through the same packaging configuration as the
runner package.

The web app should import reusable validation and registry helpers from
`benchpack` rather than shelling out to the CLI for core behavior. CLI commands
remain the operator/local artifact tools. Django management commands can wrap
shared Python functions for hosted import and maintenance.

Avoid placing the Django project inside `docs/`, `registry/`, `results/`, or
`benchpacks/`. Those directories already have product meaning.

## Data And Storage

Start with SQLite for hosted app state. The database file must live in a
persistent server-side path outside destructive source sync paths. This matches
the expected early write pattern: operator-authenticated uploads/imports,
validation state changes, and approvals.

The hosted database is application state, not the operator-local
`registry/llm-benchpacks.sqlite` file. The existing local SQLite registry format
can inform the hosted schema and import logic, but the web service owns its own
database lifecycle.

Keep a future PostgreSQL migration path open if public uploads, concurrent
review traffic, or heavier query workloads make SQLite a constraint.

Prefer SQLite over filesystem storage for hosted submission state. SQLite JSON
and text fields should hold the uploaded bundle manifest, compact run metadata,
validation output, hashes, row summaries, and review state. Approved browse and
API responses should come from those SQLite rows.

Filesystem storage should not be the default source of truth. Use it only for
temporary archive extraction during validation, or later for retained uploaded
archives if there is a deliberate audit/retention requirement and the backup
policy covers it. The first implementation should be able to delete extracted
temporary files after validation.

## Deployment Boundary

Deployment should follow the existing repo responsibility split used by other
services:

- `llm-benchpacks` owns product code, Django settings, management commands,
  templates, tests, and local developer commands.
- `ops-library` owns reusable deployment logic: uv-managed Python environment,
  source sync or git checkout, persistent SQLite and runtime directories,
  migrations, collectstatic, transactional email environment variables,
  Granian/systemd, optional worker unit, health checks, and Traefik dynamic
  config.
- `ops-control` owns private host inventory, secrets, hostnames, ports, email
  provider credentials/sender settings, and a thin playbook that calls the
  `ops-library` role.

Reference only: `homepage` demonstrates the thin app-repo wrapper into
`ops-control`, while `nyxmon` demonstrates SQLite-backed Django deployment with
Granian/systemd and Traefik. Those examples guide mechanics, not product
semantics.

Once the dynamic deployment target exists, `just deploy-staging` in this repo
should delegate to that target. The existing static deploy shortcut can remain
as an explicitly named fallback if it is still useful.

## Static Export Role

`benchpack registry site` remains useful for local/offline inspection and as a
temporary static fallback. Do not extend the static export into upload,
moderation, hosted API, or leaderboard behavior. Those belong to the Django
service.

## Open Questions

- Should validation run synchronously in the request cycle for small bundles, or
  through a lightweight background worker from the start?
- Should account registration use Django's built-in auth views plus a small
  email-verification layer, or use `django-allauth` from the first slice?
- Which email provider should staging use initially, and what sender/domain
  should appear in account and submission notifications?
- What upload size limits, per-account submission rate limits, and CSRF posture
  should apply to the compact bundle upload endpoint?
- Which exact JSON API shape should be considered stable enough for external
  consumers?
- Should the service retain uploaded bundle archives for audit, or persist only
  normalized compact payloads and validation results in SQLite?
- What backup and retention policy should be attached to the hosted SQLite
  database?
