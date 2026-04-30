# Synthetic Django App Fixture

This fixture describes a portable target application for future
Django-in-Electron wrapping work. Referenced chat cases append this file to
their loaded prompt as deterministic context. The runner does not copy it,
execute it, or turn it into a mutable repository.

## Application Shape

- Django project with a `manage.py` entrypoint and one project package.
- Server-rendered HTML templates with form posts and ordinary page navigation.
- Local SQLite database for development data.
- Static assets collected from app-level `static/` directories.
- Media uploads stored on disk through Django's file storage settings.
- A small set of authenticated views that use Django sessions and CSRF
  protection.
- Optional `/healthz/` view or smoke command that can prove the local server is
  accepting requests.

## Wrap Concerns

- Development mode may run Django with the normal development server and open an
  Electron `BrowserWindow` at a loopback URL.
- Packaged mode should start Django as a child process or bundled executable and
  wait for a health check before showing the UI.
- SQLite files, media uploads, logs, and other mutable state should live under a
  writable app-data directory in packaged mode.
- Static files must work with `DEBUG=false`, either through collection into the
  packaged app or another deterministic local serving strategy.
- The shell-to-Django boundary should stay narrow: prefer loopback-only access,
  a bounded launch token if needed, existing CSRF/session behavior, and no broad
  native bridge for arbitrary application actions.
- Verification should include a smoke command, a health endpoint check,
  authenticated view coverage, packaged-mode path checks, and regression tests
  for static/media handling.
