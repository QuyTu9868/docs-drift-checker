"""Score the agent against the planted drift in demo_repo (needs a model).

python eval.py [runs]   -> detection recall, fix accuracy, false positives per run
"""
import sys
import time

from drift.agent import DriftReport
from openminion import ProviderError

from main import NoWorkDone, auto_approve_report, check

REPO = "demo_repo"
# (keyword in the claim, keyword the fix must name; None = any fix is fine)
EXPECTED = [("TODO_FILE", "TODO_PATH"), ("--done", "--all"), ("remove", "done"), ("export", None)]


def score(report: DriftReport) -> tuple[int, int, int]:
    found = fixed = 0
    matched = set()
    for key, fix in EXPECTED:
        hits = [i for i, f in enumerate(report.findings) if key in f.claim]
        if hits:
            found += 1
            matched.update(hits)
            if fix is None or any(fix in report.findings[i].suggested_fix for i in hits):
                fixed += 1
    return found, fixed, len(report.findings) - len(matched)


def main() -> None:
    runs = int(sys.argv[1]) if len(sys.argv) > 1 else 1
    n = len(EXPECTED)
    for r in range(1, runs + 1):
        try:
            report = check(REPO, auto_approve_report, run_tag=f"-eval{time.time_ns()}")  # fresh session per run
        except (ProviderError, NoWorkDone) as exc:
            print(f"run {r}: failed ({type(exc).__name__}: {str(exc)[:120]})")
            continue
        if isinstance(report, str):
            print(f"run {r}: no structured output, raw reply: {report[:600]!r}")
            continue
        found, fixed, extra = score(report)
        print(f"run {r}: detected {found}/{n}, correct fix {fixed}/{n}, false positives {extra}")


if __name__ == "__main__":
    main()
