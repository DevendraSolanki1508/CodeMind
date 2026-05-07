import { useState, useEffect, useRef, useCallback } from "react";

const API_BASE = "http://localhost:8000";

const COLORS = {
  bg: "#0a0a0f",
  surface: "#111118",
  card: "#16161f",
  border: "#1e1e2e",
  accent: "#7c6af7",
  accentDim: "#2d2458",
  accentGlow: "rgba(124,106,247,0.15)",
  text: "#e8e6f0",
  muted: "#6b6882",
  success: "#34d399",
  warning: "#fbbf24",
  danger: "#f87171",
  info: "#60a5fa",
};

const useAPI = () => {
  const [status, setStatus] = useState(null);

  const fetchStatus = useCallback(async () => {
    try {
      const r = await fetch(`${API_BASE}/status`);
      const d = await r.json();
      setStatus(d);
    } catch {
      setStatus(null);
    }
  }, []);

  useEffect(() => {
    fetchStatus();
    const t = setInterval(fetchStatus, 5000);
    return () => clearInterval(t);
  }, [fetchStatus]);

  return { status, fetchStatus };
};

const Spinner = ({ size = 16 }) => (
  <span style={{
    display: "inline-block", width: size, height: size,
    border: `2px solid ${COLORS.border}`,
    borderTop: `2px solid ${COLORS.accent}`,
    borderRadius: "50%",
    animation: "spin 0.8s linear infinite",
  }} />
);

const Badge = ({ children, color = COLORS.accent }) => (
  <span style={{
    fontSize: 11, fontWeight: 600, letterSpacing: "0.05em",
    padding: "2px 8px", borderRadius: 20,
    background: color + "22", color,
    border: `1px solid ${color}44`,
  }}>{children}</span>
);

const MetricCard = ({ icon, label, value, sub, color = COLORS.accent }) => (
  <div style={{
    background: COLORS.card, border: `1px solid ${COLORS.border}`,
    borderRadius: 12, padding: "16px 20px",
    display: "flex", flexDirection: "column", gap: 4,
  }}>
    <div style={{ fontSize: 20, marginBottom: 4 }}>{icon}</div>
    <div style={{ fontSize: 24, fontWeight: 700, color, fontFamily: "monospace" }}>{value}</div>
    <div style={{ fontSize: 12, color: COLORS.muted, fontWeight: 500 }}>{label}</div>
    {sub && <div style={{ fontSize: 11, color: COLORS.muted }}>{sub}</div>}
  </div>
);

const ChatMessage = ({ role, content, sources, duration }) => (
  <div style={{
    display: "flex", flexDirection: "column",
    alignItems: role === "user" ? "flex-end" : "flex-start",
    gap: 6, marginBottom: 16,
  }}>
    <div style={{
      maxWidth: "78%",
      background: role === "user" ? COLORS.accentDim : COLORS.card,
      border: `1px solid ${role === "user" ? COLORS.accent + "44" : COLORS.border}`,
      borderRadius: role === "user" ? "16px 16px 4px 16px" : "16px 16px 16px 4px",
      padding: "12px 16px",
      color: COLORS.text, fontSize: 14, lineHeight: 1.7,
      whiteSpace: "pre-wrap",
    }}>
      {content}
    </div>
    {sources && sources.length > 0 && (
      <div style={{ maxWidth: "78%", display: "flex", flexWrap: "wrap", gap: 6 }}>
        {sources.map((s, i) => (
          <span key={i} style={{
            fontSize: 11, padding: "3px 8px", borderRadius: 6,
            background: COLORS.surface, border: `1px solid ${COLORS.border}`,
            color: COLORS.info, fontFamily: "monospace",
          }}>
            📄 {s.file?.split("\\").pop() || s.file}
          </span>
        ))}
        {duration && (
          <span style={{ fontSize: 11, color: COLORS.muted, padding: "3px 0" }}>
            {(duration / 1000).toFixed(1)}s
          </span>
        )}
      </div>
    )}
  </div>
);

