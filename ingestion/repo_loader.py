"""
CodeMind - ingestion/repo_loader.py
Day 2: Clone any GitHub repository and walk its files.
Filters by supported extensions, skips ignored directories,
and respects the MAX_FILES laptop-safe limit from config.
"""

import shutil
from pathlib import Path
from dataclasses import dataclass, field

import git
from rich.console import Console
from rich.progress import Progress, SpinnerColumn, TextColumn, BarColumn

import sys
sys.path.append(str(Path(__file__).resolve().parent.parent))
from config import (
    REPOS_DIR,
    MAX_FILES,
    SUPPORTED_EXTENSIONS,
    IGNORED_DIRS,
)

console = Console()


# ── Data Model ────────────────────────────────────────────────────────────────

@dataclass
class CodeFile:
    """Represents a single file extracted from a repository."""
    path: str           # relative path inside the repo
    content: str        # raw text content
    extension: str      # e.g. ".py"
    repo_name: str      # e.g. "langchain"
    language: str       # human-readable language name


# ── Extension → Language Map ──────────────────────────────────────────────────

EXTENSION_LANGUAGE_MAP: dict[str, str] = {
    ".py": "Python",
    ".js": "JavaScript",
    ".ts": "TypeScript",
    ".jsx": "JavaScript (React)",
    ".tsx": "TypeScript (React)",
    ".html": "HTML",
    ".css": "CSS",
    ".md": "Markdown",
    ".txt": "Text",
    ".rst": "reStructuredText",
    ".yaml": "YAML",
    ".yml": "YAML",
    ".toml": "TOML",
    ".json": "JSON",
    ".java": "Java",
    ".kt": "Kotlin",
    ".c": "C",
    ".cpp": "C++",
    ".h": "C Header",
    ".hpp": "C++ Header",
    ".go": "Go",
    ".rs": "Rust",
    ".sh": "Shell",
    ".bash": "Bash",
    ".ipynb": "Jupyter Notebook",
}


# ── Core Functions ────────────────────────────────────────────────────────────

def clone_repo(github_url: str, force_reclone: bool = False) -> Path:
    """
    Clone a GitHub repository into the local repos/ directory.
    If already cloned, skip unless force_reclone=True.

    Args:
        github_url: Full GitHub URL e.g. https://github.com/owner/repo
        force_reclone: Delete and re-clone if True

    Returns:
        Path to the cloned repo directory
    """
    # Extract repo name from URL
    repo_name = github_url.rstrip("/").split("/")[-1]
    if repo_name.endswith(".git"):
        repo_name = repo_name[:-4]

    repo_path = REPOS_DIR / repo_name

    # Handle existing clone
    if repo_path.exists():
        if force_reclone:
            console.print(f"[yellow]🗑  Removing existing clone: {repo_name}[/yellow]")
            shutil.rmtree(repo_path)
        else:
            console.print(f"[green]✅ Repo already cloned: {repo_name}[/green]")
            return repo_path

    # Clone with progress spinner
    console.print(f"[cyan]📥 Cloning {github_url}...[/cyan]")
    with Progress(
        SpinnerColumn(),
        TextColumn("[progress.description]{task.description}"),
        transient=True,
    ) as progress:
        progress.add_task(f"Cloning {repo_name}...", total=None)
        git.Repo.clone_from(github_url, repo_path, depth=1)  # shallow clone = faster

    console.print(f"[green]✅ Cloned successfully → {repo_path}[/green]")
    return repo_path


def _should_skip_dir(dir_name: str) -> bool:
    """Return True if this directory should be skipped during walking."""
    return dir_name in IGNORED_DIRS or dir_name.startswith(".")


def _is_supported_file(file_path: Path) -> bool:
    """Return True if this file's extension is in SUPPORTED_EXTENSIONS."""
    return file_path.suffix.lower() in SUPPORTED_EXTENSIONS


def _read_file_safe(file_path: Path) -> str | None:
    """
    Read file content safely — skip binary or unreadable files.
    Returns None if the file can't be decoded as text.
    """
    try:
        return file_path.read_text(encoding="utf-8", errors="ignore")
    except Exception:
        return None


