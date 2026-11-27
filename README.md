# Docs Drift Checker

An agent built on the **OpenMinion 0.1 Python SDK** that finds places where a repo's markdown docs
disagree with its real code: a command that no longer exists, a renamed flag, a wrong env var.
Built for Cortensor Hackathon #5.

## What it does

1. Lists the repo's markdown docs and reads them (with line numbers).
2. For each concrete claim (CLI command, flag, path, config key) it checks the code:
   greps the source, or runs `python script.py --help` / `--version`.
3. Reports only findings backed by a tool result, with file, line, evidence, severity and a suggested fix.
4. Asks the human before writing the report file. It never edits code or docs.

## OpenMinion SDK workflow

| Building block | How it is used |
|---|---|
| `@tool(min_scope="READ_ONLY", idempotent=True)` | 5 read-only tools run without prompting: `list_doc_files`, `read_file`, `search_code`, `run_help`, `list_code_surface` (env vars, subcommands and flags the code really defines, so fixes name the right replacement) |
| `@tool()` + `approval_callback` | `write_report` is a write, so the CLI asks y/n before it runs |
| `Agent(output_type=...)` | Structured `DriftReport` (findings, severity, fixes) |
| `session_id` | One session per repo |

Safety limits in [drift/tools.py](drift/tools.py): paths cannot escape the repo, and the only command
that can run is `python <script> --help|-h|--version` (no shell).

## Run it

Requires Python 3.11+ and an API key for a model provider (tested with Gemini).

```bash
python -m venv .venv
.venv/Scripts/activate            # Linux/macOS: source .venv/bin/activate
pip install -r requirements.txt

export GEMINI_API_KEY=...         # PowerShell: $env:GEMINI_API_KEY="..."
openminion setup --provider gemini --model gemini-3.1-flash-lite --agent default --no-focus

python main.py demo_repo          # answer y when it asks to write the report
```

`demo_repo/` is a tiny CLI whose README has 4 planted mismatches. The answer key is in
[EXPECTED_DRIFT.md](EXPECTED_DRIFT.md). Offline tests for the tools (no model needed): `pytest -q`.

## CI mode and eval

```bash
python main.py path/to/repo --ci   # no prompts, JSON out, exit 1 if any HIGH finding
python eval.py 3                   # 3 runs on demo_repo: detected / correct fix / false positives
```

## Result on the demo repo

`python eval.py 5` with `gemini-3.1-flash-lite`:

| run | detected | correct fix | extra findings |
|---|---|---|---|
| 1 | 4/4 | 3/4 | 1 |
| 2 | 4/4 | 3/4 | 1 |
| 3 | 4/4 | 2/4 | 0 |
| 4 | 4/4 | 3/4 | 0 |
| 5 | 4/4 | 3/4 | 0 |

All 4 planted mismatches were found in every run. The miss is `remove 3`: the agent says "remove
from docs" instead of pointing to `done <id>`. The extra finding is a real one: `done` exists in the
code but is not documented.

How it runs: turn 1 does the work with tools and saves the report (needs approval). Turn 2 turns
that report into the `DriftReport` JSON. If no report was written, the run fails with `NoWorkDone`
instead of returning an empty "no drift" result.

## Building blocks tested and what we learned

See [FINDINGS.md](FINDINGS.md): what worked, plus 10 rough edges found in OpenMinion 0.1.24 (hidden
`approval_callback` errors, `output_type` not showing the schema to the model, large default prompt
on free tiers, and more).

## AI disclosure

Written with Claude Code. The author chose the idea, the tool boundaries and the safety limits, and
ran and checked every result.
