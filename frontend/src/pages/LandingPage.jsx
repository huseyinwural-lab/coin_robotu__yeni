import { motion } from "framer-motion";
import { useState } from "react";
import { useNavigate } from "react-router-dom";
import { Link } from "react-router-dom";
import { toast } from "sonner";

import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { useAuth } from "@/context/AuthContext";

const heroImage = "https://images.unsplash.com/photo-1762278805112-a0f50365845e?crop=entropy&cs=srgb&fm=jpg&ixid=M3w4NjA3MDR8MHwxfHNlYXJjaHwyfHxhYnN0cmFjdCUyMGdlb21ldHJpYyUyMG9yYW5nZSUyMGJsYWNrJTIwZGlnaXRhbHxlbnwwfHx8fDE3NzMxODM1Njh8MA&ixlib=rb-4.1.0&q=85";

export const LandingPage = () => {
  const navigate = useNavigate();
  const { register } = useAuth();
  const [form, setForm] = useState({ email: "", password: "", confirmPassword: "" });
  const [isSubmitting, setIsSubmitting] = useState(false);

  const onRegisterSubmit = async (event) => {
    event.preventDefault();
    if (form.password !== form.confirmPassword) {
      toast.error("Şifreler uyuşmuyor");
      return;
    }

    setIsSubmitting(true);
    try {
      await register({ email: form.email.trim(), password: form.password });
      toast.success("Kayıt talebiniz alındı. Admin onayı sonrası giriş yapabilirsiniz.");
      setForm({ email: "", password: "", confirmPassword: "" });
      navigate("/user/login");
    } catch (error) {
      toast.error(error?.response?.data?.detail || "Hesap açma başarısız");
    } finally {
      setIsSubmitting(false);
    }
  };

  return (
    <div className="min-h-screen bg-orange-500 text-black" data-testid="landing-page">
      <div className="mx-auto flex w-full max-w-6xl flex-col gap-8 px-5 py-6 md:px-8 md:py-8" data-testid="landing-container">
        <motion.header
          initial={{ opacity: 0, y: 24 }}
          animate={{ opacity: 1, y: 0 }}
          transition={{ duration: 0.6 }}
          className="flex flex-wrap items-center justify-between gap-3"
        >
          <p className="font-mono text-sm font-bold uppercase tracking-widest" data-testid="landing-brand">Algorithmic Platform</p>
          <div className="flex flex-wrap gap-2" data-testid="landing-login-actions">
            <Link to="/user/login" data-testid="landing-user-login-link">
              <Button className="border border-black bg-black text-orange-500 hover:bg-zinc-900" data-testid="landing-user-login-button">Kullanıcı Girişi</Button>
            </Link>
            <Link to="/admin/login" data-testid="landing-admin-login-link">
              <Button className="border border-black bg-orange-300 text-black hover:bg-orange-200" data-testid="landing-admin-login-button">Admin Girişi</Button>
            </Link>
          </div>
        </motion.header>

        <section className="grid items-start gap-6 py-2 lg:grid-cols-2" data-testid="landing-hero-section">
          <motion.div
            initial={{ opacity: 0, x: -30 }}
            animate={{ opacity: 1, x: 0 }}
            transition={{ duration: 0.7, delay: 0.1 }}
          >
            <h1 className="text-4xl font-black uppercase tracking-tight sm:text-5xl lg:text-5xl" data-testid="landing-main-heading">
              XILO-USER Trading Engine
            </h1>
            <p className="mt-3 max-w-xl text-base font-medium" data-testid="landing-subtitle">
              Binance adapter + MOCK execution ile güvenli başlangıç. User/Admin panel, bot config, risk policy ve strategy template yönetimi ilk fazda hazır.
            </p>
            <div className="mt-5 flex flex-wrap gap-3">
              <Link to="/user/login" data-testid="landing-start-link">
                <Button className="border border-black bg-black text-orange-500 hover:bg-zinc-900" data-testid="landing-start-button">Platforma Başla</Button>
              </Link>
              <div className="border border-black px-3 py-2 text-xs font-mono" data-testid="landing-mode-chip">Execution Mode: MOCK</div>
            </div>

            <form className="mt-6 max-w-lg space-y-3 rounded border border-black/60 bg-orange-400/30 p-4" onSubmit={onRegisterSubmit} data-testid="landing-register-form">
              <p className="text-xs font-bold uppercase tracking-widest" data-testid="landing-register-title">Hesap Aç</p>
              <div className="grid gap-2" data-testid="landing-register-fields">
                <Input
                  type="email"
                  value={form.email}
                  onChange={(event) => setForm((prev) => ({ ...prev, email: event.target.value }))}
                  placeholder="E-posta"
                  className="h-10 border-black bg-orange-50 text-sm"
                  data-testid="landing-register-email-input"
                  required
                />
                <Input
                  type="password"
                  value={form.password}
                  onChange={(event) => setForm((prev) => ({ ...prev, password: event.target.value }))}
                  placeholder="Şifre"
                  className="h-10 border-black bg-orange-50 text-sm"
                  data-testid="landing-register-password-input"
                  minLength={8}
                  required
                />
                <Input
                  type="password"
                  value={form.confirmPassword}
                  onChange={(event) => setForm((prev) => ({ ...prev, confirmPassword: event.target.value }))}
                  placeholder="Şifre Tekrar"
                  className="h-10 border-black bg-orange-50 text-sm"
                  data-testid="landing-register-confirm-password-input"
                  minLength={8}
                  required
                />
              </div>
              <Button type="submit" disabled={isSubmitting} className="border border-black bg-black text-orange-500 hover:bg-zinc-900" data-testid="landing-register-submit-button">
                {isSubmitting ? "Gönderiliyor..." : "Hesap Aç"}
              </Button>
            </form>
          </motion.div>

          <motion.div
            initial={{ opacity: 0, x: 30 }}
            animate={{ opacity: 1, x: 0 }}
            transition={{ duration: 0.7, delay: 0.2 }}
            className="border border-black bg-black/10 p-2"
            data-testid="landing-hero-image-wrapper"
          >
            <div className="aspect-[4/3] max-h-[420px] overflow-hidden" data-testid="landing-hero-image-container">
              <img
                src={heroImage}
                alt="Abstract Orange Data Flow"
                className="h-full w-full object-cover object-center"
                data-testid="landing-hero-image"
              />
            </div>
          </motion.div>
        </section>

        <section className="grid gap-3 pb-2 md:grid-cols-3" data-testid="landing-feature-grid">
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
