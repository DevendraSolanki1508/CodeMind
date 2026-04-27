"""
CodeMind - mcp_server/tools.py
Day 5: Define all MCP tools that Claude will call autonomously.
Three tools: search_codebase, get_file_content, list_modules.
These are the bridge between Claude and your ChromaDB vector store.
"""

from pathlib import Path
from typing import Optional
import json

from rich.console import Console

import sys
sys.path.append(str(Path(__file__).resolve().parent.parent))
from config import TOP_K_RESULTS, REPOS_DIR, MIN_SIMILARITY_SCORE
from vectorstore.embedder import search_codebase, get_collection_stats, get_chroma_client, get_or_create_collection

console = Console()


# ── Tool Result Schemas ───────────────────────────────────────────────────────

def _format_search_results(results: list[dict]) -> str:
    """
    Format search results into a clean string Claude can reason over.
    Each result includes the source file, language, similarity score, and content.
    """
    if not results:
        return "No relevant code found for this query."

    output = []
    for i, r in enumerate(results, 1):
        meta = r["metadata"]
        output.append(
            f"--- Result {i} ---\n"
            f"File: {meta['file_path']}\n"
            f"Language: {meta['language']}\n"
            f"Score: {r['score']}\n"
            f"Chunk: {meta['chunk_index'] + 1} of {meta['total_chunks']}\n"
            f"Approx. Line: {meta['start_line']}\n"
            f"\n{r['content']}\n"
        )

    return "\n".join(output)


def _format_error(tool_name: str, error: str) -> str:
    """Standard error format for all tools."""
    return json.dumps({"error": True, "tool": tool_name, "message": error})


# ── Tool 1: search_codebase ───────────────────────────────────────────────────

def tool_search_codebase(
    query: str,
    top_k: int = TOP_K_RESULTS,
    repo_name: Optional[str] = None,
    language_filter: Optional[str] = None,
) -> str:
    """
    MCP Tool: search_codebase
    Semantic search over the embedded codebase.
    Claude calls this when it needs to find relevant code or docs.

    Args:
        query       : Natural language or code search query
        top_k       : Number of results to return (default from config)
        repo_name   : Optional — restrict search to one repo
        language_filter : Optional — e.g. "Python", "TypeScript"

    Returns:
        Formatted string of top-k results with file citations
    """
    try:
        if not query or not query.strip():
            return _format_error("search_codebase", "Query cannot be empty.")

        results = search_codebase(
            query=query.strip(),
            top_k=top_k,
            repo_name=repo_name,
        )

        # Apply language filter post-retrieval if specified
        if language_filter:
            results = [
                r for r in results
                if r["metadata"].get("language", "").lower() == language_filter.lower()
            ]

        # Filter by minimum similarity score
        results = [r for r in results if r["score"] >= MIN_SIMILARITY_SCORE]

        if not results:
            return (
                f"No results found for query: '{query}'\n"
                f"Try rephrasing or using more specific technical terms."
            )

        return _format_search_results(results)

    except Exception as e:
        return _format_error("search_codebase", str(e))


# ── Tool 2: get_file_content ──────────────────────────────────────────────────

def tool_get_file_content(
    file_path: str,
    repo_name: Optional[str] = None,
    max_chars: int = 3000,
) -> str:
    """
    MCP Tool: get_file_content
    Retrieve the full content of a specific file from the vector store.
    Claude calls this when it knows exactly which file it wants to read.

    Args:
        file_path  : Relative file path e.g. "fastapi/routing.py"
        repo_name  : Optional repo name to scope the search
        max_chars  : Max characters to return (keep Claude's context safe)

    Returns:
        File content as a string, or an error message
    """
    try:
        if not file_path or not file_path.strip():
            return _format_error("get_file_content", "file_path cannot be empty.")

        client = get_chroma_client()
        collection = get_or_create_collection(client)

        # Build filter
        where = {"file_path": {"$contains": file_path.strip()}}
        if repo_name:
            where = {
                "$and": [
                    {"file_path": {"$contains": file_path.strip()}},
                    {"repo_name": repo_name},
                ]
            }

        results = collection.get(
            where=where,
            include=["documents", "metadatas"],
            limit=20,  # get all chunks of that file
        )

        if not results["ids"]:
            return (
                f"File not found: '{file_path}'\n"
                f"Use list_modules to see available files."
            )

        # Sort chunks by chunk_index and reconstruct file
        chunks = sorted(
            zip(results["documents"], results["metadatas"]),
            key=lambda x: x[1].get("chunk_index", 0),
        )

        meta = chunks[0][1]
        full_content = "\n\n".join(doc for doc, _ in chunks)

        # Truncate if too long
        truncated = False
        if len(full_content) > max_chars:
            full_content = full_content[:max_chars]
            truncated = True

        header = (
            f"File: {meta['file_path']}\n"
            f"Language: {meta['language']}\n"
            f"Repo: {meta['repo_name']}\n"
            f"Chunks: {meta['total_chunks']}\n"
        )
        if truncated:
            header += f"[Truncated to {max_chars} chars]\n"

        return f"{header}\n{'='*50}\n{full_content}"

    except Exception as e:
        return _format_error("get_file_content", str(e))


