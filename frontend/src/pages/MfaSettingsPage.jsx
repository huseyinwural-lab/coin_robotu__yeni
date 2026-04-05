import { useEffect, useMemo, useState } from "react";
import { toast } from "sonner";

import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { useAuth } from "@/context/AuthContext";
import { apiClient, buildSessionHeaders, FRONTEND_BACKEND_URL } from "@/lib/api";

const qrUrl = (uri) => `https://api.qrserver.com/v1/create-qr-code/?size=220x220&data=${encodeURIComponent(uri)}`;
const monoBox = "overflow-x-auto bg-slate-50 p-2 text-[11px] text-slate-700";

const statusFromSettings = (settings) => {
  if (!settings?.totp_configured) return { key: "not_configured", label: "Not configured" };
  if (settings.totp_configured && !settings.totp_verified) return { key: "setup_in_progress", label: "Setup in progress" };
  if (settings.totp_verified && !settings.is_enabled) return { key: "verification_required", label: "Verification required" };
  if (settings.is_enabled && Number(settings.backup_codes_remaining || 0) === 0) return { key: "backup_depleted", label: "Backup codes depleted" };
  if (settings.is_enabled) return { key: "active", label: "Active" };
  return { key: "recovery_only", label: "Recovery only" };
};

const maskSecret = (secret) => {
  const raw = String(secret || "").replace(/\s+/g, "");
  if (raw.length <= 8) return raw;
  return `${raw.slice(0, 4)} •••• ${raw.slice(-4)}`;
};

const groupTrustedDevices = (sessions) => {
  const map = new Map();
  for (const session of sessions || []) {
    const key = String(session.device_fingerprint || session.user_agent || session.ip_address || session.session_id);
    const existing = map.get(key);
    if (!existing) {
      map.set(key, {
        key,
        device_label: key.slice(0, 18),
        first_seen: session.created_at,
        last_seen: session.last_seen_at,
        sessions: [session],
      });
    } else {
      existing.sessions.push(session);
      existing.first_seen = existing.first_seen < session.created_at ? existing.first_seen : session.created_at;
      existing.last_seen = existing.last_seen > session.last_seen_at ? existing.last_seen : session.last_seen_at;
    }
  }
  return Array.from(map.values());
};

const fetchSessionJson = async (path, { method = "GET", body = null, timeoutMs = 20000 } = {}) => {
  const controller = new AbortController();
  const timeoutId = window.setTimeout(() => controller.abort(), timeoutMs);
  const token = window.localStorage.getItem("token");
  try {
    const response = await fetch(`${FRONTEND_BACKEND_URL}/api${path}`, {
      method,
      headers: {
        ...buildSessionHeaders(),
        ...(token ? { Authorization: `Bearer ${token}` } : {}),
      },
      credentials: "include",
      cache: "no-store",
      signal: controller.signal,
      body: body ? JSON.stringify(body) : undefined,
    });
    let payload = null;
    try {
      payload = await response.json();
    } catch {
      payload = null;
    }
    if (!response.ok) {
      const error = new Error((payload && (payload.detail || payload.message)) || `request_failed_${response.status}`);
      error.response = { status: response.status, data: payload };
      throw error;
    }
    return payload;
  } finally {
    window.clearTimeout(timeoutId);
  }
};

