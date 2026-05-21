'use client';

const STATS = [
  { value: '500+', label: 'Styles in Collection' },
  { value: '3,200+', label: 'Happy Customers' },
  { value: '5-Star', label: 'AI Stylist Rating' },
  { value: 'Same-Day', label: 'Dispatch (Colombo)' },
];

export default function BrandStatsSection() {
  return (
    <section
      style={{
        background: 'var(--color-text)',
        color: 'var(--color-bg)',
        padding: '3rem clamp(1rem, 5vw, 3rem)',
      }}
    >
      <div
        className="container"
        style={{
          display: 'grid',
          gridTemplateColumns: 'repeat(auto-fit, minmax(140px, 1fr))',
          gap: '2rem',
        }}
      >
        {STATS.map((stat) => (
          <div key={stat.label} style={{ textAlign: 'center' }}>
            <p
              style={{
                fontFamily: 'var(--font-display)',
                fontSize: 'var(--text-3xl)',
                fontWeight: 300,
                color: 'var(--color-gold-light)',
                lineHeight: 1,
                marginBottom: '0.4rem',
              }}
            >
              {stat.value}
            </p>
            <p
              style={{
                fontFamily: 'var(--font-mono)',
                fontSize: 'var(--text-xs)',
                letterSpacing: '0.1em',
                textTransform: 'uppercase',
                opacity: 0.5,
              }}
            >
              {stat.label}
            </p>
          </div>
        ))}
      </div>
    </section>
  );
}
