# Benchpack Format

This is the initial manifest sketch. The schema can change until the first
release.

## Example

```toml
[pack]
id = "smoke-chat"
version = "0.1.0"
description = "Tiny endpoint smoke test"

[defaults]
temperature = 0
max_tokens = 64
stream = true
repetitions = 1

[[cases]]
id = "capital"
kind = "chat"
prompt = "What is the capital of France? Answer in one sentence."

[scoring]
mode = "contains"
expected = "Paris"
```

## Fields

`pack.id`
: Stable pack identifier used in result records.

`pack.version`
: Version of the workload. Change it when prompts, fixtures, or scoring change.

`defaults`
: Request defaults shared by cases.

`cases`
: Ordered benchmark cases.

`scoring`
: Optional deterministic scoring mode.

## Case Kinds

`chat`
: A direct prompt or message list sent to an adapter.

`completion`
: A raw prompt-completion case.

`repo-task`
: A task that prepares a disposable repository and verifies changes.

`replay`
: A recorded request sequence.

## Result Compatibility

Result records must include the pack id and version. Comparisons should warn when
pack versions differ.