const Sidebar = ({ activeTab, setActiveTab, status }) => {
  const chunks = status?.collection_stats?.total_chunks || 0;
  const online = !!status;

  const tabs = [
    { id: "chat", icon: "💬", label: "Chat" },
    { id: "repos", icon: "📦", label: "Repositories" },
    { id: "search", icon: "🔍", label: "Search" },
    { id: "analytics", icon: "📊", label: "Analytics" },
  ];

  return (
    <div style={{
      width: 220, background: COLORS.surface,
      borderRight: `1px solid ${COLORS.border}`,
      display: "flex", flexDirection: "column",
      padding: "20px 0", flexShrink: 0,
    }}>
      <div style={{ padding: "0 20px 24px" }}>
        <div style={{ fontSize: 22, fontWeight: 800, color: COLORS.text, letterSpacing: "-0.5px" }}>
          🧠 CodeMind
        </div>
        <div style={{ fontSize: 11, color: COLORS.muted, marginTop: 4 }}>
          MCP · RAG · LLaMA 3.3
        </div>
      </div>

      <div style={{ padding: "0 12px", flex: 1 }}>
        {tabs.map(t => (
          <button key={t.id} onClick={() => setActiveTab(t.id)} style={{
            width: "100%", display: "flex", alignItems: "center", gap: 10,
            padding: "10px 12px", borderRadius: 8, marginBottom: 2,
            background: activeTab === t.id ? COLORS.accentGlow : "transparent",
            border: activeTab === t.id ? `1px solid ${COLORS.accent}33` : "1px solid transparent",
            color: activeTab === t.id ? COLORS.accent : COLORS.muted,
            cursor: "pointer", fontSize: 14, fontWeight: activeTab === t.id ? 600 : 400,
            transition: "all 0.15s",
          }}>
            <span>{t.icon}</span>
            <span>{t.label}</span>
          </button>
        ))}
      </div>

      <div style={{ padding: "16px 20px", borderTop: `1px solid ${COLORS.border}` }}>
        <div style={{ display: "flex", alignItems: "center", gap: 8, marginBottom: 8 }}>
          <div style={{
            width: 8, height: 8, borderRadius: "50%",
            background: online ? COLORS.success : COLORS.danger,
          }} />
          <span style={{ fontSize: 12, color: COLORS.muted }}>
            {online ? "Backend online" : "Backend offline"}
          </span>
        </div>
        <div style={{ fontSize: 11, color: COLORS.muted }}>
          {chunks.toLocaleString()} chunks indexed
        </div>
      </div>
    </div>
  );
};

