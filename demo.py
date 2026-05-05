"""
CodeMind - demo.py
Day 9: One-command demo script.
Ingests a repo, starts the backend, and launches the UI automatically.
Run: python demo.py
"""

import subprocess
import sys
import time
import webbrowser
from pathlib import Path

import requests
from rich.console import Console
from rich.panel import Panel
from rich.table import Table

console = Console()

API_BASE = "http://localhost:8000"
UI_URL = "http://localhost:7860"
DEMO_REPO = "https://github.com/tiangolo/fastapi"


def check_backend() -> bool:
    try:
        r = requests.get(f"{API_BASE}/status", timeout=3)
        return r.status_code == 200
    except Exception:
        return False


def check_chunks() -> int:
    try:
        r = requests.get(f"{API_BASE}/status", timeout=3)
        return r.json().get("collection_stats", {}).get("total_chunks", 0)
    except Exception:
        return 0


def run_demo():
    console.print(Panel.fit(
        "[bold cyan]🧠 CodeMind — Demo[/bold cyan]\n"
        "[dim]MCP-powered RAG assistant for any GitHub repository[/dim]",
        border_style="cyan",
    ))

    # ── Step 1: Check dependencies ────────────────────────────────────────────
    console.print("\n[bold]Step 1/4 — Checking dependencies...[/bold]")
    try:
        import fastapi, gradio, chromadb, sentence_transformers, groq
        console.print("[green]✅ All dependencies installed[/green]")
    except ImportError as e:
        console.print(f"[red]❌ Missing dependency: {e}[/red]")
        console.print("[yellow]Run: pip install -r requirements.txt[/yellow]")
        sys.exit(1)

    # ── Step 2: Start FastAPI backend ─────────────────────────────────────────
    console.print("\n[bold]Step 2/4 — Starting FastAPI backend...[/bold]")

    if check_backend():
        console.print("[green]✅ Backend already running[/green]")
    else:
        backend_proc = subprocess.Popen(
            [sys.executable, "-m", "uvicorn", "api.routes:app", "--port", "8000"],
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
        )

        # Wait for backend to start
        for i in range(15):
            time.sleep(1)
            if check_backend():
                console.print("[green]✅ Backend started on http://localhost:8000[/green]")
                break
        else:
            console.print("[red]❌ Backend failed to start. Check your .env file.[/red]")
            sys.exit(1)

    # ── Step 3: Ingest demo repo ──────────────────────────────────────────────
    console.print(f"\n[bold]Step 3/4 — Checking vector store...[/bold]")

    chunks = check_chunks()
    if chunks > 0:
        console.print(f"[green]✅ {chunks} chunks already indexed — skipping ingestion[/green]")
    else:
        console.print(f"[cyan]📥 Ingesting demo repo: {DEMO_REPO}[/cyan]")
        console.print("[dim]   This takes 3-5 minutes on first run...[/dim]")

        requests.post(
            f"{API_BASE}/ingest",
            json={"github_url": DEMO_REPO, "force_reembed": False},
            timeout=10,
        )

        # Wait for ingestion
        with console.status("[cyan]Ingesting...[/cyan]"):
            for _ in range(120):
                time.sleep(3)
                try:
                    r = requests.get(f"{API_BASE}/status", timeout=5)
                    state = r.json().get("ingestion", {}).get("status", "unknown")
                    if state == "done":
                        chunks = check_chunks()
                        console.print(f"[green]✅ Ingestion complete — {chunks} chunks indexed[/green]")
                        break
                    elif state == "error":
                        err = r.json().get("ingestion", {}).get("error", "Unknown")
                        console.print(f"[red]❌ Ingestion error: {err}[/red]")
                        sys.exit(1)
                except Exception:
                    pass
            else:
                console.print("[yellow]⚠️  Ingestion taking longer than expected. Check /status.[/yellow]")

    # ── Step 4: Run a test query ──────────────────────────────────────────────
    console.print(f"\n[bold]Step 4/4 — Running test query...[/bold]")

    test_question = "How does dependency injection work?"
    console.print(f"[cyan]💬 Question: {test_question}[/cyan]")

    try:
        r = requests.post(
            f"{API_BASE}/chat",
            json={"question": test_question},
            timeout=60,
        )
        if r.status_code == 200:
            data = r.json()
            answer = data.get("answer", "")[:300]
            sources = data.get("sources", [])
            duration = data.get("duration_ms", 0)

            console.print(f"\n[bold green]✅ Answer ({duration}ms):[/bold green]")
            console.print(f"[dim]{answer}...[/dim]")

            if sources:
                console.print(f"\n[bold]📄 Sources:[/bold]")
                for s in sources[:3]:
                    console.print(f"  • {s['file']}")
        else:
            console.print(f"[yellow]⚠️  Chat test failed: {r.status_code}[/yellow]")
    except Exception as e:
        console.print(f"[yellow]⚠️  Chat test skipped: {e}[/yellow]")

    # ── Launch UI ─────────────────────────────────────────────────────────────
    console.print(f"\n[bold cyan]🚀 Launching Gradio UI...[/bold cyan]")
    console.print(f"[dim]Opening {UI_URL} in your browser...[/dim]\n")

    # Print summary table
    table = Table(title="CodeMind is Ready!")
    table.add_column("Component", style="cyan")
    table.add_column("URL", style="green")
    table.add_row("FastAPI Backend", "http://localhost:8000")
    table.add_row("Swagger Docs", "http://localhost:8000/docs")
    table.add_row("Gradio UI", "http://localhost:7860")
    console.print(table)

    console.print("\n[bold]Example questions to try:[/bold]")
    console.print("  • How does routing work?")
    console.print("  • What is dependency injection?")
    console.print("  • How are background tasks handled?")
    console.print("  • Explain the middleware system\n")

    # Open browser
    time.sleep(1)
    webbrowser.open(UI_URL)

    # Start Gradio UI (blocks until Ctrl+C)
    console.print("[dim]Press Ctrl+C to stop.[/dim]\n")
    subprocess.run([sys.executable, "ui/app.py"])


if __name__ == "__main__":
    run_demo()