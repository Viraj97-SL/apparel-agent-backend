'use client';

import { useState } from 'react';

const PRODUCTS = [
  { name: 'Wild Bloom Whisper', price: 1790, img: 'https://res.cloudinary.com/dkftnrrjq/image/upload/v1769167858/PWBW01_v1lxc3.jpg', category: 'Dresses' },
  { name: 'Midnight Velvet Dream', price: 4950, img: 'https://res.cloudinary.com/dkftnrrjq/image/upload/v1765694929/apparel_bot_products/PMVD011.jpg', category: 'Dresses' },
  { name: 'Pink Rhapsody', price: 2850, img: 'https://res.cloudinary.com/dkftnrrjq/image/upload/v1765694925/apparel_bot_products/PPR02.jpg', category: 'Tops & Blouses' },
  { name: 'Rosé Ruffle Gingham', price: 3700, img: 'https://res.cloudinary.com/dkftnrrjq/image/upload/v1769960032/PRRGM059_03_fedgsr.jpg', category: 'Sets & Co-ords' },
  { name: 'White Wrap Daydress', price: 2500, img: 'https://res.cloudinary.com/dkftnrrjq/image/upload/v1769960130/PWWD03_01_sfktbz.jpg', category: 'Dresses' },
  { name: 'Blue Floral Bloom', price: 2390, img: 'https://res.cloudinary.com/dkftnrrjq/image/upload/v1765694935/apparel_bot_products/PFB019.jpg', category: 'Tops & Blouses' },
  { name: 'Azure Teal Dream', price: 2400, img: 'https://res.cloudinary.com/dkftnrrjq/image/upload/v1769960086/PATD044_03_iuenxy.jpg', category: 'Dresses' },
  { name: 'Polished Sophistication', price: 3300, img: 'https://res.cloudinary.com/dkftnrrjq/image/upload/v1769960161/PPS025_01_ax45ln.jpg', category: 'Sets & Co-ords' },
  { name: 'Crimson Canvas', price: 2400, img: 'https://res.cloudinary.com/dkftnrrjq/image/upload/v1765694935/apparel_bot_products/PCC010.jpg', category: 'Skirts' },
  { name: 'The Every-Wear Edge', price: 2800, img: 'https://res.cloudinary.com/dkftnrrjq/image/upload/v1765694927/apparel_bot_products/PEWE06.jpg', category: 'Tops & Blouses' },
  { name: 'Forest Glade Wrap', price: 2200, img: 'https://res.cloudinary.com/dkftnrrjq/image/upload/v1769960101/PFGW039_03_l67xv5.jpg', category: 'Dresses' },
  { name: 'Summer Picnic Gingham', price: 1995, img: 'https://res.cloudinary.com/dkftnrrjq/image/upload/v1765694928/apparel_bot_products/PSPG08.jpg', category: 'Sets & Co-ords' },
];

const FILTERS = ['All', 'Dresses', 'Sets & Co-ords', 'Tops & Blouses', 'Skirts'];

function ProductCard({ product, index }) {
  const [hovered, setHovered] = useState(false);

  return (
    <div
      className="product-card animate-fade-in-up"
      style={{ animationDelay: `${index * 60}ms` }}
      onMouseEnter={() => setHovered(true)}
      onMouseLeave={() => setHovered(false)}
    >
      <div className="img-wrap" style={{ aspectRatio: '3/4' }}>
        <img
          src={product.img}
          alt={product.name}
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
        <div className="overlay" />
        <div className="ctas">
          <button
            className="btn-primary"
            style={{ padding: '0.5rem 1rem', fontSize: 'var(--text-xs)' }}
            onClick={() => {
              document.getElementById('ai-stylist')?.scrollIntoView({ behavior: 'smooth' });
            }}
          >
            Ask Stylist
          </button>
          <button
            className="btn-outline"
            style={{ padding: '0.5rem 1rem', fontSize: 'var(--text-xs)', borderColor: 'white', color: 'white' }}
            onClick={() => {
              document.getElementById('vto')?.scrollIntoView({ behavior: 'smooth' });
            }}
          >
            Try On
          </button>
        </div>
      </div>

      <div style={{ padding: '0.85rem 0' }}>
        <p style={{ fontFamily: 'var(--font-display)', fontSize: 'var(--text-lg)', fontWeight: 300 }}>
          {product.name}
        </p>
        <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginTop: '0.25rem' }}>
          <p style={{ fontSize: 'var(--text-xs)', color: 'var(--color-text-muted)' }}>
            {product.category}
          </p>
          <p style={{ fontSize: 'var(--text-sm)', fontFamily: 'var(--font-mono)', color: 'var(--color-accent)' }}>
            LKR {product.price.toLocaleString()}
          </p>
        </div>
      </div>
    </div>
  );
}

export default function FeaturedCollections() {
  const [active, setActive] = useState('All');

  const visible = active === 'All' ? PRODUCTS : PRODUCTS.filter((p) => p.category === active);

  return (
    <section id="collections" className="section-padding" style={{ background: 'var(--color-bg)' }}>
      <div className="container">
        {/* Header */}
        <div
          style={{
            display: 'flex',
            justifyContent: 'space-between',
            alignItems: 'flex-end',
            marginBottom: '2.5rem',
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
            <h2 style={{ fontSize: 'var(--text-3xl)', fontWeight: 300 }}>Our Collections</h2>
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

        {/* Filter tabs */}
        <div style={{ display: 'flex', gap: '0.75rem', flexWrap: 'wrap', marginBottom: '2.5rem' }}>
          {FILTERS.map((f) => (
            <button
              key={f}
              onClick={() => setActive(f)}
              style={{
                fontFamily: 'var(--font-mono)',
                fontSize: 'var(--text-xs)',
                letterSpacing: '0.1em',
                textTransform: 'uppercase',
                padding: '0.4rem 1rem',
                border: `1px solid ${active === f ? 'var(--color-accent)' : 'var(--color-border)'}`,
                background: active === f ? 'var(--color-accent)' : 'transparent',
                color: active === f ? 'var(--color-bg)' : 'var(--color-text-muted)',
                cursor: 'pointer',
                transition: 'all 0.2s',
                borderRadius: '2px',
              }}
            >
              {f}
            </button>
          ))}
        </div>

        {/* Product grid */}
        <div
          style={{
            display: 'grid',
            gridTemplateColumns: 'repeat(auto-fill, minmax(220px, 1fr))',
            gap: '1.5rem',
          }}
        >
          {visible.map((product, i) => (
            <ProductCard key={product.name} product={product} index={i} />
          ))}
        </div>
      </div>
    </section>
  );
}