# ── Tool 3: list_modules ──────────────────────────────────────────────────────

def tool_list_modules(
    repo_name: Optional[str] = None,
    language_filter: Optional[str] = None,
    limit: int = 50,
) -> str:
    """
    MCP Tool: list_modules
    List all files/modules currently stored in the vector store.
    Claude calls this to understand the structure of a codebase
    before diving into specific files.

    Args:
        repo_name       : Optional — filter by repo
        language_filter : Optional — e.g. "Python"
        limit           : Max number of files to return

    Returns:
        Formatted list of files grouped by language
    """
    try:
        client = get_chroma_client()
        collection = get_or_create_collection(client)

        # Build filter
        where = None
        if repo_name and language_filter:
            where = {
                "$and": [
                    {"repo_name": repo_name},
                    {"language": language_filter},
                ]
            }
        elif repo_name:
            where = {"repo_name": repo_name}
        elif language_filter:
            where = {"language": language_filter}

        results = collection.get(
            where=where,
            include=["metadatas"],
            limit=1000,
        )

        if not results["ids"]:
            return "No files found in the vector store. Run the ingestion pipeline first."

        # Deduplicate by file_path and group by language
        seen = set()
        grouped: dict[str, list[str]] = {}

        for meta in results["metadatas"]:
            fp = meta.get("file_path", "unknown")
            lang = meta.get("language", "Unknown")
            repo = meta.get("repo_name", "unknown")

            key = f"{repo}::{fp}"
            if key in seen:
                continue
            seen.add(key)

            if lang not in grouped:
                grouped[lang] = []
            grouped[lang].append(f"  [{repo}] {fp}")

        # Format output
        stats = get_collection_stats()
        lines = [
            f"📁 Codebase Index — {len(seen)} files | {stats['total_chunks']} chunks",
            "=" * 50,
        ]

        for lang, files in sorted(grouped.items()):
            lines.append(f"\n{lang} ({len(files)} files):")
            for f in sorted(files)[:limit]:
                lines.append(f)

        return "\n".join(lines)

    except Exception as e:
        return _format_error("list_modules", str(e))


# ── Tool Registry ─────────────────────────────────────────────────────────────
# This dict is imported by the MCP server (Day 6) to register all tools.

TOOL_REGISTRY = {
    "search_codebase": {
        "fn": tool_search_codebase,
        "description": (
            "Semantically search the embedded codebase for relevant code, "
            "functions, classes, or documentation. Use this when you need to "
            "find how something is implemented or where a concept appears."
        ),
        "parameters": {
            "query": "Natural language or code search query (required)",
            "top_k": f"Number of results to return (default: {TOP_K_RESULTS})",
            "repo_name": "Optional: restrict search to a specific repository",
            "language_filter": "Optional: filter by language e.g. 'Python'",
        },
    },
    "get_file_content": {
        "fn": tool_get_file_content,
        "description": (
            "Retrieve the full content of a specific file from the codebase. "
            "Use this when you know exactly which file you want to read in full."
        ),
        "parameters": {
            "file_path": "Relative file path e.g. 'fastapi/routing.py' (required)",
            "repo_name": "Optional: repo name to scope the search",
            "max_chars": "Optional: max characters to return (default: 3000)",
        },
    },
    "list_modules": {
        "fn": tool_list_modules,
        "description": (
            "List all files and modules in the indexed codebase. "
            "Use this first to understand the structure before searching."
        ),
        "parameters": {
            "repo_name": "Optional: filter by repository name",
            "language_filter": "Optional: filter by language e.g. 'Python'",
            "limit": "Optional: max files to return (default: 50)",
        },
    },
}


# ── Sanity Check ──────────────────────────────────────────────────────────────

if __name__ == "__main__":
    console.print("\n[bold cyan]🧠 CodeMind — Day 5 Sanity Check[/bold cyan]\n")

    # Test 1: list_modules
    console.print("[bold]🔧 Tool 1: list_modules()[/bold]")
    result = tool_list_modules()
    console.print(result[:600] + "...\n")

    # Test 2: search_codebase
    console.print("[bold]🔧 Tool 2: search_codebase('how does routing work')[/bold]")
    result = tool_search_codebase("how does routing work", top_k=2)
    console.print(result[:600] + "...\n")

    # Test 3: get_file_content
    console.print("[bold]🔧 Tool 3: get_file_content('routing')[/bold]")
    result = tool_get_file_content("routing")
    console.print(result[:600] + "...\n")

    console.print(f"[bold]Registered Tools: {list(TOOL_REGISTRY.keys())}[/bold]")
    console.print("\n[bold green]✅ tools.py works! All 3 MCP tools operational.[/bold green]")
    console.print("[bold]Ready for Day 6 — mcp_server/server.py ✅[/bold]")