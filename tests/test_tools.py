"""Offline tests for the tool helpers (no model needed)."""
from pathlib import Path

import pytest

from drift import tools

REPO = str(Path(__file__).resolve().parent.parent / "demo_repo")


def test_list_docs():
    assert tools.list_docs(REPO) == ["README.md"]


def test_read_text_has_line_numbers():
    assert tools.read_text(REPO, "README.md").startswith("1: # Todo CLI")


def test_path_escape_blocked():
    with pytest.raises(ValueError):
        tools.read_text(REPO, "../main.py")


def test_grep_finds_real_and_misses_fake():
    assert tools.grep_code(REPO, r"TODO_PATH")          # exists in code
    assert not tools.grep_code(REPO, r"TODO_FILE")      # only in README (drift)
    assert not tools.grep_code(REPO, r"export")


def test_run_safe_help_and_refusals():
    ok = tools.run_safe(REPO, "python todo.py --help")
    assert "exit=0" in ok and "Tiny task tracker" in ok
    assert tools.run_safe(REPO, "python todo.py add x").startswith("REFUSED")
    assert tools.run_safe(REPO, "rm -rf / --help").startswith("REFUSED")


def test_code_surface_lists_real_names():
    s = tools.code_surface(REPO)
    assert s["env_vars"] == ["TODO_PATH"]
    assert s["commands"] == ["add", "done", "list"]
    assert s["command_usage"] == ["add <title>", "done <id>", "list [--all]"]
    assert "--all" in s["flags"] and "--done" not in s["flags"]


def test_eval_score():
    from drift.agent import DriftReport, Finding
    from eval import score
    f = lambda c, fx: Finding(doc_file="README.md", claim=c, evidence="e", severity="HIGH", suggested_fix=fx)
    rep = DriftReport(repo="r", claims_checked=4, summary="s", findings=[
        f("TODO_FILE env var", "use TODO_PATH"), f("list --done", "use --all"),
        f("remove 3", "remove from docs"), f("ghost claim", "x")])
    assert score(rep) == (3, 2, 1)


def test_report_written_since(tmp_path):
    import time
    from main import report_written_since
    assert not report_written_since(str(tmp_path), 0)
    (tmp_path / "reports").mkdir()
    (tmp_path / "reports" / "drift_1.md").write_text("x")
    assert report_written_since(str(tmp_path), 0)
    assert not report_written_since(str(tmp_path), time.time() + 60)
