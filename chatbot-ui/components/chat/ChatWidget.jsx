'use client';
import { useState, useRef, useEffect, useCallback } from 'react';

const API_URL = process.env.NEXT_PUBLIC_API_URL || 'https://apparel-agent-backend-production.up.railway.app';

const SUGGESTIONS = [
  "What dresses do you have?",
  "Show me co-ord sets under LKR 4000",
  "I need an outfit for a beach wedding",
  "What's your return policy?",
];

// ── Helpers ──────────────────────────────────────────────────────────────────

function sanitiseText(text) {
  return text
    .replace(/\(\*+\)/g, '')
    .replace(/\(\*/g, '')
    .replace(/\*\)/g, '')
    .replace(/\?Style:/g, 'Style:')
    .replace(/\?Material:/g, 'Material:')
    .replace(/^\?(?=[A-Z])/gm, '');
}

function RichText({ text }) {
  const lines = text.split('\n');
  return (
    <>
      {lines.map((line, li) => {
        const parts = line.split(/\*\*(.*?)\*\*/g);
        return (
          <span key={li}>
            {parts.map((part, pi) =>
              pi % 2 === 1 ? <strong key={pi}>{part}</strong> : part
            )}
            {li < lines.length - 1 && <br />}
          </span>
        );
      })}
    </>
  );
}

function ProductGallery({ imagesStr, alt }) {
  const images = imagesStr
    ? imagesStr.split(',').map(u => u.trim()).filter(Boolean)
    : [];
  const [idx, setIdx] = useState(0);

  if (!images.length) return null;
  if (images.length === 1) {
    return (
      <img
        src={images[0]}
        alt={alt}
        style={{ width: '100%', borderRadius: '4px', marginTop: '0.5rem', maxHeight: '320px', objectFit: 'cover' }}
      />
    );
  }

  const prev = (e) => { e.stopPropagation(); setIdx(i => (i - 1 + images.length) % images.length); };
  const next = (e) => { e.stopPropagation(); setIdx(i => (i + 1) % images.length); };

  return (
    <div style={{ position: 'relative', marginTop: '0.5rem' }}>
      <button
        onClick={prev}
        aria-label="Previous image"
        style={galleryArrowStyle('left')}
      >
        ‹
      </button>
      <img
        src={images[idx]}
        alt={`${alt} ${idx + 1} of ${images.length}`}
        style={{ width: '100%', borderRadius: '4px', maxHeight: '320px', objectFit: 'cover', cursor: 'pointer' }}
        onClick={next}
      />
      <button
        onClick={next}
        aria-label="Next image"
        style={galleryArrowStyle('right')}
      >
        ›
      </button>
      <div style={{ display: 'flex', justifyContent: 'center', gap: '4px', marginTop: '6px' }}>
        {images.map((_, i) => (
          <button
            key={i}
            onClick={(e) => { e.stopPropagation(); setIdx(i); }}
            aria-label={`Image ${i + 1}`}
            style={{
              width: i === idx ? '1.5rem' : '0.4rem',
              height: '0.4rem',
              borderRadius: '2px',
              border: 'none',
              background: i === idx ? 'var(--color-accent)' : 'var(--color-border-strong)',
              cursor: 'pointer',
              transition: 'all 0.3s',
              padding: 0,
            }}
          />
        ))}
      </div>
      <span style={{ position: 'absolute', top: '8px', right: '8px', background: 'rgba(0,0,0,0.5)', color: '#fff', fontSize: '0.65rem', padding: '2px 6px', borderRadius: '10px' }}>
        {idx + 1}/{images.length}
      </span>
    </div>
  );
}

function galleryArrowStyle(side) {
  return {
    position: 'absolute',
    top: '50%',
    [side]: '6px',
    transform: 'translateY(-50%)',
    background: 'rgba(0,0,0,0.45)',
    color: '#fff',
    border: 'none',
    borderRadius: '50%',
    width: '28px',
    height: '28px',
    cursor: 'pointer',
    fontSize: '1.2rem',
    lineHeight: '28px',
    textAlign: 'center',
    zIndex: 2,
    padding: 0,
  };
}

