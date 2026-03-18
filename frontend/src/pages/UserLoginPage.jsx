import { Eye, EyeOff, Lock, Mail } from "lucide-react";
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
  const [mode, setMode] = useState("login");
  const [showPassword, setShowPassword] = useState(false);
  const [rememberMe, setRememberMe] = useState(true);
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
        toast.success(`Giriş başarılı${rememberMe ? "" : " (oturum cihazda saklanmayacak)"}`);
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
    <div className="min-h-screen bg-[#edf0f5] px-4 py-8" data-testid="user-login-page">
      <div className="mx-auto flex w-full max-w-6xl items-start justify-between gap-4" data-testid="user-login-top-strip">
        <div className="rounded-xl border border-slate-300 bg-white/95 p-2 shadow-sm" data-testid="user-login-brand-block">
          <img src={resolvedLogoPreview} alt="XILO logo" className="h-auto w-[180px] sm:w-[220px]" data-testid="user-login-brand-logo" />
        </div>
        <div className="flex items-center gap-2" data-testid="user-login-panel-toggle-group">
          <Button type="button" className="h-10 rounded-none bg-black px-4 text-sm text-orange-300 hover:bg-zinc-900" data-testid="user-login-panel-toggle-user-button">Kullanıcı Girişi</Button>
          <Button type="button" variant="outline" className="h-10 rounded-none border-slate-400 bg-white px-4 text-sm text-slate-800 hover:bg-slate-100" onClick={() => navigate("/admin/login")} data-testid="user-login-panel-toggle-admin-button">Admin Girişi</Button>
        </div>
      </div>

      <div className="mx-auto mt-6 w-full max-w-2xl rounded-2xl border border-slate-200 bg-white p-6 shadow-sm sm:p-8" data-testid="user-login-card">
        <header className="text-center" data-testid="user-login-header">
          <h1 className="text-3xl font-black text-slate-900" data-testid="user-login-title">{mode === "register" ? "Hesap Aç" : "Giriş Yap"}</h1>
          <p className="mt-2 text-base text-slate-600" data-testid="user-login-subtitle">Hesabınıza güvenli şekilde erişin.</p>
        </header>

        <form onSubmit={onSubmit} className="mx-auto mt-7 max-w-xl space-y-4" data-testid="user-login-form">
          {mode === "register" && (
            <div className="grid gap-3 sm:grid-cols-2" data-testid="user-login-register-fields-grid">
              <Input type="text" value={form.firstName} onChange={(event) => setForm((prev) => ({ ...prev, firstName: event.target.value }))} placeholder="Ad" data-testid="user-login-first-name-input" required />
              <Input type="text" value={form.lastName} onChange={(event) => setForm((prev) => ({ ...prev, lastName: event.target.value }))} placeholder="Soyad" data-testid="user-login-last-name-input" required />
              <Input type="tel" value={form.phone} onChange={(event) => setForm((prev) => ({ ...prev, phone: event.target.value }))} placeholder="Telefon" className="sm:col-span-2" data-testid="user-login-phone-input" required />
            </div>
          )}

          <div className="space-y-2" data-testid="user-login-email-block">
            <p className="text-sm font-medium text-slate-800" data-testid="user-login-email-label">E-posta</p>
            <div className="relative" data-testid="user-login-email-input-wrapper">
              <Mail className="absolute left-3 top-1/2 h-5 w-5 -translate-y-1/2 text-slate-400" />
              <Input type="email" value={form.email} onChange={(event) => setForm((prev) => ({ ...prev, email: event.target.value }))} className="h-11 border-slate-200 bg-slate-100 pl-11 text-base text-slate-900" data-testid="user-login-email-input" required />
            </div>
          </div>

          <div className="space-y-2" data-testid="user-login-password-block">
            <p className="text-sm font-medium text-slate-800" data-testid="user-login-password-label">Şifre</p>
            <div className="relative" data-testid="user-login-password-input-wrapper">
              <Lock className="absolute left-3 top-1/2 h-5 w-5 -translate-y-1/2 text-slate-400" />
              <Input type={showPassword ? "text" : "password"} value={form.password} onChange={(event) => setForm((prev) => ({ ...prev, password: event.target.value }))} className="h-11 border-slate-200 bg-slate-100 pl-11 pr-11 text-base text-slate-900" data-testid="user-login-password-input" minLength={8} required />
              <button type="button" className="absolute right-3 top-1/2 -translate-y-1/2 text-slate-400" onClick={() => setShowPassword((prev) => !prev)} data-testid="user-login-toggle-password-button">
                {showPassword ? <EyeOff className="h-5 w-5" /> : <Eye className="h-5 w-5" />}
              </button>
            </div>
          </div>

          {mode === "register" && (
            <Input type={showPassword ? "text" : "password"} value={form.confirmPassword} onChange={(event) => setForm((prev) => ({ ...prev, confirmPassword: event.target.value }))} placeholder="Şifre Tekrar" className="h-11 border-slate-200 bg-slate-100" data-testid="user-login-confirm-password-input" minLength={8} required />
          )}

          <div className="flex flex-wrap items-center justify-between gap-3" data-testid="user-login-options-row">
            <label className="inline-flex items-center gap-2 text-sm text-slate-700" data-testid="user-login-remember-label">
              <input type="checkbox" checked={rememberMe} onChange={(event) => setRememberMe(event.target.checked)} className="h-4 w-4 accent-blue-600" data-testid="user-login-remember-checkbox" />
              Oturumum açık kalsın
            </label>
            <button type="button" className="text-sm text-blue-700 underline" onClick={() => navigate(`/forgot-password?panel=user&email=${encodeURIComponent(form.email || "")}`)} data-testid="user-login-forgot-password-link">Şifremi unuttum</button>
          </div>

          <Button className="h-11 w-full bg-orange-500 text-lg font-semibold text-black hover:bg-orange-600" data-testid="user-login-submit-button" disabled={submitting}>
            {submitting ? "İşleniyor..." : mode === "register" ? "Hesap Aç" : "Giriş Yap"}
          </Button>

          <div className="text-center" data-testid="user-login-register-row">
            <span className="text-base text-slate-600" data-testid="user-login-register-text">{mode === "login" ? "Henüz hesabın yok mu?" : "Zaten hesabın var mı?"}</span>{" "}
            <button type="button" onClick={() => setMode((prev) => (prev === "login" ? "register" : "login"))} className="text-base text-blue-700 underline" data-testid="user-login-register-toggle-button">
              {mode === "login" ? "Hesap aç" : "Girişe dön"}
            </button>
          </div>

          {mfaState?.mfaRequired && (
            <div className="space-y-2 rounded border border-slate-300 bg-slate-50 p-3" data-testid="user-login-mfa-panel">
              <p className="text-xs font-semibold uppercase" data-testid="user-login-mfa-title">MFA Doğrulama</p>
              <p className="text-xs text-slate-600" data-testid="user-login-mfa-methods">Yöntemler: {(mfaState.methods || []).join(", ")}</p>
              {(mfaState.methods || []).length > 1 && (
                <select value={mfaMethod} onChange={(event) => setMfaMethod(event.target.value)} className="h-10 w-full rounded border border-slate-300 bg-white px-3 text-sm" data-testid="user-login-mfa-method-select">
                  {(mfaState.methods || []).map((item) => (
                    <option key={item} value={item} data-testid={`user-login-mfa-method-option-${item}`}>{item}</option>
                  ))}
                </select>
              )}
              <Input
                value={mfaCode}
                onChange={(event) => setMfaCode(event.target.value)}
                placeholder={mfaMethod === "email" ? "E-posta OTP kodu" : mfaMethod === "backup_code" ? "Backup code" : "Authenticator kodu"}
                data-testid="user-login-mfa-code-input"
              />
              <Button type="button" onClick={onVerifyMfa} className="w-full bg-black text-orange-300 hover:bg-zinc-900" data-testid="user-login-mfa-verify-button" disabled={submitting}>
                {submitting ? "Doğrulanıyor..." : "MFA Doğrula"}
              </Button>
              {mfaState.emailCodePreview && (
                <p className="text-xs text-slate-700" data-testid="user-login-mfa-email-code-preview">email otp preview: {mfaState.emailCodePreview}</p>
              )}
            </div>
          )}
        </form>
      </div>
    </div>
  );
};