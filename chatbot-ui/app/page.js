// app/page.js
'use client';

import { useState, useRef, useEffect } from 'react';
import styles from './Chat.module.css';

export default function Chat() {
  const [query, setQuery] = useState('');
  const [chatHistory, setChatHistory] = useState([]);
  const [threadId, setThreadId] = useState(null);
  const [isLoading, setIsLoading] = useState(false);

  // NEW: State for Mode and File
  const [mode, setMode] = useState('standard'); // 'standard' or 'vto'
  const [selectedFile, setSelectedFile] = useState(null);
  const fileInputRef = useRef(null);

  // Auto-scroll logic
  const messagesEndRef = useRef(null);
  const scrollToBottom = () => {
    messagesEndRef.current?.scrollIntoView({ behavior: 'smooth' });
  };
  useEffect(() => { scrollToBottom(); }, [chatHistory]);

  const handleSubmit = async (e) => {
    e.preventDefault();
    // Allow empty text IF there is a file (e.g., uploading the photo)
    if (!query.trim() && !selectedFile) return;

    // Optimistically show user message
    let displayContent = query;
    if (selectedFile) {
        displayContent += ` [Attached: ${selectedFile.name}]`;
    }
    const userMessage = { role: 'human', content: displayContent };

    setChatHistory((prev) => [...prev, userMessage]);
    setQuery('');

    // Create the "FormData" packet to send text + file
    const formData = new FormData();
    formData.append('query', query || " "); // Backend needs some text
    formData.append('mode', mode);          // Send the current mode
    if (threadId) formData.append('thread_id', threadId);
    if (selectedFile) formData.append('file', selectedFile);

    // Clear file after sending
    const currentFile = selectedFile;
    setSelectedFile(null);
    setIsLoading(true);

    try {
      const response = await fetch('http://127.0.0.1:8000/chat', {
        method: 'POST',
        // Note: Do NOT set Content-Type header when using FormData;
        // the browser sets it automatically with the boundary.
        body: formData,
      });

      const data = await response.json();
      const aiMessage = { role: 'ai', content: data.response };
      setChatHistory((prev) => [...prev, aiMessage]);
      setThreadId(data.thread_id);

    } catch (error) {
      console.error(error);
      // If error, put the file back so they can try again?
      // For now, just show error.
      setChatHistory((prev) => [...prev, { role: 'ai', content: "Sorry, I encountered an error connecting to the server." }]);
    } finally {
      setIsLoading(false);
    }
  };

  // Helper: Detect and render images in bot response
  const renderContent = (content) => {
    const imgRegex = /<img src="(.*?)" alt="(.*?)" \/>/g;
    const parts = [];
    let lastIndex = 0;
    let match;

    while ((match = imgRegex.exec(content)) !== null) {
      if (match.index > lastIndex) {
        parts.push(<span key={lastIndex}>{content.substring(lastIndex, match.index)}</span>);
      }
      parts.push(
        <img key={match.index} src={match[1]} alt={match[2]} className={styles.productImage} />
      );
      lastIndex = imgRegex.lastIndex;
    }
    if (lastIndex < content.length) {
      parts.push(<span key={lastIndex}>{content.substring(lastIndex)}</span>);
    }
    return parts.length > 0 ? parts : content;
  };

  return (
    <div className={styles.container}>
      {/* SIDEBAR */}
      <aside className={styles.sidebar}>
        <button className={styles.newChatButton} onClick={() => window.location.reload()}>
          + New Chat
        </button>

        {/* MODE SELECTOR */}
        <div className={styles.modeContainer}>
            <label className={styles.modeLabel}>Chat Mode</label>
            <select
                className={styles.modeSelect}
                value={mode}
                onChange={(e) => setMode(e.target.value)}
            >
                <option value="standard">Standard Support</option>
                <option value="vto">Virtual Try-On (Beta)</option>
            </select>
        </div>
      </aside>

      {/* MAIN AREA */}
      <section className={styles.chatArea}>
        <div className={styles.messageList}>
          {chatHistory.length === 0 && (
            <div className={styles.emptyState}>
              <h1>{mode === 'vto' ? 'Virtual Try-On' : 'Apparel AI'}</h1>
              <p>{mode === 'vto'
                  ? 'Upload a photo and pick a product to see how it fits!'
                  : 'Your personal fashion concierge.'}
              </p>
            </div>
          )}

          {chatHistory.map((msg, idx) => (
            <div key={idx} className={`${styles.messageRow} ${msg.role === 'human' ? styles.userRow : styles.aiRow}`}>
              <div className={`${styles.bubble} ${msg.role === 'human' ? styles.userBubble : styles.aiBubble}`}>
                {renderContent(msg.content)}
              </div>
            </div>
          ))}

          {isLoading && (
             <div className={`${styles.messageRow} ${styles.aiRow}`}>
               <div className={styles.aiBubble}>Thinking...</div>
             </div>
          )}
          <div ref={messagesEndRef} />
        </div>

        {/* INPUT AREA */}
        <div className={styles.inputContainer}>
          {selectedFile && (
            <div className={styles.filePreview}>
                <span>📎 {selectedFile.name}</span>
                <span className={styles.removeFile} onClick={() => setSelectedFile(null)}>×</span>
            </div>
          )}

          <form onSubmit={handleSubmit} className={styles.inputForm}>
            {/* HIDDEN FILE INPUT */}
            <input
                type="file"
                ref={fileInputRef}
                hidden
                accept="image/*"
                onChange={(e) => {
                    if(e.target.files?.[0]) setSelectedFile(e.target.files[0]);
                }}
            />

            {/* PAPERCLIP BUTTON */}
            <button type="button" className={styles.attachButton} onClick={() => fileInputRef.current?.click()}>
                <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" className={styles.icon}>
                    <path d="M21.44 11.05l-9.19 9.19a6 6 0 0 1-8.49-8.49l9.19-9.19a4 4 0 0 1 5.66 5.66l-9.2 9.19a2 2 0 0 1-2.83-2.83l8.49-8.48" />
                </svg>
            </button>

            <input
              type="text"
              className={styles.textInput}
              placeholder={mode === 'vto' ? "Upload photo or type product name..." : "Ask about products..."}
              value={query}
              onChange={(e) => setQuery(e.target.value)}
            />

            <button type="submit" className={styles.sendButton} disabled={isLoading || (!query && !selectedFile)}>
              <svg viewBox="0 0 24 24" fill="currentColor" className={styles.icon}>
                <path d="M2.01 21L23 12 2.01 3 2 10l15 2-15 2z" />
              </svg>
            </button>
          </form>
        </div>
      </section>
    </div>
  );
}