def walk_repo(repo_path: Path) -> list[CodeFile]:
    """
    Walk a cloned repository and extract all supported files.
    Respects MAX_FILES limit and skips ignored directories.

    Args:
        repo_path: Path to the cloned repository

    Returns:
        List of CodeFile objects ready for chunking
    """
    repo_name = repo_path.name
    code_files: list[CodeFile] = []
    skipped = 0
    total_walked = 0

    console.print(f"\n[cyan]🔍 Walking repository: {repo_name}[/cyan]")

    with Progress(
        SpinnerColumn(),
        TextColumn("[progress.description]{task.description}"),
        BarColumn(),
        TextColumn("{task.completed} files"),
        transient=True,
    ) as progress:
        task = progress.add_task("Scanning files...", total=None)

        for root, dirs, files in repo_path.walk() if hasattr(repo_path, 'walk') else _os_walk(repo_path):
            # Prune ignored directories in-place (prevents descending into them)
            dirs[:] = [d for d in dirs if not _should_skip_dir(d)]

            for file_name in files:
                file_path = Path(root) / file_name
                total_walked += 1

                # Check extension
                if not _is_supported_file(file_path):
                    skipped += 1
                    continue

                # Read content
                content = _read_file_safe(file_path)
                if not content or not content.strip():
                    skipped += 1
                    continue

                # Build relative path
                try:
                    relative_path = str(file_path.relative_to(repo_path))
                except ValueError:
                    relative_path = file_name

                ext = file_path.suffix.lower()
                code_files.append(CodeFile(
                    path=relative_path,
                    content=content,
                    extension=ext,
                    repo_name=repo_name,
                    language=EXTENSION_LANGUAGE_MAP.get(ext, "Unknown"),
                ))

                progress.update(task, completed=len(code_files))

                # Laptop safety limit
                if len(code_files) >= MAX_FILES:
                    console.print(
                        f"[yellow]⚠️  Reached MAX_FILES limit ({MAX_FILES}). "
                        f"Stopping early. Increase MAX_FILES in .env to load more.[/yellow]"
                    )
                    break

            if len(code_files) >= MAX_FILES:
                break

    return code_files


def _os_walk(path: Path):
    """Fallback os.walk wrapper that yields (Path, list, list) tuples."""
    import os
    for root, dirs, files in os.walk(path):
        yield Path(root), dirs, files


def load_repo(github_url: str, force_reclone: bool = False) -> list[CodeFile]:
    """
    Full pipeline: clone repo → walk files → return CodeFile list.
    This is the main entry point used by the chunker (Day 3).

    Args:
        github_url: GitHub repo URL
        force_reclone: Re-clone even if already exists

    Returns:
        List of CodeFile objects
    """
    repo_path = clone_repo(github_url, force_reclone=force_reclone)
    code_files = walk_repo(repo_path)

    # Summary
    _print_summary(code_files)
    return code_files


def _print_summary(code_files: list[CodeFile]) -> None:
    """Print a language breakdown summary table."""
    from rich.table import Table
    from collections import Counter

    lang_counts = Counter(f.language for f in code_files)

    table = Table(title=f"📁 Loaded {len(code_files)} files")
    table.add_column("Language", style="cyan")
    table.add_column("Files", style="green", justify="right")

    for lang, count in lang_counts.most_common():
        table.add_row(lang, str(count))

    console.print(table)


# ── Sanity Check ──────────────────────────────────────────────────────────────

if __name__ == "__main__":
    import sys

    # Default test repo — small and fast to clone
    test_url = sys.argv[1] if len(sys.argv) > 1 else "https://github.com/tiangolo/fastapi"

    console.print(f"\n[bold cyan]🧠 CodeMind — Day 2 Sanity Check[/bold cyan]")
    console.print(f"[dim]Testing with: {test_url}[/dim]\n")

    files = load_repo(test_url)

    console.print(f"\n[bold green]✅ repo_loader.py works! {len(files)} files loaded.[/bold green]")
    console.print(f"[dim]Sample file: {files[0].path} ({files[0].language})[/dim]")
    console.print("\n[bold]Ready for Day 3 — chunker.py ✅[/bold]")
