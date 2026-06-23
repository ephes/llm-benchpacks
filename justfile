# llm-benchpacks operator shortcuts

OPS_CONTROL := env_var_or_default("OPS_CONTROL", "/Users/jochen/projects/ops-control")
PROJECTS_ROOT := env_var_or_default("PROJECTS_ROOT", "/Users/jochen/projects")
BENCHMARKS_REGISTRY_DB := env_var_or_default("BENCHMARKS_REGISTRY_DB", "registry/llm-benchpacks.sqlite")
BENCHMARKS_SITE_OUT := env_var_or_default("BENCHMARKS_SITE_OUT", "registry/site")

default:
    @just --list

registry-site:
    #!/usr/bin/env bash
    set -euo pipefail
    test -f "{{BENCHMARKS_REGISTRY_DB}}" || (echo "Missing registry DB: {{BENCHMARKS_REGISTRY_DB}}"; exit 1)
    mkdir -p "$(dirname "{{BENCHMARKS_SITE_OUT}}")"
    uv run benchpack registry site \
      --db "{{BENCHMARKS_REGISTRY_DB}}" \
      --out "{{BENCHMARKS_SITE_OUT}}" \
      --force

site: registry-site

deploy-staging:
    #!/usr/bin/env bash
    set -euo pipefail

    required_files=(index.html report.md snapshot.json)

    site_complete() {
      local file
      for file in "${required_files[@]}"; do
        [[ -f "{{BENCHMARKS_SITE_OUT}}/${file}" ]] || return 1
      done
      return 0
    }

    print_missing_site_help() {
      {
        echo "No complete generated benchmark site found."
        echo "Site directory: {{BENCHMARKS_SITE_OUT}}"
        echo "Registry DB: {{BENCHMARKS_REGISTRY_DB}} (missing)"
        echo ""
        echo "Expected generated static files:"
        for file in "${required_files[@]}"; do
          echo "  - {{BENCHMARKS_SITE_OUT}}/${file}"
        done
        echo ""
        echo "Create or import a curated registry first, then render or deploy the site:"
        echo "  uv run benchpack registry import --db {{BENCHMARKS_REGISTRY_DB}} <result-dir>..."
        echo "  uv run benchpack registry bundle validate <bundle-dir>"
        echo "  uv run benchpack registry bundle import --db {{BENCHMARKS_REGISTRY_DB}} <bundle-dir>..."
        echo "  just registry-site"
        echo "  just deploy-staging"
        echo ""
        echo "If {{BENCHMARKS_SITE_OUT}} already exists, ensure it contains index.html, report.md, and snapshot.json."
      } >&2
    }

    deploy_site() {
      test -d "{{OPS_CONTROL}}" || (echo "ops-control not found at {{OPS_CONTROL}}"; exit 1)
      test -f "{{OPS_CONTROL}}/justfiles/deploy.just" || (echo "Missing ops-control deploy justfile at {{OPS_CONTROL}}/justfiles/deploy.just"; exit 1)
      if ! (cd "{{OPS_CONTROL}}" && just --summary 2>/dev/null | tr ' ' '\n' | grep -Fxq deploy-benchmarks-static); then
        echo "Missing ops-control recipe: deploy-benchmarks-static in {{OPS_CONTROL}}/justfiles/deploy.just" >&2
        echo "Install or land the ops-control static benchmarks deploy target before using this fallback deploy shortcut." >&2
        exit 1
      fi
      site_source="$(cd "{{BENCHMARKS_SITE_OUT}}" && pwd)"
      cd "{{OPS_CONTROL}}"
      PROJECTS_ROOT="{{PROJECTS_ROOT}}" \
      BENCHMARKS_STATIC_SITE_SOURCE="${site_source}" \
      just deploy-benchmarks-static
    }

    if site_complete; then
      echo "Using existing generated benchmark site at {{BENCHMARKS_SITE_OUT}}."
      deploy_site
      exit 0
    fi

    if [[ -f "{{BENCHMARKS_REGISTRY_DB}}" ]]; then
      test -d "{{OPS_CONTROL}}" || (echo "ops-control not found at {{OPS_CONTROL}}"; exit 1)
      test -f "{{OPS_CONTROL}}/justfiles/deploy.just" || (echo "Missing ops-control deploy justfile at {{OPS_CONTROL}}/justfiles/deploy.just"; exit 1)
      if ! (cd "{{OPS_CONTROL}}" && just --summary 2>/dev/null | tr ' ' '\n' | grep -Fxq deploy-benchmarks-static); then
        echo "Missing ops-control recipe: deploy-benchmarks-static in {{OPS_CONTROL}}/justfiles/deploy.just" >&2
        echo "Install or land the ops-control static benchmarks deploy target before generating the static site for deploy." >&2
        exit 1
      fi
      echo "Generating benchmark site from {{BENCHMARKS_REGISTRY_DB}} into {{BENCHMARKS_SITE_OUT}}."
      mkdir -p "$(dirname "{{BENCHMARKS_SITE_OUT}}")"
      uv run benchpack registry site \
        --db "{{BENCHMARKS_REGISTRY_DB}}" \
        --out "{{BENCHMARKS_SITE_OUT}}" \
        --force
      site_complete || (echo "Generated site is missing index.html, report.md, or snapshot.json in {{BENCHMARKS_SITE_OUT}}." >&2; exit 1)
      deploy_site
      exit 0
    fi

    print_missing_site_help
    exit 1

deploy-staging-existing:
    #!/usr/bin/env bash
    set -euo pipefail
    test -f "{{BENCHMARKS_SITE_OUT}}/index.html" || (echo "Missing generated site file: {{BENCHMARKS_SITE_OUT}}/index.html"; exit 1)
    test -f "{{BENCHMARKS_SITE_OUT}}/report.md" || (echo "Missing generated site file: {{BENCHMARKS_SITE_OUT}}/report.md"; exit 1)
    test -f "{{BENCHMARKS_SITE_OUT}}/snapshot.json" || (echo "Missing generated site file: {{BENCHMARKS_SITE_OUT}}/snapshot.json"; exit 1)
    test -d "{{OPS_CONTROL}}" || (echo "ops-control not found at {{OPS_CONTROL}}"; exit 1)
    test -f "{{OPS_CONTROL}}/justfiles/deploy.just" || (echo "Missing ops-control deploy justfile at {{OPS_CONTROL}}/justfiles/deploy.just"; exit 1)
    if ! (cd "{{OPS_CONTROL}}" && just --summary 2>/dev/null | tr ' ' '\n' | grep -Fxq deploy-benchmarks-static); then
        echo "Missing ops-control recipe: deploy-benchmarks-static in {{OPS_CONTROL}}/justfiles/deploy.just" >&2
        echo "Install or land the ops-control static benchmarks deploy target before using this fallback deploy shortcut." >&2
        exit 1
    fi
    site_source="$(cd "{{BENCHMARKS_SITE_OUT}}" && pwd)"
    cd "{{OPS_CONTROL}}"
    PROJECTS_ROOT="{{PROJECTS_ROOT}}" \
    BENCHMARKS_STATIC_SITE_SOURCE="${site_source}" \
    just deploy-benchmarks-static
