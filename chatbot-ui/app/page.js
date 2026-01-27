// app/page.js
'use client';

import { useState, useRef, useEffect } from 'react';
import styles from './Chat.module.css';

// --- DATA CONFIGURATION ---
const CLOUDINARY_BASE = "https://res.cloudinary.com/dkftnrrjq/image/upload/v1765694934/apparel_bot_products/";
const featuredProducts = [
    { name: "Wild Bloom Whisper", price: "1790", img: "PWBW01_v1lxc3.jpg" },
    { name: "Pink Rhapsody", price: "2850", img: "PPR02.jpg" },
    { name: "Blue Floral Bloom", price: "2390", img: "PFB019.jpg" },
    { name: "Verona Vine", price: "2450", img: "PVV020.jpg" },
    { name: "Crimson Canvas", price: "2400", img: "PCC010.jpg" },
    { name: "Chic Rhythms", price: "1990", img: "PCR04.jpg" }
];
const trends = [
    { title: "Trending", body: "Floral prints are up 20% this week!" },
    { title: "Restock Alert", body: "The Verona Vine is back in Medium." },
    { title: "Style Tip", body: "Pair Crimson Skirts with white heels." },
    { title: "New Arrival", body: "Summer Collection is now live." }
];

export default function Chat() {
  const [query, setQuery] = useState('');
  const [chatHistory, setChatHistory] = useState([]);
  const [threadId, setThreadId] = useState(null);
  const [isLoading, setIsLoading] = useState(false);
  const [mode, setMode] = useState('standard');
  const [selectedFile, setSelectedFile] = useState(null);
  const [toasts, setToasts] = useState([]);

  const fileInputRef = useRef(null);
  const messagesEndRef = useRef(null);

  // Auto-scroll
  useEffect(() => {
      messagesEndRef.current?.scrollIntoView({ behavior: 'smooth' });
  }, [chatHistory]);

  // --- TOAST LOGIC ---
  useEffect(() => {
    const interval = setInterval(() => {
        const randomTrend = trends[Math.floor(Math.random() * trends.length)];
        const id = Date.now();
        setToasts(prev => [...prev, { ...randomTrend, id }]);

        // Remove after 5 seconds
        setTimeout(() => {
            setToasts(prev => prev.filter(t => t.id !== id));
        }, 5000);
    }, 45000); // Every 45 seconds

    return () => clearInterval(interval);
  }, []);

  // --- SEND MESSAGE ---
  const handleSubmit = async (e, overrideText = null) => {
    if (e) e.preventDefault();
    const textToSend = overrideText || query;

    if (!textToSend.trim() && !selectedFile) return;

    let displayContent = textToSend;
    if (selectedFile) displayContent += ` [Attached: ${selectedFile.name}]`;

    const userMessage = { role: 'human', content: displayContent };
    setChatHistory((prev) => [...prev, userMessage]);
    setQuery('');

    const currentFile = selectedFile;
    setSelectedFile(null);
    setIsLoading(true);

    const formData = new FormData();
    formData.append('query', textToSend || " ");
    formData.append('mode', mode);
    if (threadId) formData.append('thread_id', threadId);
    if (currentFile) formData.append('file', currentFile);

    try {
      const API_URL = process.env.NEXT_PUBLIC_API_URL || 'http://127.0.0.1:8080';
      const response = await fetch(`${API_URL}/chat`, { method: 'POST', body: formData });
      const data = await response.json();

      // --- LOGIC: HANDLE COD & STANDARD RESPONSES ---
      let reply = data.response || data.content;

      // If the backend returned a JSON string for COD, parse it to show the clean message
      try {
        if (typeof reply === 'string' && reply.includes("COD_SUCCESS")) {
            const parsed = JSON.parse(reply);
            if (parsed.payment_url === "COD_SUCCESS") {
                reply = parsed.message; // Show the nice receipt text
            }
        }
      } catch (parseError) {
        // Not JSON, just normal text. Keep 'reply' as is.
      }

      reply = reply || "I apologize, I couldn't connect.";

      setChatHistory((prev) => [...prev, { role: 'ai', content: reply }]);
      if (data.thread_id) setThreadId(data.thread_id);

    } catch (error) {
      console.error(error);
      setChatHistory((prev) => [...prev, { role: 'ai', content: "Connection error. Please try again." }]);
    } finally {
      setIsLoading(false);
    }
  };

  // Helper: Render Images
  const renderContent = (content) => {
    const imgRegex = /<img src="(.*?)" alt="(.*?)" \/>/g;
    const parts = [];
    let lastIndex = 0;
    let match;
    while ((match = imgRegex.exec(content)) !== null) {
      if (match.index > lastIndex) parts.push(content.substring(lastIndex, match.index));
      parts.push(<img key={match.index} src={match[1]} alt={match[2]} className={styles.productImage} />);
      lastIndex = imgRegex.lastIndex;
    }
    if (lastIndex < content.length) parts.push(content.substring(lastIndex));
    return parts.length > 0 ? parts : content;
  };

  return (
    <div className={styles.container}>

      {/* 1. HEADER */}
      <header className={styles.header}>
          <div className={styles.brandContainer}>
              <div className={styles.aiRing} style={{ animationDuration: isLoading ? '0.5s' : '3s' }}></div>
              <div className={styles.brandName}>Ask Pamorya</div>
          </div>
          <select className={styles.modeSelect} value={mode} onChange={(e) => setMode(e.target.value)}>
              <option value="standard">Stylist Mode</option>
              <option value="vto">Virtual Try-On</option>
          </select>
      </header>

      {/* 2. CHAT AREA */}
      <section className={styles.chatArea}>
        <div className={styles.messageList}>
          {chatHistory.length === 0 && (
            <div className={styles.emptyState}>
              <h1>Pamorya Stylist</h1>
              <p>Welcome. I am at your service.<br/>Ask about trends, sizes, or your orders.</p>
            </div>
          )}

          {chatHistory.map((msg, idx) => (
            <div key={idx} className={`${styles.messageRow} ${msg.role === 'human' ? styles.userRow : styles.aiRow}`}>
              <div className={`${styles.bubble} ${msg.role === 'human' ? styles.userBubble : styles.aiBubble}`}>
                {msg.role === 'ai' && <span className={styles.aiName}>Pamorya Stylist</span>}
                {renderContent(msg.content)}
              </div>
            </div>
          ))}

          {isLoading && (
             <div className={`${styles.messageRow} ${styles.aiRow}`}>
               <div className={styles.aiBubble}>
                   <span className={styles.aiName}>Pamorya Stylist</span>
                   <em>Thinking...</em>
               </div>
             </div>
          )}
          <div ref={messagesEndRef} />
        </div>

        {/* INPUT */}
        <div className={styles.inputContainer}>
          {selectedFile && (
            <div className={styles.filePreview}>
                📎 {selectedFile.name} <span style={{cursor:'pointer', marginLeft:5}} onClick={() => setSelectedFile(null)}>×</span>
            </div>
          )}

          <form onSubmit={(e) => handleSubmit(e)} className={styles.inputForm}>
            <input
                type="file"
                ref={fileInputRef}
                hidden
                accept="image/*"
                onChange={(e) => e.target.files?.[0] && setSelectedFile(e.target.files[0])}
            />
            <button type="button" className={styles.attachButton} onClick={() => fileInputRef.current?.click()}>
                <svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2"><path d="M21.44 11.05l-9.19 9.19a6 6 0 0 1-8.49-8.49l9.19-9.19a4 4 0 0 1 5.66 5.66l-9.2 9.19a2 2 0 0 1-2.83-2.83l8.49-8.48"/></svg>
            </button>

            <input
              type="text"
              className={styles.textInput}
              placeholder={mode === 'vto' ? "Upload photo..." : "Type here..."}
              value={query}
              onChange={(e) => setQuery(e.target.value)}
            />

            <button type="submit" className={styles.sendButton} disabled={isLoading || (!query && !selectedFile)}>
    <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.5" strokeLinecap="round" strokeLinejoin="round">
        <line x1="22" y1="2" x2="11" y2="13"></line>
        <polygon points="22 2 15 22 11 13 2 9 22 2"></polygon>
    </svg>
</button>
          </form>
        </div>
      </section>

      {/* 3. INFINITE TICKER */}
      <div className={styles.tickerWrap}>
          <div className={styles.ticker}>
              {/* Duplicate list for infinite loop */}
              {[...featuredProducts, ...featuredProducts].map((prod, i) => (
                  <div key={i} className={styles.tickerItem} onClick={() => handleSubmit(null, `Tell me about ${prod.name}`)}>
                      <img src={`${CLOUDINARY_BASE}${prod.img}`} alt={prod.name} />
                      <span>{prod.name} - LKR {prod.price}</span>
                  </div>
              ))}
          </div>
      </div>

      {/* 4. TOASTS */}
      <div className={styles.toastContainer}>
          {toasts.map(t => (
              <div key={t.id} className={styles.toast}>
                  <h4>{t.title}</h4>
                  <p>{t.body}</p>
              </div>
          ))}
      </div>

    </div>
  );
}