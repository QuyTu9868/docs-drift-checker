"""Tools for the Docs Drift Checker. Pure helpers first, OpenMinion tool wrappers below."""
import re
import subprocess
import sys
import time
from pathlib import Path

from openminion import tool

MAX_READ = 20_000          # chars returned per file, keeps model context small
MAX_HITS = 40              # max grep hits returned
SKIP_DIRS = {".git", ".venv", "node_modules", "__pycache__", "reports"}
SAFE_FLAGS = {"--help", "-h", "--version"}   # only these may be executed


def _safe_path(repo: str, rel: str) -> Path:
    """Resolve rel inside repo, refuse paths that escape it."""
    root = Path(repo).resolve()
    p = (root / rel).resolve()
    if root != p and root not in p.parents:
        raise ValueError(f"path escapes repo: {rel}")
    return p


def list_docs(repo: str) -> list[str]:
    """Markdown files in the repo (relative paths)."""
    root = Path(repo).resolve()
    out = []
    for p in root.rglob("*.md"):
        if not (set(p.relative_to(root).parts) & SKIP_DIRS):
            out.append(p.relative_to(root).as_posix())
    return sorted(out)


def read_text(repo: str, rel: str) -> str:
    """Read a file with line numbers so findings can cite lines."""
    text = _safe_path(repo, rel).read_text(encoding="utf-8", errors="replace")
    lines = [f"{i}: {ln}" for i, ln in enumerate(text.splitlines(), 1)]
    return "\n".join(lines)[:MAX_READ]


def grep_code(repo: str, pattern: str) -> list[str]:
    """Regex search in source files (not markdown). Returns 'path:line: text' hits."""
    root = Path(repo).resolve()
    rx = re.compile(pattern)
    hits = []
    for p in root.rglob("*"):
        if (not p.is_file() or p.suffix in {".md", ".pyc", ".png", ".jpg", ".mp4"}
                or set(p.relative_to(root).parts) & SKIP_DIRS):
            continue
        try:
            for i, ln in enumerate(p.read_text(encoding="utf-8").splitlines(), 1):
                if rx.search(ln):
                    hits.append(f"{p.relative_to(root).as_posix()}:{i}: {ln.strip()[:160]}")
                    if len(hits) >= MAX_HITS:
                        return hits
        except (UnicodeDecodeError, OSError):
            continue
    return hits


def run_safe(repo: str, command: str) -> str:
    """Run a Python script / module with only --help, -h or --version (no shell)."""
    parts = command.split()
    if not parts or parts[-1] not in SAFE_FLAGS:
        return "REFUSED: only commands ending in --help, -h or --version may run"
    if parts[0] in {"python", "python3", "py"}:
        parts[0] = sys.executable
    elif parts[0] != sys.executable:
        return "REFUSED: only python scripts are allowed"
    try:
        r = subprocess.run(parts, cwd=Path(repo).resolve(), capture_output=True,
                           text=True, timeout=20)
    except subprocess.TimeoutExpired:
        return "TIMEOUT after 20s"
    return f"exit={r.returncode}\n{(r.stdout + r.stderr)[:3000]}"


ENV_RX = re.compile(r"""(?:environ(?:\.get)?\(|environ\[|getenv\()\s*["']([A-Za-z_][A-Za-z0-9_]*)""")
CMD_RX = re.compile(r"""add_parser\(\s*["']([\w-]+)""")
FLAG_RX = re.compile(r"""add_argument\(\s*["'](-{1,2}[\w-]+)""")


def code_surface(repo: str) -> dict[str, list[str]]:
    """What the code really exposes: env vars, CLI subcommands, CLI flags (Python sources)."""
    root = Path(repo).resolve()
    found = {"env_vars": set(), "commands": set(), "flags": set()}
    for p in root.rglob("*.py"):
        if set(p.relative_to(root).parts) & SKIP_DIRS:
            continue
        text = p.read_text(encoding="utf-8", errors="replace")
        found["env_vars"].update(ENV_RX.findall(text))
        found["commands"].update(CMD_RX.findall(text))
        found["flags"].update(FLAG_RX.findall(text))
    return {k: sorted(v) for k, v in found.items()}


# ---- OpenMinion tool wrappers ----

@tool(min_scope="READ_ONLY", idempotent=True)
def list_doc_files(repo: str) -> str:
    """List markdown docs in the repo."""
    return "\n".join(list_docs(repo))


@tool(min_scope="READ_ONLY", idempotent=True)
def read_file(repo: str, path: str) -> str:
    """Read a file in the repo with line numbers."""
    return read_text(repo, path)


@tool(min_scope="READ_ONLY", idempotent=True)
def search_code(repo: str, pattern: str) -> str:
    """Regex search in source files. Use it to check that a documented flag, function or file exists."""
    return "\n".join(grep_code(repo, pattern)) or "no matches"


@tool(min_scope="READ_ONLY", idempotent=True)
def run_help(repo: str, command: str) -> str:
    """Run `python script.py --help` or `--version` to compare real CLI output with the docs. Nothing else can run."""
    return run_safe(repo, command)


@tool(min_scope="READ_ONLY", idempotent=True)
def list_code_surface(repo: str) -> str:
    """List the env vars, CLI subcommands and flags the code really defines. Use it to name the correct replacement in suggested_fix."""
    return "\n".join(f"{k}: {', '.join(v) or '-'}" for k, v in code_surface(repo).items())


@tool()  # a local write: OpenMinion asks the human before it runs
def write_report(repo: str, markdown: str) -> str:
    """Save the drift report under reports/ in the repo. Needs human approval."""
    out = Path(repo).resolve() / "reports"
    out.mkdir(exist_ok=True)
    path = out / f"drift_{int(time.time())}.md"
    path.write_text(markdown, encoding="utf-8")
    return f"saved {path.name}"
