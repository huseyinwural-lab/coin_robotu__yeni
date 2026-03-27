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
    backup_codes_remaining: 0,
    mfa_enabled_not_verified: false,
    backup_download_required: false,
  });
  const [totpSetup, setTotpSetup] = useState(null);
  const [totpCode, setTotpCode] = useState("");
  const [backupCodes, setBackupCodes] = useState([]);
  const [isGeneratingBackupCodes, setIsGeneratingBackupCodes] = useState(false);
  const [backupCodesConfirmed, setBackupCodesConfirmed] = useState(false);
  const [mustConfirmBackup, setMustConfirmBackup] = useState(false);

  const roleLabel = useMemo(() => (user?.role === "user" ? "User" : "Admin"), [user?.role]);

  const refresh = async () => {
    setLoading(true);
    try {
      const { data } = await apiClient.get("/auth/mfa/settings");
      setSettings(data);
      setMustConfirmBackup(false);
      setBackupCodesConfirmed(false);
    } catch {
      toast.error("MFA ayarları alınamadı");
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    refresh();
  }, []);

  const saveSettings = async () => {
    const requiresBackupConfirmation = Boolean(settings.is_enabled) && Boolean(settings.totp_verified) && mustConfirmBackup && !backupCodesConfirmed;

    if (requiresBackupConfirmation) {
      toast.error("Backup kodlarını indirdiğinizi/kopyaladığınızı onaylamadan MFA kaydedilemez");
      return;
    }

    setSaving(true);
    try {
      const payload = {
        is_enabled: Boolean(settings.is_enabled),
        enabled_methods: settings.is_enabled ? ["totp"] : [],
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
      const { data } = await apiClient.post("/mfa/setup");
      setTotpSetup(data);
      setBackupCodesConfirmed(false);
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
      setMustConfirmBackup(true);
      setBackupCodesConfirmed(false);
      toast.success("TOTP doğrulandı");
    } catch (error) {
      toast.error(error?.response?.data?.detail || "TOTP kodu doğrulanamadı");
    } finally {
      setVerifying(false);
    }
  };

  const regenerateBackupCodes = async () => {
    setIsGeneratingBackupCodes(true);
    try {
      const { data } = await apiClient.post("/auth/mfa/backup-codes/regenerate");
      setBackupCodes(data?.generated_codes || []);
      setSettings((prev) => ({
        ...prev,
        backup_codes_remaining: Number(data?.backup_codes_remaining || 0),
      }));
      setBackupCodesConfirmed(false);
      setMustConfirmBackup(true);
      toast.success("Backup kodları yenilendi");
    } catch (error) {
      toast.error(error?.response?.data?.detail || "Backup kodları üretilemedi");
    } finally {
      setIsGeneratingBackupCodes(false);
    }
  };

  const markBackupCodesSaved = async () => {
    if (backupCodes.length > 0) {
      const payload = backupCodes.join("\n");
      try {
        await navigator.clipboard.writeText(payload);
        toast.success("Backup kodları panoya kopyalandı");
      } catch {
        toast.message("Panoya kopyalama başarısız, lütfen manuel kaydedin");
      }
    }
    setBackupCodesConfirmed(true);
    setMustConfirmBackup(false);
  };

  const wizardStep = useMemo(() => {
    if (!settings.totp_configured) return "setup";
    if (settings.totp_configured && !settings.totp_verified) return "verify";
    if (settings.totp_verified && Number(settings.backup_codes_remaining || 0) === 0) return "backup";
    return "completed";
  }, [settings.totp_configured, settings.totp_verified, settings.backup_codes_remaining]);

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
        <p className="mt-2 text-sm text-slate-400" data-testid="mfa-settings-description">MFA setup wizard: setup → verify → backup code confirmation.</p>
        <p className="mt-1 text-xs text-slate-500" data-testid="mfa-settings-wizard-step">wizard_step: {wizardStep}</p>
        {Boolean(settings.mfa_enabled_not_verified) && (
          <p className="mt-2 text-xs font-semibold text-amber-300" data-testid="mfa-settings-enabled-not-verified-warning">
            MFA enabled but not verified state aktif. TOTP doğrulama tamamlanana kadar riskli durumdasınız.
          </p>
        )}
      </header>

      <section className="space-y-3 border border-slate-800 bg-slate-900 p-4" data-testid="mfa-settings-main-card">
        <label className="inline-flex items-center gap-2 text-sm" data-testid="mfa-settings-enable-wrapper">
          <input
            type="checkbox"
            checked={Boolean(settings.is_enabled)}
            onChange={(event) => setSettings((prev) => ({
              ...prev,
              is_enabled: event.target.checked,
              enabled_methods: event.target.checked ? ["totp"] : [],
            }))}
            data-testid="mfa-settings-enable-checkbox"
          />
          MFA aktif
        </label>

        <div className="rounded border border-slate-700 bg-slate-950 p-3" data-testid="mfa-settings-method-fixed-card">
          <p className="text-xs text-slate-300" data-testid="mfa-settings-method-fixed-title">MFA yöntemi sabit</p>
          <p className="text-xs text-slate-400" data-testid="mfa-settings-method-fixed-value">Authenticator (TOTP) + Backup Code</p>
          <p className="text-xs text-slate-500" data-testid="mfa-settings-method-fixed-note">Yeni device girişlerinde Email OTP challenge otomatik devreye girer.</p>
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
          <p className="text-xs text-slate-400" data-testid="mfa-settings-status-enabled-not-verified">mfa_enabled_not_verified: {String(Boolean(settings.mfa_enabled_not_verified))}</p>
          <p className="text-xs text-slate-400" data-testid="mfa-settings-status-backup-required">backup_download_required: {String(Boolean(settings.backup_download_required))}</p>
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

      <section className="space-y-3 border border-amber-700/60 bg-amber-950/20 p-4" data-testid="mfa-backup-codes-card">
        <div className="flex flex-wrap items-center justify-between gap-2" data-testid="mfa-backup-codes-header-row">
          <p className="text-xs uppercase tracking-widest text-amber-300" data-testid="mfa-backup-codes-title">MFA Backup Codes</p>
          <p className="text-xs text-amber-100" data-testid="mfa-backup-codes-remaining">remaining: {settings.backup_codes_remaining || 0}</p>
        </div>
        <p className="text-xs text-amber-100" data-testid="mfa-backup-codes-description">
          Tek kullanımlık kurtarma kodlarıdır. MFA setup tamamlanması için kodları kaydettiğinizi onaylamanız zorunludur.
        </p>
        <Button
          type="button"
          variant="outline"
          onClick={regenerateBackupCodes}
          disabled={isGeneratingBackupCodes}
          data-testid="mfa-backup-codes-regenerate-button"
        >
          {isGeneratingBackupCodes ? "Üretiliyor..." : "Backup Kodları Yenile"}
        </Button>

        {backupCodes.length > 0 && (
          <div className="rounded border border-amber-700/50 bg-black/30 p-3" data-testid="mfa-backup-codes-list-card">
            <p className="text-xs font-semibold text-amber-200" data-testid="mfa-backup-codes-list-title">Bu kodlar sadece bir kez gösterilir:</p>
            <div className="mt-2 grid gap-2 sm:grid-cols-2" data-testid="mfa-backup-codes-list">
              {backupCodes.map((code, index) => (
                <p key={`${code}-${index}`} className="rounded border border-amber-600/40 px-2 py-1 text-xs tracking-wider text-amber-100" data-testid={`mfa-backup-code-item-${index}`}>
                  {code}
                </p>
              ))}
            </div>
            <Button
              type="button"
              variant="outline"
              className="mt-3"
              onClick={markBackupCodesSaved}
              data-testid="mfa-backup-codes-confirm-saved-button"
            >
              {backupCodesConfirmed ? "Backup Kodları Kaydedildi" : "Kodları Kaydettim / Panoya Kopyala"}
            </Button>
          </div>
        )}
      </section>
    </section>
  );
};
