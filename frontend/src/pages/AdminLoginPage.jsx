import { useState } from "react";
import { useNavigate } from "react-router-dom";
import { toast } from "sonner";

import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { useAuth } from "@/context/AuthContext";

export const AdminLoginPage = () => {
  const navigate = useNavigate();
  const { login } = useAuth();
  const [form, setForm] = useState({ email: "", password: "" });
  const [submitting, setSubmitting] = useState(false);

  const onSubmit = async (event) => {
    event.preventDefault();
    setSubmitting(true);
    try {
      await login({ ...form, panel: "admin" });
      toast.success("Admin girişi başarılı");
      navigate("/admin/dashboard");
    } catch (error) {
      toast.error(error?.response?.data?.detail || "Admin girişi başarısız");
    } finally {
      setSubmitting(false);
    }
  };

  return (
    <div className="relative flex min-h-screen items-center justify-center bg-slate-950 p-6" data-testid="admin-login-page">
      <div className="absolute left-4 top-4 right-4 flex items-start justify-between gap-4 sm:left-8 sm:top-6 sm:right-8" data-testid="admin-login-top-strip">
        <div className="rounded-xl border border-slate-300 bg-white/95 p-2 shadow-sm" data-testid="admin-login-brand-block">
          <img
            src="/xilo-logo.png"
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

      <form onSubmit={onSubmit} className="mt-24 w-full max-w-md border border-orange-500/40 bg-slate-900 p-6" data-testid="admin-login-form">
        <p className="text-xs uppercase tracking-widest text-orange-400" data-testid="admin-login-kicker">Admin Panel</p>
        <h1 className="mt-2 text-4xl font-black uppercase tracking-tight text-orange-300" data-testid="admin-login-title">Yönetici Girişi</h1>
        <p className="mt-2 text-sm text-slate-300" data-testid="admin-login-description">Sadece admin hesapları bu panelden giriş yapabilir.</p>

        <div className="mt-5 space-y-3" data-testid="admin-login-fields">
          <Input
            type="email"
            placeholder="admin e-posta"
            value={form.email}
            onChange={(event) => setForm((prev) => ({ ...prev, email: event.target.value }))}
            className="border-slate-700 bg-slate-950"
            data-testid="admin-login-email-input"
            required
          />
          <Input
            type="password"
            placeholder="şifre"
            value={form.password}
            onChange={(event) => setForm((prev) => ({ ...prev, password: event.target.value }))}
            className="border-slate-700 bg-slate-950"
            data-testid="admin-login-password-input"
            required
          />

          <button
            type="button"
            className="text-sm text-orange-300 underline underline-offset-2"
            onClick={() => navigate(`/forgot-password?panel=admin&email=${encodeURIComponent(form.email || "")}`)}
            data-testid="admin-login-forgot-password-link"
          >
            Şifremi unuttum
          </button>
        </div>

        <Button className="mt-5 w-full bg-orange-500 text-black hover:bg-orange-600" data-testid="admin-login-submit-button" disabled={submitting}>
          {submitting ? "İşleniyor..." : "Admin Olarak Giriş Yap"}
        </Button>
      </form>
    </div>
  );
};