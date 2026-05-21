export default function Footer() {
  const year = new Date().getFullYear();
  return (
    <footer
      style={{
        background: 'var(--color-text)',
        color: 'var(--color-bg)',
        padding: 'var(--space-2xl) clamp(1rem, 5vw, 3rem)',
      }}
    >
      <div
        className="container"
        style={{
          display: 'grid',
          gridTemplateColumns: 'repeat(auto-fit, minmax(180px, 1fr))',
          gap: '2.5rem',
          marginBottom: '3rem',
        }}
      >
        {/* Brand column */}
        <div>
          <p
            style={{
              fontFamily: 'var(--font-display)',
              fontSize: 'var(--text-2xl)',
              fontWeight: 300,
              letterSpacing: '0.12em',
              textTransform: 'uppercase',
              marginBottom: '1rem',
            }}
          >
            Pamorya
          </p>
          <p style={{ fontSize: 'var(--text-sm)', opacity: 0.6, lineHeight: 1.7 }}>
            Sri Lanka's first AI-powered fashion stylist. Premium apparel, curated with intelligence.
          </p>
        </div>

        {/* Shop */}
        <div>
          <p style={{ fontSize: 'var(--text-xs)', letterSpacing: '0.1em', textTransform: 'uppercase', opacity: 0.5, marginBottom: '1rem' }}>Shop</p>
          {['New Arrivals', 'Dresses', 'Tops & Blouses', 'Sets & Co-ords', 'Skirts'].map((item) => (
            <a
              key={item}
              href="#collections"
              style={{ display: 'block', fontSize: 'var(--text-sm)', opacity: 0.7, marginBottom: '0.5rem', textDecoration: 'none', color: 'inherit', transition: 'opacity 0.2s' }}
              onMouseEnter={(e) => (e.target.style.opacity = 1)}
              onMouseLeave={(e) => (e.target.style.opacity = 0.7)}
            >
              {item}
            </a>
          ))}
        </div>

        {/* Services */}
        <div>
          <p style={{ fontSize: 'var(--text-xs)', letterSpacing: '0.1em', textTransform: 'uppercase', opacity: 0.5, marginBottom: '1rem' }}>Services</p>
          {['AI Stylist', 'Virtual Try-On', 'WhatsApp Styling', 'Size Guide'].map((item) => (
            <a
              key={item}
              href="#ai-stylist"
              style={{ display: 'block', fontSize: 'var(--text-sm)', opacity: 0.7, marginBottom: '0.5rem', textDecoration: 'none', color: 'inherit', transition: 'opacity 0.2s' }}
              onMouseEnter={(e) => (e.target.style.opacity = 1)}
              onMouseLeave={(e) => (e.target.style.opacity = 0.7)}
            >
              {item}
            </a>
          ))}
        </div>

        {/* Contact */}
        <div>
          <p style={{ fontSize: 'var(--text-xs)', letterSpacing: '0.1em', textTransform: 'uppercase', opacity: 0.5, marginBottom: '1rem' }}>Connect</p>
          <p style={{ fontSize: 'var(--text-sm)', opacity: 0.7, marginBottom: '0.5rem' }}>WhatsApp: +94 7X XXX XXXX</p>
          <p style={{ fontSize: 'var(--text-sm)', opacity: 0.7, marginBottom: '1.5rem' }}>hello@pamorya.lk</p>
          <div style={{ display: 'flex', gap: '1rem' }}>
            {['Instagram', 'Facebook', 'TikTok'].map((s) => (
              <a
                key={s}
                href="#"
                style={{
                  fontSize: 'var(--text-xs)',
                  letterSpacing: '0.08em',
                  textTransform: 'uppercase',
                  opacity: 0.6,
                  textDecoration: 'none',
                  color: 'inherit',
                  transition: 'opacity 0.2s',
                }}
                onMouseEnter={(e) => (e.target.style.opacity = 1)}
                onMouseLeave={(e) => (e.target.style.opacity = 0.6)}
              >
                {s}
              </a>
            ))}
          </div>
        </div>
      </div>

      <div
        style={{
          borderTop: '1px solid rgba(248,244,239,0.15)',
          paddingTop: '1.5rem',
          display: 'flex',
          justifyContent: 'space-between',
          alignItems: 'center',
          flexWrap: 'wrap',
          gap: '1rem',
        }}
      >
        <p style={{ fontSize: 'var(--text-xs)', opacity: 0.4 }}>
          © {year} Pamorya. All rights reserved. Sri Lanka.
        </p>
        <p style={{ fontSize: 'var(--text-xs)', opacity: 0.4 }}>
          Powered by Gemini AI · LangGraph · Next.js
        </p>
      </div>
    </footer>
  );
}
