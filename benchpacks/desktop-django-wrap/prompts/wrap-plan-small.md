
You are planning a coding-agent task for an existing server-rendered Django app
that should run inside an Electron desktop shell.

Return a concise implementation outline under 160 words. Use exactly this
output skeleton, with one short sentence after each label:

DDS_WRAP_PLAN
Inspect: ...
Electron shell: ...
Django runtime: ...
Packaging: ...
Verification: ...

Cover Electron starting Django on 127.0.0.1 with a health check, dev mode
versus packaged mode, SQLite or media files moving to a writable app-data path,
keeping CSRF and a narrow shell-to-Django token boundary, and a smoke command or
bounded verification step. Do not run commands, assume local files, reference
private repos, or include absolute paths.
