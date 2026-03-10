import { useState } from "react";
import { useNavigate } from "react-router-dom";
import { toast } from "sonner";

import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { useAuth } from "@/context/AuthContext";

const authImage = "https://images.unsplash.com/photo-1634549709262-508c47d4c229?crop=entropy&cs=srgb&fm=jpg&ixid=M3w4NjA3MDR8MHwxfHNlYXJjaHwzfHxhYnN0cmFjdCUyMGdlb21ldHJpYyUyMG9yYW5nZSUyMGJsYWNrJTIwZGlnaXRhbHxlbnwwfHx8fDE3NzMxODM1Njh8MA&ixlib=rb-4.1.0&q=85";

export const LoginPage = () => {
  const navigate = useNavigate();
  const { login, register } = useAuth();
  const [mode, setMode] = useState("login");
  const [form, setForm] = useState({ email: "", password: "" });
  const [isSubmitting, setIsSubmitting] = useState(false);

  const onSubmit = async (event) => {
    event.preventDefault();
    setIsSubmitting(true);
    try {
      if (mode === "register") {
        await register(form);
        toast.success("Kayıt başarılı. Şimdi giriş yapabilirsin.");
        setMode("login");
      } else {
        const user = await login(form);
        toast.success("Giriş başarılı");
        navigate(user.role === "admin" ? "/app/admin" : "/app/user");
      }
    } catch (error) {
      toast.error(error?.response?.data?.detail || "İşlem başarısız");
    } finally {
      setIsSubmitting(false);
    }
  };

  return (
    <div className="grid min-h-screen grid-cols-1 bg-slate-950 text-slate-100 lg:grid-cols-2" data-testid="login-page">
      <div className="order-2 flex items-center justify-center p-6 lg:order-1 lg:p-10" data-testid="login-form-panel">
        <form onSubmit={onSubmit} className="w-full max-w-md border border-slate-800 bg-slate-900 p-5" data-testid="login-form">
          <p className="text-xs uppercase tracking-widest text-orange-500" data-testid="auth-mode-chip">Phase 1-b Skeleton</p>
          <h1 className="mt-2 text-4xl font-black uppercase tracking-tight" data-testid="auth-title">
            {mode === "login" ? "Login" : "Register"}
          </h1>
          <p className="mt-2 text-sm text-slate-400" data-testid="auth-description">JWT + role tabanlı erişim bu fazda aktif.</p>

          <div className="mt-5 space-y-3">
            <Input
              placeholder="email"
              type="email"
              value={form.email}
              onChange={(event) => setForm((prev) => ({ ...prev, email: event.target.value }))}
              required
              className="border-slate-700 bg-slate-950"
              data-testid="auth-email-input"
            />
            <Input
              placeholder="password"
              type="password"
              value={form.password}
              onChange={(event) => setForm((prev) => ({ ...prev, password: event.target.value }))}
              required
              minLength={8}
              className="border-slate-700 bg-slate-950"
              data-testid="auth-password-input"
            />
          </div>

          <Button
            type="submit"
            disabled={isSubmitting}
            className="mt-4 w-full bg-orange-500 text-black hover:bg-orange-600"
            data-testid="auth-submit-button"
          >
            {isSubmitting ? "İşleniyor..." : mode === "login" ? "Giriş Yap" : "Kayıt Ol"}
          </Button>

          <Button
            type="button"
            variant="outline"
            onClick={() => setMode((prev) => (prev === "login" ? "register" : "login"))}
            className="mt-2 w-full border-slate-700 bg-transparent text-slate-200 hover:border-orange-500 hover:text-orange-500"
            data-testid="auth-switch-mode-button"
          >
            {mode === "login" ? "Hesabın yok mu? Kayıt ol" : "Hesabın var mı? Giriş yap"}
          </Button>
        </form>
      </div>

      <div className="order-1 border-b border-slate-800 p-2 lg:order-2 lg:border-b-0 lg:border-l" data-testid="login-image-panel">
        <div className="h-full min-h-[280px] overflow-hidden" data-testid="login-image-container">
          <img src={authImage} alt="Geometric Dark Curve" className="h-full w-full object-cover object-center" data-testid="login-image" />
        </div>
      </div>
    </div>
  );
};
