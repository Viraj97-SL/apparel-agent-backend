import Header from '../components/layout/Header';
import Footer from '../components/layout/Footer';
import HeroSection from '../components/sections/HeroSection';
import BrandStatsSection from '../components/sections/BrandStatsSection';
import FeaturedCollections from '../components/sections/FeaturedCollections';
import BrandStorySection from '../components/sections/BrandStorySection';
import AIStylistSection from '../components/sections/AIStylistSection';
import VTOSection from '../components/sections/VTOSection';
import TrendingSection from '../components/sections/TrendingSection';
import TestimonialsSection from '../components/sections/TestimonialsSection';
import PartnersSection from '../components/sections/PartnersSection';

export default function Home() {
  return (
    <>
      <Header />
      <main>
        <HeroSection />
        <BrandStatsSection />
        <FeaturedCollections />
        <BrandStorySection />
        <AIStylistSection />
        <VTOSection />
        <TrendingSection />
        <TestimonialsSection />
        <PartnersSection />
      </main>
      <Footer />
    </>
  );
}
