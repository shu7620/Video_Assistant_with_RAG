import React, { useState, useEffect, useRef } from "react";

function App() {
  // Authentication Elements
  const [token, setToken] = useState(localStorage.getItem("token"));
  const [isSignUp, setIsSignUp] = useState(false);
  const [authEmail, setAuthEmail] = useState("");
  const [authPassword, setAuthPassword] = useState("");
  const [authMessage, setAuthMessage] = useState(null);

  // Theme Management (Light / Dark Mode State)
  const [isDarkMode, setIsDarkMode] = useState(() => {
    const savedTheme = localStorage.getItem("theme");
    return savedTheme ? savedTheme === "dark" : true; // Defaulting to dark theme
  });

  // Structural Navigation Elements
  const [isSidebarOpen, setIsSidebarOpen] = useState(true);

  // App Dashboard States
  const [uploadMode, setUploadMode] = useState("url"); // "url" or "file"
  const [selectedFile, setSelectedFile] = useState(null);
  //------------------------------------------------------------------
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

  const API_BASE_URL = import.meta.env.VITE_API_BASE_URL || "http://127.0.0.1:8000";

  // Toggle theme hook
  useEffect(() => {
    if (isDarkMode) {
      document.documentElement.classList.add("dark");
      localStorage.setItem("theme", "dark");
    } else {
      document.documentElement.classList.remove("dark");
      localStorage.setItem("theme", "light");
    }
  }, [isDarkMode]);

  useEffect(() => { 
    chatEndRef.current?.scrollIntoView({ behavior: "smooth" }); 
  }, [chatHistory]);

  // Fetch past histories when logged in
  const fetchHistory = async () => {
    if (!token) return;
    try {
      const res = await fetch(`${API_BASE_URL}/api/history`, {
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
      const response = await fetch(`${API_BASE_URL}/api/auth/${endpoint}`, {
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



const handleSubmission = async (e) => {
    e.preventDefault();
    setStatus("processing"); setError(null); setChatHistory([]);

    try {
      let response;
      
      if (uploadMode === "url") {
        if (!url) return;
        response = await fetch(`${API_BASE_URL}/api/process-video`, {
          method: "POST",
          headers: { 
            "Content-Type": "application/json",
            "Authorization": `Bearer ${token}`
          },
          body: JSON.stringify({ url, language }),
        });
      } else {
        // LOCAL FILE UPLOAD BRANCH
        if (!selectedFile) {
          throw new Error("Please select a valid local video file path first.");
        }
        
        // Prepare Multipart Form Data multi-boundary packet structure
        const formData = new FormData();
        formData.append("file", selectedFile);
        formData.append("language", language);
        
        response = await fetch(`${API_BASE_URL}/api/upload-video?language=${language}`, {
          method: "POST",
          headers: { 
            "Authorization": `Bearer ${token}`
            // Note: Do NOT set Content-Type header manually here; the browser needs to set boundaries automatically
          },
          body: formData,
        });
      }

      if (!response.ok) {
        const errorMsg = await response.json();
        throw new Error(errorMsg.detail || "Server rejected request configuration.");
      }
      
      const result = await response.json();
      setTaskId(result.task_id);
    } catch (err) { setError(err.message); setStatus("failed"); }
  };



  
  useEffect(() => {
    if (!taskId || status !== "processing") return;
    const interval = setInterval(async () => {
      try {
        const response = await fetch(`${API_BASE_URL}/api/task-status/${taskId}`);
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
    setChatHistory([]); // Clear any previous video's UI chat history state
    
    try {
      const response = await fetch(`${API_BASE_URL}/api/task-status/${historicalTaskId}`);
      const result = await response.json();
      setData(result);
      
      const chatResponse = await fetch(`${API_BASE_URL}/api/chat-history/${historicalTaskId}`, {
        headers: { "Authorization": `Bearer ${token}` }
      });
      
      if (chatResponse.ok) {
        const savedChatLogs = await chatResponse.json();
        setChatHistory(savedChatLogs); 
      }
      
      setStatus("completed");
      // Auto-collapse sidebar layout drawer on mobile screens post-selection to preserve real estate
      if (window.innerWidth < 768) {
        setIsSidebarOpen(false);
      }
    } catch (err) { 
      setError("Failed to re-hydrate history payload."); 
      setStatus("failed"); 
    }
  };
  
  const handleAskQuestion = async (e) => {
    e.preventDefault();
    if (!question.trim() || chatLoading) return;
    const userQuery = question;
    setChatHistory(prev => [...prev, { sender: "user", text: userQuery }]);
    setQuestion(""); setChatLoading(true);

    try {
      const response = await fetch(`${API_BASE_URL}/api/chat`, {
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

  // --- RENDERING LAYER 1: UN-AUTHENTICATED LOGIN / SIGNUP INTERFACE ---
  if (!token) {
    return (
      <div className={`min-h-screen flex items-center justify-center transition-colors duration-300 px-4 ${isDarkMode ? "bg-gray-900 text-gray-100" : "bg-gray-50 text-gray-800"}`}>
        {/* Floating Utility Theme Switcher for Login Screens */}
        <div className="absolute top-4 right-4">
          <button 
            onClick={() => setIsDarkMode(!isDarkMode)} 
            className={`p-2.5 rounded-full border transition-all cursor-pointer shadow-sm hover:scale-105 ${isDarkMode ? "bg-gray-800 border-gray-700 hover:bg-gray-700 text-amber-400" : "bg-white border-gray-200 hover:bg-gray-100 text-indigo-600"}`}
          >
            {isDarkMode ? "☀️ Light" : "🌙 Dark"}
          </button>
        </div>

        <form 
          onSubmit={handleAuth} 
          className={`w-full max-w-md p-8 rounded-2xl border transition-all duration-300 transform shadow-2xl ${
            isDarkMode 
              ? "bg-gray-950 border-gray-800 shadow-black/40" 
              : "bg-white border-gray-100 shadow-gray-200/80"
          }`}
        >
          <div className="text-center mb-6">
            <span className="text-3xl">🎙️TranscribeX</span>
            <h2 className={`text-2xl font-extrabold mt-2 tracking-tight ${isDarkMode ? "text-white" : "text-gray-900"}`}>
              {isSignUp ? "Create an Account" : "Welcome Back"}
            </h2>
            <p className={`text-xs mt-1 font-medium ${isDarkMode ? "text-gray-400" : "text-gray-500"}`}>
              Secure automated transcription & intelligent RAG analytics mapping workspace.
            </p>
          </div>

          {authMessage && (
            <div className={`p-3 rounded-xl text-xs border font-medium ${
              authMessage.type === "error" 
                ? "bg-red-500/10 border-red-500/20 text-red-500" 
                : "bg-emerald-500/10 border-emerald-500/20 text-emerald-500"
            }`}>
              {authMessage.text}
            </div>
          )}

          <div className="space-y-4">
            <div>
              <label className={`block text-[11px] font-bold uppercase tracking-wider mb-1.5 ${isDarkMode ? "text-gray-400" : "text-gray-600"}`}>Email Address</label>
              <input 
                type="email" 
                placeholder="name@domain.com" 
                value={authEmail} 
                onChange={e => setAuthEmail(e.target.value)} 
                className={`w-full border rounded-xl px-4 py-3 text-sm transition-all focus:outline-none focus:ring-2 focus:ring-indigo-500/20 ${
                  isDarkMode 
                    ? "bg-gray-900 border-gray-700 text-white focus:border-indigo-500" 
                    : "bg-gray-50 border-gray-200 text-gray-900 focus:border-indigo-600"
                }`} 
                required 
              />
            </div>

            <div>
              <label className={`block text-[11px] font-bold uppercase tracking-wider mb-1.5 ${isDarkMode ? "text-gray-400" : "text-gray-600"}`}>Account Password</label>
              <input 
                type="password" 
                placeholder="••••••••" 
                value={authPassword} 
                onChange={e => setAuthPassword(e.target.value)} 
                className={`w-full border rounded-xl px-4 py-3 text-sm transition-all focus:outline-none focus:ring-2 focus:ring-indigo-500/20 ${
                  isDarkMode 
                    ? "bg-gray-900 border-gray-700 text-white focus:border-indigo-500" 
                    : "bg-gray-50 border-gray-200 text-gray-900 focus:border-indigo-600"
                }`} 
                required 
              />
            </div>
          </div>

          <button 
            type="submit" 
            className="w-full bg-indigo-600 hover:bg-indigo-500 active:scale-[0.99] font-semibold text-white py-3 rounded-xl text-sm transition-all shadow-lg shadow-indigo-600/20 mt-6 cursor-pointer"
          >
            {isSignUp ? "Register Account" : "Sign In to Workspace"}
          </button>

          <p className="text-center text-xs text-gray-500 mt-5 font-medium">
            {isSignUp ? "Already have an account?" : "New to the platform?"}{" "}
            <button 
              type="button" 
              onClick={() => { setIsSignUp(!isSignUp); setAuthMessage(null); }} 
              className="text-indigo-500 hover:text-indigo-400 underline font-semibold focus:outline-none cursor-pointer"
            >
              {isSignUp ? "Sign In" : "Sign Up"}
            </button>
          </p>
        </form>
      </div>
    );
  }

  // --- RENDERING LAYER 2: VALID AUTHENTICATED WORKBENCH APPLICATION ---
  return (
    <div className={`min-h-screen flex flex-col transition-colors duration-300 ${isDarkMode ? "bg-gray-900 text-gray-100" : "bg-gray-50 text-gray-800"}`}>
      
      {/* Universal Shared Top Header Control Row */}
      <header className={`border-b px-4 py-3.5 flex justify-between items-center sticky top-0 z-40 shadow-sm backdrop-blur-md transition-colors ${
        isDarkMode ? "bg-gray-950/90 border-gray-800" : "bg-white/90 border-gray-200"
      }`}>
        <div className="flex items-center space-x-3">
          {/* Drawer Control Toggle button */}
          <button 
            onClick={() => setIsSidebarOpen(!isSidebarOpen)} 
            className={`p-2 rounded-lg border text-sm font-medium transition cursor-pointer hover:scale-105 ${
              isDarkMode ? "bg-gray-900 border-gray-800 hover:bg-gray-800 text-white" : "bg-gray-100 border-gray-200 hover:bg-gray-200 text-gray-700"
            }`}
            title="Toggle Sidebar History Panel"
          >
            {isSidebarOpen ? "📂 Close Panel" : "📁 Open Panel"}
          </button>
          <h1 className={`text-md font-black tracking-tight ${isDarkMode ? "text-white" : "text-gray-900"}`}>
            🎙️ TranscribeX - Your AI Video Assistant
          </h1>
        </div>

        <div className="flex items-center space-x-2">
          {/* Main Workspace Light/Dark mode state control hook trigger */}
          <button 
            onClick={() => setIsDarkMode(!isDarkMode)} 
            className={`p-2 rounded-lg border text-xs font-semibold transition cursor-pointer hover:scale-105 ${
              isDarkMode ? "bg-gray-900 border-gray-800 text-amber-400 hover:bg-gray-800" : "bg-gray-100 border-gray-200 text-indigo-600 hover:bg-gray-200"
            }`}
          >
            {isDarkMode ? "☀️ Light" : "🌙 Dark"}
          </button>
          
          <button 
            onClick={logout} 
            className="text-xs bg-red-600 hover:bg-red-500 font-bold text-white px-3 py-2 rounded-lg transition-all shadow-md shadow-red-600/10 cursor-pointer"
          >
            Log Out
          </button>
        </div>
      </header>

      {/* Primary Split View Dashboard Core */}
      <div className="flex-1 flex position-relative overflow-hidden">
        
        {/* COLLAPSIBLE SIDEBAR DRAWER INTERFACE */}
        <aside 
  className={`bg-gray-950 transition-all duration-300 border-r flex flex-col z-30 fixed md:static top-[57px] bottom-0 left-0 overflow-y-auto ${
    isSidebarOpen ? "w-80 p-4 opacity-100" : "w-0 p-0 opacity-0 border-transparent pointer-events-none" // 👈 Changed here
  } ${
    isDarkMode ? "bg-gray-950 border-gray-800" : "bg-white border-gray-200 shadow-lg md:shadow-none"
  }`}
>
          {isSidebarOpen && (
            <div className="flex flex-col h-full space-y-4">
              <div className="flex justify-between items-center">
                <span className={`text-[13px] font-bold uppercase tracking-wider ${isDarkMode ? "text-gray-400" : "text-gray-500"}`}>
                  Saved Analyses Vault
                </span>
                <button 
                  onClick={() => { setStatus("idle"); setTaskId(null); setUrl(""); }} 
                  className="text-[13px] bg-indigo-600 hover:bg-indigo-500 text-white px-2.5 py-1 rounded-md transition font-bold cursor-pointer"
                >
                  + New Link
                </button>
              </div>

              <div className="space-y-1.5 flex-1 overflow-y-auto pr-1">
                {history.length === 0 ? (
                  <p className={`text-[13px] italic p-3 text-center rounded-xl border ${isDarkMode ? "text-gray-600 border-gray-900" : "text-gray-400 border-gray-100"}`}>
                    No videos processed yet.
                  </p>
                ) : (
                  history.map(item => (
                    <button 
                      key={item.task_id} 
                      onClick={() => loadHistoricalAnalysis(item.task_id)} 
                      className={`w-full text-left text-[13px] p-3 rounded-xl transition-all cursor-pointer block overflow-hidden text-ellipsis whitespace-nowrap border ${
                        taskId === item.task_id 
                          ? "bg-indigo-600 border-indigo-600 text-white font-bold shadow-md shadow-indigo-600/10" 
                          : isDarkMode 
                            ? "text-gray-400 border-transparent hover:bg-gray-900 hover:text-white" 
                            : "text-gray-600 border-transparent hover:bg-gray-100 hover:text-gray-900"
                      }`}
                    >
                      🎬 {item.title}
                    </button>
                  ))
                )}
              </div>
            </div>
          )}
        </aside>

        {/* WORKSPACE AREA CONTAINER */}
        <main className="flex-1 p-4 md:p-6 overflow-y-auto w-full">
          
     

          
          {/* CONTEXT SCREEN A: PIPELINE SCHEDULER */}
          {status === "idle" && (
            <div className={`max-w-xl mx-auto mt-6 md:mt-12 border rounded-2xl p-6 md:p-8 space-y-6 shadow-xl transition-all duration-300 ${
              isDarkMode ? "bg-gray-950 border-gray-800" : "bg-white border-gray-100"
            }`}>
              <div className="text-center space-y-1.5">
                <h2 className={`text-2xl font-black tracking-tight ${isDarkMode ? "text-white" : "text-gray-900"}`}>
                  Video Analysis workspace
                </h2>
                <p className={`text-xs font-medium max-w-sm mx-auto ${isDarkMode ? "text-gray-400" : "text-gray-500"}`}>
                  Provide a Youtube video url or drag and drop local media recordings directly.
                </p>
              </div>

              {/* Mode Selection Tab bar row elements */}
              <div className="flex border-b border-gray-800 text-s">
                <button 
                  type="button"
                  onClick={() => setUploadMode("url")} 
                  className={`flex-1 py-2 font-bold transition cursor-pointer text-center ${uploadMode === "url" ? "border-b-2 border-indigo-500 text-indigo-500" : "text-gray-500"}`}
                >
                  🌐 Remote Link URL
                </button>
                <button 
                  type="button"
                  onClick={() => setUploadMode("file")} 
                  className={`flex-1 py-2 font-bold transition cursor-pointer text-center ${uploadMode === "file" ? "border-b-2 border-indigo-500 text-indigo-500" : "text-gray-500"}`}
                >
                  📁 Local Video Upload
                </button>
              </div>

              <form onSubmit={handleSubmission} className="space-y-4">
                {uploadMode === "url" ? (
                  <div>
                    <label className={`block text-[14px] font-bold uppercase tracking-wider mb-1.5 ${isDarkMode ? "text-gray-400" : "text-gray-600"}`}>Video URL</label>
                    <input 
                      type="url" 
                      placeholder="https://www.youtube.com/watch?v=..." 
                      value={url} 
                      onChange={e => setUrl(e.target.value)} 
                      className={`w-full border rounded-xl px-4 py-3 text-sm transition-all focus:outline-none focus:ring-2 focus:ring-indigo-500/20 ${
                        isDarkMode ? "bg-gray-900 border-gray-700 text-white focus:border-indigo-500" : "bg-gray-50 border-gray-200 text-gray-900 focus:border-indigo-600"
                      }`} 
                      required={uploadMode === "url"}
                    />
                  </div>
                ) : (
                  <div>
                    <label className={`block text-[14px] font-bold uppercase tracking-wider mb-1.5 ${isDarkMode ? "text-gray-400" : "text-gray-600"}`}>Select Local Video or Audio Asset</label>
                    <div className={`border-2 border-dashed rounded-xl p-6 text-center transition-all relative ${
                      isDarkMode ? "border-gray-700 bg-gray-900/40" : "border-gray-200 bg-gray-50"
                    }`}>
                      <input 
                        type="file" 
                        accept="video/*,audio/*"
                        onChange={e => setSelectedFile(e.target.files[0])}
                        className="absolute inset-0 w-full h-full opacity-0 cursor-pointer z-10"
                        required={uploadMode === "file"}
                      />
                      <div className="space-y-1">
                        <span className="text-2xl">📤</span>
                        <p className={`text-xs font-semibold ${selectedFile ? "text-indigo-500" : isDarkMode ? "text-gray-400" : "text-gray-600"}`}>
                          {selectedFile ? `Selected: ${selectedFile.name}` : "Click or Drag to Upload Video File"}
                        </p>
                        <p className="text-[10px] text-gray-500">Supports MP4, MKV, AVI, MP3, WAV up to 500MB</p>
                      </div>
                    </div>
                  </div>
                )}

                <div>
                  <label className={`block text-[14px] font-bold uppercase tracking-wider mb-1.5 ${isDarkMode ? "text-gray-400" : "text-gray-600"}`}>Video Language</label>
                  <select 
                    value={language} 
                    onChange={e => setLanguage(e.target.value)} 
                    className={`w-full border rounded-xl px-4 py-3 text-m transition-all focus:outline-none cursor-pointer focus:ring-2 focus:ring-indigo-500/20 ${
                      isDarkMode ? "bg-gray-900 border-gray-700 text-white focus:border-indigo-500" : "bg-gray-50 border-gray-200 text-gray-900 focus:border-indigo-600"
                    }`}
                  >
                    <option value="english">English </option>
                    <option value="hinglish">Hinglish / Hindi </option>
                  </select>
                </div>

                {error && (
                  <div className="p-3 bg-red-500/10 border border-red-500/20 text-red-500 rounded-xl text-xs font-medium">
                    ⚠️ {error}
                  </div>
                )}

                <button 
                  type="submit" 
                  className="w-full bg-indigo-600 hover:bg-indigo-500 active:scale-[0.99] text-white text-sm font-semibold py-3 rounded-xl transition-all shadow-lg shadow-indigo-600/20 cursor-pointer"
                >
                  Execute Video Processing
                </button>
              </form>
            </div>
          )}
          



          {/* CONTEXT SCREEN B: PROGRESS LOADING BAR */}
          {status === "processing" && (
            <div className="max-w-md mx-auto mt-24 text-center space-y-4">
              <div className="w-12 h-12 border-4 border-indigo-500 border-t-transparent rounded-full animate-spin mx-auto"></div>
              <div className="space-y-1">
                <h3 className={`text-md font-bold ${isDarkMode ? "text-white" : "text-gray-900"}`}>
                  Extracting Media Context Blocks...
                </h3>
                <p className={`text-xs px-4 max-w-xs mx-auto leading-relaxed ${isDarkMode ? "text-gray-400" : "text-gray-500"}`}>
                  Running algorithmic audio segmentation mapping, vector embedding calculations, and generating notes.
                </p>
              </div>
            </div>
          )}

          {/* CONTEXT SCREEN C: INTERACTIVE DATA SPLIT VIEW DASHBOARD */}
          {status === "completed" && (
            <div className="space-y-4 h-full flex flex-col animate-fadeIn">
              <div className="border-b pb-3 flex flex-col space-y-1">
                <span className="text-[12px] font-extrabold uppercase tracking-widest text-indigo-500">Video Content Dashboard</span>
                <h2 className={`text-xl font-black tracking-tight leading-tight ${isDarkMode ? "text-white" : "text-gray-900"}`}>
                  🎬 {data.title}
                </h2>
              </div>

              {/* Responsive Layout Grid Core Engine */}
              <div className="grid grid-cols-1 lg:grid-cols-12 gap-5 items-stretch flex-1 overflow-hidden">
                
                {/* COLUMN ONE: MULTI-TAB MATRIX NOTEBOOK VIEWER */}
                <div className={`lg:col-span-7 border rounded-2xl flex flex-col overflow-hidden shadow-md min-h-[400px] lg:h-[calc(100vh-190px)] ${
                  isDarkMode ? "bg-gray-950 border-gray-800" : "bg-white border-gray-200"
                }`}>
                  {/* Dashboard Selector Row tab buttons */}
                  <div className={`flex border-b text-s overflow-x-auto scrollbar-none sticky top-0 z-10 ${
                    isDarkMode ? "bg-gray-950 border-gray-800" : "bg-gray-50 border-gray-200"
                  }`}>
                    {["summary", "action_items", "key_decisions", "open_questions"].map(tab => (
                      <button 
                        key={tab} 
                        onClick={() => setActiveTab(tab)} 
                        className={`px-4 py-3.5 font-bold tracking-tight capitalize border-b-2 transition-all cursor-pointer whitespace-nowrap ${
                          activeTab === tab 
                            ? "border-indigo-500 text-indigo-500 bg-indigo-500/5" 
                            : "border-transparent text-gray-500 hover:text-gray-900"
                        }`}
                      >
                        {tab.replace("_", " ")}
                      </button>
                    ))}
                  </div>
                  
                  {/* Render context data content frame box */}
                  <div className={`p-5 overflow-y-auto flex-1 text-s leading-relaxed whitespace-pre-line font-medium react-markdown ${
                    isDarkMode ? "text-gray-300" : "text-gray-700"
                  }`}>
                    {data[activeTab] || "No Context Available."}
                  </div>
                </div>

                {/* COLUMN TWO: INTELLIGENT RAG CONTEXTUAL CHAT INTERFACE */}
                <div className={`lg:col-span-5 border rounded-2xl flex flex-col overflow-hidden shadow-md min-h-[450px] lg:h-[calc(100vh-190px)] ${
                  isDarkMode ? "bg-gray-950 border-gray-800" : "bg-white border-gray-200"
                }`}>
                  <div className={`p-3.5 border-b text-xs font-bold uppercase tracking-wider flex justify-between items-center ${
                    isDarkMode ? "bg-gray-950/50 border-gray-800 text-white" : "bg-gray-50 border-gray-200 text-gray-800"
                  }`}>
                    <span>Chat with your video</span>
                    <span className="h-2 w-2 rounded-full bg-emerald-500 animate-pulse"></span>
                  </div>

                  {/* Messaging history stream panel box wrapper */}
                  <div className={`p-4 flex-1 overflow-y-auto space-y-3.5 ${isDarkMode ? "bg-gray-950" : "bg-gray-50/50"}`}>
                    {chatHistory.length === 0 ? (
                      <div className="h-full flex flex-col items-center justify-center text-center p-6 space-y-2">
                        <span className="text-3xl">💬</span>
                        <h4 className={`text-s font-bold ${isDarkMode ? "text-gray-400" : "text-gray-700"}`}>Video Context Loaded</h4>
                        <p className="text-[14px] text-gray-500 max-w-xs leading-relaxed">Ask anything about discussions, timestamps, action trackers, or conceptual statements.</p>
                      </div>
                    ) : (
                      chatHistory.map((msg, index) => (
                        <div key={index} className={`flex ${msg.sender === "user" ? "justify-end" : "justify-start"}`}>
                          <div className={`max-w-[85%] rounded-2xl px-4 py-2.5 text-s font-medium shadow-sm border ${
                            msg.sender === "user" 
                              ? "bg-indigo-600 border-indigo-600 text-white rounded-tr-none" 
                              : isDarkMode 
                                ? "bg-gray-900 border-gray-800 text-gray-100 rounded-tl-none" 
                                : "bg-white border-gray-200 text-gray-800 rounded-tl-none"
                          }`}>
                            <p className="whitespace-pre-line leading-relaxed">{msg.text}</p>
                          </div>
                        </div>
                      ))
                    )}
                    {chatLoading && (
                      <div className="flex justify-start">
                        <div className={`rounded-2xl px-4 py-3 text-[14px] font-bold italic animate-pulse border ${
                          isDarkMode ? "bg-gray-900 border-gray-800 text-gray-400" : "bg-white border-gray-200 text-gray-500"
                        }`}>
                          AI is analyzing...
                        </div>
                      </div>
                    )}
                    <div ref={chatEndRef} />
                  </div>

                  {/* Operational submission tracking query execution input container row */}
                  <form 
                    onSubmit={handleAskQuestion} 
                    className={`p-3 border-t flex gap-2 items-center sticky bottom-0 ${
                      isDarkMode ? "bg-gray-950 border-gray-800" : "bg-white border-gray-200"
                    }`}
                  >
                    <input 
                      type="text" 
                      placeholder="Ask questions about timestamps or parameters..." 
                      value={question} 
                      onChange={e => setQuestion(e.target.value)} 
                      disabled={chatLoading} 
                      className={`flex-1 border rounded-xl px-4 py-2.5 text-s transition-all focus:outline-none focus:ring-2 focus:ring-indigo-500/20 ${
                        isDarkMode ? "bg-gray-900 border-gray-700 text-white focus:border-indigo-500" : "bg-gray-50 border-gray-200 text-gray-900 focus:border-indigo-600"
                      }`} 
                    />
                    <button 
                      type="submit" 
                      disabled={chatLoading || !question.trim()} 
                      className="bg-indigo-600 hover:bg-indigo-500 text-white text-xs font-bold px-4 py-2.5 rounded-xl disabled:bg-gray-300 disabled:text-gray-500 transition-all cursor-pointer shadow-md shadow-indigo-600/10"
                    >
                      Send
                    </button>
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