const ChatPanel = ({ queryHistory, setQueryHistory }) => {
  const [messages, setMessages] = useState([
    { role: "assistant", content: "Hi! I'm CodeMind. Ask me anything about the indexed codebase — I'll search through the code and give you cited answers." }
  ]);
  const [input, setInput] = useState("");
  const [loading, setLoading] = useState(false);
  const bottomRef = useRef(null);

  useEffect(() => {
    bottomRef.current?.scrollIntoView({ behavior: "smooth" });
  }, [messages]);

  const send = async () => {
    if (!input.trim() || loading) return;
    const q = input.trim();
    setInput("");
    setMessages(m => [...m, { role: "user", content: q }]);
    setLoading(true);

    const start = Date.now();
    try {
      const r = await fetch(`${API_BASE}/chat`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ question: q }),
      });
      const d = await r.json();
      if (r.ok) {
        setMessages(m => [...m, {
          role: "assistant",
          content: d.answer,
          sources: d.sources,
          duration: d.duration_ms,
        }]);
        setQueryHistory(h => [{
          question: q,
          answer: d.answer?.slice(0, 120) + "...",
          sources: d.sources?.length || 0,
          duration: d.duration_ms,
          time: new Date().toLocaleTimeString(),
        }, ...h.slice(0, 19)]);
      } else {
        setMessages(m => [...m, { role: "assistant", content: `❌ ${d.detail || "Error"}` }]);
      }
    } catch (e) {
      setMessages(m => [...m, { role: "assistant", content: `❌ Cannot connect to backend. Make sure FastAPI is running on port 8000.` }]);
    }
    setLoading(false);
  };

  const examples = [
    "How does routing work?",
    "What is dependency injection?",
    "How are background tasks handled?",
    "Explain the middleware system",
  ];

  return (
    <div style={{ display: "flex", flexDirection: "column", height: "100%" }}>
      <div style={{ padding: "20px 24px", borderBottom: `1px solid ${COLORS.border}` }}>
        <div style={{ fontSize: 18, fontWeight: 700, color: COLORS.text }}>Chat with Codebase</div>
        <div style={{ fontSize: 13, color: COLORS.muted, marginTop: 2 }}>Ask anything — CodeMind searches and cites</div>
      </div>

      <div style={{ flex: 1, overflowY: "auto", padding: "20px 24px" }}>
        {messages.map((m, i) => (
          <ChatMessage key={i} {...m} />
        ))}
        {loading && (
          <div style={{ display: "flex", alignItems: "center", gap: 10, color: COLORS.muted, fontSize: 13 }}>
            <Spinner /> Searching codebase...
          </div>
        )}
        <div ref={bottomRef} />
      </div>

      <div style={{ padding: "12px 24px", borderTop: `1px solid ${COLORS.border}` }}>
        <div style={{ display: "flex", flexWrap: "wrap", gap: 6, marginBottom: 12 }}>
          {examples.map((e, i) => (
            <button key={i} onClick={() => setInput(e)} style={{
              fontSize: 11, padding: "4px 10px", borderRadius: 20,
              background: COLORS.surface, border: `1px solid ${COLORS.border}`,
              color: COLORS.muted, cursor: "pointer",
            }}>{e}</button>
          ))}
        </div>
        <div style={{ display: "flex", gap: 10 }}>
          <input
            value={input}
            onChange={e => setInput(e.target.value)}
            onKeyDown={e => e.key === "Enter" && send()}
            placeholder="Ask anything about the codebase..."
            style={{
              flex: 1, background: COLORS.card, border: `1px solid ${COLORS.border}`,
              borderRadius: 10, padding: "12px 16px", color: COLORS.text,
              fontSize: 14, outline: "none",
            }}
          />
          <button onClick={send} disabled={loading} style={{
            padding: "12px 20px", borderRadius: 10,
            background: loading ? COLORS.border : COLORS.accent,
            border: "none", color: "#fff", cursor: loading ? "not-allowed" : "pointer",
            fontSize: 14, fontWeight: 600, transition: "all 0.15s",
          }}>
            {loading ? <Spinner size={14} /> : "Send"}
          </button>
        </div>
      </div>
    </div>
  );
};

