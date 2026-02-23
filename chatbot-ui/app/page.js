'use client';

import { useState, useRef, useEffect } from 'react';
import styles from './Chat.module.css';

// ---------------------------------------------------------------------------
// STATIC DATA
// ---------------------------------------------------------------------------
const featuredProducts = [
    { name: "Wild Bloom Whisper",       price: "1790", img: "https://res.cloudinary.com/dkftnrrjq/image/upload/v1769167858/PWBW01_v1lxc3.jpg" },
    { name: "Midnight Velvet Dream",    price: "4950", img: "https://res.cloudinary.com/dkftnrrjq/image/upload/v1765694929/apparel_bot_products/PMVD011.jpg" },
    { name: "Pink Rhapsody",            price: "2850", img: "https://res.cloudinary.com/dkftnrrjq/image/upload/v1765694925/apparel_bot_products/PPR02.jpg" },
    { name: "Rosé Ruffle Gingham",      price: "3700", img: "https://res.cloudinary.com/dkftnrrjq/image/upload/v1769960032/PRRGM059_03_fedgsr.jpg" },
    { name: "White Wrap Daydress",      price: "2500", img: "https://res.cloudinary.com/dkftnrrjq/image/upload/v1769960130/PWWD03_01_sfktbz.jpg" },
    { name: "Blue Floral Bloom",        price: "2390", img: "https://res.cloudinary.com/dkftnrrjq/image/upload/v1765694935/apparel_bot_products/PFB019.jpg" },
    { name: "Azure Teal Dream",         price: "2400", img: "https://res.cloudinary.com/dkftnrrjq/image/upload/v1769960086/PATD044_03_iuenxy.jpg" },
    { name: "Polished Sophistication",  price: "3300", img: "https://res.cloudinary.com/dkftnrrjq/image/upload/v1769960161/PPS025_01_ax45ln.jpg" },
    { name: "Crimson Canvas",           price: "2400", img: "https://res.cloudinary.com/dkftnrrjq/image/upload/v1765694935/apparel_bot_products/PCC010.jpg" },
    { name: "The Every-Wear Edge",      price: "2800", img: "https://res.cloudinary.com/dkftnrrjq/image/upload/v1765694927/apparel_bot_products/PEWE06.jpg" },
    { name: "Forest Glade Wrap",        price: "2200", img: "https://res.cloudinary.com/dkftnrrjq/image/upload/v1769960101/PFGW039_03_l67xv5.jpg" },
    { name: "Summer Picnic Gingham",    price: "1995", img: "https://res.cloudinary.com/dkftnrrjq/image/upload/v1765694928/apparel_bot_products/PSPG08.jpg" },
];

const SUGGESTIONS = [
    "What dresses do you have?",
    "What's your return policy?",
    "Show me co-ord sets",
    "Tell me about Wild Bloom Whisper",
];

// ---------------------------------------------------------------------------
// HELPERS
// ---------------------------------------------------------------------------

/** Strip display artifacts from AI response text before rendering. */
function sanitiseText(text) {
    return text
        .replace(/\(\*+\)/g, '')            // (**) (**)
        .replace(/\(\*/g, '')               // (*
        .replace(/\*\)/g, '')               // *)
        .replace(/\?Style:/g, 'Style:')     // ?Style: (encoding artefact)
        .replace(/\?Material:/g, 'Material:')
        .replace(/^\?(?=[A-Z])/gm, '');     // leading ? before a capital letter
}

