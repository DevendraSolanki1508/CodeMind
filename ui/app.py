import requests
import gradio as gr
from pathlib import Path
import sys
sys.path.append(str(Path(__file__).resolve().parent.parent))
from config import API_HOST, API_PORT, APP_VERSION

API_BASE = f"http://{API_HOST}:{API_PORT}"

def chat(message, history):
    try:
        r = requests.post(f"{API_BASE}/chat", json={"question": message}, timeout=60)
        if r.status_code == 200:
            data = r.json()
            answer = data.get("answer", "No answer.")
            sources = data.get("sources", [])
            if sources:
                files = "\n".join(f"📄 {s['file']}" for s in sources)
                answer += f"\n\n**Sources:**\n{files}"
            return answer
        else:
            return f"❌ Error: {r.json().get('detail', r.text)}"
    except Exception as e:
        return f"❌ {str(e)}"

demo = gr.ChatInterface(
    fn=chat,
    title="🧠 CodeMind",
    description="MCP-powered RAG assistant — chat with any GitHub repository",
    examples=["How does routing work?", "What is dependency injection?", "How are background tasks handled?"],
)

if __name__ == "__main__":
    print(f"\n🧠 CodeMind v{APP_VERSION} — Gradio UI\n   Backend: {API_BASE}\n")
    demo.launch(server_name="0.0.0.0", server_port=7860, show_error=True)