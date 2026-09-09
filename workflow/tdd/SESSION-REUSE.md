# Native session and provider adapters

Load when changing the external runner or a provider adapter. Normal issue execution follows the
shared context policy without loading this file. Check the linked official documentation for the
selected endpoint/model before changing provider parameters.

Keep one explicit native session ID for a continuous run. Resume that ID on subsequent calls;
“continue latest” may select another task. Keep required independent review in a separate session.
Only a real context/host boundary creates a handoff. Let native replay preserve the original
messages, tool results, and reasoning blocks; do not copy that history into cards or worker briefs.

`scripts/overnight.py` uses Claude's `--session-id` then `--resume` for its own run. Its session ID
is process-local. A restarted runner stops at an unknown open execution for reconciliation by its
owning host. Once admission can resume, its new session reads non-derivable state from the handoff.
The process supervisor covers its POSIX group or Windows Job, not detached remote agents or services.

OpenAI prompt caching reuses an exact unchanged prefix. Keep stable input and tool order ahead of
new turn content; routing keys do not guarantee a hit. Inspect the endpoint's returned cached-token
usage instead of predicting it from repeated text.
[Official prompt caching guide](https://developers.openai.com/api/docs/guides/prompt-caching)

GLM's documented implicit cache is automatic; even formatting changes can reduce reuse. Chat
Completions reports hits in `usage.prompt_tokens_details.cached_tokens`. The cache documentation's
token-price discounts apply to the standard API and explicitly exclude Coding Plan and resource
packages; do not apply that price model to subscription usage.
[Official GLM cache guide](https://docs.bigmodel.cn/cn/guide/capabilities/cache)

GLM preserved thinking defaults on for Coding Plan and off for the standard API. For a standard API
adapter that enables it, the documented switch is `thinking.clear_thinking: false`; replay complete,
unmodified `reasoning_content` in its original order. This is a native replay requirement, not a
reason to insert reasoning into shared project files.
[Official GLM thinking guide](https://docs.bigmodel.cn/cn/guide/capabilities/thinking-mode)

Do not assume undocumented GLM minimum prefix length, TTL, or cache sharing across agents. Record
actual cached and uncached input separately through existing provider usage/telemetry. Cache savings
do not shrink the context window, and deterministic instruction checks do not measure model speed,
quality, or cache hit rate.
