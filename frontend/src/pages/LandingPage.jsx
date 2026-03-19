import { motion } from "framer-motion";
import { useEffect, useState } from "react";
import { useNavigate } from "react-router-dom";
import { Link } from "react-router-dom";
import { toast } from "sonner";

import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { useAuth } from "@/context/AuthContext";

const FIXED_HEADER_LOGO_URL = "https://customer-assets.emergentagent.com/job_7c46efd0-6499-4da5-832c-e8dbd8b11e57/artifacts/qeyh5tzg_Gemini_Generated_Image_ikkodjikkodjikko.png";

export const LandingPage = () => {
  const navigate = useNavigate();
  const { register } = useAuth();
  const [form, setForm] = useState({
    firstName: "",
    lastName: "",
    phone: "",
    email: "",
    password: "",
    confirmPassword: "",
  });
  const [isSubmitting, setIsSubmitting] = useState(false);
  const [appName, setAppName] = useState("XILO-USER TRADING ENGINE");
  const [onboarding, setOnboarding] = useState({
    email: "",
    verificationCode: "",
    generatedCode: "",
    status: null,
    isRequesting: false,
    isVerifying: false,
  });

  const refreshOnboardingStatus = async (email) => {
    const normalizedEmail = String(email || "").trim();
    if (!normalizedEmail) {
      return;
    }
    const response = await fetch(`/api/auth/onboarding-status?email=${encodeURIComponent(normalizedEmail)}`);
    const payload = await response.json();
    if (!response.ok) {
      throw new Error(payload?.detail || "Onboarding durumu alınamadı");
    }
    setOnboarding((previous) => ({ ...previous, email: normalizedEmail, status: payload || null }));
  };

  const requestVerificationCode = async (email) => {
    const normalizedEmail = String(email || "").trim();
    if (!normalizedEmail) {
      return;
    }
    setOnboarding((previous) => ({ ...previous, isRequesting: true, email: normalizedEmail }));
    try {
      const response = await fetch("/api/auth/email-verification/request", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ email: normalizedEmail }),
      });
      const payload = await response.json();
      if (!response.ok) {
        throw new Error(payload?.detail || "Doğrulama kodu oluşturulamadı");
      }
      setOnboarding((previous) => ({ ...previous, generatedCode: payload?.verification_code || "" }));
      toast.success("Doğrulama kodu üretildi");
      await refreshOnboardingStatus(normalizedEmail);
    } catch (error) {
      toast.error(error?.message || "Doğrulama kodu üretilemedi");
    } finally {
      setOnboarding((previous) => ({ ...previous, isRequesting: false }));
    }
  };

  const verifyEmailCode = async () => {
    const normalizedEmail = String(onboarding.email || "").trim();
    if (!normalizedEmail || !onboarding.verificationCode.trim()) {
      toast.error("E-posta ve doğrulama kodu zorunlu");
      return;
    }
    setOnboarding((previous) => ({ ...previous, isVerifying: true }));
    try {
      const response = await fetch("/api/auth/email-verification/verify", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ email: normalizedEmail, code: onboarding.verificationCode.trim() }),
      });
      const payload = await response.json();
      if (!response.ok) {
        throw new Error(payload?.detail || "E-posta doğrulaması başarısız");
      }
      toast.success("E-posta doğrulaması tamamlandı");
      setOnboarding((previous) => ({ ...previous, verificationCode: "", generatedCode: "" }));
      await refreshOnboardingStatus(normalizedEmail);
    } catch (error) {
      toast.error(error?.message || "E-posta doğrulaması başarısız");
    } finally {
      setOnboarding((previous) => ({ ...previous, isVerifying: false }));
    }
  };

  useEffect(() => {
    const loadBrand = async () => {
      try {
        const response = await fetch("/api/branding/settings");
        const payload = await response.json();
        if (!response.ok) {
          return;
        }
        if (payload?.app_name) {
          setAppName(String(payload.app_name).toUpperCase());
        }
      } catch {
        // silent fallback
      }
    };
    loadBrand();
  }, []);

  const onRegisterSubmit = async (event) => {
    event.preventDefault();
    if (form.password !== form.confirmPassword) {
      toast.error("Şifreler uyuşmuyor");
      return;
    }

    setIsSubmitting(true);
    try {
      const normalizedEmail = form.email.trim();
      await register({
        email: normalizedEmail,
        password: form.password,
        first_name: form.firstName.trim(),
        last_name: form.lastName.trim(),
        full_name: `${form.firstName.trim()} ${form.lastName.trim()}`.trim(),
        phone: form.phone.trim(),
      });
      toast.success("Kayıt talebiniz alındı. Admin onayı sonrası giriş yapabilirsiniz.");
      setForm({ firstName: "", lastName: "", phone: "", email: "", password: "", confirmPassword: "" });
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
          className="flex flex-wrap items-center justify-between gap-4"
          data-testid="landing-header"
        >
          <div className="w-full max-w-[320px] overflow-hidden rounded border border-black/70 bg-black/25 p-1" data-testid="landing-fixed-logo-area">
            <div className="aspect-[16/5] w-full overflow-hidden rounded bg-black/70" data-testid="landing-fixed-logo-frame">
              <img
                src={FIXED_HEADER_LOGO_URL}
                alt="XILO sabit logo"
                className="h-full w-full object-cover object-center"
                data-testid="landing-fixed-logo-image"
              />
            </div>
          </div>

          <div className="flex min-h-[96px] items-center" data-testid="landing-user-login-area">
            <Link to="/user/login" data-testid="landing-user-login-link">
              <Button className="border border-black bg-black text-orange-500 hover:bg-zinc-900" data-testid="landing-user-login-button">Kullanıcı Girişi</Button>
            </Link>
          </div>
        </motion.header>

        <section className="grid items-start gap-6 py-2 lg:grid-cols-2" data-testid="landing-hero-section">
          <motion.div
            initial={{ opacity: 0, x: -30 }}
            animate={{ opacity: 1, x: 0 }}
            transition={{ duration: 0.7, delay: 0.1 }}
          >
            <h1 className="text-4xl font-black uppercase tracking-tight sm:text-5xl lg:text-5xl" data-testid="landing-main-heading">{appName}</h1>
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
                  type="text"
                  value={form.firstName}
                  onChange={(event) => setForm((prev) => ({ ...prev, firstName: event.target.value }))}
                  placeholder="First Name"
                  className="h-10 border-black bg-orange-50 text-sm"
                  data-testid="landing-register-first-name-input"
                  required
                />
                <Input
                  type="text"
                  value={form.lastName}
                  onChange={(event) => setForm((prev) => ({ ...prev, lastName: event.target.value }))}
                  placeholder="Last Name"
                  className="h-10 border-black bg-orange-50 text-sm"
                  data-testid="landing-register-last-name-input"
                  required
                />
                <Input
                  type="tel"
                  value={form.phone}
                  onChange={(event) => setForm((prev) => ({ ...prev, phone: event.target.value }))}
                  placeholder="Phone Number"
                  className="h-10 border-black bg-orange-50 text-sm"
                  data-testid="landing-register-phone-input"
                  required
                />
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

            {onboarding.email && (
              <div className="mt-4 max-w-lg space-y-3 rounded border border-black/60 bg-black/10 p-4" data-testid="landing-onboarding-status-card">
                <p className="text-xs font-bold uppercase tracking-widest" data-testid="landing-onboarding-status-title">Onboarding Adımları</p>
                <p className="text-xs" data-testid="landing-onboarding-status-email">E-posta: {onboarding.email}</p>
                <div className="space-y-1" data-testid="landing-onboarding-status-steps">
                  {(onboarding.status?.steps || []).map((step) => (
                    <p key={step.key} className="text-xs" data-testid={`landing-onboarding-step-${step.key}`}>
                      {step.done ? "✅" : "⏳"} {step.label}
                    </p>
                  ))}
                </div>
                {onboarding.generatedCode && (
                  <p className="text-xs font-mono" data-testid="landing-onboarding-generated-code">Doğrulama Kodu: {onboarding.generatedCode}</p>
                )}
                <div className="flex flex-wrap gap-2" data-testid="landing-onboarding-actions">
                  <Button type="button" variant="outline" onClick={() => requestVerificationCode(onboarding.email)} disabled={onboarding.isRequesting} data-testid="landing-onboarding-request-code-button">
                    {onboarding.isRequesting ? "Gönderiliyor..." : "Kod Yeniden Üret"}
                  </Button>
                  <Input
                    value={onboarding.verificationCode}
                    onChange={(event) => setOnboarding((prev) => ({ ...prev, verificationCode: event.target.value }))}
                    placeholder="Doğrulama kodu"
                    className="h-9 max-w-[180px] border-black bg-orange-50 text-sm"
                    data-testid="landing-onboarding-code-input"
                  />
                  <Button type="button" onClick={verifyEmailCode} disabled={onboarding.isVerifying} data-testid="landing-onboarding-verify-button">
                    {onboarding.isVerifying ? "Doğrulanıyor..." : "E-postayı Doğrula"}
                  </Button>
                  <Button type="button" variant="outline" onClick={() => navigate("/user/login")} data-testid="landing-onboarding-go-login-button">Girişe Git</Button>
                </div>
              </div>
            )}
          </motion.div>

          <motion.div
            initial={{ opacity: 0, x: 30 }}
            animate={{ opacity: 1, x: 0 }}
            transition={{ duration: 0.7, delay: 0.2 }}
            className="border-2 border-[#c76916] bg-black p-2"
            data-testid="landing-hero-image-wrapper"
          >
            <div
              className="aspect-[4/3] max-h-[420px] overflow-hidden"
              style={{
                backgroundColor: "#020202",
                backgroundImage: "repeating-linear-gradient(120deg, #ff8a00 0 6px, transparent 6px 16px), repeating-linear-gradient(120deg, transparent 0 42px, #ffffff 42px 45px)",
                backgroundBlendMode: "screen",
              }}
              data-testid="landing-hero-image-container"
            />
          </motion.div>
        </section>

        <section className="rounded border border-black/70 bg-black/10 p-4" data-testid="landing-live-status-card">
          <p className="text-xs font-bold uppercase tracking-widest" data-testid="landing-live-status-title">Canlı Durum</p>
          <div className="mt-2 grid gap-2 md:grid-cols-3" data-testid="landing-live-status-grid">
            <p className="text-xs" data-testid="landing-live-status-platform">Platform: 🟢 Online</p>
            <p className="text-xs" data-testid="landing-live-status-engine">Execution Engine: 🟢 İşlemde</p>
            <p className="text-xs" data-testid="landing-live-status-note">Not: İlk kurulumda testnet ile başlamanız önerilir.</p>
          </div>
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
