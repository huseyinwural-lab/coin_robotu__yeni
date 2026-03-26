import { useEffect, useState } from "react";
import { useNavigate } from "react-router-dom";
import { toast } from "sonner";

import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { useAuth } from "@/context/AuthContext";

export const AdminLoginPage = () => {
  const navigate = useNavigate();
  const { login, verifyMfaChallenge, user, loading } = useAuth();
  const [form, setForm] = useState({ email: "", password: "" });
  const [submitting, setSubmitting] = useState(false);
  const [mfaState, setMfaState] = useState(null);
  const [mfaCode, setMfaCode] = useState("");

  const resolveMfaMethod = (rawCode) => {
    const normalized = String(rawCode || "").trim();
    const backupLike = normalized.includes("-") || /[A-Za-z]/.test(normalized);
    return backupLike ? "backup_code" : "totp";
  };

  useEffect(() => {
    if (loading || !user) {
      return;
    }
    const adminRoles = new Set(["super_admin", "admin", "ops"]);
    if (adminRoles.has(user.role)) {
      navigate("/admin/dashboard", { replace: true });
    }
  }, [loading, navigate, user]);

  const onSubmit = async (event) => {
    event.preventDefault();
    setSubmitting(true);
    try {
      const result = await login({ ...form, panel: "admin" });
      if (result?.mfaRequired) {
        setMfaState(result);
        setMfaCode("");
        toast.info("MFA doğrulama kodunu giriniz");
        return;
      }
      toast.success("Admin girişi başarılı");
      navigate("/admin/dashboard", { replace: true });
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
        method: resolveMfaMethod(mfaCode),
        code: mfaCode,
      });
      toast.success("MFA doğrulandı");
      navigate("/admin/dashboard", { replace: true });
    } catch (error) {
      toast.error(error?.response?.data?.detail || "MFA doğrulaması başarısız");
    } finally {
      setSubmitting(false);
    }
  };

  return (
    <div className="relative flex min-h-screen items-center justify-center bg-white p-6" data-testid="admin-login-page">
      <div className="absolute left-4 top-4 right-4 flex items-start justify-between gap-4 sm:left-8 sm:top-6 sm:right-8" data-testid="admin-login-top-strip">
        <div className="rounded-xl border border-slate-300 bg-white/95 px-3 py-2 shadow-sm" data-testid="admin-login-brand-block">
          <p className="text-xs font-semibold uppercase tracking-widest text-slate-700" data-testid="admin-login-brand-text">Admin Panel</p>
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
            <p className="text-xs text-slate-600" data-testid="admin-login-mfa-methods">Yöntem: Authenticator (TOTP) + Backup Code</p>
            <Input
              value={mfaCode}
              onChange={(event) => setMfaCode(event.target.value)}
              placeholder="Authenticator kodu veya backup code"
              data-testid="admin-login-mfa-code-input"
            />
            <Button type="button" onClick={onVerifyMfa} className="w-full rounded-none bg-black text-orange-300 hover:bg-zinc-900" data-testid="admin-login-mfa-verify-button" disabled={submitting}>
              {submitting ? "Doğrulanıyor..." : "MFA Doğrula"}
            </Button>
          </div>
        )}
      </form>
    </div>
  );
};