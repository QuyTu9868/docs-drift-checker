"""CLI: python main.py <repo_path> [--ci]

--ci: no prompts (the report write is auto-approved, it only writes under reports/),
prints JSON and exits 1 when any HIGH finding exists. For use in CI pipelines.
"""
import sys
import time
from pathlib import Path

from openminion import AgentOutputValidationError, ProviderError

from drift.agent import JSON_ONLY, DriftReport, build_agent

TASK = "Check the docs of the repo at {repo} for drift from the code. Start with list_doc_files."
MAX_TRIES = 4  # retries on transient provider errors
TRANSIENT = ("RATE_LIMITED", "HTTP 503", "TIMEOUT")


class NoWorkDone(RuntimeError):
    """The agent replied without calling tools (e.g. a canned guardrail reply)."""


def latest_report(repo: str) -> str:
    return max((Path(repo) / "reports").glob("drift_*.md"), key=lambda p: p.stat().st_mtime).read_text(encoding="utf-8")


def report_written_since(repo: str, t: float) -> bool:
    reports = Path(repo) / "reports"
    return reports.is_dir() and any(p.stat().st_mtime >= t for p in reports.glob("drift_*.md"))


def ask_human(tool_name: str, args: dict, approval_id: str) -> bool:
    """approval_callback (SDK passes tool name, args, approval id): show the call and ask y/n."""
    print(f"\n[approval needed] {tool_name} {str(args)[:300]}")
    return input("Allow? [y/N] ").strip().lower() == "y"


def auto_approve_report(tool_name: str, args: dict, approval_id: str) -> bool:
    """CI mode: only the report write may run without a human."""
    return tool_name == "write_report"


def check(repo: str, approve=ask_human, run_tag: str = "") -> DriftReport | str:
    """Run the agent once. Returns the structured report, or the raw text if the model skipped JSON."""
    for attempt in range(1, MAX_TRIES + 1):
        try:
            started = time.time()
            with build_agent(repo, run_tag) as agent:
                text = ""
                try:  # turn 1: do the work; it usually ends in prose, which output_type rejects
                    text = agent.run(TASK.format(repo=repo), approval_callback=approve,
                                     timeout_seconds=600).text
                except AgentOutputValidationError as exc:
                    text = exc.raw_text
                # no report file = no work done (empty answer or canned guardrail reply, #870)
                if not report_written_since(repo, started):
                    raise NoWorkDone(text)
                # turn 2: the SDK does not carry turn 1 into turn 2 even in the same session
                # (FINDINGS.md), so pass the saved report in the message itself
                result = agent.run(f"{JSON_ONLY}\n\nReport for repo {repo}:\n{latest_report(repo)}",
                                   approval_callback=approve, timeout_seconds=300)
                return result.output or result.text
        except ProviderError as exc:
            # the SDK reports 503 only as a generic PROVIDER_ERROR, so match the text
            if any(code in str(exc) for code in TRANSIENT) and attempt < MAX_TRIES:
                wait = 20 * attempt  # simple linear backoff
                print(f"provider busy, retry {attempt}/{MAX_TRIES - 1} in {wait}s", file=sys.stderr)
                time.sleep(wait)
                continue
            raise
        except AgentOutputValidationError as exc:
            # the model answered in prose instead of the JSON schema (see FINDINGS.md)
            return exc.raw_text


def main() -> None:
    repo = sys.argv[1]
    ci = "--ci" in sys.argv
    try:
        report = check(repo, auto_approve_report if ci else ask_human)
    except (ProviderError, NoWorkDone) as exc:
        print(f"run failed: {type(exc).__name__}: {str(exc)[:300]}")
        sys.exit(2)
    if isinstance(report, str):
        print(f"(structured output not returned, raw reply)\n{report}")
        sys.exit(2 if ci else 0)
    print(report.model_dump_json(indent=2))
    if ci and any(f.severity.upper() == "HIGH" for f in report.findings):
        sys.exit(1)


if __name__ == "__main__":
    main()