function OrderReceipt({ data }) {
  return (
    <div style={{
      marginTop: '0.75rem',
      padding: '1rem',
      background: 'var(--color-surface)',
      border: '1px solid var(--color-border)',
      borderRadius: '4px',
      fontSize: 'var(--text-sm)',
    }}>
      <p style={{ fontFamily: 'var(--font-mono)', fontSize: '0.65rem', letterSpacing: '0.1em', textTransform: 'uppercase', color: 'var(--color-accent)', marginBottom: '0.4rem' }}>
        Order Confirmed
      </p>
      <p style={{ fontFamily: 'var(--font-display)', fontSize: 'var(--text-lg)', fontWeight: 300, marginBottom: '0.5rem' }}>
        #{data.order_number}
      </p>
      <div style={{ height: '1px', background: 'var(--color-border)', margin: '0.5rem 0' }} />
      <ul style={{ listStyle: 'none', padding: 0, margin: '0 0 0.5rem' }}>
        {data.items.map((item, i) => (
          <li key={i} style={{ display: 'flex', justifyContent: 'space-between', marginBottom: '0.25rem' }}>
            <span>{item.qty}× {item.name} ({item.size})</span>
            <span style={{ fontFamily: 'var(--font-mono)' }}>LKR {item.price.toLocaleString()}</span>
          </li>
        ))}
      </ul>
      <div style={{ height: '1px', background: 'var(--color-border)', margin: '0.5rem 0' }} />
      <div style={{ display: 'flex', justifyContent: 'space-between', fontWeight: 600 }}>
        <span>Total</span>
        <span style={{ fontFamily: 'var(--font-mono)', color: 'var(--color-accent)' }}>LKR {data.total.toLocaleString()}</span>
      </div>
      <p style={{ marginTop: '0.5rem', color: 'var(--color-text-muted)', fontSize: 'var(--text-xs)' }}>
        Delivering to: {data.customer_name} · {data.address} · {data.phone}<br />
        Payment: Cash on Delivery
      </p>
    </div>
  );
}

function VtoSteps({ step }) {
  const steps = ['Upload Photo', 'Choose Style', 'Try On'];
  return (
    <div style={{ display: 'flex', gap: '0.5rem', justifyContent: 'center', padding: '0.75rem', borderBottom: '1px solid var(--color-border)' }}>
      {steps.map((label, i) => (
        <div key={i} className={`vto-step-dot${step === i + 1 ? ' active' : ''}`} style={{ display: 'flex', alignItems: 'center', gap: '0.35rem', fontSize: 'var(--text-xs)', color: step === i + 1 ? 'var(--color-accent)' : 'var(--color-text-muted)', fontFamily: 'var(--font-mono)', letterSpacing: '0.05em' }}>
          <span style={{
            width: '20px', height: '20px', borderRadius: '50%',
            background: step > i ? 'var(--color-accent)' : 'var(--color-border)',
            color: step > i ? '#fff' : 'var(--color-text-muted)',
            display: 'flex', alignItems: 'center', justifyContent: 'center',
            fontSize: '0.6rem', fontWeight: 700, flexShrink: 0,
          }}>
            {step > i + 1 ? '✓' : i + 1}
          </span>
          {label}
          {i < 2 && <span style={{ color: 'var(--color-border-strong)', margin: '0 0.15rem' }}>—</span>}
        </div>
      ))}
    </div>
  );
}

function TypingDots() {
  return (
    <div style={{ display: 'flex', gap: '4px', padding: '4px 0', alignItems: 'center' }}>
      {[0, 1, 2].map(i => (
        <span
          key={i}
          style={{
            width: '6px', height: '6px', borderRadius: '50%',
            background: 'var(--color-accent)',
            animation: `typingDot 1.2s ease-in-out infinite`,
            animationDelay: `${i * 0.2}s`,
            display: 'inline-block',
          }}
        />
      ))}
    </div>
  );
}

// ── VTO polling ───────────────────────────────────────────────────────────────

