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
    <div className="flex min-h-screen items-center justify-center bg-slate-950 p-6" data-testid="admin-login-page">
      <form onSubmit={onSubmit} className="w-full max-w-md border border-orange-500/40 bg-slate-900 p-6" data-testid="admin-login-form">
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