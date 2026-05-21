'use client';
import { useEffect, useState } from 'react';

const API_URL = process.env.NEXT_PUBLIC_API_URL || 'https://apparel-agent-backend-production.up.railway.app';

const PLACEHOLDER_PRODUCTS = [
  { product_name: 'Crimson Canvas', category: 'Tops & Blouses', price: 3200 },
  { product_name: 'Wild Bloom Whisper', category: 'Dresses', price: 5800 },
  { product_name: 'Midnight Petal', category: 'Skirts', price: 2900 },
  { product_name: 'Golden Hour Set', category: 'Sets & Co-ords', price: 7500 },
  { product_name: 'Velvet Reverie', category: 'Dresses', price: 6200 },
  { product_name: 'Sage Linen Trouser', category: 'Pants & Trousers', price: 4100 },
];

export default function TrendingSection() {
  const [products, setProducts] = useState(PLACEHOLDER_PRODUCTS);

  useEffect(() => {
    fetch(`${API_URL}/api/trending`)
      .then((r) => r.json())
      .then((data) => { if (data?.length) setProducts(data); })
      .catch(() => {}); // silently use placeholder data
  }, []);

  return (
    <section id="trending" className="section-padding" style={{ background: 'var(--color-bg)' }}>
      <div className="container">
        {/* Header */}
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
              Most Loved This Week
            </p>
            <h2 style={{ fontSize: 'var(--text-3xl)', fontWeight: 300 }}>Trending Now</h2>
          </div>
          <span className="trending-badge">Live ●</span>
        </div>

        {/* Product grid */}
        <div
          style={{
            display: 'grid',
            gridTemplateColumns: 'repeat(auto-fill, minmax(200px, 1fr))',
            gap: '1.5rem',
          }}
        >
          {products.slice(0, 6).map((product, i) => (
            <div
              key={product.product_name}
              className="product-card animate-fade-in-up"
              style={{ animationDelay: `${i * 60}ms` }}
            >
              {/* Image placeholder */}
              <div
                className="img-wrap"
                style={{
                  background: `hsl(${(i * 47 + 20) % 360}, 25%, 88%)`,
                  display: 'flex',
                  alignItems: 'center',
                  justifyContent: 'center',
                  position: 'relative',
                }}
              >
                <p
                  style={{
                    fontFamily: 'var(--font-display)',
                    fontSize: 'var(--text-lg)',
                    textAlign: 'center',
                    padding: '1rem',
                    opacity: 0.4,
                    color: 'var(--color-text)',
                  }}
                >
                  {product.product_name}
                </p>
                <div className="overlay" />
                <div className="ctas">
                  <button className="btn-primary" style={{ padding: '0.45rem 0.9rem', fontSize: '0.65rem' }}>
                    Buy Now
                  </button>
                </div>
              </div>

              {/* Info */}
              <div style={{ padding: '0.75rem 0' }}>
                <p style={{ fontFamily: 'var(--font-display)', fontSize: 'var(--text-base)', fontWeight: 300 }}>
                  {product.product_name}
                </p>
                <div
                  style={{
                    display: 'flex',
                    justifyContent: 'space-between',
                    alignItems: 'center',
                    marginTop: '0.25rem',
                  }}
                >
                  <p style={{ fontSize: 'var(--text-xs)', color: 'var(--color-text-muted)' }}>
                    {product.category}
                  </p>
                  <p
                    style={{
                      fontFamily: 'var(--font-mono)',
                      fontSize: 'var(--text-sm)',
                      color: 'var(--color-text)',
                    }}
                  >
                    LKR {product.price?.toLocaleString()}
                  </p>
                </div>
              </div>
            </div>
          ))}
        </div>
      </div>
    </section>
  );
}
