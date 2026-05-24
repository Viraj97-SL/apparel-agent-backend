'use client';
import { Camera, Shirt, Sparkles } from 'lucide-react';

const STEPS = [
  {
    number: '01',
    title: 'Upload Your Photo',
    desc: 'A full-body shot works best. Stand against a plain background in fitted clothes.',
    Icon: Camera,
  },
  {
    number: '02',
    title: 'Choose a Style',
    desc: 'Browse our collection or tell the AI stylist which piece you want to try.',
    Icon: Shirt,
  },
  {
    number: '03',
    title: 'See Your Look',
    desc: 'Our AI generates a photorealistic try-on in under 30 seconds.',
    Icon: Sparkles,
  },
];

export default function VTOSection() {
  return (
    <section
      id="vto"
      className="section-padding"
      style={{ background: 'var(--color-surface-warm)' }}
    >
      <div className="container">
        {/* Header */}
        <div style={{ maxWidth: '640px', marginBottom: '4rem' }}>
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
            AI Technology
          </p>
          <h2 style={{ fontSize: 'var(--text-3xl)', fontWeight: 300, marginBottom: '1.25rem' }}>
            Try Before You Buy
          </h2>
          <p style={{ color: 'var(--color-text-muted)', fontSize: 'var(--text-lg)', lineHeight: 1.6 }}>
            Our virtual try-on uses state-of-the-art AI to show you exactly how any garment will look on your body — no guessing required.
          </p>
        </div>

        {/* Steps */}
        <div
          style={{
            display: 'grid',
            gridTemplateColumns: 'repeat(auto-fit, minmax(260px, 1fr))',
            gap: '2rem',
            marginBottom: '4rem',
          }}
        >
          {STEPS.map((step, i) => (
            <div
              key={step.number}
              className="animate-fade-in-up"
              style={{
                animationDelay: `${i * 100}ms`,
                padding: '2rem',
                background: 'var(--color-surface)',
                border: '1px solid var(--color-border)',
                position: 'relative',
              }}
            >
              {/* Step number watermark */}
              <span
                style={{
                  position: 'absolute',
                  top: '1rem',
                  right: '1.25rem',
                  fontFamily: 'var(--font-display)',
                  fontSize: '4rem',
                  fontWeight: 300,
                  color: 'var(--color-accent-light)',
                  lineHeight: 1,
                  userSelect: 'none',
                }}
              >
                {step.number}
              </span>

              <div style={{
                width: '48px',
                height: '48px',
                background: 'var(--color-accent-light)',
                borderRadius: '50%',
                display: 'flex',
                alignItems: 'center',
                justifyContent: 'center',
                marginBottom: '1.25rem',
              }}>
                <step.Icon size={22} color="var(--color-accent)" />
              </div>
              <h3
                style={{
                  fontFamily: 'var(--font-display)',
                  fontSize: 'var(--text-xl)',
                  fontWeight: 300,
                  marginBottom: '0.75rem',
                }}
              >
                {step.title}
              </h3>
              <p style={{ fontSize: 'var(--text-sm)', color: 'var(--color-text-muted)', lineHeight: 1.7 }}>
                {step.desc}
              </p>
            </div>
          ))}
        </div>

        {/* CTA */}
        <div style={{ display: 'flex', gap: '1rem', alignItems: 'center', flexWrap: 'wrap' }}>
          <a href="#ai-stylist" className="btn-primary">
            Try It Now — Free
          </a>
          <p style={{ fontSize: 'var(--text-xs)', color: 'var(--color-text-muted)' }}>
            5 free try-ons per day · No sign-up required
          </p>
        </div>
      </div>
    </section>
  );
}
