'use client';
import { useEffect, useState } from 'react';

const API_URL = process.env.NEXT_PUBLIC_API_URL || 'https://apparel-agent-backend-production.up.railway.app';

const PLACEHOLDER_PRODUCTS = [
  { product_name: 'Wild Bloom Whisper', category: 'Dresses', price: 1790, image_url: 'https://res.cloudinary.com/dkftnrrjq/image/upload/v1769167858/PWBW01_v1lxc3.jpg' },
  { product_name: 'Midnight Velvet Dream', category: 'Dresses', price: 4950, image_url: 'https://res.cloudinary.com/dkftnrrjq/image/upload/v1765694929/apparel_bot_products/PMVD011.jpg' },
  { product_name: 'Pink Rhapsody', category: 'Tops & Blouses', price: 2850, image_url: 'https://res.cloudinary.com/dkftnrrjq/image/upload/v1765694925/apparel_bot_products/PPR02.jpg' },
  { product_name: 'Rosé Ruffle Gingham', category: 'Sets & Co-ords', price: 3700, image_url: 'https://res.cloudinary.com/dkftnrrjq/image/upload/v1769960032/PRRGM059_03_fedgsr.jpg' },
  { product_name: 'Azure Teal Dream', category: 'Dresses', price: 2400, image_url: 'https://res.cloudinary.com/dkftnrrjq/image/upload/v1769960086/PATD044_03_iuenxy.jpg' },
  { product_name: 'Crimson Canvas', category: 'Skirts', price: 2400, image_url: 'https://res.cloudinary.com/dkftnrrjq/image/upload/v1765694935/apparel_bot_products/PCC010.jpg' },
];

function TrendingCard({ product, index }) {
  const [hovered, setHovered] = useState(false);

  return (
    <div
      className="product-card animate-fade-in-up"
      style={{ animationDelay: `${index * 60}ms` }}
      onMouseEnter={() => setHovered(true)}
      onMouseLeave={() => setHovered(false)}
    >
      <div className="img-wrap" style={{ position: 'relative' }}>
        {product.image_url ? (
          <img
            src={product.image_url}
            alt={product.product_name}
            style={{
              position: 'absolute',
              inset: 0,
              width: '100%',
              height: '100%',
              objectFit: 'cover',
              transition: 'transform 0.6s ease',
              transform: hovered ? 'scale(1.04)' : 'scale(1)',
            }}
          />
        ) : (
          <div
            style={{
              position: 'absolute',
              inset: 0,
              background: `hsl(${(index * 47 + 20) % 360}, 25%, 88%)`,
              display: 'flex',
              alignItems: 'center',
              justifyContent: 'center',
            }}
          >
            <p style={{ fontFamily: 'var(--font-display)', fontSize: 'var(--text-lg)', opacity: 0.4 }}>
              {product.product_name}
            </p>
          </div>
        )}
        <div className="overlay" />
        <div className="ctas">
          <button
            className="btn-primary"
            style={{ padding: '0.45rem 0.9rem', fontSize: '0.65rem' }}
            onClick={() => document.getElementById('ai-stylist')?.scrollIntoView({ behavior: 'smooth' })}
          >
            Buy Now
          </button>
          <button
            className="btn-outline"
            style={{ padding: '0.45rem 0.9rem', fontSize: '0.65rem', borderColor: 'white', color: 'white' }}
            onClick={() => document.getElementById('vto')?.scrollIntoView({ behavior: 'smooth' })}
          >
            Try On
          </button>
        </div>
      </div>

      <div style={{ padding: '0.75rem 0' }}>
        <p style={{ fontFamily: 'var(--font-display)', fontSize: 'var(--text-base)', fontWeight: 300 }}>
          {product.product_name}
        </p>
        <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginTop: '0.25rem' }}>
          <p style={{ fontSize: 'var(--text-xs)', color: 'var(--color-text-muted)' }}>{product.category}</p>
          <p style={{ fontFamily: 'var(--font-mono)', fontSize: 'var(--text-sm)', color: 'var(--color-accent)' }}>
            LKR {product.price?.toLocaleString()}
          </p>
        </div>
      </div>
    </div>
  );
}

export default function TrendingSection() {
  const [products, setProducts] = useState(PLACEHOLDER_PRODUCTS);

  useEffect(() => {
    fetch(`${API_URL}/api/trending`)
      .then((r) => r.json())
      .then((data) => {
        if (Array.isArray(data) && data.length) setProducts(data);
      })
      .catch(() => {}); // silently keep placeholder data on error
  }, []);

  return (
    <section id="trending" className="section-padding" style={{ background: 'var(--color-bg)' }}>
      <div className="container">
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

        <div
          style={{
            display: 'grid',
            gridTemplateColumns: 'repeat(auto-fill, minmax(200px, 1fr))',
            gap: '1.5rem',
          }}
        >
          {products.slice(0, 6).map((product, i) => (
            <TrendingCard key={product.product_name} product={product} index={i} />
          ))}
        </div>
      </div>
    </section>
  );
}
