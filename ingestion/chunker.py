"""
CodeMind - ingestion/chunker.py
Day 3: Smart code-aware chunking.
Splits code files into meaningful chunks while preserving
function/class boundaries, docstrings, and context.
Each chunk carries rich metadata for precise retrieval.
"""

from dataclasses import dataclass, field
from pathlib import Path

from langchain_text_splitters import (
    RecursiveCharacterTextSplitter,
    Language,
)
from rich.console import Console
from rich.table import Table

import sys
sys.path.append(str(Path(__file__).resolve().parent.parent))
from config import CHUNK_SIZE, CHUNK_OVERLAP
from ingestion.repo_loader import CodeFile

console = Console()


# ── Data Model ────────────────────────────────────────────────────────────────

@dataclass
class CodeChunk:
    """
    A single chunk of code ready for embedding.
    Carries enough metadata for the MCP tool to return
    precise, cited answers to the user.
    """
    content: str          # the actual text to embed
    repo_name: str        # which repo this came from
    file_path: str        # relative path inside the repo
    language: str         # human-readable language
    extension: str        # .py, .ts, .md etc.
    chunk_index: int      # position of this chunk within its file
    total_chunks: int     # how many chunks the file was split into
    start_line: int       # approximate start line (for citation)
    chunk_id: str         # unique ID: repo::path::index

    def to_metadata(self) -> dict:
        """Convert to flat dict for ChromaDB metadata storage."""
        return {
            "repo_name": self.repo_name,
            "file_path": self.file_path,
            "language": self.language,
            "extension": self.extension,
            "chunk_index": self.chunk_index,
            "total_chunks": self.total_chunks,
            "start_line": self.start_line,
            "chunk_id": self.chunk_id,
        }


# ── Language → LangChain Splitter Map ────────────────────────────────────────

# LangChain has language-aware splitters that respect
# function/class boundaries for these languages
LANGUAGE_SPLITTER_MAP: dict[str, Language] = {
    ".py": Language.PYTHON,
    ".js": Language.JS,
    ".ts": Language.JS,       # TS uses same separators as JS
    ".jsx": Language.JS,
    ".tsx": Language.JS,
    ".go": Language.GO,
    ".rs": Language.RUST,
    ".java": Language.JAVA,
    ".kt": Language.KOTLIN,
    ".cpp": Language.CPP,
    ".c": Language.C,
    ".h": Language.C,
    ".hpp": Language.CPP,
    ".rb": Language.RUBY,
    ".md": Language.MARKDOWN,
    ".rst": Language.RST,
    ".html": Language.HTML,
}


# ── Core Chunker ──────────────────────────────────────────────────────────────

def _get_splitter(extension: str) -> RecursiveCharacterTextSplitter:
    """
    Return the best splitter for the given file extension.
    Language-aware splitters respect code structure (functions, classes).
    Falls back to generic recursive splitter for unknown types.
    """
    if extension in LANGUAGE_SPLITTER_MAP:
        return RecursiveCharacterTextSplitter.from_language(
            language=LANGUAGE_SPLITTER_MAP[extension],
            chunk_size=CHUNK_SIZE,
            chunk_overlap=CHUNK_OVERLAP,
        )
    # Generic fallback for YAML, JSON, TOML, shell scripts etc.
    return RecursiveCharacterTextSplitter(
        chunk_size=CHUNK_SIZE,
        chunk_overlap=CHUNK_OVERLAP,
        separators=["\n\n", "\n", " ", ""],
    )


def _estimate_start_line(content: str, chunk_text: str) -> int:
    """Estimate the starting line number of a chunk within its file."""
    idx = content.find(chunk_text[:50])  # match on first 50 chars
    if idx == -1:
        return 0
    return content[:idx].count("\n") + 1


