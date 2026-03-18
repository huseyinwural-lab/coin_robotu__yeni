import { Mail } from "lucide-react";
import { useMemo, useState } from "react";
import { useNavigate, useSearchParams } from "react-router-dom";
import { toast } from "sonner";

import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { apiClient } from "@/lib/api";

export const ForgotPasswordPage = () => {
  const navigate = useNavigate();
  const [searchParams] = useSearchParams();
  const panel = (searchParams.get("panel") || "user").toLowerCase() === "admin" ? "admin" : "user";
  const emailPrefill = searchParams.get("email") || "";

  const [email, setEmail] = useState(emailPrefill);
  const [isSubmitting, setIsSubmitting] = useState(false);
  const [submitted, setSubmitted] = useState(false);

  const backPath = useMemo(() => (panel === "admin" ? "/admin/login" : "/user/login"), [panel]);

  const onSubmit = async (event) => {
    event.preventDefault();
    setIsSubmitting(true);
    try {
      const { data } = await apiClient.post("/auth/password-reset/request", { email });
      setSubmitted(true);
      toast.success(data?.message || "Bağlantı gönderildiyse e-posta kutunu kontrol et.");
    } catch (error) {
      toast.error(error?.response?.data?.detail || "İşlem başarısız");
    } finally {
      setIsSubmitting(false);
    }
  };

  return (
    <section className="min-h-screen bg-[#edf0f5] px-4 py-10" data-testid="forgot-password-page">
      <div className="mx-auto w-full max-w-xl rounded-2xl border border-slate-200 bg-white p-6 shadow-sm sm:p-8" data-testid="forgot-password-card">
        <h1 className="text-4xl font-black text-slate-900" data-testid="forgot-password-title">Şifremi unuttum</h1>
        <p className="mt-2 text-sm text-slate-600" data-testid="forgot-password-description">
          E-posta adresini gir. Hesap kayıtlıysa 15 dakika geçerli sıfırlama bağlantısı gönderilir.
        </p>

        <form onSubmit={onSubmit} className="mt-6 space-y-4" data-testid="forgot-password-form">
          <label className="text-sm font-semibold text-slate-700" htmlFor="forgot-password-email" data-testid="forgot-password-email-label">
            E-posta
          </label>
          <div className="relative" data-testid="forgot-password-email-input-wrap">
            <Mail className="absolute left-3 top-1/2 h-5 w-5 -translate-y-1/2 text-slate-400" />
            <Input
              id="forgot-password-email"
              type="email"
              value={email}
              onChange={(event) => setEmail(event.target.value)}
              className="h-11 border-slate-200 bg-slate-100 pl-11"
              required
              data-testid="forgot-password-email-input"
            />
          </div>

          <Button className="h-11 w-full bg-orange-500 text-black hover:bg-orange-600" disabled={isSubmitting} data-testid="forgot-password-submit-button">
            {isSubmitting ? "Gönderiliyor..." : "Sıfırlama bağlantısı gönder"}
          </Button>

          {submitted ? (
            <p className="rounded-md border border-emerald-200 bg-emerald-50 p-3 text-sm text-emerald-700" data-testid="forgot-password-success-message">
              Eğer e-posta kayıtlıysa şifre sıfırlama bağlantısı gönderildi.
            </p>
          ) : null}

          <Button
            type="button"
            variant="outline"
            className="h-11 w-full"
            onClick={() => navigate(backPath)}
            data-testid="forgot-password-back-to-login-button"
          >
            Giriş ekranına dön
          </Button>
        </form>
      </div>
    </section>
  );
};
