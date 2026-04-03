import { useEffect, useState } from "react";
import { useLocation, useNavigate } from "react-router-dom";
import { toast } from "sonner";

import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { useAuth } from "@/context/AuthContext";
import { apiClient } from "@/lib/api";

export const AdminLoginPage = () => {
  const navigate = useNavigate();
  const location = useLocation();
  const { login, verifyMfaChallenge, user, loading, logout } = useAuth();
  const [form, setForm] = useState({ email: "", password: "" });
  const [submitting, setSubmitting] = useState(false);
  const [mfaState, setMfaState] = useState(null);
  const [mfaCode, setMfaCode] = useState("");
  const [selectedMfaMethod, setSelectedMfaMethod] = useState("totp");

  const mfaMethods = Array.isArray(mfaState?.methods) ? mfaState.methods : [];
  const hasGraceAck = mfaMethods.includes("grace_ack");
  const hasCodeBasedMfa = mfaMethods.includes("totp") || mfaMethods.includes("backup_code") || mfaMethods.includes("email_otp");

  const getErrorMessage = (error, fallback) => {
    const detail = error?.response?.data?.detail;
    if (typeof detail === "string" && detail.trim()) {
      return detail;
    }
    if (detail && typeof detail === "object" && typeof detail?.reason_code === "string") {
      return detail.reason_code;
    }
    return fallback;
  };

  const resolveMfaMethod = (rawCode) => {
    const normalized = String(rawCode || "").trim();
    const backupLike = normalized.includes("-") || /[A-Za-z]/.test(normalized);
    return backupLike ? "backup_code" : "totp";
  };

  useEffect(() => {
    const params = new URLSearchParams(location.search || "");
    const email = params.get("email");
    if (email) {
      setForm((prev) => ({ ...prev, email }));
    }
  }, [location.search]);

  useEffect(() => {
    const storedToken = localStorage.getItem("token");
    if (!storedToken && user) {
      return;
    }

    if (loading || mfaState?.mfaRequired || !user || !storedToken) {
      return;
    }
    const adminRoles = new Set(["super_admin", "admin", "ops"]);
    if (adminRoles.has(user.role)) {
      navigate("/admin/dashboard", { replace: true });
      return;
    }
    setForm((prev) => ({ ...prev, email: user?.email || prev.email }));
  }, [loading, mfaState?.mfaRequired, navigate, user]);

  const onSubmit = async (event) => {
    event.preventDefault();
    if (submitting) {
      return;
    }
    const storedToken = localStorage.getItem("token");
    if (storedToken && user) {
      const adminRoles = new Set(["super_admin", "admin", "ops"]);
      navigate(adminRoles.has(user.role) ? "/admin/dashboard" : "/user/dashboard", { replace: true });
      return;
    }
    setSubmitting(true);
    try {
      const attemptLogin = async () => login({ ...form, panel: "admin" });

      let result;
      try {
        result = await attemptLogin();
      } catch (firstError) {
        const code = String(firstError?.code || "").toUpperCase();
        const message = String(firstError?.message || "").toLowerCase();
        const retryableAbort =
          code === "ERR_CANCELED" ||
          code === "ERR_ABORTED" ||
          message.includes("aborted") ||
          message.includes("canceled") ||
          message.includes("network error");
        if (!retryableAbort) {
          throw firstError;
        }
        await new Promise((resolve) => setTimeout(resolve, 350));
        result = await attemptLogin();
      }

      if (result?.mfaRequired) {
        setMfaState(result);
        setMfaCode("");
        setSelectedMfaMethod((result?.methods || [])[0] || "totp");
        const reasons = Array.isArray(result?.riskReasons) ? result.riskReasons.join(", ") : "";
        toast.info(`MFA doğrulama adımı gerekli${reasons ? ` (${reasons})` : ""}`);
        return;
      }
      toast.success("Admin girişi başarılı");
      navigate("/admin/dashboard", { replace: true });
    } catch (error) {
      toast.error(getErrorMessage(error, "Admin girişi başarısız"));
    } finally {
      setSubmitting(false);
    }
  };

  const onVerifyMfa = async (overrideMethod = null, overrideCode = null) => {
    if (!mfaState?.challengeToken || submitting) {
      return;
    }
    setSubmitting(true);
    try {
      const finalCode = overrideCode ?? mfaCode;
      const finalMethod = overrideMethod ?? selectedMfaMethod ?? resolveMfaMethod(finalCode);
      await verifyMfaChallenge({
        challengeToken: mfaState.challengeToken,
        method: finalMethod,
        code: finalCode,
      });
      if (finalMethod === "grace_ack") {
        toast.success("Grace period ile giriş tamamlandı");
      } else {
        toast.success("MFA doğrulandı");
      }
      navigate("/admin/dashboard", { replace: true });
    } catch (error) {
      toast.error(getErrorMessage(error, "MFA doğrulaması başarısız"));
    } finally {
      setSubmitting(false);
    }
  };

  const onResendEmailOtp = async () => {
    if (!mfaState?.challengeToken || submitting) return;
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

        <Button type="submit" className="mt-5 w-full rounded-none bg-black text-orange-300 hover:bg-zinc-900" data-testid="admin-login-submit-button" disabled={submitting}>
          {submitting ? "İşleniyor..." : "Admin Olarak Giriş Yap"}
        </Button>

        {mfaState?.mfaRequired && (
          <div className="mt-4 space-y-2 rounded border border-slate-300 bg-slate-50 p-3" data-testid="admin-login-mfa-panel">
            <p className="text-xs font-semibold uppercase" data-testid="admin-login-mfa-title">MFA Doğrulama</p>
            <p className="text-xs text-slate-600" data-testid="admin-login-mfa-methods">
              Yöntemler: {mfaMethods.length ? mfaMethods.join(", ") : "totp"}
            </p>
            {!!mfaState?.riskReasons?.length && (
              <p className="text-xs text-rose-700" data-testid="admin-login-risk-reasons">
                risk_reasons: {mfaState.riskReasons.join(", ")}
              </p>
            )}
            {!!mfaState?.challengeReason && (
              <p className="text-xs text-slate-600" data-testid="admin-login-challenge-reason">
                challenge_reason: {mfaState.challengeReason}
              </p>
            )}
            {mfaState?.emailDeliveryStatus && (
              <p className="text-xs text-slate-600" data-testid="admin-login-mfa-email-delivery-status">
                email_delivery_status: {mfaState.emailDeliveryStatus}
              </p>
            )}
            {mfaState?.graceActive && (
              <p className="text-xs text-amber-700" data-testid="admin-login-mfa-grace-note">
                MFA kurulum grace period aktif. Son tarih: {mfaState?.graceExpiresAt ? new Date(mfaState.graceExpiresAt).toLocaleString() : "yakında"}
              </p>
            )}
            {hasCodeBasedMfa && (
              <>
                <label className="text-xs text-slate-600" data-testid="admin-login-mfa-method-select-wrapper">
                  Doğrulama yöntemi
                  <select
                    className="mt-1 w-full border border-slate-300 bg-white px-2 py-1 text-xs"
                    value={selectedMfaMethod}
                    onChange={(event) => setSelectedMfaMethod(event.target.value)}
                    data-testid="admin-login-mfa-method-select"
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
                  data-testid="admin-login-mfa-code-input"
                />
                <Button type="button" onClick={() => onVerifyMfa()} className="w-full rounded-none bg-black text-orange-300 hover:bg-zinc-900" data-testid="admin-login-mfa-verify-button" disabled={submitting}>
                  {submitting ? "Doğrulanıyor..." : "MFA Doğrula"}
                </Button>
                {mfaMethods.includes("email_otp") && (
                  <Button
                    type="button"
                    variant="outline"
                    className="w-full rounded-none"
                    onClick={onResendEmailOtp}
                    data-testid="admin-login-mfa-resend-email-otp-button"
                    disabled={submitting}
                  >
                    Email OTP Yeniden Gönder
                  </Button>
                )}
              </>
            )}
            {hasGraceAck && (
              <Button
                type="button"
                variant="outline"
                className="w-full rounded-none border-amber-400 text-amber-700 hover:bg-amber-50"
                onClick={() => onVerifyMfa("grace_ack", "grace_ack")}
                data-testid="admin-login-mfa-grace-continue-button"
                disabled={submitting}
              >
                {submitting ? "İşleniyor..." : "Grace ile Devam Et"}
              </Button>
            )}
          </div>
        )}
      </form>
    </div>
  );
};