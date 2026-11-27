"""Docs Drift Checker agent on the OpenMinion 0.1 Python SDK."""
import hashlib
from pathlib import Path

from pydantic import BaseModel, Field
from openminion import Agent

from drift.tools import list_code_surface, list_doc_files, read_file, search_code, run_help, write_report

INSTRUCTIONS = """You are Docs Drift Checker. Report where markdown docs disagree with code. Never edit files.
1. list_doc_files, read README.md (max 3 other docs).
2. Call list_code_surface once.
3. Verify each concrete claim (command, flag, path, env var) with search_code or run_help.
4. Report only claims a tool result disproves. suggested_fix names the real name from
   list_code_surface (a removed command may map to a real one taking the same argument),
   else "remove from docs". Severity: HIGH breaks, MEDIUM misleads, LOW cosmetic.
5. Call write_report once with a short markdown report.
"""


# Asked in a second turn, only after the work is done: putting the JSON format in the
# instructions made the model answer with an empty JSON at once, without tools (FINDINGS.md).
JSON_ONLY = """Convert the drift report below to JSON. Reply with only the JSON. No prose, no tool calls. Shape:
{"repo":"x","claims_checked":4,"summary":"...","findings":[{"doc_file":"README.md","line":9,
"claim":"...","evidence":"...","severity":"HIGH","suggested_fix":"..."}]}"""


class Finding(BaseModel):
    doc_file: str
    line: int | None = None
    claim: str = Field(description="What the docs say")
    evidence: str = Field(description="What the tool result showed")
    severity: str = Field(description="HIGH, MEDIUM or LOW")
    suggested_fix: str


class DriftReport(BaseModel):
    repo: str
    claims_checked: int
    findings: list[Finding]
    summary: str


def build_agent(repo: str, run_tag: str = "") -> Agent:
    """One session per repo so a follow-up run keeps context."""
    # OpenMinion 0.1.24 does not show output_type's schema to the model (issue #853), and long
    # instructions get cut (#811), so a short JSON example is in INSTRUCTIONS instead.
    return Agent(
        instructions=INSTRUCTIONS,
        tools=[list_code_surface, list_doc_files, read_file, search_code, run_help, write_report],
        output_type=DriftReport,
        # hashlib, not hash(): hash() changes per process, so the session would never be reused
        session_id=f"drift-{hashlib.sha1(str(Path(repo).resolve()).encode()).hexdigest()[:10]}{run_tag}",
    )