def chunk_file(code_file: CodeFile) -> list[CodeChunk]:
    """
    Split a single CodeFile into a list of CodeChunks.
    Uses language-aware splitting to preserve code structure.

    Args:
        code_file: A CodeFile object from repo_loader.py

    Returns:
        List of CodeChunk objects with rich metadata
    """
    splitter = _get_splitter(code_file.extension)

    # Split the raw content
    raw_chunks = splitter.split_text(code_file.content)

    # Filter out empty or whitespace-only chunks
    raw_chunks = [c for c in raw_chunks if c.strip()]

    if not raw_chunks:
        return []

    chunks: list[CodeChunk] = []
    total = len(raw_chunks)

    for idx, chunk_text in enumerate(raw_chunks):
        # Build a unique, human-readable chunk ID
        safe_path = code_file.path.replace("\\", "/").replace(" ", "_")
        chunk_id = f"{code_file.repo_name}::{safe_path}::{idx}"

        start_line = _estimate_start_line(code_file.content, chunk_text)

        chunks.append(CodeChunk(
            content=chunk_text,
            repo_name=code_file.repo_name,
            file_path=code_file.path,
            language=code_file.language,
            extension=code_file.extension,
            chunk_index=idx,
            total_chunks=total,
            start_line=start_line,
            chunk_id=chunk_id,
        ))

    return chunks


def chunk_repo(code_files: list[CodeFile]) -> list[CodeChunk]:
    """
    Chunk an entire repository's worth of CodeFiles.
    Main entry point used by the embedder (Day 4).

    Args:
        code_files: List of CodeFile objects from repo_loader.py

    Returns:
        Flat list of all CodeChunks across all files
    """
    all_chunks: list[CodeChunk] = []
    skipped_files = 0

    console.print(f"\n[cyan]✂️  Chunking {len(code_files)} files...[/cyan]")

    for code_file in code_files:
        chunks = chunk_file(code_file)
        if chunks:
            all_chunks.extend(chunks)
        else:
            skipped_files += 1

    _print_chunk_summary(all_chunks, skipped_files)
    return all_chunks


def _print_chunk_summary(chunks: list[CodeChunk], skipped: int) -> None:
    """Print a summary of chunking results."""
    from collections import Counter

    lang_counts = Counter(c.language for c in chunks)

    table = Table(title=f"✂️  Chunking Complete — {len(chunks)} total chunks")
    table.add_column("Language", style="cyan")
    table.add_column("Chunks", style="green", justify="right")

    for lang, count in lang_counts.most_common():
        table.add_row(lang, str(count))

    console.print(table)

    if skipped:
        console.print(f"[yellow]⚠️  Skipped {skipped} empty files[/yellow]")

    # Stats
    avg_len = sum(len(c.content) for c in chunks) / len(chunks) if chunks else 0
    console.print(f"[dim]Avg chunk size: {avg_len:.0f} chars | "
                  f"Chunk size: {CHUNK_SIZE} | Overlap: {CHUNK_OVERLAP}[/dim]")


# ── Sanity Check ──────────────────────────────────────────────────────────────

if __name__ == "__main__":
    import sys
    from ingestion.repo_loader import load_repo

    test_url = sys.argv[1] if len(sys.argv) > 1 else "https://github.com/tiangolo/fastapi"

    console.print(f"\n[bold cyan]🧠 CodeMind — Day 3 Sanity Check[/bold cyan]")
    console.print(f"[dim]Repo: {test_url}[/dim]\n")

    # Load repo (will use cached clone from Day 2)
    code_files = load_repo(test_url)

    # Chunk everything
    chunks = chunk_repo(code_files)

    # Show a sample chunk
    if chunks:
        sample = chunks[0]
        console.print(f"\n[bold]Sample Chunk:[/bold]")
        console.print(f"  ID       : [cyan]{sample.chunk_id}[/cyan]")
        console.print(f"  File     : [green]{sample.file_path}[/green]")
        console.print(f"  Language : {sample.language}")
        console.print(f"  Lines ~  : {sample.start_line}")
        console.print(f"  Length   : {len(sample.content)} chars")
        console.print(f"\n[dim]{sample.content[:300]}...[/dim]")

    console.print(f"\n[bold green]✅ chunker.py works! {len(chunks)} chunks ready for embedding.[/bold green]")
    console.print("[bold]Ready for Day 4 — embedder.py ✅[/bold]")