async function pollVtoStatus(jobId, onResult, signal) {
  const maxAttempts = 40;
  for (let attempt = 0; attempt < maxAttempts; attempt++) {
    if (signal?.aborted) return;
    await new Promise(r => setTimeout(r, 3000));
    if (signal?.aborted) return;
    try {
      const res = await fetch(`${API_URL}/vto/status/${jobId}`, { signal });
      const data = await res.json();
      if (data.status === 'done') { onResult({ success: true, response: data.result }); return; }
      if (data.status === 'failed') { onResult({ success: false, response: data.error || 'Try-on failed. Please try again.' }); return; }
    } catch (err) {
      if (err.name === 'AbortError') return;
    }
  }
  onResult({ success: false, response: 'Try-on timed out. Please try again.' });
}

// ── Main component ────────────────────────────────────────────────────────────

export default function ChatWidget({ compact = false }) {
  const [query, setQuery]           = useState('');
  const [chatHistory, setChatHistory] = useState([]);
  const [threadId, setThreadId]     = useState(null);
  const [isLoading, setIsLoading]   = useState(false);
  const [mode, setMode]             = useState('standard');
  const [selectedFile, setSelectedFile] = useState(null);
  const [filePreviewUrl, setFilePreviewUrl] = useState(null);
  const [vtoJobId, setVtoJobId]     = useState(null);

  const fileInputRef    = useRef(null);
  const messagesEndRef  = useRef(null);
  const vtoAbortRef     = useRef(null);

  useEffect(() => {
    messagesEndRef.current?.scrollIntoView({ behavior: 'smooth' });
  }, [chatHistory, isLoading]);

  useEffect(() => {
    return () => { if (filePreviewUrl) URL.revokeObjectURL(filePreviewUrl); };
  }, [filePreviewUrl]);

  // Abort any in-flight VTO poll when component unmounts
  useEffect(() => {
    return () => { vtoAbortRef.current?.abort(); };
  }, []);

  const handleFileChange = (e) => {
    const file = e.target.files?.[0];
    if (!file) return;
    setSelectedFile(file);
    setFilePreviewUrl(URL.createObjectURL(file));
  };

  const clearFile = () => {
    setSelectedFile(null);
    if (filePreviewUrl) URL.revokeObjectURL(filePreviewUrl);
    setFilePreviewUrl(null);
    if (fileInputRef.current) fileInputRef.current.value = '';
  };

  const handleSubmit = async (e, overrideText = null) => {
    if (e) e.preventDefault();
    const textToSend = overrideText || query;
    if (!textToSend.trim() && !selectedFile) return;

    let displayContent = textToSend;
    if (selectedFile) displayContent += ` [Photo: ${selectedFile.name}]`;

    setChatHistory(prev => [...prev, { role: 'human', content: displayContent }]);
    setQuery('');

    const currentFile = selectedFile;
    clearFile();
    setIsLoading(true);

    // VTO async path
    if (mode === 'vto' && currentFile) {
      const formData = new FormData();
      formData.append('query', textToSend || ' ');
      if (threadId) formData.append('thread_id', threadId);
      formData.append('file', currentFile);

      try {
        const res  = await fetch(`${API_URL}/vto/start`, { method: 'POST', body: formData });
        const data = await res.json();

        if (data.job_id) {
          setVtoJobId(data.job_id);
          setChatHistory(prev => [...prev, { role: 'ai', content: 'Generating your virtual try-on… this takes about 30 seconds.' }]);

          vtoAbortRef.current?.abort();
          const abortCtrl = new AbortController();
          vtoAbortRef.current = abortCtrl;

          pollVtoStatus(data.job_id, ({ success, response }) => {
            setIsLoading(false);
            setVtoJobId(null);
            setChatHistory(prev => [...prev, { role: 'ai', content: response }]);
          }, abortCtrl.signal);
          return;
        }
      } catch (err) {
        // fall through to standard chat path on error
      }
    }

    // Standard chat path
    const formData = new FormData();
    formData.append('query', textToSend || ' ');
    formData.append('mode', mode);
    if (threadId)    formData.append('thread_id', threadId);
    if (currentFile) formData.append('file', currentFile);

    try {
      const res  = await fetch(`${API_URL}/chat`, { method: 'POST', body: formData });
      const data = await res.json();

      let reply = data.response || data.content || '';
      let receiptData = null;

      try {
        if (reply.includes('COD_SUCCESS')) {
          const jsonMatch = reply.match(/\{[\s\S]*"status"\s*:\s*"COD_SUCCESS"[\s\S]*\}/);
          if (jsonMatch) {
            const parsed = JSON.parse(jsonMatch[0]);
            if (parsed.status === 'COD_SUCCESS') {
              receiptData = parsed;
              reply = parsed.message || 'Order confirmed!';
            }
          }
        }
      } catch (_) {}

      reply = reply || "I apologise — I couldn't connect. Please try again.";

      setChatHistory(prev => [
        ...prev,
        receiptData
          ? { role: 'ai', content: reply, isReceipt: true, receiptData }
          : { role: 'ai', content: reply },
      ]);
      if (data.thread_id) setThreadId(data.thread_id);

    } catch (err) {
      setChatHistory(prev => [...prev, {
        role: 'ai',
        content: 'Connection error. Please check your internet and try again.',
      }]);
    } finally {
      setIsLoading(false);
    }
  };

  const renderContent = useCallback((raw) => {
    const content = sanitiseText(raw);
    const imgRegex = /<img src="([^"]*)" alt="([^"]*)"[^>]*>/g;
    const parts = [];
    let lastIndex = 0;
    let match;

    while ((match = imgRegex.exec(content)) !== null) {
      if (match.index > lastIndex) {
        parts.push(<RichText key={`t-${lastIndex}`} text={content.substring(lastIndex, match.index)} />);
      }
      parts.push(<ProductGallery key={`g-${match.index}`} imagesStr={match[1]} alt={match[2]} />);
      lastIndex = imgRegex.lastIndex;
    }

    if (lastIndex < content.length) {
      parts.push(<RichText key="t-end" text={content.substring(lastIndex)} />);
    }
    return parts.length > 0 ? parts : <RichText text={content} />;
  }, []);

  const vtoStep = (() => {
    if (mode !== 'vto') return 1;
    const hasProduct = chatHistory.some(m => m.role === 'ai' && (m.content.includes('try on') || m.content.includes('Step 3') || m.content.includes('Generating')));
    const hasPhoto   = chatHistory.some(m => m.role === 'human' && m.content.includes('[Photo:'));
    if (hasProduct) return 3;
    if (hasPhoto)   return 2;
    return 1;
  })();

  const containerHeight = compact ? '600px' : '100vh';

  return (
    <div
      className="chat-widget"
      style={{
        display: 'flex',
        flexDirection: 'column',
        height: containerHeight,
        background: 'var(--color-surface)',
        border: '1px solid var(--color-border)',
        overflow: 'hidden',
      }}
    >
      {/* Header */}
      <div style={{
        display: 'flex',
        alignItems: 'center',
        justifyContent: 'space-between',
        padding: '0.85rem 1.25rem',
        borderBottom: '1px solid var(--color-border)',
        background: 'var(--color-bg)',
        flexShrink: 0,
      }}>
        <div style={{ display: 'flex', alignItems: 'center', gap: '0.6rem' }}>
          <div style={{
            width: '10px', height: '10px', borderRadius: '50%',
            background: isLoading ? 'var(--color-gold)' : 'var(--color-accent)',
            boxShadow: isLoading ? '0 0 8px var(--color-gold)' : 'none',
            transition: 'all 0.3s',
            animation: isLoading ? 'pulse 0.8s ease-in-out infinite alternate' : 'none',
          }} />
          <span style={{ fontFamily: 'var(--font-display)', fontSize: 'var(--text-base)', fontWeight: 300, letterSpacing: '0.03em' }}>
            Pamorya Stylist
          </span>
        </div>

        <div style={{ display: 'flex', gap: '0.25rem', background: 'var(--color-surface-warm)', padding: '3px', borderRadius: '4px' }}>
          {['standard', 'vto'].map(m => (
            <button
              key={m}
              onClick={() => setMode(m)}
              style={{
                padding: '0.3rem 0.75rem',
                background: mode === m ? 'var(--color-accent)' : 'transparent',
                color: mode === m ? '#fff' : 'var(--color-text-muted)',
                border: 'none',
                borderRadius: '2px',
                cursor: 'pointer',
                fontFamily: 'var(--font-mono)',
                fontSize: '0.65rem',
                letterSpacing: '0.08em',
                textTransform: 'uppercase',
                transition: 'all 0.2s',
              }}
            >
              {m === 'standard' ? 'Stylist' : 'Try-On'}
            </button>
          ))}
        </div>
      </div>

      {/* VTO steps */}
      {mode === 'vto' && <VtoSteps step={vtoStep} />}

      {/* Messages */}
      <div style={{ flex: 1, overflowY: 'auto', padding: '1rem', display: 'flex', flexDirection: 'column', gap: '0.75rem' }}>

        {/* Empty state */}
        {chatHistory.length === 0 && !isLoading && (
          <div style={{ flex: 1, display: 'flex', flexDirection: 'column', justifyContent: 'center', alignItems: 'center', textAlign: 'center', padding: '2rem 1rem' }}>
            {mode === 'vto' ? (
              <div style={{ background: 'var(--color-surface-warm)', padding: '1.25rem', border: '1px solid var(--color-border)', marginBottom: '1.5rem', textAlign: 'left', maxWidth: '360px', width: '100%' }}>
                <p style={{ fontFamily: 'var(--font-mono)', fontSize: '0.6rem', letterSpacing: '0.1em', textTransform: 'uppercase', color: 'var(--color-accent)', marginBottom: '0.5rem' }}>Photo Tips</p>
                <p style={{ fontSize: 'var(--text-xs)', color: 'var(--color-text-muted)', lineHeight: 1.8 }}>
                  • Full-body shot (head to toe)<br />
                  • Plain background, good lighting<br />
                  • Fitted clothes so AI sees your shape
                </p>
              </div>
            ) : (
              <>
                <p style={{ fontFamily: 'var(--font-display)', fontSize: 'var(--text-xl)', fontWeight: 300, marginBottom: '0.5rem' }}>
                  How can I help you?
                </p>
                <p style={{ fontSize: 'var(--text-xs)', color: 'var(--color-text-muted)', marginBottom: '1.5rem' }}>
                  Your personal AI fashion stylist
                </p>
              </>
            )}
            <div style={{ display: 'flex', flexWrap: 'wrap', gap: '0.5rem', justifyContent: 'center' }}>
              {SUGGESTIONS.map((s, i) => (
                <button
                  key={i}
                  onClick={() => handleSubmit(null, s)}
                  style={{
                    padding: '0.4rem 0.85rem',
                    background: 'transparent',
                    border: '1px solid var(--color-border)',
                    color: 'var(--color-text-muted)',
                    fontFamily: 'var(--font-body)',
                    fontSize: 'var(--text-xs)',
                    cursor: 'pointer',
                    transition: 'all 0.2s',
                    borderRadius: '2px',
                  }}
                  onMouseEnter={e => { e.currentTarget.style.borderColor = 'var(--color-accent)'; e.currentTarget.style.color = 'var(--color-accent)'; }}
                  onMouseLeave={e => { e.currentTarget.style.borderColor = 'var(--color-border)'; e.currentTarget.style.color = 'var(--color-text-muted)'; }}
                >
                  {s}
                </button>
              ))}
            </div>
          </div>
        )}

        {/* Message history */}
        {chatHistory.map((msg, i) => (
          <div
            key={i}
            style={{
              display: 'flex',
              justifyContent: msg.role === 'human' ? 'flex-end' : 'flex-start',
              animation: 'fadeInUp 0.25s ease both',
            }}
          >
            <div
              className={msg.role === 'human' ? 'message-user' : 'message-ai'}
              style={{
                maxWidth: '80%',
                padding: '0.7rem 1rem',
                fontSize: 'var(--text-sm)',
                lineHeight: 1.6,
                borderRadius: '2px',
              }}
            >
              {msg.role === 'ai' && (
                <span style={{ display: 'block', fontFamily: 'var(--font-mono)', fontSize: '0.6rem', letterSpacing: '0.08em', textTransform: 'uppercase', color: 'var(--color-accent)', marginBottom: '0.3rem' }}>
                  Pamorya Stylist
                </span>
              )}
              {msg.role === 'ai'
                ? (msg.isReceipt
                  ? <><RichText text={msg.content} /><OrderReceipt data={msg.receiptData} /></>
                  : renderContent(msg.content))
                : msg.content}
            </div>
          </div>
        ))}

        {/* Typing indicator */}
        {isLoading && (
          <div style={{ display: 'flex', justifyContent: 'flex-start', animation: 'fadeInUp 0.25s ease both' }}>
            <div className="message-ai" style={{ padding: '0.7rem 1rem', borderRadius: '2px' }}>
              <span style={{ display: 'block', fontFamily: 'var(--font-mono)', fontSize: '0.6rem', letterSpacing: '0.08em', textTransform: 'uppercase', color: 'var(--color-accent)', marginBottom: '0.3rem' }}>
                Pamorya Stylist
              </span>
              <TypingDots />
            </div>
          </div>
        )}

        <div ref={messagesEndRef} />
      </div>

      {/* Input */}
      <div style={{ flexShrink: 0, borderTop: '1px solid var(--color-border)', background: 'var(--color-bg)' }}>
        {/* File preview */}
        {selectedFile && (
          <div style={{ display: 'flex', alignItems: 'center', gap: '0.5rem', padding: '0.5rem 1rem', borderBottom: '1px solid var(--color-border)', background: 'var(--color-surface-warm)' }}>
            {filePreviewUrl && (
              <img src={filePreviewUrl} alt="Preview" style={{ width: '36px', height: '36px', objectFit: 'cover', borderRadius: '2px', border: '1px solid var(--color-border)' }} />
            )}
            <span style={{ fontSize: 'var(--text-xs)', color: 'var(--color-text-muted)', flex: 1, overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}>
              {selectedFile.name}
            </span>
            <button
              onClick={clearFile}
              aria-label="Remove file"
              style={{ background: 'none', border: 'none', color: 'var(--color-text-muted)', cursor: 'pointer', fontSize: '1rem', lineHeight: 1, padding: '2px 4px' }}
            >
              ×
            </button>
          </div>
        )}

        <form onSubmit={handleSubmit} style={{ display: 'flex', alignItems: 'center', gap: '0.5rem', padding: '0.75rem 1rem' }}>
          <input
            type="file"
            ref={fileInputRef}
            hidden
            accept="image/*"
            onChange={handleFileChange}
          />
          <button
            type="button"
            onClick={() => fileInputRef.current?.click()}
            title="Attach image"
            style={iconBtnStyle}
          >
            <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
              <path d="M21.44 11.05l-9.19 9.19a6 6 0 0 1-8.49-8.49l9.19-9.19a4 4 0 0 1 5.66 5.66l-9.2 9.19a2 2 0 0 1-2.83-2.83l8.49-8.48" />
            </svg>
          </button>

          <input
            type="text"
            placeholder={mode === 'vto' ? 'Upload a photo & name a product…' : 'Ask about styles, sizes, orders…'}
            value={query}
            onChange={e => setQuery(e.target.value)}
            style={{
              flex: 1,
              padding: '0.6rem 0.75rem',
              background: 'var(--color-surface)',
              border: '1px solid var(--color-border)',
              color: 'var(--color-text)',
              fontFamily: 'var(--font-body)',
              fontSize: 'var(--text-sm)',
              outline: 'none',
              borderRadius: '2px',
            }}
          />

          <button
            type="submit"
            disabled={isLoading || (!query.trim() && !selectedFile)}
            aria-label="Send"
            style={{
              ...iconBtnStyle,
              background: isLoading || (!query.trim() && !selectedFile) ? 'var(--color-border)' : 'var(--color-accent)',
              color: '#fff',
              cursor: isLoading || (!query.trim() && !selectedFile) ? 'not-allowed' : 'pointer',
              transition: 'background 0.2s',
            }}
          >
            <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.5" strokeLinecap="round" strokeLinejoin="round">
              <line x1="22" y1="2" x2="11" y2="13" />
              <polygon points="22 2 15 22 11 13 2 9 22 2" />
            </svg>
          </button>
        </form>
      </div>
    </div>
  );
}

const iconBtnStyle = {
  display: 'flex',
  alignItems: 'center',
  justifyContent: 'center',
  width: '36px',
  height: '36px',
  border: '1px solid var(--color-border)',
  background: 'transparent',
  color: 'var(--color-text-muted)',
  cursor: 'pointer',
  borderRadius: '2px',
  flexShrink: 0,
};
