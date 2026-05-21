'use client';
import { useState } from 'react';

const TESTIMONIALS = [
  {
    name: 'Nimasha P.',
    location: 'Colombo',
    rating: 5,
    text: 'The virtual try-on is incredible. I ordered the Wild Bloom dress after trying it on in the app — it fit perfectly. The AI stylist even suggested the right size based on my height!',
    product: 'Wild Bloom Whisper Dress',
  },
  {
    name: 'Dilani S.',
    location: 'Kandy',
    rating: 5,
    text: 'I love how the chatbot remembers my style preferences. Every time I come back it already knows I prefer flowy fabrics and earthy tones. It\'s like having a real personal shopper.',
    product: 'Sage Linen Co-ord Set',
  },
  {
    name: 'Kavindi F.',
    location: 'Galle',
    rating: 5,
    text: 'Ordered via WhatsApp and got same-day delivery to Colombo. The COD option made everything so easy. The quality is amazing for the price — I\'ve already bought three pieces!',
    product: 'Crimson Canvas Top',
  },
];

export default function TestimonialsSection() {
  const [active, setActive] = useState(0);

  return (
    <section
      className="section-padding"
      style={{ background: 'var(--color-surface-warm)' }}
    >
      <div className="container">
        {/* Header */}
        <div style={{ textAlign: 'center', marginBottom: '3.5rem' }}>
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
            Customer Stories
          </p>
          <h2 style={{ fontSize: 'var(--text-3xl)', fontWeight: 300 }}>
            Loved by{' '}
            <em style={{ color: 'var(--color-accent)' }}>Real Women</em>
          </h2>
        </div>

        {/* Active testimonial */}
        <div
          style={{
            maxWidth: '680px',
            margin: '0 auto',
            textAlign: 'center',
            padding: '3rem',
            background: 'var(--color-surface)',
            border: '1px solid var(--color-border)',
            position: 'relative',
          }}
        >
          {/* Quote mark */}
          <span
            style={{
              fontFamily: 'var(--font-display)',
              fontSize: '5rem',
              lineHeight: 0.8,
              color: 'var(--color-accent-light)',
              display: 'block',
              marginBottom: '1rem',
            }}
          >
            "
          </span>

          <p
            style={{
              fontFamily: 'var(--font-display)',
              fontSize: 'var(--text-xl)',
              fontWeight: 300,
              fontStyle: 'italic',
              lineHeight: 1.6,
              color: 'var(--color-text)',
              marginBottom: '2rem',
            }}
          >
            {TESTIMONIALS[active].text}
          </p>

          <div
            style={{
              display: 'flex',
              flexDirection: 'column',
              alignItems: 'center',
              gap: '0.25rem',
            }}
          >
            <p
              style={{
                fontFamily: 'var(--font-body)',
                fontSize: 'var(--text-sm)',
                fontWeight: 600,
                color: 'var(--color-text)',
              }}
            >
              {TESTIMONIALS[active].name}
            </p>
            <p
              style={{
                fontFamily: 'var(--font-mono)',
                fontSize: 'var(--text-xs)',
                color: 'var(--color-text-muted)',
                letterSpacing: '0.08em',
              }}
            >
              {TESTIMONIALS[active].location} · {TESTIMONIALS[active].product}
            </p>
            <div style={{ display: 'flex', gap: '3px', marginTop: '0.5rem' }}>
              {Array.from({ length: TESTIMONIALS[active].rating }).map((_, i) => (
                <span key={i} style={{ color: 'var(--color-gold)', fontSize: '0.8rem' }}>★</span>
              ))}
            </div>
          </div>
        </div>

        {/* Dots */}
        <div style={{ display: 'flex', justifyContent: 'center', gap: '0.5rem', marginTop: '1.5rem' }}>
          {TESTIMONIALS.map((_, i) => (
            <button
              key={i}
              onClick={() => setActive(i)}
              style={{
                width: i === active ? '2rem' : '0.5rem',
                height: '0.5rem',
                background: i === active ? 'var(--color-accent)' : 'var(--color-border-strong)',
                border: 'none',
                cursor: 'pointer',
                borderRadius: '2px',
                transition: 'all 0.3s',
              }}
              aria-label={`Testimonial ${i + 1}`}
            />
          ))}
        </div>
      </div>
    </section>
  );
}
