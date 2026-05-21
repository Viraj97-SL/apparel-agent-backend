'use client';

const PRESS = [
  { name: 'Daily Mirror LK', tag: 'Press' },
  { name: 'Colombo Telegraph', tag: 'Press' },
  { name: 'The Sunday Times SL', tag: 'Press' },
  { name: 'LKR Fashion Week', tag: 'Partner' },
  { name: 'Twilio', tag: 'Tech Partner' },
  { name: 'Google AI', tag: 'AI Partner' },
];

export default function PartnersSection() {
  return (
    <section
      className="section-padding"
      style={{
        background: 'var(--color-bg)',
        borderTop: '1px solid var(--color-border)',
        borderBottom: '1px solid var(--color-border)',
      }}
    >
      <div className="container">
        <p
          style={{
            textAlign: 'center',
            fontFamily: 'var(--font-mono)',
            fontSize: 'var(--text-xs)',
            letterSpacing: '0.15em',
            textTransform: 'uppercase',
            color: 'var(--color-text-light)',
            marginBottom: '2.5rem',
          }}
        >
          As Seen In &amp; Powered By
        </p>

        <div
          style={{
            display: 'flex',
            flexWrap: 'wrap',
            justifyContent: 'center',
            gap: '2rem 3.5rem',
            alignItems: 'center',
          }}
        >
          {PRESS.map((partner) => (
            <div
              key={partner.name}
              style={{
                display: 'flex',
                flexDirection: 'column',
                alignItems: 'center',
                gap: '0.3rem',
                opacity: 0.45,
                transition: 'opacity 0.2s',
                cursor: 'default',
              }}
              onMouseEnter={(e) => (e.currentTarget.style.opacity = 1)}
              onMouseLeave={(e) => (e.currentTarget.style.opacity = 0.45)}
            >
              <p
                style={{
                  fontFamily: 'var(--font-display)',
                  fontSize: 'var(--text-lg)',
                  fontWeight: 300,
                  letterSpacing: '0.05em',
                  color: 'var(--color-text)',
                }}
              >
                {partner.name}
              </p>
              <span
                style={{
                  fontFamily: 'var(--font-mono)',
                  fontSize: '0.6rem',
                  letterSpacing: '0.1em',
                  textTransform: 'uppercase',
                  color: 'var(--color-accent)',
                }}
              >
                {partner.tag}
              </span>
            </div>
          ))}
        </div>
      </div>
    </section>
  );
}
