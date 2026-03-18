import { useEffect, useMemo, useState } from "react";
import { useNavigate } from "react-router-dom";
import { toast } from "sonner";

import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { useAuth } from "@/context/AuthContext";
import { apiClient } from "@/lib/api";

const backendBase = process.env.REACT_APP_BACKEND_URL;

export const AdminLoginPage = () => {
  const navigate = useNavigate();
  const { login, verifyMfaChallenge } = useAuth();
  const [form, setForm] = useState({ email: "", password: "" });
  const [submitting, setSubmitting] = useState(false);
  const [logoPreview, setLogoPreview] = useState("/xilo-logo.png");
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
        // silent fallback
      }
    };
    loadBrand();
  }, []);

  const onSubmit = async (event) => {
    event.preventDefault();
    setSubmitting(true);
    try {
      const result = await login({ ...form, panel: "admin" });
      if (result?.mfaRequired) {
        setMfaState(result);
        setMfaMethod((result.methods || ["totp"])[0] || "totp");
        setMfaCode("");
        toast.info("MFA doğrulama kodunu giriniz");
        return;
      }
      toast.success("Admin girişi başarılı");
      navigate("/admin/dashboard");
    } catch (error) {
      toast.error(error?.response?.data?.detail || "Admin girişi başarısız");
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
      navigate("/admin/dashboard");
    } catch (error) {
      toast.error(error?.response?.data?.detail || "MFA doğrulaması başarısız");
    } finally {
      setSubmitting(false);
    }
  };

  return (
    <div className="relative flex min-h-screen items-center justify-center bg-white p-6" data-testid="admin-login-page">
      <div className="absolute left-4 top-4 right-4 flex items-start justify-between gap-4 sm:left-8 sm:top-6 sm:right-8" data-testid="admin-login-top-strip">
        <div className="rounded-xl border border-slate-300 bg-white/95 p-2 shadow-sm" data-testid="admin-login-brand-block">
          <img
            src={resolvedLogoPreview}
            alt="XILO User Trading Engine"
            className="h-auto w-[170px] sm:w-[220px]"
            data-testid="admin-login-brand-logo"
          />
        </div>
        <div className="flex items-center gap-2" data-testid="admin-login-panel-toggle-group">
          <Button
            type="button"
            variant="outline"
            className="h-10 rounded-none border-slate-500 bg-white px-4 text-sm text-slate-800 hover:bg-slate-100"
            onClick={() => navigate("/user/login")}
            data-testid="admin-login-panel-toggle-user-button"
          >
            Kullanıcı Girişi
          </Button>
          <Button
            type="button"
            className="h-10 rounded-none bg-black px-4 text-sm text-orange-300 hover:bg-zinc-900"
            data-testid="admin-login-panel-toggle-admin-button"
          >
            Admin Girişi
          </Button>
        </div>
      </div>

      <form onSubmit={onSubmit} className="mt-24 w-full max-w-md border border-slate-300 bg-white p-6 shadow-sm" data-testid="admin-login-form">
        <p className="text-xs uppercase tracking-widest text-orange-500" data-testid="admin-login-kicker">Admin Panel</p>
        <h1 className="mt-2 text-4xl font-black uppercase tracking-tight text-slate-900" data-testid="admin-login-title">Yönetici Girişi</h1>
        <p className="mt-2 text-sm text-slate-600" data-testid="admin-login-description">Sadece admin hesapları bu panelden giriş yapabilir.</p>

        <div className="mt-5 space-y-3" data-testid="admin-login-fields">
          <Input
            type="email"
            placeholder="admin e-posta"
            value={form.email}
            onChange={(event) => setForm((prev) => ({ ...prev, email: event.target.value }))}
            className="border-slate-300 bg-white"
            data-testid="admin-login-email-input"
            required
          />
          <Input
            type="password"
            placeholder="şifre"
            value={form.password}
            onChange={(event) => setForm((prev) => ({ ...prev, password: event.target.value }))}
            className="border-slate-300 bg-white"
            data-testid="admin-login-password-input"
            required
          />

          <button
            type="button"
            className="text-sm text-orange-600 underline underline-offset-2"
            onClick={() => navigate(`/forgot-password?panel=admin&email=${encodeURIComponent(form.email || "")}`)}
            data-testid="admin-login-forgot-password-link"
          >
            Şifremi unuttum
          </button>
        </div>

        <Button className="mt-5 w-full rounded-none bg-black text-orange-300 hover:bg-zinc-900" data-testid="admin-login-submit-button" disabled={submitting}>
          {submitting ? "İşleniyor..." : "Admin Olarak Giriş Yap"}
        </Button>

        {mfaState?.mfaRequired && (
          <div className="mt-4 space-y-2 rounded border border-slate-300 bg-slate-50 p-3" data-testid="admin-login-mfa-panel">
            <p className="text-xs font-semibold uppercase" data-testid="admin-login-mfa-title">MFA Doğrulama</p>
            <p className="text-xs text-slate-600" data-testid="admin-login-mfa-methods">Yöntemler: {(mfaState.methods || []).join(", ")}</p>
            {(mfaState.methods || []).length > 1 && (
              <select value={mfaMethod} onChange={(event) => setMfaMethod(event.target.value)} className="h-10 w-full border border-slate-300 px-3 text-sm" data-testid="admin-login-mfa-method-select">
                {(mfaState.methods || []).map((item) => (
                  <option key={item} value={item} data-testid={`admin-login-mfa-method-option-${item}`}>{item}</option>
                ))}
              </select>
            )}
            <Input value={mfaCode} onChange={(event) => setMfaCode(event.target.value)} placeholder={mfaMethod === "email" ? "E-posta OTP kodu" : "Authenticator kodu"} data-testid="admin-login-mfa-code-input" />
            <Button type="button" onClick={onVerifyMfa} className="w-full rounded-none bg-black text-orange-300 hover:bg-zinc-900" data-testid="admin-login-mfa-verify-button" disabled={submitting}>
              {submitting ? "Doğrulanıyor..." : "MFA Doğrula"}
            </Button>
            {mfaState.emailCodePreview && (
              <p className="text-xs text-slate-700" data-testid="admin-login-mfa-email-code-preview">email otp preview: {mfaState.emailCodePreview}</p>
            )}
          </div>
        )}
      </form>
    </div>
  );
};