import { Eye, EyeOff, Lock, Mail } from "lucide-react";
import { useEffect, useState } from "react";
import { useNavigate } from "react-router-dom";
import { toast } from "sonner";

import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { useAuth } from "@/context/AuthContext";
import { apiClient } from "@/lib/api";

export const UserLoginPage = () => {
  const navigate = useNavigate();
  const { login, verifyMfaChallenge, register, user, loading } = useAuth();
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
  const [submitting, setSubmitting] = useState(false);
  const [mfaState, setMfaState] = useState(null);
  const [mfaCode, setMfaCode] = useState("");
  const [selectedMfaMethod, setSelectedMfaMethod] = useState("totp");
  const [panelHint, setPanelHint] = useState("");
  const mfaMethods = Array.isArray(mfaState?.methods) ? mfaState.methods : [];

  const getErrorMessage = (error, fallback) => {
    const code = String(error?.code || "").toUpperCase();
    const rawMessage = String(error?.message || "").toLowerCase();
    if (code === "LOGIN_TIMEOUT" || rawMessage.includes("login_timeout") || rawMessage.includes("timeout")) {
      return "Sunucu yanıtı gecikti. Lütfen tekrar deneyin.";
    }
    const detail = error?.response?.data?.detail;
    if (typeof detail === "string" && detail.trim()) {
      return detail;
    }
    if (detail && typeof detail === "object" && typeof detail?.reason_code === "string") {
      return detail.reason_code;
    }
    return error?.message || fallback;
  };

  const resolveMfaMethod = (rawCode) => {
    const normalized = String(rawCode || "").trim();
    const backupLike = normalized.includes("-") || /[A-Za-z]/.test(normalized);
    return backupLike ? "backup_code" : "totp";
  };

  useEffect(() => {
    const storedToken = localStorage.getItem("token");
    if (!storedToken && user) {
      return;
    }
    if (loading || mfaState?.mfaRequired || !user || !storedToken) {
      return;
    }
    const adminRoles = new Set(["super_admin", "admin", "ops"]);
    const normalizedRole = String(user.role || "").toLowerCase();
    if (adminRoles.has(normalizedRole)) {
      setPanelHint("admin");
      return;
    }
    navigate("/user/dashboard", { replace: true });
  }, [loading, mfaState?.mfaRequired, navigate, user]);

  const onSubmit = async (event) => {
    event.preventDefault();
    if (submitting) {
      return;
    }
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
        setPanelHint("");
        const loginResult = await login({ email: form.email, password: form.password, panel: "user" });
        if (loginResult?.mfaRequired) {
          setMfaState(loginResult);
          setMfaCode("");
          setSelectedMfaMethod((loginResult?.methods || [])[0] || "totp");
          const reasons = Array.isArray(loginResult?.riskReasons) ? loginResult.riskReasons.join(", ") : "";
          toast.info(`MFA doğrulama adımı gerekli${reasons ? ` (${reasons})` : ""}`);
          return;
        }
        const normalizedRole = String(loginResult?.user?.role || "").toLowerCase();
        const adminRoles = new Set(["super_admin", "admin", "ops"]);
        const nextPath = adminRoles.has(normalizedRole) ? "/admin/dashboard" : "/user/dashboard";
        toast.success(`Giriş başarılı${rememberMe ? "" : " (oturum cihazda saklanmayacak)"}`);
        navigate(nextPath, { replace: true });
      }
    } catch (error) {
      const message = getErrorMessage(error, "İşlem başarısız");
      if (String(message || "").toLowerCase().includes("yanlış giriş paneli")) {
        setPanelHint("admin");
        toast.error("Bu hesap admin paneline ait. /admin/login ekranına yönlendiriliyorsunuz.");
        setTimeout(() => {
          navigate(`/admin/login?email=${encodeURIComponent(form.email || "")}`);
        }, 900);
      } else {
        toast.error(message);
      }
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
        method: selectedMfaMethod || resolveMfaMethod(mfaCode),
        code: mfaCode,
      });
      toast.success("MFA doğrulandı");
      navigate("/user/dashboard");
    } catch (error) {
      toast.error(getErrorMessage(error, "MFA doğrulaması başarısız"));
    } finally {
      setSubmitting(false);
    }
  };

  const onResendEmailOtp = async () => {
    if (!mfaState?.challengeToken) return;
    setSubmitting(true);
    try {
      const { data } = await apiClient.post("/mfa/challenge/resend", { challenge_token: mfaState.challengeToken });
      setMfaState((prev) => ({
        ...(prev || {}),
        emailDeliveryStatus: data?.email_delivery_status || prev?.emailDeliveryStatus,
        expiresAt: data?.mfa_expires_at || prev?.expiresAt,
      }));
      toast.success("Email OTP yeniden gönderildi");
    } catch (error) {
      toast.error(getErrorMessage(error, "Email OTP yeniden gönderilemedi"));
    } finally {
      setSubmitting(false);
    }
  };

  return (
    <div className="min-h-screen bg-[#edf0f5] px-4 py-8" data-testid="user-login-page">
      <div className="mx-auto mt-6 w-full max-w-2xl rounded-2xl border border-slate-200 bg-white p-6 shadow-sm sm:p-8" data-testid="user-login-card">
        <header className="text-center" data-testid="user-login-header">
          <h1 className="text-3xl font-black text-slate-900" data-testid="user-login-title">{mode === "register" ? "Hesap Aç" : "Giriş Yap"}</h1>
          <p className="mt-2 text-base text-slate-600" data-testid="user-login-subtitle">Hesabınıza güvenli şekilde erişin.</p>
          <button
            type="button"
            className="mt-3 text-sm font-semibold text-blue-700 underline"
            onClick={() => navigate(`/admin/login?email=${encodeURIComponent(form.email || "")}`)}
            data-testid="user-login-admin-shortcut-button"
          >
            Yönetici paneline geç → /admin/login
          </button>
        </header>

        {panelHint === "admin" && (
          <div className="mt-4 rounded-md border border-amber-300 bg-amber-50 p-3 text-sm text-amber-800" data-testid="user-login-wrong-panel-cta">
            Bu hesap admin paneline ait. Doğru giriş yolu: <span className="font-semibold">/admin/login</span>
            <div className="mt-2">
              <button
                type="button"
                className="font-semibold underline"
                onClick={() => navigate(`/admin/login?email=${encodeURIComponent(form.email || "")}`)}
                data-testid="user-login-wrong-panel-go-admin-button"
              >
                Admin paneline git
              </button>
            </div>
          </div>
        )}

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
              <p className="text-xs text-slate-600" data-testid="user-login-mfa-methods">
                Yöntemler: {mfaMethods.length ? mfaMethods.join(", ") : "totp"}
              </p>
              {!!mfaState?.riskReasons?.length && (
                <p className="text-xs text-rose-700" data-testid="user-login-risk-reasons">
                  risk_reasons: {mfaState.riskReasons.join(", ")}
                </p>
              )}
              {!!mfaState?.challengeReason && (
                <p className="text-xs text-slate-600" data-testid="user-login-challenge-reason">
                  challenge_reason: {mfaState.challengeReason}
                </p>
              )}
              {mfaState?.emailDeliveryStatus && (
                <p className="text-xs text-slate-600" data-testid="user-login-mfa-email-delivery-status">
                  email_delivery_status: {mfaState.emailDeliveryStatus}
                </p>
              )}
              <label className="text-xs text-slate-600" data-testid="user-login-mfa-method-select-wrapper">
                Doğrulama yöntemi
                <select
                  className="mt-1 w-full border border-slate-300 bg-white px-2 py-1 text-xs"
                  value={selectedMfaMethod}
                  onChange={(event) => setSelectedMfaMethod(event.target.value)}
                  data-testid="user-login-mfa-method-select"
                >
                  {mfaMethods.map((method) => (
                    <option key={method} value={method}>
                      {method}
                    </option>
                  ))}
                </select>
              </label>
              <Input
                value={mfaCode}
                onChange={(event) => setMfaCode(event.target.value)}
                placeholder={selectedMfaMethod === "email_otp" ? "E-posta OTP kodu" : "Authenticator kodu veya backup code"}
                data-testid="user-login-mfa-code-input"
              />
              <Button type="button" onClick={onVerifyMfa} className="w-full bg-black text-orange-300 hover:bg-zinc-900" data-testid="user-login-mfa-verify-button" disabled={submitting}>
                {submitting ? "Doğrulanıyor..." : "MFA Doğrula"}
              </Button>
              {mfaMethods.includes("email_otp") && (
                <Button
                  type="button"
                  variant="outline"
                  className="w-full rounded-none"
                  onClick={onResendEmailOtp}
                  data-testid="user-login-mfa-resend-email-otp-button"
                  disabled={submitting}
                >
                  Email OTP Yeniden Gönder
                </Button>
              )}
            </div>
          )}
        </form>
      </div>
    </div>
  );
};