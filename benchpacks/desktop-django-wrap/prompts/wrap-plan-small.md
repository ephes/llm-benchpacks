
You are planning a coding-agent task for an existing server-rendered Django app
that should run inside an Electron desktop shell.

Return a concise implementation outline. The output must start with the exact
marker DDS_WRAP_PLAN, then use at most six bullets. Cover: Electron starting
Django on 127.0.0.1 with a health check, dev mode versus packaged mode,
SQLite or media files moving to a writable app-data path, keeping CSRF and a
narrow shell-to-Django token boundary, a smoke command, and verification steps.
Do not run commands, assume local files, or include absolute paths.