const ReposPanel = ({ fetchStatus }) => {
  const [url, setUrl] = useState("");
  const [loading, setLoading] = useState(false);
  const [result, setResult] = useState(null);
  const [ingestionState, setIngestionState] = useState(null);

  const ingest = async () => {
    if (!url.trim()) return;
    setLoading(true);
    setResult(null);
    try {
      const r = await fetch(`${API_BASE}/ingest`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ github_url: url.trim(), force_reembed: false }),
      });
      const d = await r.json();
      setResult({ type: "info", msg: d.message });

      const poll = setInterval(async () => {
        const s = await fetch(`${API_BASE}/status`);
        const sd = await s.json();
        const ing = sd.ingestion;
        setIngestionState(ing);
        if (ing.status === "done") {
          clearInterval(poll);
          setResult({ type: "success", msg: `✅ Done! ${ing.files_loaded} files → ${ing.chunks_embedded} new chunks embedded.` });
          setLoading(false);
          fetchStatus();
        } else if (ing.status === "error") {
          clearInterval(poll);
          setResult({ type: "danger", msg: `❌ Error: ${ing.error}` });
          setLoading(false);
        }
      }, 3000);
    } catch (e) {
      setResult({ type: "danger", msg: `❌ ${e.message}` });
      setLoading(false);
    }
  };

  const quickRepos = [
    "https://github.com/tiangolo/fastapi",
    "https://github.com/pallets/flask",
    "https://github.com/django/django",
    "https://github.com/pytorch/pytorch",
  ];

  return (
    <div style={{ padding: "24px", overflowY: "auto", height: "100%" }}>
      <div style={{ fontSize: 18, fontWeight: 700, color: COLORS.text, marginBottom: 4 }}>Repositories</div>
      <div style={{ fontSize: 13, color: COLORS.muted, marginBottom: 24 }}>Ingest any GitHub repository into the vector store</div>

      <div style={{ background: COLORS.card, border: `1px solid ${COLORS.border}`, borderRadius: 12, padding: 20, marginBottom: 20 }}>
        <div style={{ fontSize: 13, fontWeight: 600, color: COLORS.text, marginBottom: 12 }}>Ingest New Repository</div>
        <div style={{ display: "flex", gap: 10, marginBottom: 12 }}>
          <input
            value={url}
            onChange={e => setUrl(e.target.value)}
            placeholder="https://github.com/owner/repo"
            style={{
              flex: 1, background: COLORS.surface, border: `1px solid ${COLORS.border}`,
              borderRadius: 8, padding: "10px 14px", color: COLORS.text,
              fontSize: 13, outline: "none",
            }}
          />
          <button onClick={ingest} disabled={loading} style={{
            padding: "10px 20px", borderRadius: 8,
            background: loading ? COLORS.border : COLORS.accent,
            border: "none", color: "#fff", cursor: loading ? "not-allowed" : "pointer",
            fontSize: 13, fontWeight: 600, whiteSpace: "nowrap",
          }}>
            {loading ? "Ingesting..." : "🚀 Ingest"}
          </button>
        </div>

        {result && (
          <div style={{
            padding: "10px 14px", borderRadius: 8, fontSize: 13,
            background: COLORS[result.type] + "11",
            border: `1px solid ${COLORS[result.type]}33`,
            color: COLORS[result.type],
          }}>{result.msg}</div>
        )}

        {loading && ingestionState && (
          <div style={{ marginTop: 12 }}>
            <div style={{ display: "flex", justifyContent: "space-between", fontSize: 12, color: COLORS.muted, marginBottom: 6 }}>
              <span>Files loaded: {ingestionState.files_loaded || 0}</span>
              <span>{ingestionState.status}</span>
            </div>
            <div style={{ height: 4, background: COLORS.border, borderRadius: 2, overflow: "hidden" }}>
              <div style={{
                height: "100%", background: COLORS.accent, borderRadius: 2,
                width: ingestionState.status === "done" ? "100%" : "60%",
                animation: "progress 2s ease infinite",
              }} />
            </div>
          </div>
        )}
      </div>

      <div style={{ background: COLORS.card, border: `1px solid ${COLORS.border}`, borderRadius: 12, padding: 20 }}>
        <div style={{ fontSize: 13, fontWeight: 600, color: COLORS.text, marginBottom: 12 }}>Quick Add</div>
        <div style={{ display: "flex", flexDirection: "column", gap: 8 }}>
          {quickRepos.map((r, i) => (
            <button key={i} onClick={() => setUrl(r)} style={{
              display: "flex", justifyContent: "space-between", alignItems: "center",
              padding: "10px 14px", borderRadius: 8,
              background: COLORS.surface, border: `1px solid ${COLORS.border}`,
              color: COLORS.text, cursor: "pointer", fontSize: 13,
            }}>
              <span style={{ fontFamily: "monospace", color: COLORS.info }}>{r.replace("https://github.com/", "")}</span>
              <span style={{ color: COLORS.muted, fontSize: 11 }}>Use →</span>
            </button>
          ))}
        </div>
      </div>
    </div>
  );
};

