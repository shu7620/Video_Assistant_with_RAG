import React, { useState, useEffect, useRef } from "react";

function App() {
  // Authentication Elements
  const [token, setToken] = useState(localStorage.getItem("token"));
  const [isSignUp, setIsSignUp] = useState(false);
  const [authEmail, setAuthEmail] = useState("");
  const [authPassword, setAuthPassword] = useState("");
  const [authMessage, setAuthMessage] = useState(null);

  // App Dashboard States
  const [url, setUrl] = useState("");
  const [language, setLanguage] = useState("english");
  const [taskId, setTaskId] = useState(null);
  const [status, setStatus] = useState("idle");
  const [error, setError] = useState(null);
  const [history, setHistory] = useState([]);
  
  const [data, setData] = useState({ title: "", summary: "", action_items: "", key_decisions: "", open_questions: "" });
  const [activeTab, setActiveTab] = useState("summary");

  // Chat parameters
  const [question, setQuestion] = useState("");
  const [chatHistory, setChatHistory] = useState([]);
  const [chatLoading, setChatLoading] = useState(false);
  const chatEndRef = useRef(null);

  useEffect(() => { chatEndRef.current?.scrollIntoView({ behavior: "smooth" }); }, [chatHistory]);

  // Fetch past histories when logged in
  const fetchHistory = async () => {
    if (!token) return;
    try {
      const res = await fetch("http://127.0.0.1:8000/api/history", {
        headers: { "Authorization": `Bearer ${token}` }
      });
      if (res.ok) setHistory(await res.json());
    } catch (err) { console.error("Error fetching history", err); }
  };

  useEffect(() => { fetchHistory(); }, [token]);

  // Handle Authentication Submission
  const handleAuth = async (e) => {
    e.preventDefault();
    setAuthMessage(null);
    const endpoint = isSignUp ? "signup" : "login";
    try {
      const response = await fetch(`http://127.0.0.1:8000/api/auth/${endpoint}`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ email: authEmail, password: authPassword })
      });
      const resData = await response.json();
      if (!response.ok) throw new Error(resData.detail || "Authentication Failed.");

      if (isSignUp) {
        setAuthMessage({ type: "success", text: resData.message });
        setIsSignUp(false);
      } else {
        localStorage.setItem("token", resData.access_token);
        setToken(resData.access_token);
      }
    } catch (err) { setAuthMessage({ type: "error", text: err.message }); }
  };

  // Run Extraction Pipeline
  const handleSubmission = async (e) => {
    e.preventDefault();
    if (!url) return;
    setStatus("processing"); setError(null); setChatHistory([]);

    try {
      const response = await fetch("http://127.0.0.1:8000/api/process-video", {
        method: "POST",
        headers: { 
          "Content-Type": "application/json",
          "Authorization": `Bearer ${token}`
        },
        body: JSON.stringify({ url, language }),
      });
      if (!response.ok) throw new Error("Server rejected request configuration.");
      const result = await response.json();
      setTaskId(result.task_id);
    } catch (err) { setError(err.message); setStatus("failed"); }
  };

  // Poll Background Worker status 
  useEffect(() => {
    if (!taskId || status !== "processing") return;
    const interval = setInterval(async () => {
      try {
        const response = await fetch(`http://127.0.0.1:8000/api/task-status/${taskId}`);
        const result = await response.json();
        if (result.status === "completed") {
          clearInterval(interval);
          setData(result);
          setStatus("completed");
          fetchHistory(); // Refresh sidebar layout links
        } else if (result.status === "failed") {
          clearInterval(interval); setError(result.error); setStatus("failed");
        }
      } catch (err) { clearInterval(interval); setError(err.message); setStatus("failed"); }
    }, 3000);
    return () => clearInterval(interval);
  }, [taskId, status]);

  // Load an item selected from History logs
  const loadHistoricalAnalysis = async (historicalTaskId) => {
    setStatus("processing");
    setTaskId(historicalTaskId);
    setChatHistory([]);
    try {
      const response = await fetch(`http://127.0.0.1:8000/api/task-status/${historicalTaskId}`);
      const result = await response.json();
      setData(result);
      setStatus("completed");
    } catch (err) { setError("Failed to re-hydrate history payload."); setStatus("failed"); }
  };

  // Chat Execution Form Hook
  const handleAskQuestion = async (e) => {
    e.preventDefault();
    if (!question.trim() || chatLoading) return;
    const userQuery = question;
    setChatHistory(prev => [...prev, { sender: "user", text: userQuery }]);
    setQuestion(""); setChatLoading(true);

    try {
      const response = await fetch("http://127.0.0.1:8000/api/chat", {
        method: "POST",
        headers: { 
          "Content-Type": "application/json",
          "Authorization": `Bearer ${token}`
        },
        body: JSON.stringify({ task_id: taskId, question: userQuery }),
      });
      const result = await response.json();
      setChatHistory(prev => [...prev, { sender: "ai", text: result.answer }]);
    } catch (err) { setChatHistory(prev => [...prev, { sender: "ai", text: `Error: ${err.message}` }]); }
    finally { setChatLoading(false); }
  };

  const logout = () => {
    localStorage.removeItem("token");
    setToken(null);
    setStatus("idle");
  };

  // --- RENDERING LAYER 1: UN-AUTHENTICATED LOGIN INTERFACE ---
  if (!token) {
    return (
      <div className="min-h-screen bg-gray-900 flex items-center justify-center text-gray-100 px-4">
        <form onSubmit={handleAuth} className="w-full max-w-sm bg-gray-950 p-6 rounded-xl border border-gray-800 space-y-4 shadow-2xl">
          <h2 className="text-xl font-bold text-center text-white">{isSignUp ? "Create an Account" : "Welcome Back"}</h2>
          {authMessage && (
            <div className={`p-2.5 rounded text-xs border ${authMessage.type === "error" ? "bg-red-950/40 border-red-800 text-red-400" : "bg-green-950/40 border-green-800 text-green-400"}`}>
              {authMessage.text}
            </div>
          )}
          <input type="email" placeholder="Email Address" value={authEmail} onChange={e => setAuthEmail(e.target.value)} className="w-full bg-gray-900 border border-gray-700 rounded px-3 py-2 text-sm focus:outline-none focus:border-indigo-500 text-white" required />
          <input type="password" placeholder="Secret Password" value={authPassword} onChange={e => setAuthPassword(e.target.value)} className="w-full bg-gray-900 border border-gray-700 rounded px-3 py-2 text-sm focus:outline-none focus:border-indigo-500 text-white" required />
          <button type="submit" className="w-full bg-indigo-600 hover:bg-indigo-500 font-medium py-2 rounded text-sm transition">{isSignUp ? "Sign Up" : "Sign In"}</button>
          <p className="text-center text-xs text-gray-400">
            {isSignUp ? "Already have an account?" : "New to the platform?"}{" "}
            <button type="button" onClick={() => { setIsSignUp(!isSignUp); setAuthMessage(null); }} className="text-indigo-400 underline font-medium focus:outline-none">{isSignUp ? "Sign In" : "Sign Up"}</button>
          </p>
        </form>
      </div>
    );
  }

  // --- RENDERING LAYER 2: VALID AUTHENTICATED WORKBENCH APPLICATION ---
  return (
    <div className="min-h-screen bg-gray-900 text-gray-100 flex flex-col">
      {/* Universal Sticky Header Banner */}
      <header className="bg-gray-950 border-b border-gray-800 p-4 flex justify-between items-center sticky top-0 z-10">
        <h1 className="text-lg font-bold text-indigo-400">🎙️ AI Video Assistant</h1>
        <button onClick={logout} className="text-xs bg-gray-800 hover:bg-gray-700 px-3 py-1.5 rounded transition text-gray-300 font-medium">Log Out</button>
      </header>

      {/* Split Window Workspace Layout Setup */}
      <div className="flex-1 flex overflow-hidden">
        {/* SIDEBAR NAVIGATION PANEL (Historical Tracking Vault) */}
        <aside className="w-64 bg-gray-950 border-r border-gray-800 p-4 hidden md:flex flex-col space-y-4 overflow-y-auto">
          <div className="flex justify-between items-center">
            <span className="text-xs font-semibold text-gray-400 uppercase tracking-widest">Saved Analyses</span>
            <button onClick={() => { setStatus("idle"); setTaskId(null); setUrl(""); }} className="text-[10px] bg-indigo-600/20 hover:bg-indigo-600/30 text-indigo-400 px-2 py-1 rounded transition font-bold">New Analysis</button>
          </div>
          <div className="space-y-1 flex-1">
            {history.length === 0 ? (
              <p className="text-xs text-gray-600 italic p-2">No historical videos processed yet.</p>
            ) : (
              history.map(item => (
                <button key={item.task_id} onClick={() => loadHistoricalAnalysis(item.task_id)} className={`w-full text-left text-xs p-2.5 rounded transition block overflow-hidden text-ellipsis whitespace-nowrap ${taskId === item.task_id ? "bg-indigo-950/40 border border-indigo-800 text-indigo-400 font-medium" : "text-gray-400 hover:bg-gray-900 hover:text-white"}`}>
                  🎬 {item.title}
                </button>
              ))
            )}
          </div>
        </aside>

        {/* WORKSPACE ELEMENT BLOCK CONTAINER */}
        <main className="flex-1 p-6 overflow-y-auto">
          {status === "idle" && (
            <div className="max-w-xl mx-auto mt-12 bg-gray-950 border border-gray-800 rounded-xl p-6 space-y-4">
              <div className="text-center"><h2 className="text-xl font-bold text-white">Analyse Video streams</h2><p className="text-xs text-gray-400">Past executions will automatically save to your profile vault.</p></div>
              <form onSubmit={handleSubmission} className="space-y-4">
                <input type="url" placeholder="Paste target media context url..." value={url} onChange={e => setUrl(e.target.value)} className="w-full bg-gray-900 border border-gray-700 rounded-lg px-4 py-2.5 text-white text-sm focus:outline-none focus:border-indigo-500" required />
                <select value={language} onChange={e => setLanguage(e.target.value)} className="w-full bg-gray-900 border border-gray-700 rounded-lg px-4 py-2.5 text-white text-sm focus:outline-none focus:border-indigo-500">
                  <option value="english">English (Local Whisper)</option>
                  <option value="hinglish">Hinglish (Sarvam AI)</option>
                </select>
                {error && <div className="p-2.5 bg-red-950/30 border border-red-800 text-red-400 rounded text-xs">{error}</div>}
                <button type="submit" className="w-full bg-indigo-600 hover:bg-indigo-500 py-2.5 rounded-lg text-sm font-semibold transition">Execute Pipeline</button>
              </form>
            </div>
          )}

          {status === "processing" && (
            <div className="max-w-md mx-auto mt-24 text-center space-y-3">
              <div className="w-10 h-10 border-4 border-indigo-500 border-t-transparent rounded-full animate-spin mx-auto"></div>
              <h3 className="text-sm font-semibold text-white">Processing Data Context Matrix...</h3>
            </div>
          )}

          {status === "completed" && (
            <div className="space-y-4 h-full flex flex-col">
              <h2 className="text-lg font-bold text-white border-b border-gray-800 pb-2">🎬 {data.title}</h2>
              <div className="grid grid-cols-1 lg:grid-cols-12 gap-6 items-stretch flex-1 overflow-hidden">
                {/* Metrics tab blocks selection layout */}
                <div className="lg:col-span-7 bg-gray-950 border border-gray-800 rounded-xl flex flex-col overflow-hidden shadow-xl min-h-[500px]">
                  <div className="flex border-b border-gray-800 bg-gray-950 text-xs overflow-x-auto">
                    {["summary", "action_items", "key_decisions", "open_questions"].map(tab => (
                      <button key={tab} onClick={() => setActiveTab(tab)} className={`px-4 py-3 font-medium capitalize border-b-2 transition ${activeTab === tab ? "border-indigo-500 text-indigo-400 bg-gray-900/30" : "border-transparent text-gray-500 hover:text-gray-300"}`}>{tab.replace("_", " ")}</button>
                    ))}
                  </div>
                  <div className="p-4 overflow-y-auto flex-1 text-xs leading-relaxed text-gray-300 whitespace-pre-line">{data[activeTab]}</div>
                </div>

                {/* Chat window column interface component */}
                <div className="lg:col-span-5 bg-gray-950 border border-gray-800 rounded-xl flex flex-col overflow-hidden shadow-xl min-h-[500px]">
                  <div className="p-3 border-b border-gray-800 text-xs font-bold text-white uppercase tracking-wider">Context Chat</div>
                  <div className="p-4 flex-1 overflow-y-auto space-y-3">
                    {chatHistory.map((msg, index) => (
                      <div key={index} className={`flex ${msg.sender === "user" ? "justify-end" : "justify-start"}`}>
                        <div className={`max-w-[85%] rounded px-3 py-2 text-xs ${msg.sender === "user" ? "bg-indigo-600 text-white" : "bg-gray-800 text-gray-200 border border-gray-700"}`}><p className="whitespace-pre-line">{msg.text}</p></div>
                      </div>
                    ))}
                    {chatLoading && <div className="text-[10px] text-gray-500 italic animate-pulse">AI is thinking...</div>}
                    <div ref={chatEndRef} />
                  </div>
                  <form onSubmit={handleAskQuestion} className="p-2 border-t border-gray-800 flex gap-2">
                    <input type="text" placeholder="Ask details..." value={question} onChange={e => setQuestion(e.target.value)} disabled={chatLoading} className="flex-1 bg-gray-900 border border-gray-700 rounded px-3 py-1.5 text-xs focus:outline-none focus:border-indigo-500 text-white" />
                    <button type="submit" disabled={chatLoading || !question.trim()} className="bg-indigo-600 hover:bg-indigo-500 text-white text-xs font-semibold px-3 py-1.5 rounded disabled:bg-gray-800 transition">Send</button>
                  </form>
                </div>
              </div>
            </div>
          )}
        </main>
      </div>
    </div>
  );
}

export default App;