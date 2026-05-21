'use client';
import { useEffect, useRef } from 'react';

export default function HeroSection() {
  const headingRef = useRef(null);

  useEffect(() => {
    // Stagger animate each word on load
    const el = headingRef.current;
    if (!el) return;
    const words = el.querySelectorAll('.hero-word');
    words.forEach((word, i) => {
      word.style.animationDelay = `${i * 120}ms`;
      word.classList.add('animate-fade-in-up');
    });
  }, []);

  return (
    <section
      style={{
        position: 'relative',
        minHeight: '100svh',
        display: 'flex',
        alignItems: 'flex-end',
        paddingBottom: 'clamp(3rem, 6vw, 6rem)',
        overflow: 'hidden',
        background: 'var(--color-text)',
        color: 'var(--color-bg)',
      }}
    >
      {/* Background image placeholder — swap with real editorial photo */}
      <div
        style={{
          position: 'absolute',
          inset: 0,
          background: 'linear-gradient(135deg, #1C1410 0%, #3D2820 40%, #6B2D3E 100%)',
          opacity: 0.9,
        }}
      />

      {/* Subtle grain overlay */}
      <div
        style={{
          position: 'absolute',
          inset: 0,
          backgroundImage: 'url("data:image/svg+xml,%3Csvg viewBox=\'0 0 256 256\' xmlns=\'http://www.w3.org/2000/svg\'%3E%3Cfilter id=\'noise\'%3E%3CfeTurbulence type=\'fractalNoise\' baseFrequency=\'0.9\' numOctaves=\'4\' stitchTiles=\'stitch\'/%3E%3C/filter%3E%3Crect width=\'100%25\' height=\'100%25\' filter=\'url(%23noise)\' opacity=\'0.04\'/%3E%3C/svg%3E")',
          opacity: 0.4,
          pointerEvents: 'none',
        }}
      />

      <div className="container" style={{ position: 'relative', zIndex: 1 }}>
        <div style={{ maxWidth: '900px' }}>
          {/* Eyebrow */}
          <p
            className="animate-fade-in"
            style={{
              fontFamily: 'var(--font-mono)',
              fontSize: 'var(--text-xs)',
              letterSpacing: '0.2em',
              textTransform: 'uppercase',
              opacity: 0.6,
              marginBottom: '1.5rem',
            }}
          >
            Sri Lanka's First AI Fashion Stylist
          </p>

          {/* Main heading — words animate in */}
          <h1
            ref={headingRef}
            style={{
              fontFamily: 'var(--font-display)',
              fontSize: 'var(--text-hero)',
              fontWeight: 300,
              lineHeight: 1.0,
              letterSpacing: '-0.03em',
              color: 'var(--color-bg)',
              marginBottom: '0.5rem',
            }}
          >
            {['Dress', 'For', 'Every'].map((word) => (
              <span
                key={word}
                className="hero-word"
                style={{
                  display: 'inline-block',
                  marginRight: '0.3em',
                  opacity: 0,
                }}
              >
                {word}
              </span>
            ))}
            <em
              className="hero-word"
              style={{
                display: 'inline-block',
                fontStyle: 'italic',
                color: 'var(--color-gold-light)',
                opacity: 0,
              }}
            >
              Moment.
            </em>
          </h1>

          {/* Gold accent line */}
          <div
            className="animate-fade-in delay-400"
            style={{
              width: '4rem',
              height: '1px',
              background: 'var(--color-gold)',
              margin: '1.5rem 0',
              opacity: 0,
            }}
          />

          {/* Subheading */}
          <p
            className="animate-fade-in-up delay-300"
            style={{
              fontSize: 'var(--text-lg)',
              fontFamily: 'var(--font-display)',
              fontWeight: 300,
              opacity: 0.75,
              maxWidth: '520px',
              lineHeight: 1.5,
              marginBottom: '2.5rem',
            }}
          >
            Curated fashion, AI-powered styling, and virtual try-on — all in one place.
          </p>

          {/* CTAs */}
          <div
            className="animate-fade-in-up delay-400"
            style={{ display: 'flex', gap: '1rem', flexWrap: 'wrap', opacity: 0 }}
          >
            <a
              href="#ai-stylist"
              style={{
                display: 'inline-flex',
                alignItems: 'center',
                gap: '0.5rem',
                padding: '0.9rem 2.2rem',
                background: 'var(--color-gold)',
                color: 'var(--color-text)',
                fontFamily: 'var(--font-body)',
                fontSize: 'var(--text-xs)',
                fontWeight: 600,
                letterSpacing: '0.12em',
                textTransform: 'uppercase',
                textDecoration: 'none',
                transition: 'transform 0.2s, background 0.2s',
              }}
              onMouseEnter={(e) => (e.currentTarget.style.transform = 'translateY(-2px)')}
              onMouseLeave={(e) => (e.currentTarget.style.transform = 'translateY(0)')}
            >
              Talk to Your Stylist
            </a>
            <a
              href="#collections"
              style={{
                display: 'inline-flex',
                alignItems: 'center',
                padding: '0.9rem 2.2rem',
                background: 'transparent',
                color: 'var(--color-bg)',
                fontFamily: 'var(--font-body)',
                fontSize: 'var(--text-xs)',
                fontWeight: 500,
                letterSpacing: '0.12em',
                textTransform: 'uppercase',
                border: '1px solid rgba(248,244,239,0.4)',
                textDecoration: 'none',
                transition: 'border-color 0.2s, background 0.2s',
              }}
              onMouseEnter={(e) => {
                e.currentTarget.style.borderColor = 'var(--color-bg)';
                e.currentTarget.style.background = 'rgba(248,244,239,0.08)';
              }}
              onMouseLeave={(e) => {
                e.currentTarget.style.borderColor = 'rgba(248,244,239,0.4)';
                e.currentTarget.style.background = 'transparent';
              }}
            >
              Explore Collections
            </a>
          </div>
        </div>

        {/* Scroll indicator */}
        <div
          style={{
            position: 'absolute',
            bottom: '-1rem',
            right: 'clamp(1rem, 5vw, 3rem)',
            display: 'flex',
            flexDirection: 'column',
            alignItems: 'center',
            gap: '0.5rem',
            opacity: 0.4,
          }}
        >
          <p
            style={{
              fontFamily: 'var(--font-mono)',
              fontSize: '0.65rem',
              letterSpacing: '0.15em',
              textTransform: 'uppercase',
              writingMode: 'vertical-rl',
            }}
          >
            Scroll
          </p>
          <div
            style={{
              width: '1px',
              height: '3rem',
              background: 'var(--color-bg)',
              opacity: 0.5,
            }}
          />
        </div>
      </div>
    </section>
  );
}
