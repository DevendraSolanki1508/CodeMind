"""
CodeMind - vectorstore/embedder.py
Day 4: Embed code chunks using sentence-transformers (all-MiniLM-L6-v2)
and store them persistently in ChromaDB.
After this runs once, chunks are cached — no re-embedding needed.
"""

from pathlib import Path
from typing import Optional

import chromadb
from chromadb.config import Settings
from sentence_transformers import SentenceTransformer
from rich.console import Console
from rich.progress import (
    Progress,
    SpinnerColumn,
    TextColumn,
    BarColumn,
    TaskProgressColumn,
    TimeRemainingColumn,
)
from rich.table import Table

import sys
sys.path.append(str(Path(__file__).resolve().parent.parent))
from config import (
    EMBEDDING_MODEL,
    EMBEDDING_DEVICE,
    CHROMA_DB_PATH,
    CHROMA_COLLECTION_NAME,
    TOP_K_RESULTS,
)
from ingestion.chunker import CodeChunk

console = Console()

# ── Batch size: safe for 8GB RAM on CPU ───────────────────────────────────────
EMBED_BATCH_SIZE = 32


# ── ChromaDB Client (singleton) ───────────────────────────────────────────────

def get_chroma_client() -> chromadb.PersistentClient:
    """Return a persistent ChromaDB client."""
    return chromadb.PersistentClient(
        path=CHROMA_DB_PATH,
        settings=Settings(anonymized_telemetry=False),
    )


def get_or_create_collection(client: chromadb.PersistentClient) -> chromadb.Collection:
    """Get existing collection or create a new one."""
    return client.get_or_create_collection(
        name=CHROMA_COLLECTION_NAME,
        metadata={"hnsw:space": "cosine"},  # cosine similarity for code search
    )


# ── Embedding Model (singleton) ───────────────────────────────────────────────

_model: Optional[SentenceTransformer] = None

def get_embedding_model() -> SentenceTransformer:
    """Load embedding model once and cache it in memory."""
    global _model
    if _model is None:
        console.print(f"[cyan]📦 Loading embedding model: {EMBEDDING_MODEL}[/cyan]")
        console.print(f"[dim]   Device: {EMBEDDING_DEVICE} | First load downloads ~80MB[/dim]")
        _model = SentenceTransformer(EMBEDDING_MODEL, device=EMBEDDING_DEVICE)
        console.print(f"[green]✅ Model loaded[/green]")
    return _model


# ── Core Embedder ─────────────────────────────────────────────────────────────

def embed_chunks(chunks: list[CodeChunk], force_reembed: bool = False) -> int:
    """
    Embed all chunks and store in ChromaDB.
    Skips chunks that are already stored (by chunk_id) unless force_reembed=True.

    Args:
        chunks: List of CodeChunk objects from chunker.py
        force_reembed: Delete existing collection and re-embed everything

    Returns:
        Number of new chunks embedded
    """
    if not chunks:
        console.print("[yellow]⚠️  No chunks to embed.[/yellow]")
        return 0

    client = get_chroma_client()

    # Handle force re-embed
    if force_reembed:
        console.print("[yellow]🗑  Deleting existing collection...[/yellow]")
        try:
            client.delete_collection(CHROMA_COLLECTION_NAME)
        except Exception:
            pass

    collection = get_or_create_collection(client)
    model = get_embedding_model()

    # Find which chunks are already stored
    existing_ids = set()
    try:
        existing = collection.get(include=[])
        existing_ids = set(existing["ids"])
    except Exception:
        pass

    # Filter to only new chunks
    new_chunks = [c for c in chunks if c.chunk_id not in existing_ids]

    if not new_chunks:
        console.print(f"[green]✅ All {len(chunks)} chunks already embedded. Nothing to do.[/green]")
        return 0

    console.print(f"\n[cyan]🔢 Embedding {len(new_chunks)} new chunks "
                  f"({len(existing_ids)} already cached)...[/cyan]")

    # Embed in batches
    total_embedded = 0

    with Progress(
        SpinnerColumn(),
        TextColumn("[progress.description]{task.description}"),
        BarColumn(),
        TaskProgressColumn(),
        TimeRemainingColumn(),
    ) as progress:
        task = progress.add_task("Embedding...", total=len(new_chunks))

        for i in range(0, len(new_chunks), EMBED_BATCH_SIZE):
            batch = new_chunks[i : i + EMBED_BATCH_SIZE]

            texts = [c.content for c in batch]
            ids = [c.chunk_id for c in batch]
            metadatas = [c.to_metadata() for c in batch]

            # Generate embeddings
            embeddings = model.encode(
                texts,
                batch_size=EMBED_BATCH_SIZE,
                show_progress_bar=False,
                normalize_embeddings=True,  # needed for cosine similarity
            ).tolist()

            # Store in ChromaDB
            collection.add(
                ids=ids,
                embeddings=embeddings,
                documents=texts,
                metadatas=metadatas,
            )

            total_embedded += len(batch)
            progress.update(task, advance=len(batch))

    console.print(f"[bold green]✅ Embedded {total_embedded} chunks into ChromaDB[/bold green]")
    console.print(f"[dim]   Stored at: {CHROMA_DB_PATH}[/dim]")
    return total_embedded