export const MfaSettingsPage = () => {
  const { user } = useAuth();
  const [loading, setLoading] = useState(true);
  const [settings, setSettings] = useState(null);
  const [totpSetup, setTotpSetup] = useState(null);
  const [totpCode, setTotpCode] = useState("");
  const [backupCodes, setBackupCodes] = useState([]);
  const [backupAcknowledged, setBackupAcknowledged] = useState(false);
  const [secureForm, setSecureForm] = useState({ current_password: "", method: "totp", code: "", revoke_other_sessions: false });
  const [sessions, setSessions] = useState([]);
  const [securityEvents, setSecurityEvents] = useState([]);
  const [busyKey, setBusyKey] = useState("");

  const status = useMemo(() => statusFromSettings(settings), [settings]);
  const trustedDevices = useMemo(() => groupTrustedDevices(sessions), [sessions]);
  const roleLabel = useMemo(() => (user?.role === "user" ? "User" : "Admin"), [user?.role]);

  const refresh = async () => {
    setLoading(true);
    try {
      const [settingsPayload, sessionsPayload, activityPayload] = await Promise.all([
        fetchSessionJson("/auth/mfa/settings", { method: "GET", timeoutMs: 20000 }),
        fetchSessionJson("/auth/sessions/active", { method: "GET", timeoutMs: 20000 }),
        fetchSessionJson("/user/activity-log?limit=100", { method: "GET", timeoutMs: 20000 }),
      ]);
      setSettings(settingsPayload || null);
      setSessions(sessionsPayload?.items || []);
      setSecurityEvents((activityPayload || []).filter((item) => String(item.action || "").toLowerCase().includes("mfa") || String(item.action || "").toLowerCase().includes("session")));
    } catch (error) {
      toast.error(error?.response?.data?.detail || "MFA ayarları yüklenemedi");
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    refresh();
  }, []);

  const startSetup = async () => {
    setBusyKey("setup");
    try {
      const data = await fetchSessionJson("/auth/mfa/totp/setup", { method: "POST", timeoutMs: 20000 });
      setTotpSetup(data);
      setBackupCodes([]);
      setBackupAcknowledged(false);
      toast.success("QR tabanlı MFA kurulumu başlatıldı");
    } catch (error) {
      toast.error(error?.response?.data?.detail || "MFA setup başlatılamadı");
    } finally {
      setBusyKey("");
    }
  };

  const verifySetup = async () => {
    setBusyKey("verify");
    try {
      const data = await fetchSessionJson("/auth/mfa/totp/verify-setup", { method: "POST", body: { code: totpCode }, timeoutMs: 20000 });
      setSettings(data);
      const backupRes = await fetchSessionJson("/auth/mfa/backup-codes/regenerate", { method: "POST", timeoutMs: 20000 });
      setBackupCodes(backupRes?.generated_codes || []);
      setBackupAcknowledged(false);
      toast.success("OTP doğrulandı; backup codes hazırlandı");
    } catch (error) {
      toast.error(error?.response?.data?.detail || "OTP doğrulanamadı");
    } finally {
      setBusyKey("");
    }
  };

  const toggleMfaSimple = async () => {
    setBusyKey("simple-toggle");
    try {
      const currentlyEnabled = Boolean(settings?.is_enabled);
      if (currentlyEnabled) {
        const { data } = await apiClient.put(
          "/auth/mfa/settings",
          { is_enabled: false, enabled_methods: [] },
          { timeout: 20000 },
        );
        setSettings(data || null);
        toast.success("MFA kapatıldı");
        await refresh();
        return;
      }

      if (!settings?.totp_configured) {
        await startSetup();
        toast.message("MFA açmak için önce QR kurulumunu tamamlayın.");
        return;
      }

      if (!settings?.totp_verified) {
        toast.message("MFA açmak için OTP doğrulamasını tamamlayın.");
        return;
      }

      const { data } = await apiClient.put(
        "/auth/mfa/settings",
        { is_enabled: true, enabled_methods: ["totp"] },
        { timeout: 20000 },
      );
      setSettings(data || null);
      toast.success("MFA açıldı");
      await refresh();
    } catch (error) {
      toast.error(error?.response?.data?.detail || "MFA durumu güncellenemedi");
    } finally {
      setBusyKey("");
    }
  };

  const activateMfa = async () => {
    if (!backupAcknowledged) {
      toast.error("Backup code’ları güvenli yere kaydettiğinizi onaylamalısınız");
      return;
    }
    setBusyKey("activate");
    try {
      const { data } = await apiClient.put("/auth/mfa/settings", { is_enabled: true, enabled_methods: ["totp"] }, { timeout: 20000 });
      setSettings(data);
      setBackupCodes([]);
      setTotpSetup(null);
      toast.success("MFA activated");
      await refresh();
    } catch (error) {
      toast.error(error?.response?.data?.detail || "MFA aktifleştirilemedi");
    } finally {
      setBusyKey("");
    }
  };

  const disableMfa = async () => {
    setBusyKey("disable");
    try {
      const data = await fetchSessionJson("/auth/mfa/disable-secure", { method: "POST", body: secureForm, timeoutMs: 20000 });
      setSettings(data);
      setTotpSetup(null);
      setBackupCodes([]);
      toast.success("MFA güvenli şekilde kapatıldı");
      await refresh();
    } catch (error) {
      toast.error(error?.response?.data?.detail || "MFA kapatılamadı");
    } finally {
      setBusyKey("");
    }
  };

  const regenerateBackupCodes = async () => {
    setBusyKey("regen");
    try {
      const data = await fetchSessionJson("/auth/mfa/backup-codes/regenerate-secure", { method: "POST", body: secureForm, timeoutMs: 20000 });
      setBackupCodes(data?.generated_codes || []);
      setBackupAcknowledged(false);
      toast.success("Yeni backup codes üretildi");
      await refresh();
    } catch (error) {
      toast.error(error?.response?.data?.detail || "Backup code regenerate başarısız");
    } finally {
      setBusyKey("");
    }
  };

  const revokeSession = async (sessionId, reason = "manual_revoke") => {
    try {
      await apiClient.post(`/auth/sessions/${sessionId}/revoke`, { reason });
      toast.success("Session revoke edildi");
      await refresh();
    } catch (error) {
      toast.error(error?.response?.data?.detail || "Session revoke başarısız");
    }
  };

  const revokeAllOthers = async () => {
    const currentSession = sessions[0]?.session_id;
    const others = (sessions || []).filter((item) => item.session_id !== currentSession);
    for (const session of others) {
      // eslint-disable-next-line no-await-in-loop
      await revokeSession(session.session_id, "revoke_all_others");
    }
  };

  const revokeDeviceTrust = async (deviceKey) => {
    const device = trustedDevices.find((item) => item.key === deviceKey);
    if (!device) return;
    for (const session of device.sessions) {
      // eslint-disable-next-line no-await-in-loop
      await revokeSession(session.session_id, "trusted_device_revoke");
    }
  };

  if (loading) {
    return <section className="border border-slate-800 bg-slate-900 p-4" data-testid="mfa-settings-loading"><p>MFA ayarları yükleniyor...</p></section>;
  }

  return (
    <section className="space-y-4" data-testid="mfa-settings-page">
      <header className="border border-slate-800 bg-slate-900 p-4" data-testid="mfa-settings-header">
        <h2 className="text-4xl font-black uppercase tracking-tight" data-testid="mfa-settings-title">{roleLabel} MFA Security</h2>
        <p className="mt-2 text-sm text-slate-400" data-testid="mfa-settings-description">QR setup, doğrulanmış aktivasyon, güvenli disable, trusted devices ve session yönetimi tek akışta.</p>
      </header>

      <div className="grid gap-3 md:grid-cols-3" data-testid="mfa-status-grid">
        <article className="border border-slate-800 bg-slate-900 p-4" data-testid="mfa-status-card"><p className="text-xs uppercase tracking-widest text-slate-500">Status</p><p className="mt-2 text-lg font-bold text-emerald-300" data-testid="mfa-status-label">{status.label}</p></article>
        <article className="border border-slate-800 bg-slate-900 p-4" data-testid="mfa-backup-status-card"><p className="text-xs uppercase tracking-widest text-slate-500">Backup Codes</p><p className="mt-2 text-lg font-bold text-emerald-300">{settings?.backup_codes_remaining ?? 0}</p></article>
        <article className="border border-slate-800 bg-slate-900 p-4" data-testid="mfa-last-verified-card"><p className="text-xs uppercase tracking-widest text-slate-500">Last Verified</p><p className="mt-2 text-sm font-bold text-emerald-300">{settings?.last_verified_at || "never"}</p></article>
      </div>

      <section className="border border-slate-800 bg-slate-900 p-4" data-testid="mfa-simple-toggle-panel">
        <div className="flex flex-wrap items-center justify-between gap-3">
          <div>
            <p className="text-xs uppercase tracking-widest text-slate-500">Basit Aç / Kapat</p>
            <p className="mt-1 text-sm text-slate-300" data-testid="mfa-simple-toggle-hint">
              İlk kurulumda MFA kapalı gelir. İsterseniz açar, isterseniz kapatırsınız.
            </p>
          </div>
          <Button
            type="button"
            onClick={toggleMfaSimple}
            disabled={busyKey === "simple-toggle"}
            data-testid="mfa-simple-toggle-button"
          >
            {settings?.is_enabled ? "MFA Kapat" : "MFA Aç"}
          </Button>
        </div>
      </section>

      <section className="border border-slate-800 bg-slate-900 p-4" data-testid="mfa-setup-wizard-panel">
        <p className="text-xs uppercase tracking-widest text-slate-500">MFA Setup Wizard</p>
        <div className="mt-3 flex flex-wrap gap-2 text-xs text-slate-300" data-testid="mfa-setup-steps">
          {['Start setup','Scan QR','Verify OTP','Backup codes','Acknowledge','Activated'].map((step, index) => <span key={step} className="rounded border border-slate-700 px-2 py-1" data-testid={`mfa-setup-step-${index}`}>{step}</span>)}
        </div>

        {!totpSetup && !settings?.totp_configured && <Button className="mt-4" onClick={startSetup} disabled={busyKey === "setup"} data-testid="mfa-start-setup-button">Start setup</Button>}

        {(totpSetup || settings?.totp_configured) && (
          <div className="mt-4 grid gap-4 lg:grid-cols-2" data-testid="mfa-qr-setup-block">
            <div className="border border-slate-700 bg-slate-950 p-4" data-testid="mfa-qr-card">
              <p className="text-xs uppercase tracking-widest text-slate-500">Scan QR</p>
              {totpSetup?.otpauth_uri ? <img src={qrUrl(totpSetup.otpauth_uri)} alt="MFA QR" className="mt-3 h-56 w-56 bg-white p-2" data-testid="mfa-qr-image" /> : <p className="mt-3 text-sm text-slate-400">QR setup üretildiğinde burada görünür.</p>}
              {totpSetup?.secret && <p className="mt-3 text-sm text-slate-300" data-testid="mfa-manual-key-masked">manual key: {maskSecret(totpSetup.secret)}</p>}
            </div>
            <div className="border border-slate-700 bg-slate-950 p-4" data-testid="mfa-verify-card">
              <p className="text-xs uppercase tracking-widest text-slate-500">Verify OTP</p>
              <Input value={totpCode} onChange={(event) => setTotpCode(event.target.value)} placeholder="6 haneli OTP" className="mt-3" data-testid="mfa-totp-code-input" />
              <Button className="mt-3" variant="outline" onClick={verifySetup} disabled={busyKey === "verify"} data-testid="mfa-verify-otp-button">OTP doğrula</Button>
            </div>
          </div>
        )}

        {backupCodes.length > 0 && (
          <div className="mt-4 border border-amber-700/60 bg-amber-950/20 p-4" data-testid="mfa-backup-codes-wizard-card">
            <p className="text-xs uppercase tracking-widest text-amber-300">Backup Codes (one-time view)</p>
            <div className="mt-3 grid gap-2 sm:grid-cols-2" data-testid="mfa-backup-codes-list">
              {backupCodes.map((code, index) => <p key={`${code}-${index}`} className="rounded border border-amber-600/40 px-2 py-1 text-xs text-amber-100" data-testid={`mfa-backup-code-item-${index}`}>{code}</p>)}
            </div>
            <div className="mt-3 flex flex-wrap gap-2" data-testid="mfa-backup-actions-row">
              <Button type="button" variant="outline" onClick={async () => navigator.clipboard.writeText(backupCodes.join("\n"))} data-testid="mfa-backup-copy-button">Copy</Button>
              <Button type="button" variant="outline" onClick={() => {
                const blob = new Blob([backupCodes.join("\n")], { type: "text/plain" });
                const blobUrl = window.URL.createObjectURL(blob);
                const link = document.createElement("a");
                link.href = blobUrl;
                link.download = "mfa-backup-codes.txt";
                link.click();
                window.URL.revokeObjectURL(blobUrl);
              }} data-testid="mfa-backup-download-button">Download</Button>
            </div>
            <label className="mt-4 flex items-center gap-2 text-sm text-amber-100" data-testid="mfa-backup-acknowledge-wrapper">
              <input type="checkbox" checked={backupAcknowledged} onChange={(event) => setBackupAcknowledged(event.target.checked)} data-testid="mfa-backup-acknowledge-checkbox" />
              Kopyaladım / güvenli yere kaydettim
            </label>
            <Button className="mt-3" onClick={activateMfa} disabled={!backupAcknowledged || busyKey === "activate"} data-testid="mfa-activate-button">MFA activated</Button>
          </div>
        )}
      </section>

      <section className="grid gap-4 xl:grid-cols-12" data-testid="mfa-operations-grid">
        <article className="border border-slate-800 bg-slate-900 p-4 xl:col-span-4" data-testid="mfa-disable-panel">
          <p className="text-xs uppercase tracking-widest text-slate-500">Secure Disable</p>
          <Input className="mt-3" type="password" placeholder="Current password" value={secureForm.current_password} onChange={(event) => setSecureForm((prev) => ({ ...prev, current_password: event.target.value }))} data-testid="mfa-disable-current-password-input" />
          <select className="mt-3 h-10 w-full rounded border border-slate-700 bg-slate-950 px-3 text-sm" value={secureForm.method} onChange={(event) => setSecureForm((prev) => ({ ...prev, method: event.target.value }))} data-testid="mfa-disable-method-select"><option value="totp">totp</option><option value="backup_code">backup_code</option></select>
          <Input className="mt-3" placeholder="OTP / Backup code" value={secureForm.code} onChange={(event) => setSecureForm((prev) => ({ ...prev, code: event.target.value }))} data-testid="mfa-disable-code-input" />
          <label className="mt-3 flex items-center gap-2 text-sm text-slate-300" data-testid="mfa-disable-revoke-sessions-wrapper"><input type="checkbox" checked={secureForm.revoke_other_sessions} onChange={(event) => setSecureForm((prev) => ({ ...prev, revoke_other_sessions: event.target.checked }))} data-testid="mfa-disable-revoke-sessions-checkbox" />disable all trusted devices / revoke sessions</label>
          <Button className="mt-3" variant="outline" onClick={disableMfa} disabled={busyKey === "disable"} data-testid="mfa-disable-button">Disable MFA</Button>
        </article>

        <article className="border border-slate-800 bg-slate-900 p-4 xl:col-span-4" data-testid="mfa-backup-regenerate-panel">
          <p className="text-xs uppercase tracking-widest text-slate-500">Backup Codes</p>
          <p className="mt-2 text-sm text-slate-300" data-testid="mfa-backup-remaining-friendly">remaining count: {settings?.backup_codes_remaining ?? 0}</p>
          {Number(settings?.backup_codes_remaining || 0) === 0 && <p className="mt-2 text-sm text-amber-300" data-testid="mfa-backup-depleted-warning">Backup codes depleted — regenerate veya recovery başlatın.</p>}
          <Button className="mt-3" variant="outline" onClick={regenerateBackupCodes} disabled={busyKey === "regen"} data-testid="mfa-backup-regenerate-secure-button">Regenerate Backup Codes</Button>
        </article>

        <article className="border border-slate-800 bg-slate-900 p-4 xl:col-span-4" data-testid="mfa-enforcement-panel">
          <p className="text-xs uppercase tracking-widest text-slate-500">MFA Enforcement</p>
          <div className="mt-3 space-y-2 text-sm text-slate-300">
            <p data-testid="mfa-enforcement-login-required">Login protection: {settings?.is_enabled ? "MFA active" : "optional / not active"}</p>
            <p data-testid="mfa-enforcement-role-scope">Privileged role strictness: ops role disable forbidden</p>
            <p data-testid="mfa-enforcement-step-up">Step-up actions: trade, API key delete, critical settings</p>
            <p data-testid="mfa-enforcement-grace">grace period: {settings?.mfa_grace_active ? `active until ${settings?.mfa_grace_expires_at}` : "none"}</p>
          </div>
        </article>
      </section>

      <section className="grid gap-4 xl:grid-cols-2" data-testid="mfa-session-management-grid">
        <article className="border border-slate-800 bg-slate-900 p-4" data-testid="mfa-trusted-devices-panel">
          <p className="text-xs uppercase tracking-widest text-slate-500">Trusted Devices</p>
          <div className="mt-3 space-y-2" data-testid="mfa-trusted-devices-list">
            {trustedDevices.map((device, index) => (
              <div key={device.key} className="rounded border border-slate-700 p-3 text-sm" data-testid={`mfa-trusted-device-item-${index}`}>
                <p className="font-semibold">{device.device_label}</p>
                <p className="text-xs text-slate-400">first seen: {device.first_seen || '-'}</p>
                <p className="text-xs text-slate-400">last seen: {device.last_seen || '-'}</p>
                <Button className="mt-2" variant="outline" onClick={() => revokeDeviceTrust(device.key)} data-testid={`mfa-trusted-device-revoke-button-${index}`}>Revoke trust</Button>
              </div>
            ))}
          </div>
        </article>

        <article className="border border-slate-800 bg-slate-900 p-4" data-testid="mfa-active-sessions-panel">
          <div className="flex items-center justify-between gap-2">
            <p className="text-xs uppercase tracking-widest text-slate-500">Active Sessions</p>
            <Button variant="outline" onClick={revokeAllOthers} data-testid="mfa-sessions-revoke-all-others-button">Revoke all others</Button>
          </div>
          <div className="mt-3 space-y-2" data-testid="mfa-active-sessions-list">
            {(sessions || []).map((session, index) => (
              <div key={session.session_id} className="rounded border border-slate-700 p-3 text-sm" data-testid={`mfa-active-session-item-${index}`}>
                <p className="font-semibold">{session.session_id}</p>
                <p className="text-xs text-slate-400">last seen: {session.last_seen_at || '-'}</p>
                <p className="text-xs text-slate-400">device: {session.device_fingerprint || '-'}</p>
                <Button className="mt-2" variant="outline" onClick={() => revokeSession(session.session_id)} data-testid={`mfa-active-session-revoke-button-${index}`}>Revoke</Button>
              </div>
            ))}
          </div>
        </article>
      </section>

      <section className="border border-slate-800 bg-slate-900 p-4" data-testid="mfa-diagnostics-panel">
        <p className="text-xs uppercase tracking-widest text-slate-500">MFA Diagnostics / Audit</p>
        <pre className={`${monoBox} mt-3`} data-testid="mfa-diagnostics-json">{JSON.stringify((securityEvents || []).slice(0, 20), null, 2)}</pre>
      </section>
    </section>
  );
};