const SearchPanel = () => {
  const [query, setQuery] = useState("");
  const [results, setResults] = useState(null);
  const [loading, setLoading] = useState(false);

  const search = async () => {
    if (!query.trim()) return;
    setLoading(true);
    try {
      const r = await fetch(`${API_BASE}/search?q=${encodeURIComponent(query)}&top_k=8`);
      const d = await r.json();
      setResults(d.results);
    } catch (e) {
      setResults("error");
    }
    setLoading(false);
  };

  const parseResults = (raw) => {
    if (!raw || raw === "error") return [];
    const blocks = raw.split("--- Result").filter(b => b.trim());
    return blocks.map(b => {
      const lines = b.split("\n").filter(l => l.trim());
      const file = lines.find(l => l.startsWith("File:"))?.replace("File:", "").trim();
      const lang = lines.find(l => l.startsWith("Language:"))?.replace("Language:", "").trim();
      const score = lines.find(l => l.startsWith("Score:"))?.replace("Score:", "").trim();
      const contentStart = lines.findIndex(l => l.startsWith("Approx. Line:")) + 1;
      const content = lines.slice(contentStart).join("\n").trim();
      return { file, lang, score, content };
    }).filter(r => r.file);
  };

  const parsed = results ? parseResults(results) : [];

  return (
    <div style={{ padding: "24px", overflowY: "auto", height: "100%" }}>
      <div style={{ fontSize: 18, fontWeight: 700, color: COLORS.text, marginBottom: 4 }}>Semantic Search</div>
      <div style={{ fontSize: 13, color: COLORS.muted, marginBottom: 24 }}>Search directly over the vector store</div>

      <div style={{ display: "flex", gap: 10, marginBottom: 20 }}>
        <input
          value={query}
          onChange={e => setQuery(e.target.value)}
          onKeyDown={e => e.key === "Enter" && search()}
          placeholder="Search the codebase..."
          style={{
            flex: 1, background: COLORS.card, border: `1px solid ${COLORS.border}`,
            borderRadius: 8, padding: "10px 14px", color: COLORS.text,
            fontSize: 13, outline: "none",
          }}
        />
        <button onClick={search} disabled={loading} style={{
          padding: "10px 20px", borderRadius: 8,
          background: loading ? COLORS.border : COLORS.accent,
          border: "none", color: "#fff", cursor: "pointer",
          fontSize: 13, fontWeight: 600,
        }}>
          {loading ? <Spinner size={14} /> : "Search"}
        </button>
      </div>

      {parsed.length > 0 && (
        <div style={{ display: "flex", flexDirection: "column", gap: 12 }}>
          {parsed.map((r, i) => (
            <div key={i} style={{
              background: COLORS.card, border: `1px solid ${COLORS.border}`,
              borderRadius: 10, padding: 16,
            }}>
              <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", marginBottom: 8 }}>
                <span style={{ fontFamily: "monospace", fontSize: 12, color: COLORS.info }}>
                  📄 {r.file}
                </span>
                <div style={{ display: "flex", gap: 6 }}>
                  {r.lang && <Badge color={COLORS.accent}>{r.lang}</Badge>}
                  {r.score && <Badge color={COLORS.success}>{parseFloat(r.score).toFixed(2)}</Badge>}
                </div>
              </div>
              <pre style={{
                fontSize: 12, color: COLORS.muted, whiteSpace: "pre-wrap",
                fontFamily: "monospace", lineHeight: 1.6,
                maxHeight: 120, overflow: "hidden",
                margin: 0,
              }}>{r.content?.slice(0, 300)}{r.content?.length > 300 ? "..." : ""}</pre>
            </div>
          ))}
        </div>
      )}
    </div>
  );
};

