import { motion } from "framer-motion";
import { Link } from "react-router-dom";

import { Button } from "@/components/ui/button";

const heroImage = "https://images.unsplash.com/photo-1762278805112-a0f50365845e?crop=entropy&cs=srgb&fm=jpg&ixid=M3w4NjA3MDR8MHwxfHNlYXJjaHwyfHxhYnN0cmFjdCUyMGdlb21ldHJpYyUyMG9yYW5nZSUyMGJsYWNrJTIwZGlnaXRhbHxlbnwwfHx8fDE3NzMxODM1Njh8MA&ixlib=rb-4.1.0&q=85";

export const LandingPage = () => {
  return (
    <div className="min-h-screen bg-orange-500 text-black" data-testid="landing-page">
      <div className="mx-auto flex min-h-screen w-full max-w-7xl flex-col justify-between px-6 py-10 md:px-10">
        <motion.header
          initial={{ opacity: 0, y: 24 }}
          animate={{ opacity: 1, y: 0 }}
          transition={{ duration: 0.6 }}
          className="flex flex-wrap items-center justify-between gap-3"
        >
          <p className="font-mono text-sm font-bold uppercase tracking-widest" data-testid="landing-brand">Algorithmic Platform</p>
          <Link to="/login" data-testid="landing-login-link">
            <Button className="border border-black bg-black text-orange-500 hover:bg-zinc-900" data-testid="landing-login-button">Giriş Yap</Button>
          </Link>
        </motion.header>

        <section className="grid items-center gap-8 py-12 lg:grid-cols-2" data-testid="landing-hero-section">
          <motion.div
            initial={{ opacity: 0, x: -30 }}
            animate={{ opacity: 1, x: 0 }}
            transition={{ duration: 0.7, delay: 0.1 }}
          >
            <h1 className="text-4xl font-black uppercase tracking-tight sm:text-5xl lg:text-6xl" data-testid="landing-main-heading">
              Multi-User Trading Engine
            </h1>
            <p className="mt-4 max-w-xl text-base font-medium sm:text-lg" data-testid="landing-subtitle">
              Binance adapter + MOCK execution ile güvenli başlangıç. User/Admin panel, bot config, risk policy ve strategy template yönetimi ilk fazda hazır.
            </p>
            <div className="mt-6 flex flex-wrap gap-3">
              <Link to="/login" data-testid="landing-start-link">
                <Button className="border border-black bg-black text-orange-500 hover:bg-zinc-900" data-testid="landing-start-button">Platforma Başla</Button>
              </Link>
              <div className="border border-black px-3 py-2 text-xs font-mono" data-testid="landing-mode-chip">Execution Mode: MOCK</div>
            </div>
          </motion.div>

          <motion.div
            initial={{ opacity: 0, x: 30 }}
            animate={{ opacity: 1, x: 0 }}
            transition={{ duration: 0.7, delay: 0.2 }}
            className="border border-black bg-black/10 p-2"
            data-testid="landing-hero-image-wrapper"
          >
            <div className="aspect-[4/3] overflow-hidden" data-testid="landing-hero-image-container">
              <img
                src={heroImage}
                alt="Abstract Orange Data Flow"
                className="h-full w-full object-cover object-center"
                data-testid="landing-hero-image"
              />
            </div>
          </motion.div>
        </section>

        <section className="grid gap-3 md:grid-cols-3" data-testid="landing-feature-grid">
          {[
            "JWT + Rol Tabanlı Erişim",
            "PostgreSQL + Redis + Docker Compose",
            "Adapter Tabanlı Çoklu Borsa Hazırlığı",
          ].map((item, index) => (
            <div key={item} className="border border-black bg-orange-400/30 p-3" data-testid={`landing-feature-card-${index}`}>
              <p className="text-sm font-bold uppercase tracking-wide" data-testid={`landing-feature-text-${index}`}>{item}</p>
            </div>
          ))}
        </section>
      </div>
    </div>
  );
};
