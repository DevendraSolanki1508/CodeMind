"""
CodeMind - config.py
Day 1: Central configuration module.
All constants, environment variables, and path settings live here.
Every other module imports from this file.
"""

import os
from pathlib import Path
from dotenv import load_dotenv

# ── Load .env file ────────────────────────────────────────────────────────────
load_dotenv()

# ── Base Paths ────────────────────────────────────────────────────────────────
BASE_DIR = Path(__file__).resolve().parent
VECTORSTORE_DIR = BASE_DIR / "vectorstore" / "chroma_db"
REPOS_DIR = BASE_DIR / "repos"  # cloned repos land here

# Create dirs if they don't exist
VECTORSTORE_DIR.mkdir(parents=True, exist_ok=True)
REPOS_DIR.mkdir(parents=True, exist_ok=True)

# ── Anthropic ─────────────────────────────────────────────────────────────────
ANTHROPIC_API_KEY: str = os.getenv("ANTHROPIC_API_KEY", "")
CLAUDE_MODEL: str = "claude-sonnet-4-20250514"

if not ANTHROPIC_API_KEY:
    raise EnvironmentError(
        "ANTHROPIC_API_KEY is not set. "
        "Copy .env.example to .env and add your key."
    )

# ── Embedding Model ───────────────────────────────────────────────────────────
# all-MiniLM-L6-v2: only 80MB, CPU-friendly, great for code similarity
EMBEDDING_MODEL: str = os.getenv("EMBEDDING_MODEL", "all-MiniLM-L6-v2")
EMBEDDING_DEVICE: str = "cpu"  # change to "cuda" if GPU available

# ── ChromaDB ──────────────────────────────────────────────────────────────────
CHROMA_DB_PATH: str = os.getenv("CHROMA_DB_PATH", str(VECTORSTORE_DIR))
CHROMA_COLLECTION_NAME: str = "codemind_codebase"

# ── Ingestion Settings ────────────────────────────────────────────────────────
# Laptop-safe limit: keeps RAM usage under control on 8GB machines
MAX_FILES: int = int(os.getenv("MAX_FILES", "200"))

# Code-aware chunk settings
# Smaller chunks = more precise retrieval
# Larger overlap = better context preservation across chunk boundaries
CHUNK_SIZE: int = 512
CHUNK_OVERLAP: int = 64

# File extensions to ingest (covers most codebases)
SUPPORTED_EXTENSIONS: set[str] = {
    # Python
    ".py",
    # JavaScript / TypeScript
    ".js", ".ts", ".jsx", ".tsx",
    # Web
    ".html", ".css",
    # Docs & config
    ".md", ".txt", ".rst", ".yaml", ".yml", ".toml", ".json",
    # Java / Kotlin
    ".java", ".kt",
    # C / C++
    ".c", ".cpp", ".h", ".hpp",
    # Go
    ".go",
    # Rust
    ".rs",
    # Shell
    ".sh", ".bash",
    # Notebooks
    ".ipynb",
}

# Directories to always skip during ingestion
IGNORED_DIRS: set[str] = {
    ".git", "__pycache__", "node_modules", ".venv", "venv",
    "env", ".env", "dist", "build", ".mypy_cache", ".pytest_cache",
    "*.egg-info", ".tox", "coverage", ".DS_Store",
}

# ── MCP Server ────────────────────────────────────────────────────────────────
MCP_SERVER_HOST: str = os.getenv("MCP_SERVER_HOST", "localhost")
MCP_SERVER_PORT: int = int(os.getenv("MCP_SERVER_PORT", "8001"))
MCP_SERVER_URL: str = f"http://{MCP_SERVER_HOST}:{MCP_SERVER_PORT}"

# ── FastAPI ───────────────────────────────────────────────────────────────────
API_HOST: str = os.getenv("API_HOST", "localhost")
API_PORT: int = int(os.getenv("API_PORT", "8000"))

# ── Retrieval Settings ────────────────────────────────────────────────────────
# Top-k chunks to retrieve per MCP tool call
TOP_K_RESULTS: int = 5

# Minimum similarity score to include a chunk (0.0 - 1.0)
MIN_SIMILARITY_SCORE: float = 0.3

# ── Agent Settings ────────────────────────────────────────────────────────────
MAX_AGENT_ITERATIONS: int = 5
AGENT_TEMPERATURE: float = 0.0  # deterministic for code Q&A

# ── Display ───────────────────────────────────────────────────────────────────
APP_NAME: str = "CodeMind"
APP_VERSION: str = "0.1.0"
APP_DESCRIPTION: str = "MCP-powered RAG assistant for any GitHub repository"


# ── Sanity check (run this file directly to verify config loads correctly) ────
if __name__ == "__main__":
    from rich.console import Console
    from rich.table import Table

    console = Console()

    table = Table(title=f"⚙️  {APP_NAME} v{APP_VERSION} — Configuration")
    table.add_column("Setting", style="cyan", no_wrap=True)
    table.add_column("Value", style="green")

    table.add_row("Anthropic API Key", "✅ Loaded" if ANTHROPIC_API_KEY else "❌ Missing")
    table.add_row("Claude Model", CLAUDE_MODEL)
    table.add_row("Embedding Model", EMBEDDING_MODEL)
    table.add_row("Embedding Device", EMBEDDING_DEVICE)
    table.add_row("ChromaDB Path", CHROMA_DB_PATH)
    table.add_row("Max Files", str(MAX_FILES))
    table.add_row("Chunk Size", str(CHUNK_SIZE))
    table.add_row("Chunk Overlap", str(CHUNK_OVERLAP))
    table.add_row("Supported Extensions", str(len(SUPPORTED_EXTENSIONS)) + " types")
    table.add_row("MCP Server", MCP_SERVER_URL)
    table.add_row("FastAPI", f"http://{API_HOST}:{API_PORT}")
    table.add_row("Top-K Retrieval", str(TOP_K_RESULTS))

    console.print(table)
    console.print("\n[bold green]✅ Config loaded successfully. Ready for Day 2![/bold green]")