/** Render a plain-text segment with basic markdown: **bold** and line breaks. */
function RichText({ text }) {
    const lines = text.split('\n');
    return (
        <>
            {lines.map((line, li) => {
                // Split on **...**
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

// ---------------------------------------------------------------------------
// PRODUCT GALLERY (with prev / next arrows + dot indicators)
// ---------------------------------------------------------------------------
function ProductGallery({ imagesStr, alt }) {
    const images = imagesStr
        ? imagesStr.split(',').map(u => u.trim()).filter(u => u.length > 0)
        : [];
    const [idx, setIdx] = useState(0);

    if (!images.length) return null;

    if (images.length === 1) {
        return <img src={images[0]} alt={alt} className={styles.productImage} />;
    }

    const prev = (e) => { e.stopPropagation(); setIdx(i => (i - 1 + images.length) % images.length); };
    const next = (e) => { e.stopPropagation(); setIdx(i => (i + 1) % images.length); };

    return (
        <div className={styles.galleryContainer}>
            <button className={`${styles.galleryArrow} ${styles.galleryArrowLeft}`} onClick={prev} aria-label="Previous image">&#8249;</button>
            <img
                src={images[idx]}
                alt={`${alt} ${idx + 1} of ${images.length}`}
                className={styles.galleryImage}
                onClick={next}
            />
            <button className={`${styles.galleryArrow} ${styles.galleryArrowRight}`} onClick={next} aria-label="Next image">&#8250;</button>
            <div className={styles.dotsContainer}>
                {images.map((_, i) => (
                    <button
                        key={i}
                        className={`${styles.dot} ${i === idx ? styles.dotActive : ''}`}
                        onClick={(e) => { e.stopPropagation(); setIdx(i); }}
                        aria-label={`Image ${i + 1}`}
                    />
                ))}
            </div>
            <span className={styles.galleryCounter}>{idx + 1}/{images.length}</span>
        </div>
    );
}

// ---------------------------------------------------------------------------
// TYPING INDICATOR
// ---------------------------------------------------------------------------
function TypingDots() {
    return (
        <div className={styles.typingDots}>
            <span /><span /><span />
        </div>
    );
}

// ---------------------------------------------------------------------------
// MAIN CHAT COMPONENT
// ---------------------------------------------------------------------------
export default function Chat() {
    const [query, setQuery]           = useState('');
    const [chatHistory, setChatHistory] = useState([]);
    const [threadId, setThreadId]     = useState(null);
    const [isLoading, setIsLoading]   = useState(false);
    const [mode, setMode]             = useState('standard');
    const [selectedFile, setSelectedFile] = useState(null);
    const [filePreviewUrl, setFilePreviewUrl] = useState(null);

    const fileInputRef   = useRef(null);
    const messagesEndRef = useRef(null);

    useEffect(() => {
        messagesEndRef.current?.scrollIntoView({ behavior: 'smooth' });
    }, [chatHistory, isLoading]);

    // Free the object URL when the preview changes
    useEffect(() => {
        return () => { if (filePreviewUrl) URL.revokeObjectURL(filePreviewUrl); };
    }, [filePreviewUrl]);

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

        const formData = new FormData();
        formData.append('query', textToSend || ' ');
        formData.append('mode', mode);
        if (threadId)    formData.append('thread_id', threadId);
        if (currentFile) formData.append('file', currentFile);

        try {
            const API_URL = process.env.NEXT_PUBLIC_API_URL || 'http://127.0.0.1:8080';
            const res  = await fetch(`${API_URL}/chat`, { method: 'POST', body: formData });
            const data = await res.json();

            let reply = data.response || data.content || '';

            // Handle COD receipt (legacy JSON format)
            try {
                if (reply.includes('COD_SUCCESS')) {
                    const parsed = JSON.parse(reply);
                    if (parsed.payment_url === 'COD_SUCCESS') reply = parsed.message;
                }
            } catch (_) {}

            reply = reply || "I apologise — I couldn't connect. Please try again.";

            setChatHistory(prev => [...prev, { role: 'ai', content: reply }]);
            if (data.thread_id) setThreadId(data.thread_id);

        } catch (err) {
            console.error(err);
            setChatHistory(prev => [...prev, {
                role: 'ai',
                content: "Connection error. Please check your internet and try again.",
            }]);
        } finally {
            setIsLoading(false);
        }
    };

    /**
     * Render an AI message:
     *  1. Strip display artefacts ((**), ?Style: etc.)
     *  2. Extract <img> tags → ProductGallery components
     *  3. Render remaining text with basic markdown (**bold**, line breaks)
     */
    const renderContent = (raw) => {
        const content = sanitiseText(raw);
        const imgRegex = /<img src="([^"]*)" alt="([^"]*)"[^>]*>/g;
        const parts = [];
        let lastIndex = 0;
        let match;

        while ((match = imgRegex.exec(content)) !== null) {
            if (match.index > lastIndex) {
                const text = content.substring(lastIndex, match.index);
                parts.push(<RichText key={`t-${lastIndex}`} text={text} />);
            }
            parts.push(
                <ProductGallery key={`g-${match.index}`} imagesStr={match[1]} alt={match[2]} />
            );
            lastIndex = imgRegex.lastIndex;
        }

        if (lastIndex < content.length) {
            parts.push(<RichText key={`t-end`} text={content.substring(lastIndex)} />);
        }

        return parts.length > 0 ? parts : <RichText text={content} />;
    };

    return (
        <div className={styles.container}>
            {/* ── HEADER ─────────────────────────────────────────────── */}
            <header className={styles.header}>
                <div className={styles.brandContainer}>
                    <div className={styles.aiRing} style={{ animationDuration: isLoading ? '0.4s' : '3s' }} />
                    <div className={styles.brandName}>Ask Pamorya</div>
                </div>

                {/* Tab-style mode toggle — replaces the plain <select> */}
                <div className={styles.modeToggle}>
                    <button
                        className={`${styles.modeBtn} ${mode === 'standard' ? styles.modeBtnActive : ''}`}
                        onClick={() => setMode('standard')}
                    >
                        Stylist
                    </button>
                    <button
                        className={`${styles.modeBtn} ${mode === 'vto' ? styles.modeBtnActive : ''}`}
                        onClick={() => setMode('vto')}
                    >
                        Try-On
                    </button>
                </div>
            </header>

            {/* ── CHAT AREA ───────────────────────────────────────────── */}
            <section className={styles.chatArea}>
                <div className={styles.messageList}>

                    {/* Empty state with suggestion chips */}
                    {chatHistory.length === 0 && (
                        <div className={styles.emptyState}>
                            <h1>Pamorya Stylist</h1>
                            <p>Welcome — your personal fashion concierge.<br />How can I assist you today?</p>
                            <div className={styles.suggestionChips}>
                                {SUGGESTIONS.map((s, i) => (
                                    <button
                                        key={i}
                                        className={styles.chip}
                                        onClick={() => handleSubmit(null, s)}
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
                            className={`${styles.messageRow} ${msg.role === 'human' ? styles.userRow : styles.aiRow}`}
                        >
                            <div className={`${styles.bubble} ${msg.role === 'human' ? styles.userBubble : styles.aiBubble}`}>
                                {msg.role === 'ai' && <span className={styles.aiName}>Pamorya Stylist</span>}
                                {msg.role === 'ai' ? renderContent(msg.content) : msg.content}
                            </div>
                        </div>
                    ))}

                    {/* Typing indicator */}
                    {isLoading && (
                        <div className={`${styles.messageRow} ${styles.aiRow}`}>
                            <div className={styles.aiBubble}>
                                <span className={styles.aiName}>Pamorya Stylist</span>
                                <TypingDots />
                            </div>
                        </div>
                    )}

                    <div ref={messagesEndRef} />
                </div>

                {/* ── INPUT AREA ─────────────────────────────────────── */}
                <div className={styles.inputContainer}>
                    {/* File / image preview */}
                    {selectedFile && (
                        <div className={styles.filePreview}>
                            {filePreviewUrl && (
                                <img
                                    src={filePreviewUrl}
                                    alt="Preview"
                                    className={styles.fileThumb}
                                />
                            )}
                            <span className={styles.fileName}>{selectedFile.name}</span>
                            <button className={styles.clearFile} onClick={clearFile} aria-label="Remove file">×</button>
                        </div>
                    )}

                    <form onSubmit={handleSubmit} className={styles.inputForm}>
                        <input
                            type="file"
                            ref={fileInputRef}
                            hidden
                            accept="image/*"
                            onChange={handleFileChange}
                        />
                        <button
                            type="button"
                            className={styles.attachButton}
                            onClick={() => fileInputRef.current?.click()}
                            title="Attach image"
                        >
                            {/* Paperclip icon */}
                            <svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
                                <path d="M21.44 11.05l-9.19 9.19a6 6 0 0 1-8.49-8.49l9.19-9.19a4 4 0 0 1 5.66 5.66l-9.2 9.19a2 2 0 0 1-2.83-2.83l8.49-8.48" />
                            </svg>
                        </button>

                        <input
                            type="text"
                            className={styles.textInput}
                            placeholder={
                                mode === 'vto'
                                    ? 'Upload a photo & name a product to try on…'
                                    : 'Ask about styles, sizes, orders…'
                            }
                            value={query}
                            onChange={(e) => setQuery(e.target.value)}
                        />

                        <button
                            type="submit"
                            className={styles.sendButton}
                            disabled={isLoading || (!query.trim() && !selectedFile)}
                            aria-label="Send"
                        >
                            <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.5" strokeLinecap="round" strokeLinejoin="round">
                                <line x1="22" y1="2" x2="11" y2="13" />
                                <polygon points="22 2 15 22 11 13 2 9 22 2" />
                            </svg>
                        </button>
                    </form>
                </div>
            </section>

            {/* ── PRODUCT TICKER ─────────────────────────────────────── */}
            <div className={styles.tickerWrap}>
                <div className={styles.ticker}>
                    {[...featuredProducts, ...featuredProducts].map((prod, i) => (
                        <div
                            key={i}
                            className={styles.tickerItem}
                            onClick={() => handleSubmit(null, `Tell me about ${prod.name}`)}
                            role="button"
                            tabIndex={0}
                            onKeyDown={(e) => e.key === 'Enter' && handleSubmit(null, `Tell me about ${prod.name}`)}
                        >
                            <img src={prod.img} alt={prod.name} />
                            <div className={styles.tickerInfo}>
                                <span className={styles.tickerName}>{prod.name}</span>
                                <span className={styles.tickerPrice}>LKR {prod.price}</span>
                            </div>
                        </div>
                    ))}
                </div>
            </div>
        </div>
    );
}
