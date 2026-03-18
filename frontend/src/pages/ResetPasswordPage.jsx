import { Lock } from "lucide-react";
import { useState } from "react";
import { useNavigate, useSearchParams } from "react-router-dom";
import { toast } from "sonner";

import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { apiClient } from "@/lib/api";

export const ResetPasswordPage = () => {
  const navigate = useNavigate();
  const [searchParams] = useSearchParams();
  const token = searchParams.get("token") || "";

  const [newPassword, setNewPassword] = useState("");
  const [confirmPassword, setConfirmPassword] = useState("");
  const [isSubmitting, setIsSubmitting] = useState(false);
  const [isDone, setIsDone] = useState(false);

  const onSubmit = async (event) => {
    event.preventDefault();
    if (!token) {
      toast.error("Sıfırlama bağlantısı geçersiz");
      return;
    }
    if (newPassword !== confirmPassword) {
      toast.error("Şifreler eşleşmiyor");
      return;
    }

    setIsSubmitting(true);
    try {
      const { data } = await apiClient.post("/auth/password-reset/confirm", {
        token,
        new_password: newPassword,
      });
      setIsDone(true);
      toast.success(data?.message || "Şifre güncellendi");
    } catch (error) {
      toast.error(error?.response?.data?.detail || "Sıfırlama başarısız");
    } finally {
      setIsSubmitting(false);
    }
  };

  return (
    <section className="min-h-screen bg-[#edf0f5] px-4 py-10" data-testid="reset-password-page">
      <div className="mx-auto w-full max-w-xl rounded-2xl border border-slate-200 bg-white p-6 shadow-sm sm:p-8" data-testid="reset-password-card">
        <h1 className="text-4xl font-black text-slate-900" data-testid="reset-password-title">Yeni şifre belirle</h1>
        <p className="mt-2 text-sm text-slate-600" data-testid="reset-password-description">
          Şifre en az 10 karakter olmalı ve büyük/küçük harf, rakam, sembol içermelidir.
        </p>

        {!token ? (
          <div className="mt-5 rounded-md border border-rose-200 bg-rose-50 p-3 text-sm text-rose-700" data-testid="reset-password-invalid-token-message">
            Sıfırlama bağlantısı eksik veya geçersiz.
          </div>
        ) : null}

        <form onSubmit={onSubmit} className="mt-6 space-y-4" data-testid="reset-password-form">
          <label className="text-sm font-semibold text-slate-700" htmlFor="reset-password-new" data-testid="reset-password-new-label">
            Yeni şifre
          </label>
          <div className="relative" data-testid="reset-password-new-input-wrap">
            <Lock className="absolute left-3 top-1/2 h-5 w-5 -translate-y-1/2 text-slate-400" />
            <Input
              id="reset-password-new"
              type="password"
              value={newPassword}
              onChange={(event) => setNewPassword(event.target.value)}
              minLength={10}
              className="h-11 border-slate-200 bg-slate-100 pl-11"
              required
              data-testid="reset-password-new-input"
            />
          </div>

          <label className="text-sm font-semibold text-slate-700" htmlFor="reset-password-confirm" data-testid="reset-password-confirm-label">
            Yeni şifre (tekrar)
          </label>
          <div className="relative" data-testid="reset-password-confirm-input-wrap">
            <Lock className="absolute left-3 top-1/2 h-5 w-5 -translate-y-1/2 text-slate-400" />
            <Input
              id="reset-password-confirm"
              type="password"
              value={confirmPassword}
              onChange={(event) => setConfirmPassword(event.target.value)}
              minLength={10}
              className="h-11 border-slate-200 bg-slate-100 pl-11"
              required
              data-testid="reset-password-confirm-input"
            />
          </div>

          <Button className="h-11 w-full bg-orange-500 text-black hover:bg-orange-600" disabled={isSubmitting || !token || isDone} data-testid="reset-password-submit-button">
            {isSubmitting ? "Kaydediliyor..." : isDone ? "Şifre güncellendi" : "Şifreyi güncelle"}
          </Button>

          <Button
            type="button"
            variant="outline"
            className="h-11 w-full"
            onClick={() => navigate("/user/login")}
            data-testid="reset-password-back-login-button"
          >
            Giriş ekranına dön
          </Button>
        </form>
      </div>
    </section>
  );
};
