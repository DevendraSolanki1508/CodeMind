"""
CodeMind - api/routes.py
Day 7 (final): FastAPI routes — manual RAG without tool calling.
We handle retrieval ourselves, then pass context to LLaMA for synthesis.
No tool calling = no Groq schema issues.
"""

from pathlib import Path
from typing import Optional
import time

from fastapi import FastAPI, HTTPException, BackgroundTasks
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, Field
from rich.console import Console

import sys
sys.path.append(str(Path(__file__).resolve().parent.parent))
from config import (
    APP_NAME,
    APP_VERSION,
    APP_DESCRIPTION,
    GROQ_API_KEY,
    TOP_K_RESULTS,
)
from mcp_server.tools import tool_search_codebase, tool_list_modules
from vectorstore.embedder import get_collection_stats

console = Console()

app = FastAPI(title=APP_NAME, version=APP_VERSION, description=APP_DESCRIPTION)
app.add_middleware(CORSMiddleware, allow_origins=["*"], allow_methods=["*"], allow_headers=["*"])

ingestion_state = {
    "status": "idle", "repo_url": None, "files_loaded": 0,
    "chunks_embedded": 0, "error": None, "started_at": None, "finished_at": None,
}


# ── Schemas ───────────────────────────────────────────────────────────────────

class ChatRequest(BaseModel):
    question: str = Field(..., min_length=1)
    repo_name: Optional[str] = Field(None)
    top_k: int = Field(TOP_K_RESULTS, ge=1, le=20)

class ChatResponse(BaseModel):
    answer: str
    sources: list[dict]
    tools_called: list[str]
    duration_ms: int

class IngestRequest(BaseModel):
    github_url: str
    force_reembed: bool = False

class IngestResponse(BaseModel):
    message: str
    status: str

class StatusResponse(BaseModel):
    app: str
    version: str
    collection_stats: dict
    ingestion: dict


# ── Manual RAG (no tool calling) ──────────────────────────────────────────────

def _run_rag_chat(question: str, repo_name: Optional[str], top_k: int) -> dict:
    """
    Manual RAG pipeline:
    1. Search ChromaDB for relevant chunks
    2. Build a context prompt with the retrieved code
    3. Send to LLaMA for synthesis — no tool calling involved
    """
    from groq import Groq
    import httpx

    client = Groq(
        api_key=GROQ_API_KEY,
        http_client=httpx.Client(verify=False),
    )

    # Step 1 — Retrieve relevant chunks from ChromaDB
    console.print(f"[cyan]🔍 Searching codebase for: {question}[/cyan]")
    search_result = tool_search_codebase(
        query=question,
        top_k=top_k,
        repo_name=repo_name,
    )

    # Step 2 — Extract sources for citation
    sources = []
    for line in search_result.split("\n"):
        if line.startswith("File:"):
            fp = line.replace("File:", "").strip()
            if {"file": fp} not in sources:
                sources.append({"file": fp})

    console.print(f"[green]✅ Retrieved {len(sources)} source files[/green]")

    # Step 3 — Build context prompt
    system_prompt = (
        "You are CodeMind, an expert codebase assistant. "
        "Answer questions about code based ONLY on the provided context. "
        "Always cite the exact file path when referencing code. "
        "Be concise but thorough."
    )

    user_prompt = f"""Question: {question}

Here is the relevant code context retrieved from the codebase:

{search_result}

Based on the above context, please answer the question. 
Cite specific files when referencing code."""

    # Step 4 — Send to LLaMA for synthesis (no tools)
    response = client.chat.completions.create(
        model="llama-3.3-70b-versatile",
        messages=[
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_prompt},
        ],
        max_tokens=1024,
        temperature=0.1,
    )

    answer = response.choices[0].message.content

    return {
        "answer": answer,
        "sources": sources,
        "tools_called": ["search_codebase"],  # we called it manually
    }


# ── Routes ────────────────────────────────────────────────────────────────────

@app.get("/", tags=["Health"])
async def root():
    return {"app": APP_NAME, "version": APP_VERSION, "status": "running"}


@app.get("/status", response_model=StatusResponse, tags=["Health"])
async def status():
    stats = get_collection_stats()
    return StatusResponse(
        app=APP_NAME, version=APP_VERSION,
        collection_stats=stats, ingestion=ingestion_state,
    )


@app.post("/chat", response_model=ChatResponse, tags=["Chat"])
async def chat(request: ChatRequest):
    if not request.question.strip():
        raise HTTPException(status_code=400, detail="Question cannot be empty.")

    stats = get_collection_stats()
    if stats["total_chunks"] == 0:
        raise HTTPException(status_code=400, detail="No codebase indexed yet. POST to /ingest first.")

    console.print(f"\n[bold cyan]💬 Question:[/bold cyan] {request.question}")
    start = time.time()

    try:
        result = _run_rag_chat(
            question=request.question,
            repo_name=request.repo_name,
            top_k=request.top_k,
        )
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

    duration_ms = int((time.time() - start) * 1000)
    console.print(f"[green]✅ Answer ready in {duration_ms}ms[/green]")

    return ChatResponse(
        answer=result["answer"],
        sources=result["sources"],
        tools_called=result["tools_called"],
        duration_ms=duration_ms,
    )


@app.post("/ingest", response_model=IngestResponse, tags=["Ingestion"])
async def ingest(request: IngestRequest, background_tasks: BackgroundTasks):
    if ingestion_state["status"] == "running":
        raise HTTPException(status_code=409, detail="Ingestion already running.")

    def _run_ingestion():
        from ingestion.repo_loader import load_repo
        from ingestion.chunker import chunk_repo
        from vectorstore.embedder import embed_chunks

        ingestion_state.update({"status": "running", "repo_url": request.github_url,
                                 "started_at": time.time(), "error": None})
        try:
            code_files = load_repo(request.github_url)
            ingestion_state["files_loaded"] = len(code_files)
            chunks = chunk_repo(code_files)
            count = embed_chunks(chunks, force_reembed=request.force_reembed)
            ingestion_state.update({"chunks_embedded": count, "status": "done",
                                     "finished_at": time.time()})
        except Exception as e:
            ingestion_state.update({"status": "error", "error": str(e),
                                     "finished_at": time.time()})

    background_tasks.add_task(_run_ingestion)
    return IngestResponse(
        message=f"Ingestion started for {request.github_url}. Check /status.",
        status="running",
    )


@app.get("/search", tags=["Search"])
async def search(q: str, top_k: int = TOP_K_RESULTS, repo: Optional[str] = None):
    if not q:
        raise HTTPException(status_code=400, detail="Query 'q' is required.")
    result = tool_search_codebase(query=q, top_k=top_k, repo_name=repo)
    return {"query": q, "results": result}


@app.get("/modules", tags=["Search"])
async def modules(repo: Optional[str] = None, language: Optional[str] = None):
    result = tool_list_modules(repo_name=repo, language_filter=language)
    return {"modules": result}