"""
CodeMind - mcp_server/server.py
Day 6: Spin up the MCP server and register all tools.
Claude connects to this server and autonomously decides
which tools to call and when.
"""

from pathlib import Path
from typing import Any
import asyncio
import json

from mcp.server import Server
from mcp.server.stdio import stdio_server
from mcp import types
from rich.console import Console

import sys
sys.path.append(str(Path(__file__).resolve().parent.parent))
from config import APP_NAME, APP_VERSION, MCP_SERVER_HOST, MCP_SERVER_PORT
from mcp_server.tools import (
    tool_search_codebase,
    tool_get_file_content,
    tool_list_modules,
    TOOL_REGISTRY,
)

console = Console()

# ── MCP Server Instance ───────────────────────────────────────────────────────
app = Server(APP_NAME)


# ── Register: List Tools ──────────────────────────────────────────────────────

@app.list_tools()
async def list_tools() -> list[types.Tool]:
    """Tell Claude which tools are available and what they do."""
    tools = []

    for name, meta in TOOL_REGISTRY.items():
        # Build input schema from parameters
        properties = {}
        required = []

        for param_name, param_desc in meta["parameters"].items():
            properties[param_name] = {
                "type": "string",
                "description": param_desc,
            }
            if "(required)" in param_desc:
                required.append(param_name)

        tools.append(
            types.Tool(
                name=name,
                description=meta["description"],
                inputSchema={
                    "type": "object",
                    "properties": properties,
                    "required": required,
                },
            )
        )

    return tools


# ── Register: Call Tool ───────────────────────────────────────────────────────

@app.call_tool()
async def call_tool(name: str, arguments: dict[str, Any]) -> list[types.TextContent]:
    """
    Route Claude's tool call to the correct function.
    All tools return TextContent that Claude reads and reasons over.
    """
    console.print(f"[cyan]🔧 Tool called: [bold]{name}[/bold][/cyan]")
    console.print(f"[dim]   Args: {json.dumps(arguments, indent=2)[:200]}[/dim]")

    if name not in TOOL_REGISTRY:
        error_msg = f"Unknown tool: '{name}'. Available: {list(TOOL_REGISTRY.keys())}"
        return [types.TextContent(type="text", text=error_msg)]

    tool_fn = TOOL_REGISTRY[name]["fn"]

    try:
        # Run the (synchronous) tool function in a thread pool
        # so we don't block the async event loop
        loop = asyncio.get_event_loop()
        result = await loop.run_in_executor(None, lambda: tool_fn(**arguments))

        console.print(f"[green]✅ Tool '{name}' returned {len(str(result))} chars[/green]")
        return [types.TextContent(type="text", text=str(result))]

    except TypeError as e:
        # Wrong arguments passed
        error = f"Invalid arguments for tool '{name}': {str(e)}"
        console.print(f"[red]❌ {error}[/red]")
        return [types.TextContent(type="text", text=error)]

    except Exception as e:
        error = f"Tool '{name}' failed: {str(e)}"
        console.print(f"[red]❌ {error}[/red]")
        return [types.TextContent(type="text", text=error)]


# ── Register: Server Info ─────────────────────────────────────────────────────

@app.list_prompts()
async def list_prompts() -> list[types.Prompt]:
    """Optional: expose a starter prompt for Claude."""
    return [
        types.Prompt(
            name="explore_codebase",
            description="Start exploring the indexed codebase",
            arguments=[
                types.PromptArgument(
                    name="question",
                    description="What do you want to know about the codebase?",
                    required=True,
                )
            ],
        )
    ]


@app.get_prompt()
async def get_prompt(name: str, arguments: dict[str, str]) -> types.GetPromptResult:
    """Return the starter prompt content."""
    question = arguments.get("question", "Give me an overview of this codebase.")
    return types.GetPromptResult(
        description="Codebase exploration prompt",
        messages=[
            types.PromptMessage(
                role="user",
                content=types.TextContent(
                    type="text",
                    text=(
                        f"You are CodeMind, an expert codebase assistant. "
                        f"You have access to tools to search and read code. "
                        f"Always cite the file and line when referencing code.\n\n"
                        f"Question: {question}"
                    ),
                ),
            )
        ],
    )


# ── Main Entry Point ──────────────────────────────────────────────────────────

async def main():
    console.print(f"\n[bold cyan]🧠 {APP_NAME} v{APP_VERSION} — MCP Server[/bold cyan]")
    console.print(f"[green]✅ Registered tools: {list(TOOL_REGISTRY.keys())}[/green]")
    console.print(f"[dim]Waiting for Claude to connect via stdio...[/dim]\n")

    async with stdio_server() as (read_stream, write_stream):
        await app.run(
            read_stream,
            write_stream,
            app.create_initialization_options(),
        )


if __name__ == "__main__":
    console.print("\n[bold cyan]🧠 CodeMind — Day 6 Sanity Check[/bold cyan]")
    console.print("[dim]Starting MCP server over stdio...[/dim]")
    console.print("[dim]Press Ctrl+C to stop.[/dim]\n")

    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        console.print("\n[yellow]🛑 MCP Server stopped.[/yellow]")