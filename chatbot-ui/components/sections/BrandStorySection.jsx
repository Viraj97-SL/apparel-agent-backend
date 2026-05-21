export default function BrandStorySection() {
  return (
    <section
      id="brand-story"
      className="section-padding"
      style={{ background: 'var(--color-text)', color: 'var(--color-bg)' }}
    >
      <div
        className="container"
        style={{
          display: 'grid',
          gridTemplateColumns: 'repeat(auto-fit, minmax(300px, 1fr))',
          gap: 'clamp(2rem, 6vw, 6rem)',
          alignItems: 'center',
        }}
      >
        {/* Text side */}
        <div>
          <p
            style={{
              fontFamily: 'var(--font-mono)',
              fontSize: 'var(--text-xs)',
              letterSpacing: '0.15em',
              textTransform: 'uppercase',
              color: 'var(--color-gold)',
              marginBottom: '1rem',
            }}
          >
            Our Story
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
            Fashion Meets
            <br />
            <em style={{ color: 'var(--color-gold-light)' }}>Intelligence</em>
          </h2>
          <div
            style={{
              width: '3rem',
              height: '1px',
              background: 'var(--color-gold)',
              marginBottom: '1.5rem',
            }}
          />
          <p style={{ fontSize: 'var(--text-base)', opacity: 0.7, lineHeight: 1.8, marginBottom: '1rem' }}>
            Pamorya was born from a simple idea: every woman in Sri Lanka deserves access to a personal stylist who understands her body, her lifestyle, and her budget.
          </p>
          <p style={{ fontSize: 'var(--text-base)', opacity: 0.7, lineHeight: 1.8, marginBottom: '2rem' }}>
            We combined decades of fashion expertise with cutting-edge AI to create a platform that doesn't just sell clothes — it helps you discover your style identity.
          </p>
          <a
            href="#ai-stylist"
            style={{
              display: 'inline-flex',
              padding: '0.85rem 2rem',
              background: 'transparent',
              color: 'var(--color-bg)',
              fontFamily: 'var(--font-body)',
              fontSize: 'var(--text-xs)',
              fontWeight: 500,
              letterSpacing: '0.1em',
              textTransform: 'uppercase',
              border: '1px solid rgba(248,244,239,0.3)',
              textDecoration: 'none',
              transition: 'border-color 0.2s, background 0.2s',
            }}
            onMouseEnter={(e) => {
              e.currentTarget.style.borderColor = 'var(--color-bg)';
              e.currentTarget.style.background = 'rgba(248,244,239,0.06)';
            }}
            onMouseLeave={(e) => {
              e.currentTarget.style.borderColor = 'rgba(248,244,239,0.3)';
              e.currentTarget.style.background = 'transparent';
            }}
          >
            Meet Your Stylist
          </a>
        </div>

        {/* Visual side — feature tiles */}
        <div
          style={{
            display: 'grid',
            gridTemplateColumns: '1fr 1fr',
            gap: '1px',
            background: 'rgba(248,244,239,0.1)',
          }}
        >
          {[
            { icon: '🤖', title: 'AI-Powered', desc: 'LangGraph multi-agent system routes queries to specialist models' },
            { icon: '👗', title: 'Virtual Try-On', desc: 'Fashn.ai photorealistic garment fitting in 30 seconds' },
            { icon: '💬', title: 'WhatsApp Native', desc: 'Order, style-check, and try-on without leaving WhatsApp' },
            { icon: '🧠', title: 'Remembers You', desc: 'Multi-layer memory learns your preferences over time' },
          ].map((feat) => (
            <div
              key={feat.title}
              style={{
                padding: '1.75rem',
                background: 'rgba(28,20,16,0.5)',
                transition: 'background 0.3s',
              }}
              onMouseEnter={(e) => (e.currentTarget.style.background = 'rgba(201,151,78,0.1)')}
              onMouseLeave={(e) => (e.currentTarget.style.background = 'rgba(28,20,16,0.5)')}
            >
              <div style={{ fontSize: '1.75rem', marginBottom: '0.75rem' }}>{feat.icon}</div>
              <p
                style={{
                  fontFamily: 'var(--font-display)',
                  fontSize: 'var(--text-lg)',
                  fontWeight: 300,
                  marginBottom: '0.4rem',
                }}
              >
                {feat.title}
              </p>
              <p style={{ fontSize: 'var(--text-xs)', opacity: 0.55, lineHeight: 1.6 }}>{feat.desc}</p>
            </div>
          ))}
        </div>
      </div>
    </section>
  );
}
