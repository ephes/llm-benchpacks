# tool-json

Strict JSON and tool-call-shaped formatting checks for chat endpoints.

This pack is intentionally endpoint-only and deterministic. It asks the model
to return raw JSON with no Markdown, no prose, and no hidden reasoning text.
Scoring uses `json-schema` against pack-local schema fixtures. It does not use
OpenAI tool-calling APIs, function-call request fields, repo workspaces,
external agents, or verifier scripts.

Cases:

- `strict-object`: returns a fixed compact data extraction object.
- `tool-call-arguments`: returns a JSON object shaped like a tool call with
  strict argument keys and enums.

Interpretation boundary: a pass means the endpoint produced parseable JSON with
the required shape for this prompt. It is not broad tool-use evidence and does
not measure whether a runtime supports native tool-call request or response
fields.
