# Findings on OpenMinion 0.1.24 (Building Blocks Tested)

Environment: Windows 11, Python 3.14, OpenMinion 0.1.24, Gemini (`gemini-3.1-flash-lite`) via the
`gemini` provider preset.

## What worked
- `@tool(min_scope="READ_ONLY", idempotent=True)` tools run without a prompt, as documented.
- A bare `@tool()` that writes a file triggers `approval_callback` before it runs.
- On the demo repo the agent found all 4 planted doc/code mismatches (see EXPECTED_DRIFT.md).

## What did not / rough edges
1. **Callback errors are hidden.** `approval_callback` is called with `(tool_name, args, approval_id)`,
   but the README/getting-started do not show the signature. A 1-argument callback raised a
   `TypeError` inside the turn state machine, which the SDK turned into a normal-looking reply
   (`State machine error: ... takes 1 positional argument but 3 were given`) instead of raising.
   Expected: the exception reaches the caller, or the docs show the callback signature.
2. **`output_type` does not show the schema to the model.** `Agent(output_type=Model)` only parses the
   reply as JSON. A model told to "reply with answer=hello" answered in prose and validation failed.
   Workaround: put `Model.model_json_schema()` in `instructions`. Even then the model sometimes ends
   with prose after a tool call, so the CLI falls back to printing `AgentOutputValidationError.raw_text`.
3. **Replies are prefixed with the agent id** (`default: ...`), so raw replies are never valid JSON by
   themselves and rely on the SDK's JSON-extraction fallback.
4. **Large default prompt vs free tiers.** Even `Agent(instructions="...").run("Say hi")` returned
   HTTP 413 on Groq's free tier for 3 models (`gpt-oss-120b`, `gpt-oss-20b`, `qwen3.8-27b`:
   request too large for tokens per minute), so the SDK's built-in prompt is large.
5. **Provider errors can look like model output.** With a 429 or timeout, runs sometimes hung until
   `timeout_seconds` instead of surfacing `RATE_LIMITED` quickly.
6. **Recommended model in `setup --list-providers` is stale for Groq**: `llama-3.3-70b-versatile`
   returned 404 on the account tested.
7. **A canned guardrail reply comes back as a completed run.** With `gemini-flash-lite-latest`, a
   multi-step request with a search tool plus a tool that needs approval returns, with no tool call and no error:
   `I could not safely update the task conditions. Please restate the current task and its required conditions.`
   Minimal repro (instructions are just "You are helpful."):
   | tools | message | result |
   |---|---|---|
   | 6 tools incl. `write_report` (`@tool()`) | "Check the docs of the repo at demo_repo for drift from the code." | canned reply |
   | same 6 tools | "List the markdown docs in the repo at demo_repo." | correct answer |
   | 5 read-only tools (no `write_report`) | drift message | full drift analysis |
   Expected: the run does the work, or fails with a typed error the caller can catch. Actual: a
   normal-looking reply, so callers cannot tell it apart from a real answer (same class as #804).
   Dropping either `search_code` or `write_report` makes it go away. Reported as
   [openminion#870](https://github.com/openminion/openminion/issues/870) with a standalone repro.
8. **HTTP 503 from the provider is reported as a generic `PROVIDER_ERROR`**, not a retryable code
   like `RATE_LIMITED`, so callers must string-match `"HTTP 503"` to retry (see `main.py`).
9. **Asking for a JSON output format in `instructions` makes the entry step skip tools.** With
   "reply ONLY with JSON" plus an example in the instructions, 4 of 5 runs of `gemini-3.1-flash-lite`
   answered at once with an empty JSON (`claims_checked: 0`). Telemetry shows `brain.entry` with
   `route: respond` and `tool_call_names: []`. Workaround: no format in the instructions; ask for
   JSON in a second turn after the tool work. Related to #853 (the schema has to go somewhere).
10. **A second `agent.run` on the same `Agent` did not see the first turn.** Turn 1 found and saved 4
   findings; turn 2 in the same `with Agent(...)` block, same `session_id`, asked "reply with the
   JSON for the findings above" and got `{"claims_checked": 0, "findings": []}`. Workaround: pass the
   saved report text in the turn 2 message.
