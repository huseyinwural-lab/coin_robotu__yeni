import { useEffect, useMemo, useState } from "react";
import { toast } from "sonner";

import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { useAuth } from "@/context/AuthContext";
import { apiClient } from "@/lib/api";

export const MfaSettingsPage = () => {
  const { user } = useAuth();
  const [loading, setLoading] = useState(true);
  const [saving, setSaving] = useState(false);
  const [verifying, setVerifying] = useState(false);
  const [settings, setSettings] = useState({
    is_enabled: false,
    enabled_methods: [],
    totp_configured: false,
    totp_verified: false,
    email_otp_verified: false,
  });
  const [totpSetup, setTotpSetup] = useState(null);
  const [totpCode, setTotpCode] = useState("");

  const roleLabel = useMemo(() => (user?.role === "user" ? "User" : "Admin"), [user?.role]);

  const refresh = async () => {
    setLoading(true);
    try {
      const { data } = await apiClient.get("/auth/mfa/settings");
      setSettings(data);
    } catch {
      toast.error("MFA ayarları alınamadı");
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    refresh();
  }, []);

  const toggleMethod = (method) => {
    setSettings((prev) => {
      const methods = new Set(prev.enabled_methods || []);
      if (methods.has(method)) {
        methods.delete(method);
      } else {
        methods.add(method);
      }
      return { ...prev, enabled_methods: Array.from(methods) };
    });
  };

  const saveSettings = async () => {
    setSaving(true);
    try {
      const payload = {
        is_enabled: Boolean(settings.is_enabled),
        enabled_methods: settings.enabled_methods || [],
      };
      const { data } = await apiClient.put("/auth/mfa/settings", payload);
      setSettings(data);
      toast.success("MFA ayarları kaydedildi");
    } catch (error) {
      toast.error(error?.response?.data?.detail || "MFA kaydı başarısız");
    } finally {
      setSaving(false);
    }
  };

  const generateTotpSetup = async () => {
    try {
      const { data } = await apiClient.post("/auth/mfa/totp/setup");
      setTotpSetup(data);
      toast.success("TOTP secret üretildi");
    } catch (error) {
      toast.error(error?.response?.data?.detail || "TOTP setup başlatılamadı");
    }
  };

  const verifyTotp = async () => {
    setVerifying(true);
    try {
      const { data } = await apiClient.post("/auth/mfa/totp/verify-setup", { code: totpCode });
      setSettings(data);
      setTotpCode("");
      toast.success("TOTP doğrulandı");
    } catch (error) {
      toast.error(error?.response?.data?.detail || "TOTP kodu doğrulanamadı");
    } finally {
      setVerifying(false);
    }
  };

  if (loading) {
    return (
      <section className="border border-slate-800 bg-slate-900 p-4" data-testid="mfa-settings-loading">
        <p className="text-sm text-slate-300" data-testid="mfa-settings-loading-text">MFA ayarları yükleniyor...</p>
      </section>
    );
  }

  return (
    <section className="space-y-4" data-testid="mfa-settings-page">
      <header className="border border-slate-800 bg-slate-900 p-4" data-testid="mfa-settings-header">
        <h2 className="text-4xl font-black uppercase tracking-tight" data-testid="mfa-settings-title">{roleLabel} MFA Settings</h2>
        <p className="mt-2 text-sm text-slate-400" data-testid="mfa-settings-description">Giriş sonrası opsiyonel ikinci doğrulama katmanı.</p>
      </header>

      <section className="space-y-3 border border-slate-800 bg-slate-900 p-4" data-testid="mfa-settings-main-card">
        <label className="inline-flex items-center gap-2 text-sm" data-testid="mfa-settings-enable-wrapper">
          <input
            type="checkbox"
            checked={Boolean(settings.is_enabled)}
            onChange={(event) => setSettings((prev) => ({ ...prev, is_enabled: event.target.checked }))}
            data-testid="mfa-settings-enable-checkbox"
          />
          MFA aktif
        </label>

        <div className="grid gap-2 sm:grid-cols-2" data-testid="mfa-settings-method-grid">
          <label className="inline-flex items-center gap-2 text-sm" data-testid="mfa-settings-method-email-wrapper">
            <input
              type="checkbox"
              checked={(settings.enabled_methods || []).includes("email")}
              onChange={() => toggleMethod("email")}
              data-testid="mfa-settings-method-email-checkbox"
            />
            E-posta OTP
          </label>
          <label className="inline-flex items-center gap-2 text-sm" data-testid="mfa-settings-method-totp-wrapper">
            <input
              type="checkbox"
              checked={(settings.enabled_methods || []).includes("totp")}
              onChange={() => toggleMethod("totp")}
              data-testid="mfa-settings-method-totp-checkbox"
            />
            Authenticator (TOTP)
          </label>
        </div>

        <div className="flex flex-wrap gap-2" data-testid="mfa-settings-actions-row">
          <Button type="button" variant="outline" onClick={generateTotpSetup} data-testid="mfa-settings-generate-totp-button">TOTP Secret Üret</Button>
          <Button type="button" onClick={saveSettings} disabled={saving} data-testid="mfa-settings-save-button">{saving ? "Kaydediliyor..." : "Ayarları Kaydet"}</Button>
        </div>

        <div className="rounded border border-slate-700 bg-slate-950 p-3" data-testid="mfa-settings-status-card">
          <p className="text-xs text-slate-400" data-testid="mfa-settings-status-enabled">enabled: {String(Boolean(settings.is_enabled))}</p>
          <p className="text-xs text-slate-400" data-testid="mfa-settings-status-methods">methods: {(settings.enabled_methods || []).join(",") || "-"}</p>
          <p className="text-xs text-slate-400" data-testid="mfa-settings-status-totp-configured">totp_configured: {String(Boolean(settings.totp_configured))}</p>
          <p className="text-xs text-slate-400" data-testid="mfa-settings-status-totp-verified">totp_verified: {String(Boolean(settings.totp_verified))}</p>
        </div>
      </section>

      {(totpSetup || settings.totp_configured) && (
        <section className="space-y-3 border border-cyan-700 bg-cyan-950/20 p-4" data-testid="mfa-totp-setup-card">
          <p className="text-xs uppercase tracking-widest text-cyan-300" data-testid="mfa-totp-setup-title">TOTP Setup</p>
          {totpSetup && (
            <>
              <p className="text-xs break-all text-cyan-100" data-testid="mfa-totp-secret-value">secret: {totpSetup.secret}</p>
              <p className="text-xs break-all text-cyan-100" data-testid="mfa-totp-uri-value">uri: {totpSetup.otpauth_uri}</p>
            </>
          )}
          <div className="flex flex-wrap items-center gap-2" data-testid="mfa-totp-verify-row">
            <Input value={totpCode} onChange={(event) => setTotpCode(event.target.value)} placeholder="6 haneli TOTP kodu" data-testid="mfa-totp-code-input" />
            <Button type="button" variant="outline" onClick={verifyTotp} disabled={verifying} data-testid="mfa-totp-verify-button">{verifying ? "Doğrulanıyor..." : "TOTP Doğrula"}</Button>
          </div>
        </section>
      )}
    </section>
  );
};
