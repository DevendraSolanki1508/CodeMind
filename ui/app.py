"""
CodeMind - ui/app.py
Day 8: Gradio UI compatible with Gradio 6.14
"""

import time
from pathlib import Path
import requests
import gradio as gr

import sys
sys.path.append(str(Path(__file__).resolve().parent.parent))
from config import API_HOST, API_PORT, APP_VERSION

API_BASE = f"http://{API_HOST}:{API_PORT}"


def get_status():
    try:
        r = requests.get(f"{API_BASE}/status", timeout=5)
        data = r.json()
        chunks = data.get("collection_stats", {}).get("total_chunks", 0)
        repo = data.get("ingestion", {}).get("repo_url", None)
        return f"✅ Backend online | 📦 {chunks} chunks indexed | 🗂 Repo: {repo or 'None'}"
    except Exception:
        return "❌ Backend offline — run: uvicorn api.routes:app --port 8000"


def ingest_repo(github_url):
    if not github_url.strip():
        return "⚠️ Please enter a GitHub URL."
    try:
        requests.post(
            f"{API_BASE}/ingest",
            json={"github_url": github_url, "force_reembed": False},
            timeout=10,
        )
        for _ in range(60):
            time.sleep(3)
            s = requests.get(f"{API_BASE}/status", timeout=5).json()
            state = s.get("ingestion", {}).get("status", "unknown")
            if state == "done":
                files = s["ingestion"].get("files_loaded", 0)
                chunks = s["ingestion"].get("chunks_embedded", 0)
                return f"✅ Done! {files} files → {chunks} new chunks."
            elif state == "error":
                return f"❌ {s['ingestion'].get('error', 'Unknown error')}"
        return "⏳ Still running. Check /status."
    except Exception as e:
        return f"❌ {str(e)}"


def chat(message, history, repo_name):
    if not message.strip():
        return history, "", "_No sources._", "_No tools._"
    try:
        payload = {"question": message}
        if repo_name.strip():
            payload["repo_name"] = repo_name.strip()

        r = requests.post(f"{API_BASE}/chat", json=payload, timeout=60)

        if r.status_code == 200:
            data = r.json()
            answer = data.get("answer", "No answer.")
            sources = data.get("sources", [])
            tools = data.get("tools_called", [])
            duration = data.get("duration_ms", 0)
            sources_text = "\n".join(f"📄 `{s['file']}`" for s in sources) or "_No sources._"
            tools_text = " → ".join(f"🔧 `{t}`" for t in tools) or "_No tools._"
            tools_text += f" ({duration}ms)"
            history = history + [{"role": "user", "content": message}, {"role": "assistant", "content": answer}]
            return history, "", sources_text, tools_text
        else:
            err = r.json().get("detail", r.text)
            history = history + [{"role": "user", "content": message}, {"role": "assistant", "content": f"❌ {err}"}]
            return history, "", "", ""
    except Exception as e:
        history = history + [{"role": "user", "content": message}, {"role": "assistant", "content": f"❌ {str(e)}"}]
        return history, "", "", ""


with gr.Blocks(title="CodeMind") as demo:
    gr.Markdown(f"# 🧠 CodeMind\n**MCP-powered RAG assistant** · v{APP_VERSION} · LLaMA 3.3 70B · ChromaDB")
    status_md = gr.Markdown(value=get_status())
    gr.Markdown("---")

    with gr.Row():
        with gr.Column(scale=1):
            gr.Markdown("### 📥 Ingest a Repository")
            github_url = gr.Textbox(placeholder="https://github.com/tiangolo/fastapi", label="GitHub URL")
            repo_filter = gr.Textbox(placeholder="Optional: fastapi", label="Repo name filter")
            ingest_btn = gr.Button("🚀 Ingest Repo", variant="primary")
            ingest_status = gr.Markdown("_Enter a GitHub URL and click Ingest._")
            gr.Markdown("---")
            gr.Markdown("### 💡 Example Questions\n- `How does routing work?`\n- `What is dependency injection?`\n- `How are background tasks handled?`\n- `Explain the middleware system`")

        with gr.Column(scale=2):
            gr.Markdown("### 💬 Chat with the Codebase")
            chatbot = gr.Chatbot(label="CodeMind", height=420, show_label=False, type="messages")
            with gr.Row():
                msg_input = gr.Textbox(placeholder="Ask anything about the codebase...", show_label=False, scale=5)
                send_btn = gr.Button("Send ➤", variant="primary", scale=1)
            clear_btn = gr.Button("🗑 Clear Chat", size="sm")

    gr.Markdown("---")
    with gr.Row():
        with gr.Column():
            gr.Markdown("### 📄 Sources Cited")
            sources_box = gr.Markdown("_Sources will appear here._")
        with gr.Column():
            gr.Markdown("### 🔧 Tools Called")
            tools_box = gr.Markdown("_Tool chain will appear here._")

    send_btn.click(fn=chat, inputs=[msg_input, chatbot, repo_filter], outputs=[chatbot, msg_input, sources_box, tools_box])
    msg_input.submit(fn=chat, inputs=[msg_input, chatbot, repo_filter], outputs=[chatbot, msg_input, sources_box, tools_box])
    ingest_btn.click(fn=ingest_repo, inputs=[github_url], outputs=[ingest_status])
    clear_btn.click(fn=lambda: ([], "", "_Sources will appear here._", "_Tool chain will appear here._"), outputs=[chatbot, msg_input, sources_box, tools_box])
    demo.load(fn=get_status, outputs=[status_md])

if __name__ == "__main__":
    print(f"\n🧠 CodeMind v{APP_VERSION} — Gradio UI\n   Backend: {API_BASE}\n")
    demo.launch(server_name="0.0.0.0", server_port=7860, show_error=True)