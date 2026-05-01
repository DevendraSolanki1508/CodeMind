"""
CodeMind - api/routes.py
Day 7 (final): FastAPI routes with Groq (LLaMA 3.3 70B) as the LLM.
Free, fast, no quota issues. Same endpoints, same tool-calling loop.
"""

from pathlib import Path
from typing import Optional
import time
import json

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
from mcp_server.tools import (
    tool_search_codebase,
    tool_get_file_content,
    tool_list_modules,
)
from vectorstore.embedder import get_collection_stats

console = Console()

# ── FastAPI App ───────────────────────────────────────────────────────────────

app = FastAPI(
    title=APP_NAME,
    version=APP_VERSION,
    description=APP_DESCRIPTION,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

# ── Ingestion state ───────────────────────────────────────────────────────────
ingestion_state = {
    "status": "idle",
    "repo_url": None,
    "files_loaded": 0,
    "chunks_embedded": 0,
    "error": None,
    "started_at": None,
    "finished_at": None,
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


# ── Groq Tool Definitions ─────────────────────────────────────────────────────

GROQ_TOOLS = [
    {
        "type": "function",
        "function": {
            "name": "search_codebase",
            "description": "Semantically search the codebase for relevant code, functions, classes, or documentation. Use this when you need to find how something is implemented.",
            "parameters": {
                "type": "object",
                "properties": {
                    "query": {"type": "string", "description": "Natural language search query"},
                    "top_k": {"type": "integer", "description": "Number of results to return"},
                    "repo_name": {"type": "string", "description": "Optional repo name filter"},
                },
                "required": ["query"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "get_file_content",
            "description": "Retrieve the full content of a specific file from the codebase.",
            "parameters": {
                "type": "object",
                "properties": {
                    "file_path": {"type": "string", "description": "Relative file path"},
                    "repo_name": {"type": "string", "description": "Optional repo filter"},
                },
                "required": ["file_path"],
            },
        },
    },
    {
    "type": "function",
    "function": {
        "name": "list_modules",
        "description": "List all files and modules in the indexed codebase. Use this first to understand structure. Call with no arguments to list everything.",
        "parameters": {
            "type": "object",
            "properties": {
                "repo_name": {"type": "string", "description": "Optional repo filter"},
            },
        },
    },
},
]


# ── Tool Router ───────────────────────────────────────────────────────────────

def _call_tool(name: str, args: dict) -> str:
    console.print(f"[cyan]🔧 LLaMA calling: {name}({args})[/cyan]")
    if name == "search_codebase":
        return tool_search_codebase(**args)
    elif name == "get_file_content":
        return tool_get_file_content(**args)
    elif name == "list_modules":
        return tool_list_modules(**args)
    return f"Unknown tool: {name}"


# ── Agentic Chat with Groq ────────────────────────────────────────────────────

def _run_agentic_chat(question: str, repo_name: Optional[str], top_k: int) -> dict:
    """
    Agentic loop using Groq (LLaMA 3.3 70B) with OpenAI-compatible tool calling.
    LLaMA decides which tools to call, iterates, then synthesizes a cited answer.
    """
    from groq import Groq
    import httpx

    client = Groq(
    api_key=GROQ_API_KEY,
    http_client=httpx.Client(verify=False),
)

    tools_called = []
    sources = []

    system_prompt = (
        "You are CodeMind, an expert codebase assistant. "
        "You have tools to search and read code from an indexed repository. "
        "Always cite the exact file path when referencing code. "
        "Be concise but thorough. Search multiple times with different queries if needed."
    )

    messages = [
        {"role": "system", "content": system_prompt},
        {"role": "user", "content": question},
    ]

    # Agentic loop — LLaMA calls tools until it has enough context
    for _ in range(5):
        response = client.chat.completions.create(
            model="llama-3.3-70b-versatile",
            messages=messages,
            tools=GROQ_TOOLS,
            tool_choice="auto",
            max_tokens=2048,
        )

        msg = response.choices[0].message
        finish_reason = response.choices[0].finish_reason

        # Add assistant message to history
        messages.append({
            "role": "assistant",
            "content": msg.content or "",
            "tool_calls": [
                {
                    "id": tc.id,
                    "type": "function",
                    "function": {
                        "name": tc.function.name,
                        "arguments": tc.function.arguments,
                    }
                }
                for tc in (msg.tool_calls or [])
            ] or None,
        })

        # No tool calls — final answer
        if finish_reason == "stop" or not msg.tool_calls:
            answer = msg.content or "No answer generated."
            return {"answer": answer, "sources": sources, "tools_called": tools_called}

        # Process tool calls
        for tc in msg.tool_calls:
            tool_name = tc.function.name
            try:
                tool_args = json.loads(tc.function.arguments)
            except Exception:
                tool_args = {}

            # Inject defaults
            if tool_name == "search_codebase":
                tool_args.setdefault("top_k", top_k)
                if repo_name:
                    tool_args.setdefault("repo_name", repo_name)

            tools_called.append(tool_name)
            result = _call_tool(tool_name, tool_args)

            # Extract sources
            if tool_name == "search_codebase":
                for line in result.split("\n"):
                    if line.startswith("File:"):
                        fp = line.replace("File:", "").strip()
                        if {"file": fp} not in sources:
                            sources.append({"file": fp})

            # Add tool result to message history
            messages.append({
                "role": "tool",
                "tool_call_id": tc.id,
                "content": result,
            })

    return {
        "answer": "Could not find a complete answer. Try rephrasing your question.",
        "sources": sources,
        "tools_called": tools_called,
    }


# ── Routes ────────────────────────────────────────────────────────────────────

@app.get("/", tags=["Health"])
async def root():
    return {"app": APP_NAME, "version": APP_VERSION, "status": "running"}


@app.get("/status", response_model=StatusResponse, tags=["Health"])
async def status():
    stats = get_collection_stats()
    return StatusResponse(
        app=APP_NAME,
        version=APP_VERSION,
        collection_stats=stats,
        ingestion=ingestion_state,
    )


@app.post("/chat", response_model=ChatResponse, tags=["Chat"])
async def chat(request: ChatRequest):
    """
    Main chat endpoint.
    LLaMA 3.3 70B autonomously searches the codebase and returns a cited answer.
    """
    if not request.question.strip():
        raise HTTPException(status_code=400, detail="Question cannot be empty.")

    stats = get_collection_stats()
    if stats["total_chunks"] == 0:
        raise HTTPException(
            status_code=400,
            detail="No codebase indexed yet. POST to /ingest first."
        )

    console.print(f"\n[bold cyan]💬 Question:[/bold cyan] {request.question}")
    start = time.time()

    try:
        result = _run_agentic_chat(
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
    """Ingest a GitHub repository into the vector store."""
    if ingestion_state["status"] == "running":
        raise HTTPException(status_code=409, detail="Ingestion already running.")

    def _run_ingestion():
        from ingestion.repo_loader import load_repo
        from ingestion.chunker import chunk_repo
        from vectorstore.embedder import embed_chunks

        ingestion_state.update({
            "status": "running",
            "repo_url": request.github_url,
            "started_at": time.time(),
            "error": None,
        })
        try:
            code_files = load_repo(request.github_url)
            ingestion_state["files_loaded"] = len(code_files)
            chunks = chunk_repo(code_files)
            count = embed_chunks(chunks, force_reembed=request.force_reembed)
            ingestion_state.update({
                "chunks_embedded": count,
                "status": "done",
                "finished_at": time.time(),
            })
        except Exception as e:
            ingestion_state.update({
                "status": "error",
                "error": str(e),
                "finished_at": time.time(),
            })

    background_tasks.add_task(_run_ingestion)
    return IngestResponse(
        message=f"Ingestion started for {request.github_url}. Check /status.",
        status="running",
    )


@app.get("/search", tags=["Search"])
async def search(q: str, top_k: int = TOP_K_RESULTS, repo: Optional[str] = None):
    """Quick search endpoint for testing retrieval directly."""
    if not q:
        raise HTTPException(status_code=400, detail="Query 'q' is required.")
    result = tool_search_codebase(query=q, top_k=top_k, repo_name=repo)
    return {"query": q, "results": result}


@app.get("/modules", tags=["Search"])
async def modules(repo: Optional[str] = None, language: Optional[str] = None):
    """List all indexed modules/files."""
    result = tool_list_modules(repo_name=repo, language_filter=language)
    return {"modules": result}