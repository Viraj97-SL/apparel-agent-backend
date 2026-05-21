'use client';

const CATEGORIES = [
  { name: 'Dresses', tagline: 'Flow with elegance', color: '#E8D5B0', img: null },
  { name: 'Sets & Co-ords', tagline: 'Effortlessly matched', color: '#E8C5CD', img: null },
  { name: 'Tops & Blouses', tagline: 'Versatile essentials', color: '#D5E0E8', img: null },
  { name: 'Skirts', tagline: 'Movement and grace', color: '#D5E8D5', img: null },
  { name: 'Pants & Trousers', tagline: 'Structured confidence', color: '#E8E0D8', img: null },
];

export default function FeaturedCollections() {
  return (
    <section id="collections" className="section-padding" style={{ background: 'var(--color-bg)' }}>
      <div className="container">
        {/* Section header */}
        <div
          style={{
            display: 'flex',
            justifyContent: 'space-between',
            alignItems: 'flex-end',
            marginBottom: '3rem',
            flexWrap: 'wrap',
            gap: '1rem',
          }}
        >
          <div>
            <p
              style={{
                fontFamily: 'var(--font-mono)',
                fontSize: 'var(--text-xs)',
                letterSpacing: '0.15em',
                textTransform: 'uppercase',
                color: 'var(--color-accent)',
                marginBottom: '0.5rem',
              }}
            >
              Curated for You
            </p>
            <h2 style={{ fontSize: 'var(--text-3xl)', fontWeight: 300 }}>
              Our Collections
            </h2>
          </div>
          <a
            href="#ai-stylist"
            style={{
              fontFamily: 'var(--font-mono)',
              fontSize: 'var(--text-xs)',
              letterSpacing: '0.1em',
              textTransform: 'uppercase',
              color: 'var(--color-text-muted)',
              textDecoration: 'none',
              borderBottom: '1px solid var(--color-border-strong)',
              paddingBottom: '2px',
              transition: 'color 0.2s',
            }}
            onMouseEnter={(e) => (e.target.style.color = 'var(--color-accent)')}
            onMouseLeave={(e) => (e.target.style.color = 'var(--color-text-muted)')}
          >
            Ask AI Stylist →
          </a>
        </div>

        {/* Horizontal scroll on mobile, grid on desktop */}
        <div
          style={{
            display: 'grid',
            gridTemplateColumns: 'repeat(auto-fill, minmax(220px, 1fr))',
            gap: '1.5rem',
          }}
        >
          {CATEGORIES.map((cat, i) => (
            <div
              key={cat.name}
              className="product-card animate-fade-in-up"
              style={{ animationDelay: `${i * 80}ms` }}
            >
              {/* Image area */}
              <div
                className="img-wrap"
                style={{ background: cat.color, aspectRatio: '3/4' }}
              >
                {/* Image will be added here when user provides assets */}
                <div
                  style={{
                    position: 'absolute',
                    inset: 0,
                    display: 'flex',
                    flexDirection: 'column',
                    alignItems: 'center',
                    justifyContent: 'center',
                    gap: '0.5rem',
                    opacity: 0.5,
                  }}
                >
                  <p
                    style={{
                      fontFamily: 'var(--font-display)',
                      fontSize: 'var(--text-2xl)',
                      fontWeight: 300,
                      color: 'var(--color-text)',
                    }}
                  >
                    {cat.name}
                  </p>
                </div>
                <div className="overlay" />
                <div className="ctas">
                  <button className="btn-primary" style={{ padding: '0.5rem 1rem', fontSize: 'var(--text-xs)' }}>
                    Browse
                  </button>
                  <button className="btn-outline" style={{ padding: '0.5rem 1rem', fontSize: 'var(--text-xs)', borderColor: 'white', color: 'white' }}>
                    Try On
                  </button>
                </div>
              </div>

              {/* Card info */}
              <div style={{ padding: '0.85rem 0' }}>
                <p style={{ fontFamily: 'var(--font-display)', fontSize: 'var(--text-lg)', fontWeight: 300 }}>
                  {cat.name}
                </p>
                <p style={{ fontSize: 'var(--text-xs)', color: 'var(--color-text-muted)', marginTop: '0.2rem' }}>
                  {cat.tagline}
                </p>
              </div>
            </div>
          ))}
        </div>
      </div>
    </section>
  );
}