const AnalyticsPanel = ({ queryHistory, status }) => {
  const chunks = status?.collection_stats?.total_chunks || 0;
  const totalQueries = queryHistory.length;
  const avgDuration = queryHistory.length
    ? Math.round(queryHistory.reduce((a, b) => a + (b.duration || 0), 0) / queryHistory.length)
    : 0;
  const avgSources = queryHistory.length
    ? (queryHistory.reduce((a, b) => a + (b.sources || 0), 0) / queryHistory.length).toFixed(1)
    : 0;

  return (
    <div style={{ padding: "24px", overflowY: "auto", height: "100%" }}>
      <div style={{ fontSize: 18, fontWeight: 700, color: COLORS.text, marginBottom: 4 }}>Analytics</div>
      <div style={{ fontSize: 13, color: COLORS.muted, marginBottom: 24 }}>Session metrics and query history</div>

      <div style={{ display: "grid", gridTemplateColumns: "repeat(2, 1fr)", gap: 12, marginBottom: 24 }}>
        <MetricCard icon="📦" label="Chunks Indexed" value={chunks.toLocaleString()} color={COLORS.accent} />
        <MetricCard icon="💬" label="Queries This Session" value={totalQueries} color={COLORS.info} />
        <MetricCard icon="⚡" label="Avg Response Time" value={avgDuration ? `${(avgDuration / 1000).toFixed(1)}s` : "—"} color={COLORS.success} />
        <MetricCard icon="📄" label="Avg Sources Cited" value={avgSources || "—"} color={COLORS.warning} />
      </div>

      <div style={{ background: COLORS.card, border: `1px solid ${COLORS.border}`, borderRadius: 12, padding: 20 }}>
        <div style={{ fontSize: 13, fontWeight: 600, color: COLORS.text, marginBottom: 16 }}>Query History</div>
        {queryHistory.length === 0 ? (
          <div style={{ fontSize: 13, color: COLORS.muted, textAlign: "center", padding: "20px 0" }}>
            No queries yet. Ask something in the Chat tab.
          </div>
        ) : (
          <div style={{ display: "flex", flexDirection: "column", gap: 10 }}>
            {queryHistory.map((q, i) => (
              <div key={i} style={{
                padding: "12px 14px", borderRadius: 8,
                background: COLORS.surface, border: `1px solid ${COLORS.border}`,
              }}>
                <div style={{ display: "flex", justifyContent: "space-between", marginBottom: 4 }}>
                  <span style={{ fontSize: 13, fontWeight: 600, color: COLORS.text }}>{q.question}</span>
                  <span style={{ fontSize: 11, color: COLORS.muted }}>{q.time}</span>
                </div>
                <div style={{ fontSize: 12, color: COLORS.muted, marginBottom: 6 }}>{q.answer}</div>
                <div style={{ display: "flex", gap: 8 }}>
                  <Badge color={COLORS.info}>{q.sources} sources</Badge>
                  <Badge color={COLORS.success}>{(q.duration / 1000).toFixed(1)}s</Badge>
                </div>
              </div>
            ))}
          </div>
        )}
      </div>
    </div>
  );
};

export default function App() {
  const [activeTab, setActiveTab] = useState("chat");
  const [queryHistory, setQueryHistory] = useState([]);
  const { status, fetchStatus } = useAPI();

  return (
    <>
      <style>{`
        * { box-sizing: border-box; margin: 0; padding: 0; }
        body { background: ${COLORS.bg}; font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', sans-serif; color: ${COLORS.text}; }
        @keyframes spin { to { transform: rotate(360deg); } }
        @keyframes progress { 0% { transform: translateX(-100%); } 100% { transform: translateX(200%); } }
        ::-webkit-scrollbar { width: 4px; }
        ::-webkit-scrollbar-track { background: transparent; }
        ::-webkit-scrollbar-thumb { background: ${COLORS.border}; border-radius: 2px; }
        input::placeholder { color: ${COLORS.muted}; }
      `}</style>
      <div style={{ display: "flex", height: "100vh", overflow: "hidden" }}>
        <Sidebar activeTab={activeTab} setActiveTab={setActiveTab} status={status} />
        <div style={{ flex: 1, overflow: "hidden", display: "flex", flexDirection: "column" }}>
          {activeTab === "chat" && <ChatPanel queryHistory={queryHistory} setQueryHistory={setQueryHistory} />}
          {activeTab === "repos" && <ReposPanel fetchStatus={fetchStatus} />}
          {activeTab === "search" && <SearchPanel />}
          {activeTab === "analytics" && <AnalyticsPanel queryHistory={queryHistory} status={status} />}
        </div>
      </div>
    </>
  );
}