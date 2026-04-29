
You are given a portable benchmark prompt that approximates wrapping an
existing Django project in Electron. The target is synthetic: it has a
manage.py entrypoint, server-rendered templates, SQLite for local data, static
assets, and a few authenticated views. The desired desktop app should keep the
Django UI, add a thin Electron shell, work in local development and packaged
mode, and avoid network dependencies.

Write a short implementation plan for a coding agent. Include the exact marker
DDS_WRAP_PLAN somewhere in the first line. Keep the answer under 180 words and
structure it as sections for inspect, Electron shell, Django runtime,
packaging, and verification. Mention a health endpoint or smoke command,
writable app-data paths for packaged SQLite/media, static files with
DEBUG=false, and bounded tests. Do not reference private repos, local absolute
paths, or command execution you performed.