# ── Search (preview of what MCP tools will use) ───────────────────────────────

def search_codebase(query: str, top_k: int = TOP_K_RESULTS, repo_name: Optional[str] = None) -> list[dict]:
    """
    Semantic search over the embedded codebase.
    This is a preview — the full MCP tool wraps this on Day 5.

    Args:
        query: Natural language or code query
        top_k: Number of results to return
        repo_name: Optional filter to search within a specific repo

    Returns:
        List of result dicts with content, metadata, and score
    """
    client = get_chroma_client()
    collection = get_or_create_collection(client)
    model = get_embedding_model()

    # Embed the query
    query_embedding = model.encode(
        query,
        normalize_embeddings=True,
    ).tolist()

    # Build optional filter
    where = {"repo_name": repo_name} if repo_name else None

    # Query ChromaDB
    results = collection.query(
        query_embeddings=[query_embedding],
        n_results=min(top_k, collection.count()),
        where=where,
        include=["documents", "metadatas", "distances"],
    )

    # Format results
    formatted = []
    if results["ids"] and results["ids"][0]:
        for doc, meta, dist in zip(
            results["documents"][0],
            results["metadatas"][0],
            results["distances"][0],
        ):
            formatted.append({
                "content": doc,
                "metadata": meta,
                "score": round(1 - dist, 4),  # convert distance → similarity
            })

    return formatted


def get_collection_stats() -> dict:
    """Return stats about the current ChromaDB collection."""
    client = get_chroma_client()
    collection = get_or_create_collection(client)
    count = collection.count()
    return {"total_chunks": count, "collection": CHROMA_COLLECTION_NAME}


# ── Sanity Check ──────────────────────────────────────────────────────────────

if __name__ == "__main__":
    import sys
    from ingestion.repo_loader import load_repo
    from ingestion.chunker import chunk_repo

    test_url = sys.argv[1] if len(sys.argv) > 1 else "https://github.com/tiangolo/fastapi"

    console.print(f"\n[bold cyan]🧠 CodeMind — Day 4 Sanity Check[/bold cyan]")
    console.print(f"[dim]Repo: {test_url}[/dim]\n")

    # Full pipeline: load → chunk → embed
    code_files = load_repo(test_url)
    chunks = chunk_repo(code_files)
    embed_chunks(chunks)

    # Stats
    stats = get_collection_stats()
    console.print(f"\n[bold]ChromaDB Stats:[/bold]")
    console.print(f"  Collection : [cyan]{stats['collection']}[/cyan]")
    console.print(f"  Total chunks stored : [green]{stats['total_chunks']}[/green]")

    # Test search
    console.print(f"\n[bold]🔍 Test Search:[/bold] 'how does dependency injection work?'")
    results = search_codebase("how does dependency injection work?", top_k=3)

    for i, r in enumerate(results, 1):
        console.print(f"\n[cyan]Result {i}[/cyan] — score: [green]{r['score']}[/green]")
        console.print(f"  File: {r['metadata']['file_path']}")
        console.print(f"  Lang: {r['metadata']['language']}")
        console.print(f"  [dim]{r['content'][:200]}...[/dim]")

    console.print(f"\n[bold green]✅ embedder.py works! ChromaDB is live.[/bold green]")
    console.print("[bold]Ready for Day 5 — mcp_server/tools.py ✅[/bold]")