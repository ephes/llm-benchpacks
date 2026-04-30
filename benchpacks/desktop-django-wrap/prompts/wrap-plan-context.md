
You are given a portable benchmark prompt that approximates wrapping an
existing Django project in Electron. The target is synthetic: it has a
manage.py entrypoint, server-rendered templates, SQLite for local data, static
assets, and a few authenticated views. The desired desktop app should keep the
Django UI, add a thin Electron shell, work in local development and packaged
mode, and avoid network dependencies.

Write a short implementation plan for a coding agent. Include the exact marker
DDS_WRAP_PLAN as the first line. Keep the answer under 180 words. Use exactly
this output skeleton, with one short sentence after each label:

DDS_WRAP_PLAN
Inspect: ...
Electron shell: ...
Django runtime: ...
Packaging: ...
Verification: ...

Mention Electron starting Django on 127.0.0.1 with a health endpoint or smoke
command, dev mode versus packaged mode, writable app-data paths for packaged
SQLite/media, static files with DEBUG=false, CSRF plus a narrow shell-to-Django
boundary, and bounded tests. Do not reference private repos, local absolute
paths, or command execution you performed.
