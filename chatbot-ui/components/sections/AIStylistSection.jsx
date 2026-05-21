'use client';
import ChatWidget from '../chat/ChatWidget';

const FEATURES = [
  { icon: '🧠', label: 'Remembers You', desc: 'Multi-layer memory learns your style across sessions' },
  { icon: '🌍', label: 'Deep Research', desc: 'Searches trends in real-time to give current advice' },
  { icon: '📦', label: 'Order Instantly', desc: 'Buy via chat with Cash on Delivery — no account needed' },
  { icon: '💬', label: 'WhatsApp Too', desc: 'Same AI available on WhatsApp — style on the go' },
];

export default function AIStylistSection() {
  return (
    <section
      id="ai-stylist"
      className="section-padding"
      style={{ background: 'var(--color-bg)' }}
    >
      <div
        className="container"
        style={{
          display: 'grid',
          gridTemplateColumns: 'repeat(auto-fit, minmax(320px, 1fr))',
          gap: 'clamp(2rem, 5vw, 5rem)',
          alignItems: 'start',
        }}
      >
        {/* Left: editorial copy */}
        <div style={{ paddingTop: '0.5rem' }}>
          <p
            style={{
              fontFamily: 'var(--font-mono)',
              fontSize: 'var(--text-xs)',
              letterSpacing: '0.15em',
              textTransform: 'uppercase',
              color: 'var(--color-accent)',
              marginBottom: '0.75rem',
            }}
          >
            AI Stylist
          </p>

          <h2
            style={{
              fontFamily: 'var(--font-display)',
              fontSize: 'var(--text-3xl)',
              fontWeight: 300,
              lineHeight: 1.1,
              marginBottom: '1.5rem',
            }}
          >
            Your Personal
            <br />
            <em style={{ color: 'var(--color-accent)' }}>Fashion Advisor</em>
          </h2>

          <div
            style={{
              width: '3rem',
              height: '1px',
              background: 'var(--color-accent)',
              marginBottom: '1.5rem',
            }}
          />

          <p
            style={{
              fontSize: 'var(--text-base)',
              color: 'var(--color-text-muted)',
              lineHeight: 1.8,
              marginBottom: '2rem',
              maxWidth: '420px',
            }}
          >
            Powered by Google Gemini and a LangGraph multi-agent system, Pamorya Stylist understands your body, your lifestyle, and your budget — then recommends outfits you'll actually love.
          </p>

          {/* Feature list */}
          <div style={{ display: 'flex', flexDirection: 'column', gap: '1rem', marginBottom: '2.5rem' }}>
            {FEATURES.map((feat) => (
              <div
                key={feat.label}
                style={{
                  display: 'flex',
                  alignItems: 'flex-start',
                  gap: '0.85rem',
                }}
              >
                <span style={{ fontSize: '1.25rem', flexShrink: 0, marginTop: '1px' }}>{feat.icon}</span>
                <div>
                  <p
                    style={{
                      fontFamily: 'var(--font-body)',
                      fontWeight: 600,
                      fontSize: 'var(--text-sm)',
                      color: 'var(--color-text)',
                      marginBottom: '0.1rem',
                    }}
                  >
                    {feat.label}
                  </p>
                  <p style={{ fontSize: 'var(--text-xs)', color: 'var(--color-text-muted)', lineHeight: 1.6 }}>
                    {feat.desc}
                  </p>
                </div>
              </div>
            ))}
          </div>

          {/* WhatsApp CTA */}
          <a
            href="https://wa.me/94XXXXXXXXX"
            target="_blank"
            rel="noopener noreferrer"
            style={{
              display: 'inline-flex',
              alignItems: 'center',
              gap: '0.5rem',
              padding: '0.75rem 1.5rem',
              background: '#25D366',
              color: '#fff',
              fontFamily: 'var(--font-body)',
              fontSize: 'var(--text-xs)',
              fontWeight: 500,
              letterSpacing: '0.05em',
              textDecoration: 'none',
              transition: 'opacity 0.2s',
            }}
            onMouseEnter={e => (e.currentTarget.style.opacity = '0.85')}
            onMouseLeave={e => (e.currentTarget.style.opacity = '1')}
          >
            <svg width="16" height="16" viewBox="0 0 24 24" fill="currentColor">
              <path d="M17.472 14.382c-.297-.149-1.758-.867-2.03-.967-.273-.099-.471-.148-.67.15-.197.297-.767.966-.94 1.164-.173.199-.347.223-.644.075-.297-.15-1.255-.463-2.39-1.475-.883-.788-1.48-1.761-1.653-2.059-.173-.297-.018-.458.13-.606.134-.133.298-.347.446-.52.149-.174.198-.298.298-.497.099-.198.05-.371-.025-.52-.075-.149-.669-1.612-.916-2.207-.242-.579-.487-.5-.669-.51-.173-.008-.371-.01-.57-.01-.198 0-.52.074-.792.372-.272.297-1.04 1.016-1.04 2.479 0 1.462 1.065 2.875 1.213 3.074.149.198 2.096 3.2 5.077 4.487.709.306 1.262.489 1.694.625.712.227 1.36.195 1.871.118.571-.085 1.758-.719 2.006-1.413.248-.694.248-1.289.173-1.413-.074-.124-.272-.198-.57-.347m-5.421 7.403h-.004a9.87 9.87 0 01-5.031-1.378l-.361-.214-3.741.982.998-3.648-.235-.374a9.86 9.86 0 01-1.51-5.26c.001-5.45 4.436-9.884 9.888-9.884 2.64 0 5.122 1.03 6.988 2.898a9.825 9.825 0 012.893 6.994c-.003 5.45-4.437 9.884-9.885 9.884m8.413-18.297A11.815 11.815 0 0012.05 0C5.495 0 .16 5.335.157 11.892c0 2.096.547 4.142 1.588 5.945L.057 24l6.305-1.654a11.882 11.882 0 005.683 1.448h.005c6.554 0 11.89-5.335 11.893-11.893a11.821 11.821 0 00-3.48-8.413z" />
            </svg>
            Chat on WhatsApp
          </a>
        </div>

        {/* Right: embedded chat widget */}
        <div style={{ position: 'sticky', top: '5rem' }}>
          <ChatWidget compact={true} />
          <p
            style={{
              marginTop: '0.75rem',
              textAlign: 'center',
              fontFamily: 'var(--font-mono)',
              fontSize: '0.6rem',
              letterSpacing: '0.08em',
              textTransform: 'uppercase',
              color: 'var(--color-text-light)',
            }}
          >
            Powered by Google Gemini · LangGraph · Fashn.ai VTO
          </p>
        </div>
      </div>
    </section>
  );
}
