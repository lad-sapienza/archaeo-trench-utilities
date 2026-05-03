"""Template data management for ArchaeoTrench Utilities.

Template data (schema.sql, QML styles) live in ~/.archaeotrench/.

Setup options (no git required for basic use):
  1. download_template() — download ZIP from GitHub, extract to ~/.archaeotrench.
                           Works with no git installed. Suitable for all users.
  2. clone()            — full git clone. Requires git. Enables pull/commit/push.

Day-to-day update options:
  1. download_template() — re-download ZIP (overwrites types/ only). No git.
  2. pull()             — git pull --ff-only. Requires git repo.

Publishing (requires git):
  commit() → push("fork") → open PR URL in browser.

Template directory resolution:
  get_template_dir(project_type) → ~/.archaeotrench/types/{project_type}/
  No bundled fallback: the plugin requires setup before first use.
"""

from __future__ import annotations

import json
import subprocess
from pathlib import Path

# ---------------------------------------------------------------------------
# Paths & constants
# ---------------------------------------------------------------------------

USER_DIR     = Path.home() / ".archaeotrench"
_CONFIG      = USER_DIR / "config.json"
UPSTREAM_URL = "https://github.com/lad-sapienza/caj-archeo-trench"


# ---------------------------------------------------------------------------
# Template directory resolution
# ---------------------------------------------------------------------------

def get_template_dir(project_type: str) -> Path:
    """Return the template directory for project_type in ~/.archaeotrench."""
    return USER_DIR / "types" / project_type


def is_template_available() -> bool:
    """Return True if at least the plan schema exists in ~/.archaeotrench."""
    return (USER_DIR / "types").is_dir()


# ---------------------------------------------------------------------------
# Git availability
# ---------------------------------------------------------------------------

def is_git_available() -> bool:
    """Return True if the git binary is on PATH."""
    try:
        result = subprocess.run(
            ["git", "--version"],
            capture_output=True, timeout=5,
        )
        return result.returncode == 0
    except (FileNotFoundError, subprocess.TimeoutExpired):
        return False


# ---------------------------------------------------------------------------
# Repo state
# ---------------------------------------------------------------------------

def is_repo_initialized() -> bool:
    """Return True if ~/.archaeotrench is a git repository."""
    return (USER_DIR / ".git").is_dir()


_GITIGNORE_CONTENT = (
    "# macOS\n"
    ".DS_Store\n"
    "\n"
    "# QGIS lock files\n"
    "*.qgs~\n"
    "*.qgz~\n"
    "\n"
    "# Plugin config (local only)\n"
    "config.json\n"
)

_UNTRACK_PATTERNS = [".DS_Store", "config.json"]


def ensure_gitignore() -> bool:
    """Write .gitignore if absent/stale and untrack any files that should be ignored.

    Returns True if any change was made (caller may want to commit).
    """
    if not is_repo_initialized():
        return False

    changed = False

    gitignore = USER_DIR / ".gitignore"
    if not gitignore.exists() or gitignore.read_text(encoding="utf-8") != _GITIGNORE_CONTENT:
        gitignore.write_text(_GITIGNORE_CONTENT, encoding="utf-8")
        changed = True

    for pattern in _UNTRACK_PATTERNS:
        ok, out, _ = _run("ls-files", "--cached", "--error-unmatch", pattern, cwd=USER_DIR)
        if ok and out.strip():
            _run("rm", "--cached", "-r", "--ignore-unmatch", pattern, cwd=USER_DIR)
            changed = True

    ok, out, _ = _run("ls-files", "--cached", cwd=USER_DIR)
    if ok:
        for tracked in out.splitlines():
            if tracked.strip().endswith(".DS_Store"):
                _run("rm", "--cached", "--ignore-unmatch", tracked.strip(), cwd=USER_DIR)
                changed = True

    return changed


def get_changed_files() -> list[str]:
    """Return list of modified/added/deleted files relative to the last commit."""
    ok, out, _ = _run("status", "--short", cwd=USER_DIR)
    if not ok or not out.strip():
        return []
    return [line[3:].strip() for line in out.splitlines() if line.strip()]


def has_changes() -> bool:
    return bool(get_changed_files())


# ---------------------------------------------------------------------------
# Config (repo URL, fork URL)
# ---------------------------------------------------------------------------

def load_config() -> dict:
    if _CONFIG.exists():
        try:
            return json.loads(_CONFIG.read_text(encoding="utf-8"))
        except Exception:
            pass
    return {}


def save_config(config: dict):
    USER_DIR.mkdir(parents=True, exist_ok=True)
    _CONFIG.write_text(json.dumps(config, indent=2), encoding="utf-8")


def get_repo_url() -> str | None:
    return load_config().get("repo_url")


def set_repo_url(url: str):
    cfg = load_config()
    cfg["repo_url"] = url
    save_config(cfg)


def get_fork_url() -> str | None:
    return load_config().get("fork_url")


def set_fork_url(url: str):
    cfg = load_config()
    cfg["fork_url"] = url
    save_config(cfg)


# ---------------------------------------------------------------------------
# Download (no git required)
# ---------------------------------------------------------------------------

def _zip_url(repo_url: str, branch: str = "main") -> str:
    """Return the GitHub ZIP archive URL for a given repo URL and branch."""
    return repo_url.removesuffix(".git") + f"/archive/refs/heads/{branch}.zip"


