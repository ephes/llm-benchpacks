Return exactly one JSON object shaped like a tool call and nothing else.

Do not include Markdown fences, prose, comments, hidden reasoning, or extra
keys.

The object must have:

- tool: create_ticket
- arguments.title: Investigate cache parity warning
- arguments.severity: medium
- arguments.assignee: benchpack
- arguments.due_days: 3
