import { Eye, EyeOff, Lock, Mail, Upload } from "lucide-react";
import { useEffect, useMemo, useState } from "react";
import { useNavigate } from "react-router-dom";
import { toast } from "sonner";

import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { useAuth } from "@/context/AuthContext";
import { apiClient } from "@/lib/api";

const backendBase = process.env.REACT_APP_BACKEND_URL;

export const UserLoginPage = () => {
  const navigate = useNavigate();
  const { login, verifyMfaChallenge, register } = useAuth();
  const [mode, setMode] = useState("register");
  const [showPassword, setShowPassword] = useState(false);
  const [form, setForm] = useState({
    firstName: "",
    lastName: "",
    phone: "",
    email: "",
    password: "",
    confirmPassword: "",
  });
  const [logoPreview, setLogoPreview] = useState("/xilo-logo.png");
  const [submitting, setSubmitting] = useState(false);
  const [mfaState, setMfaState] = useState(null);
  const [mfaMethod, setMfaMethod] = useState("totp");
  const [mfaCode, setMfaCode] = useState("");

  const resolvedLogoPreview = useMemo(() => {
    if (!logoPreview || String(logoPreview).startsWith("data:")) {
      return logoPreview || "/xilo-logo.png";
    }
    if (String(logoPreview).startsWith("http")) {
      return logoPreview;
    }
    return `${backendBase}${logoPreview}`;
  }, [logoPreview]);

  useEffect(() => {
    const loadBrand = async () => {
      try {
        const { data } = await apiClient.get("/branding/settings");
        if (data?.logo_url) {
          setLogoPreview(`${data.logo_url}${data.updated_at ? `?v=${encodeURIComponent(data.updated_at)}` : ""}`);
        }
      } catch {
        // silent fallback to bundled logo
      }
    };
    loadBrand();
  }, []);

  const onLogoFileChange = (event) => {
    const file = event.target.files?.[0];
    if (!file) {
      return;
    }
    const reader = new FileReader();
    reader.onload = () => {
      if (typeof reader.result === "string") {
        setLogoPreview(reader.result);
      }
    };
    reader.readAsDataURL(file);
  };

  const onSubmit = async (event) => {
    event.preventDefault();
    setSubmitting(true);
    try {
      if (mode === "register") {
        if (form.password !== form.confirmPassword) {
          throw new Error("Şifreler uyuşmuyor");
        }
        await register({
          email: form.email.trim(),
          password: form.password,
          first_name: form.firstName.trim(),
          last_name: form.lastName.trim(),
          full_name: `${form.firstName.trim()} ${form.lastName.trim()}`.trim(),
          phone: form.phone.trim(),
        });
        toast.success("Talebiniz alındı. Admin onayı sonrası giriş yapabilirsiniz.");
        setMode("login");
      } else {
        const loginResult = await login({ email: form.email, password: form.password, panel: "user" });
        if (loginResult?.mfaRequired) {
          setMfaState(loginResult);
          setMfaMethod((loginResult.methods || ["totp"])[0] || "totp");
          setMfaCode("");
          toast.info("MFA doğrulama kodunu giriniz");
          return;
        }
        toast.success("Giriş başarılı");
        navigate("/user/dashboard");
      }
    } catch (error) {
      toast.error(error?.response?.data?.detail || error?.message || "İşlem başarısız");
    } finally {
      setSubmitting(false);
    }
  };

  const onVerifyMfa = async () => {
    if (!mfaState?.challengeToken) {
      return;
    }
    setSubmitting(true);
    try {
      await verifyMfaChallenge({
        challengeToken: mfaState.challengeToken,
        method: mfaMethod,
        code: mfaCode,
      });
      toast.success("MFA doğrulandı");
      navigate("/user/dashboard");
    } catch (error) {
      toast.error(error?.response?.data?.detail || "MFA doğrulaması başarısız");
    } finally {
      setSubmitting(false);
    }
  };

  return (
    <div className="min-h-screen bg-[#f3f4f2] px-4 py-6 text-black" data-testid="user-login-page">
      <div className="mx-auto w-full max-w-7xl space-y-6" data-testid="user-login-layout">
        <header className="flex flex-wrap items-start justify-between gap-4" data-testid="user-login-top-strip">
          <div className="rounded border border-slate-300 bg-white p-2" data-testid="user-login-brand-block">
            <img src={resolvedLogoPreview} alt="XILO logo" className="h-auto w-[170px] sm:w-[230px]" data-testid="user-login-brand-logo" />
          </div>
          <div className="flex flex-wrap gap-2" data-testid="user-login-panel-toggle-group">
            <Button type="button" className="rounded-none bg-black text-orange-300 hover:bg-zinc-900" data-testid="user-login-panel-toggle-user-button">Kullanıcı Girişi</Button>
            <Button type="button" variant="outline" className="rounded-none border-slate-400 bg-white text-slate-800 hover:bg-slate-100" onClick={() => navigate("/admin/login")} data-testid="user-login-panel-toggle-admin-button">Admin Girişi</Button>
          </div>
        </header>

        <section className="grid gap-6 lg:grid-cols-2" data-testid="user-login-hero-section">
          <div className="space-y-4" data-testid="user-login-left-column">
            <h1 className="text-4xl font-black uppercase tracking-tight sm:text-5xl" data-testid="user-login-title">XILO-USER TRADING ENGINE</h1>
            <p className="max-w-2xl text-base text-slate-800" data-testid="user-login-subtitle">
              Binance adapter + MOCK execution ile güvenli başlangıç. User/Admin panel, bot config, risk policy ve strategy template yönetimi ilk fazda hazır.
            </p>
            <div className="flex flex-wrap gap-3" data-testid="user-login-action-chips">
              <Button type="button" className="rounded-none border border-black bg-black text-orange-300 hover:bg-zinc-900" onClick={() => setMode("login")} data-testid="user-login-start-button">Platforma Başla</Button>
              <div className="border border-black bg-white px-3 py-2 text-sm" data-testid="user-login-mode-chip">Execution Mode: MOCK</div>
            </div>

            <form onSubmit={onSubmit} className="max-w-xl space-y-3 rounded border-2 border-[#c76916] bg-[#ff7f1f] p-4" data-testid="user-login-form">
              <p className="text-xs font-bold uppercase tracking-widest" data-testid="user-login-form-title">{mode === "register" ? "Hesap Aç" : "Giriş Yap"}</p>

              <label className="block" data-testid="user-login-logo-upload-block">
                <span className="mb-1 inline-flex items-center gap-2 text-xs font-semibold" data-testid="user-login-logo-upload-label"><Upload className="h-3 w-3" /> Logo Yükle</span>
                <Input type="file" accept="image/*" onChange={onLogoFileChange} className="h-10 border-black bg-orange-50 file:mr-3 file:border-0 file:bg-black file:px-3 file:py-1 file:text-xs file:text-orange-300" data-testid="user-login-logo-file-input" />
              </label>

              {mode === "register" && (
                <>
                  <Input type="text" value={form.firstName} onChange={(event) => setForm((prev) => ({ ...prev, firstName: event.target.value }))} placeholder="First Name" className="h-11 border-black bg-orange-50" data-testid="user-login-first-name-input" required />
                  <Input type="text" value={form.lastName} onChange={(event) => setForm((prev) => ({ ...prev, lastName: event.target.value }))} placeholder="Last Name" className="h-11 border-black bg-orange-50" data-testid="user-login-last-name-input" required />
                  <Input type="tel" value={form.phone} onChange={(event) => setForm((prev) => ({ ...prev, phone: event.target.value }))} placeholder="Phone Number" className="h-11 border-black bg-orange-50" data-testid="user-login-phone-input" required />
                </>
              )}

              <div className="relative" data-testid="user-login-email-input-wrapper">
                <Mail className="absolute left-3 top-1/2 h-4 w-4 -translate-y-1/2 text-slate-600" />
                <Input type="email" value={form.email} onChange={(event) => setForm((prev) => ({ ...prev, email: event.target.value }))} placeholder="E-posta" className="h-11 border-black bg-orange-50 pl-10" data-testid="user-login-email-input" required />
              </div>

              <div className="relative" data-testid="user-login-password-input-wrapper">
                <Lock className="absolute left-3 top-1/2 h-4 w-4 -translate-y-1/2 text-slate-600" />
                <Input type={showPassword ? "text" : "password"} value={form.password} onChange={(event) => setForm((prev) => ({ ...prev, password: event.target.value }))} placeholder="Şifre" className="h-11 border-black bg-orange-50 pl-10 pr-10" data-testid="user-login-password-input" minLength={8} required />
                <button type="button" className="absolute right-3 top-1/2 -translate-y-1/2" onClick={() => setShowPassword((prev) => !prev)} data-testid="user-login-toggle-password-button">
                  {showPassword ? <EyeOff className="h-4 w-4" /> : <Eye className="h-4 w-4" />}
                </button>
              </div>

              {mode === "register" && (
                <Input type={showPassword ? "text" : "password"} value={form.confirmPassword} onChange={(event) => setForm((prev) => ({ ...prev, confirmPassword: event.target.value }))} placeholder="Şifre Tekrar" className="h-11 border-black bg-orange-50" data-testid="user-login-confirm-password-input" minLength={8} required />
              )}

              <div className="flex flex-wrap items-center justify-between gap-2" data-testid="user-login-form-footer">
                <Button className="rounded-none border border-black bg-black text-orange-300 hover:bg-zinc-900" data-testid="user-login-submit-button" disabled={submitting}>
                  {submitting ? "İşleniyor..." : mode === "register" ? "Hesap Aç" : "Giriş Yap"}
                </Button>
                <button type="button" className="text-sm underline" onClick={() => setMode((prev) => (prev === "login" ? "register" : "login"))} data-testid="user-login-register-toggle-button">
                  {mode === "login" ? "Hesap aç" : "Girişe dön"}
                </button>
              </div>

              <button type="button" className="text-xs underline" onClick={() => navigate(`/forgot-password?panel=user&email=${encodeURIComponent(form.email || "")}`)} data-testid="user-login-forgot-password-link">Şifremi unuttum</button>

              {mfaState?.mfaRequired && (
                <div className="space-y-2 rounded border border-black bg-white/70 p-3" data-testid="user-login-mfa-panel">
                  <p className="text-xs font-semibold uppercase" data-testid="user-login-mfa-title">MFA Doğrulama</p>
                  <p className="text-xs" data-testid="user-login-mfa-methods">Yöntemler: {(mfaState.methods || []).join(", ")}</p>
                  {(mfaState.methods || []).length > 1 && (
                    <select value={mfaMethod} onChange={(event) => setMfaMethod(event.target.value)} className="h-10 w-full border border-black bg-white px-3 text-sm" data-testid="user-login-mfa-method-select">
                      {(mfaState.methods || []).map((item) => (
                        <option key={item} value={item} data-testid={`user-login-mfa-method-option-${item}`}>{item}</option>
                      ))}
                    </select>
                  )}
                  <Input value={mfaCode} onChange={(event) => setMfaCode(event.target.value)} placeholder={mfaMethod === "email" ? "E-posta OTP kodu" : "Authenticator kodu"} className="h-10 border-black bg-white" data-testid="user-login-mfa-code-input" />
                  <Button type="button" onClick={onVerifyMfa} className="rounded-none border border-black bg-black text-orange-300 hover:bg-zinc-900" data-testid="user-login-mfa-verify-button" disabled={submitting}>
                    {submitting ? "Doğrulanıyor..." : "MFA Doğrula"}
                  </Button>
                  {mfaState.emailCodePreview && (
                    <p className="text-xs text-slate-700" data-testid="user-login-mfa-email-code-preview">email otp preview: {mfaState.emailCodePreview}</p>
                  )}
                </div>
              )}
            </form>
          </div>

          <div className="rounded border-2 border-[#c76916] bg-black p-2" data-testid="user-login-visual-panel">
            <div
              className="aspect-[4/3] w-full"
              style={{
                backgroundColor: "#020202",
                backgroundImage: "repeating-linear-gradient(120deg, #ff8a00 0 6px, transparent 6px 16px), repeating-linear-gradient(120deg, transparent 0 42px, #ffffff 42px 45px)",
                backgroundBlendMode: "screen",
              }}
              data-testid="user-login-visual-pattern"
            />
          </div>
        </section>

        <section className="rounded border border-black/40 bg-white p-4" data-testid="user-login-live-status-card">
          <p className="text-xs font-bold uppercase tracking-widest" data-testid="user-login-live-status-title">Canlı Durum</p>
          <div className="mt-2 grid gap-2 md:grid-cols-3" data-testid="user-login-live-status-grid">
            <p className="text-sm" data-testid="user-login-live-status-platform">Platform: 🟢 Online</p>
            <p className="text-sm" data-testid="user-login-live-status-engine">Execution Engine: 🟢 İşlemde</p>
            <p className="text-sm" data-testid="user-login-live-status-note">Not: ilk kurulumda testnet ile başlamanız önerilir.</p>
          </div>
        </section>

        <section className="grid gap-3 md:grid-cols-3" data-testid="user-login-feature-grid">
          {["JWT + ROL TABANLI ERİŞİM", "POSTGRESQL + REDIS + DOCKER COMPOSE", "ADAPTER TABANLI ÇOKLU BORSA HAZIRLIĞI"].map((item, index) => (
            <div key={item} className="border border-black bg-[#ff8a00] px-3 py-3" data-testid={`user-login-feature-card-${index}`}>
              <p className="text-sm font-bold uppercase" data-testid={`user-login-feature-text-${index}`}>{item}</p>
            </div>
          ))}
        </section>
      </div>
    </div>
  );
};