def download_template(repo_url: str = UPSTREAM_URL) -> tuple[bool, str]:
    """Download and extract the template ZIP from GitHub into ~/.archaeotrench.

    Replaces the types/ subtree only; any other local files are untouched.
    No git installation required.

    Returns (success, message).
    """
    import shutil
    import tempfile
    import urllib.request
    import zipfile

    zip_url = _zip_url(repo_url)
    USER_DIR.mkdir(parents=True, exist_ok=True)

    try:
        with tempfile.NamedTemporaryFile(suffix=".zip", delete=False) as tmp:
            tmp_path = Path(tmp.name)

        urllib.request.urlretrieve(zip_url, tmp_path)

        with zipfile.ZipFile(tmp_path) as zf:
            tops = {p.split("/")[0] for p in zf.namelist() if "/" in p}
            if len(tops) != 1:
                return False, "Unexpected ZIP structure from GitHub."
            top_dir = tops.pop()

            with tempfile.TemporaryDirectory() as extract_dir:
                zf.extractall(extract_dir)
                src_types = Path(extract_dir) / top_dir / "types"
                if not src_types.is_dir():
                    return False, "ZIP does not contain a 'types/' folder."
                dst_types = USER_DIR / "types"
                if dst_types.exists():
                    shutil.rmtree(dst_types)
                shutil.copytree(str(src_types), str(dst_types))

        set_repo_url(repo_url)
        return True, f"Template downloaded from {repo_url}"

    except Exception as exc:
        return False, str(exc)
    finally:
        try:
            tmp_path.unlink()
        except Exception:
            pass


# ---------------------------------------------------------------------------
# Clone / pull (git required)
# ---------------------------------------------------------------------------

def clone(repo_url: str) -> tuple[bool, str]:
    """Clone repo_url into USER_DIR (requires git).

    Merges cloned contents into USER_DIR so any existing config.json is kept.
    """
    USER_DIR.mkdir(parents=True, exist_ok=True)
    if is_repo_initialized():
        return True, "Repository already initialised."

    parent   = USER_DIR.parent
    tmp_dir  = parent / (USER_DIR.name + "_clone_tmp")

    ok, out, err = _run("clone", repo_url, str(tmp_dir), cwd=parent)
    if not ok:
        return False, err or out

    import shutil
    for item in tmp_dir.iterdir():
        dest = USER_DIR / item.name
        if dest.exists():
            if dest.is_dir():
                shutil.rmtree(dest)
            else:
                dest.unlink()
        shutil.move(str(item), str(dest))
    shutil.rmtree(tmp_dir, ignore_errors=True)

    ensure_gitignore()
    set_repo_url(repo_url)
    return True, f"Cloned {repo_url} into {USER_DIR}"


def pull() -> tuple[bool, str]:
    """Pull latest changes from origin (requires git repo)."""
    if not is_repo_initialized():
        return False, "Not a git repository — use «Update template» to re-download."
    ok, out, err = _run("pull", "--ff-only", cwd=USER_DIR)
    return ok, (out + err).strip() or ("Up to date." if ok else "Pull failed.")


# ---------------------------------------------------------------------------
# Commit & push (git required)
# ---------------------------------------------------------------------------

def commit(message: str) -> tuple[bool, str]:
    """Stage all changes and create a commit."""
    ok, _, err = _run("add", "-A", cwd=USER_DIR)
    if not ok:
        return False, err

    ok, out, err = _run("commit", "-m", message, cwd=USER_DIR)
    if not ok:
        if "nothing to commit" in out + err:
            return True, "Nothing to commit."
        return False, (err or out).strip()
    return True, out.strip()


def push(remote: str = "origin") -> tuple[bool, str]:
    """Push current branch to the given remote."""
    ok, out, err = _run("push", remote, cwd=USER_DIR)
    return ok, (out + err).strip()


def ensure_remote(name: str, url: str):
    """Add remote if absent, or update URL if it has changed."""
    ok, out, _ = _run("remote", "get-url", name, cwd=USER_DIR)
    if ok and out.strip() == url:
        return
    if ok:
        _run("remote", "set-url", name, url, cwd=USER_DIR)
    else:
        _run("remote", "add", name, url, cwd=USER_DIR)


def get_current_branch() -> str:
    ok, out, _ = _run("rev-parse", "--abbrev-ref", "HEAD", cwd=USER_DIR)
    return out.strip() if ok else "main"


# ---------------------------------------------------------------------------
# PR URL construction
# ---------------------------------------------------------------------------

def build_pr_url(base_repo_url: str, fork_url: str) -> str:
    """Return a GitHub compare/PR URL for opening in the browser."""
    branch = get_current_branch()
    base_owner, base_repo = _parse_github_url(base_repo_url)
    fork_owner, _         = _parse_github_url(fork_url)
    if base_owner and fork_owner:
        repo = base_repo.removesuffix(".git")
        return (
            f"https://github.com/{base_owner}/{repo}/compare/"
            f"main...{fork_owner}:{branch}?expand=1"
        )
    return fork_url.removesuffix(".git")


def _parse_github_url(url: str) -> tuple[str, str]:
    try:
        if "github.com/" in url:
            path = url.split("github.com/", 1)[1]
        elif "github.com:" in url:
            path = url.split("github.com:", 1)[1]
        else:
            return "", ""
        parts = path.strip("/").split("/")
        return parts[0], parts[1]
    except (IndexError, ValueError):
        return "", ""


# ---------------------------------------------------------------------------
# Internal helper
# ---------------------------------------------------------------------------

def _run(*args, cwd: Path | None = None) -> tuple[bool, str, str]:
    """Run a git command. Returns (success, stdout, stderr)."""
    try:
        result = subprocess.run(
            ["git"] + list(args),
            cwd=str(cwd) if cwd else None,
            capture_output=True,
            text=True,
            timeout=30,
        )
        return result.returncode == 0, result.stdout, result.stderr
    except FileNotFoundError:
        return False, "", "git not found"
    except subprocess.TimeoutExpired:
        return False, "", "git command timed out"
