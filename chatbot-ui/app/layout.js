import "./globals.css";

export const metadata = {
  title: "Pamorya — Premium AI Fashion",
  description: "Sri Lanka's first AI-powered personal stylist. Discover curated fashion, virtual try-on, and personalised styling advice.",
  keywords: "fashion, Sri Lanka, AI stylist, virtual try-on, women's clothing",
  openGraph: {
    title: "Pamorya — Premium AI Fashion",
    description: "Sri Lanka's first AI-powered personal stylist.",
    type: "website",
  },
};

export default function RootLayout({ children }) {
  return (
    <html lang="en">
      <head>
        <link rel="preconnect" href="https://fonts.googleapis.com" />
        <link rel="preconnect" href="https://fonts.gstatic.com" crossOrigin="anonymous" />
      </head>
      <body>{children}</body>
    </html>
  );
}
