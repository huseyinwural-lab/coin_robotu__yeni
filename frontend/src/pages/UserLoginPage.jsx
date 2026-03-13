import { Eye, EyeOff, Lock, Mail } from "lucide-react";
import { useState } from "react";
import { useNavigate } from "react-router-dom";
import { toast } from "sonner";

import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { useAuth } from "@/context/AuthContext";

export const UserLoginPage = () => {
  const navigate = useNavigate();
  const { login, register } = useAuth();
  const [mode, setMode] = useState("login");
  const [showPassword, setShowPassword] = useState(false);
  const [rememberMe, setRememberMe] = useState(true);
  const [form, setForm] = useState({ email: "", password: "" });
  const [submitting, setSubmitting] = useState(false);

  const onSubmit = async (event) => {
    event.preventDefault();
    setSubmitting(true);
    try {
      if (mode === "register") {
        await register(form);
        toast.success("Talebiniz alındı. Admin onayı sonrası giriş yapabilirsiniz.");
        setMode("login");
      } else {
        await login({ ...form, panel: "user" });
        toast.success(`Giriş başarılı${rememberMe ? " (oturum korunacak)" : ""}`);
        navigate("/user/dashboard");
      }
    } catch (error) {
      toast.error(error?.response?.data?.detail || "İşlem başarısız");
    } finally {
      setSubmitting(false);
    }
  };

  return (
    <div className="min-h-screen bg-[#edf0f5] px-4 py-8" data-testid="user-login-page">
      <div className="mx-auto w-full max-w-2xl rounded-2xl border border-slate-200 bg-white p-6 shadow-sm sm:p-8" data-testid="user-login-card">
        <header className="text-center" data-testid="user-login-header">
          <h1 className="text-3xl font-black text-slate-900" data-testid="user-login-title">Giriş yap</h1>
          <p className="mt-2 text-base text-slate-600" data-testid="user-login-subtitle">Hesabınıza giriş yapın.</p>
        </header>

        <form onSubmit={onSubmit} className="mx-auto mt-7 max-w-xl space-y-4" data-testid="user-login-form">
          <div className="space-y-2" data-testid="user-login-type-block">
            <p className="text-base font-semibold text-slate-800" data-testid="user-login-type-label">Giriş türü</p>
            <label className="inline-flex items-center gap-2 text-base font-medium text-slate-800" data-testid="user-login-type-individual-label">
              <input type="radio" name="login-type" checked readOnly className="h-5 w-5 accent-blue-600" data-testid="user-login-type-individual-radio" />
              Bireysel
            </label>
          </div>

          <div className="space-y-2" data-testid="user-login-email-block">
            <p className="text-base font-medium text-slate-800" data-testid="user-login-email-label">E-posta</p>
            <div className="relative" data-testid="user-login-email-input-wrapper">
              <Mail className="absolute left-3 top-1/2 h-5 w-5 -translate-y-1/2 text-slate-400" />
              <Input
                type="email"
                value={form.email}
                onChange={(event) => setForm((prev) => ({ ...prev, email: event.target.value }))}
                className="h-11 border-slate-200 bg-slate-100 pl-11 text-base text-slate-900"
                data-testid="user-login-email-input"
                required
              />
            </div>
          </div>

          <div className="space-y-2" data-testid="user-login-password-block">
            <p className="text-base font-medium text-slate-800" data-testid="user-login-password-label">Şifre</p>
            <div className="relative" data-testid="user-login-password-input-wrapper">
              <Lock className="absolute left-3 top-1/2 h-5 w-5 -translate-y-1/2 text-slate-400" />
              <Input
                type={showPassword ? "text" : "password"}
                value={form.password}
                onChange={(event) => setForm((prev) => ({ ...prev, password: event.target.value }))}
                className="h-11 border-slate-200 bg-slate-100 pl-11 pr-11 text-base text-slate-900"
                data-testid="user-login-password-input"
                minLength={8}
                required
              />
              <button
                type="button"
                className="absolute right-3 top-1/2 -translate-y-1/2 text-slate-400"
                onClick={() => setShowPassword((prev) => !prev)}
                data-testid="user-login-toggle-password-button"
              >
                {showPassword ? <EyeOff className="h-5 w-5" /> : <Eye className="h-5 w-5" />}
              </button>
            </div>
          </div>

          <div className="flex flex-wrap items-center justify-between gap-3" data-testid="user-login-options-row">
            <label className="inline-flex items-center gap-2 text-base text-slate-700" data-testid="user-login-remember-label">
              <input
                type="checkbox"
                checked={rememberMe}
                onChange={(event) => setRememberMe(event.target.checked)}
                className="h-4 w-4 accent-blue-600"
                data-testid="user-login-remember-checkbox"
              />
              Oturumum açık kalsın
            </label>
            <button type="button" className="text-base text-blue-700 underline" data-testid="user-login-forgot-password-link">
              Şifremi unuttum
            </button>
          </div>

          <Button className="h-11 w-full bg-orange-500 text-lg font-semibold text-black hover:bg-orange-600" data-testid="user-login-submit-button" disabled={submitting}>
            {submitting ? "İşleniyor..." : mode === "register" ? "Talep Oluştur" : "E-posta ile giriş yap"}
          </Button>

          <div className="text-center" data-testid="user-login-register-row">
            <span className="text-base text-slate-600" data-testid="user-login-register-text">Henüz hesabın yok mu?</span>{" "}
            <button
              type="button"
              onClick={() => setMode((prev) => (prev === "login" ? "register" : "login"))}
              className="text-base text-blue-700 underline"
              data-testid="user-login-register-toggle-button"
            >
              {mode === "login" ? "Hesap aç" : "Girişe dön"}
            </button>
          </div>
          <p className="text-center text-xs text-slate-500" data-testid="user-login-mode-label">{mode === "register" ? "Kayıt talebi admin onayına gider." : "VEYA"}</p>
        </form>
      </div>
    </div>
  );
};