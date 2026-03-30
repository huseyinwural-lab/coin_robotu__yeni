import { useEffect, useState } from "react";
import { toast } from "sonner";

import { apiClient } from "@/lib/api";

const monoBox = "overflow-x-auto bg-slate-50 p-2 text-[11px] text-slate-700";

export const UserSettingsPage = () => {
  const [profile, setProfile] = useState(null);
  const [connections, setConnections] = useState([]);
  const [risk, setRisk] = useState(null);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    const load = async () => {
      setLoading(true);
      try {
        const [meRes, connectionsRes, riskRes] = await Promise.all([
          apiClient.get("/auth/me"),
          apiClient.get("/user/exchange-connections"),
          apiClient.get("/user-risk/settings"),
        ]);
        setProfile(meRes.data || null);
        setConnections(connectionsRes.data || []);
        setRisk(riskRes.data || null);
      } catch (error) {
        toast.error(error?.response?.data?.detail || "Settings yüklenemedi");
      } finally {
        setLoading(false);
      }
    };
    load();
  }, []);

  return (
    <section className="space-y-4" data-testid="user-settings-page">
      <header className="border border-slate-800 bg-slate-900 p-4" data-testid="user-settings-header">
        <h2 className="text-4xl font-black uppercase tracking-tight" data-testid="user-settings-title">Settings</h2>
        <p className="mt-2 text-sm text-slate-400" data-testid="user-settings-description">Profile, Exchange Connections, API Keys ve Risk Settings tek sayfada.</p>
      </header>

      <div className="grid gap-4 xl:grid-cols-12" data-testid="user-settings-main-grid">
        <article className="border border-slate-800 bg-slate-900 p-4 xl:col-span-4" data-testid="user-settings-profile-panel">
          <h3 className="text-base font-semibold" data-testid="user-settings-profile-title">Profile</h3>
          <pre className={`${monoBox} mt-3`} data-testid="user-settings-profile-json">{JSON.stringify(profile || {}, null, 2)}</pre>
        </article>
        <article className="border border-slate-800 bg-slate-900 p-4 xl:col-span-4" data-testid="user-settings-exchange-panel">
          <h3 className="text-base font-semibold" data-testid="user-settings-exchange-title">Exchange Connections</h3>
          <pre className={`${monoBox} mt-3`} data-testid="user-settings-exchange-json">{JSON.stringify(connections || [], null, 2)}</pre>
        </article>
        <article className="border border-slate-800 bg-slate-900 p-4 xl:col-span-4" data-testid="user-settings-risk-panel">
          <h3 className="text-base font-semibold" data-testid="user-settings-risk-title">Risk Settings</h3>
          <pre className={`${monoBox} mt-3`} data-testid="user-settings-risk-json">{JSON.stringify(risk || {}, null, 2)}</pre>
        </article>
      </div>

      <article className="border border-slate-800 bg-slate-900 p-4" data-testid="user-settings-api-keys-panel">
        <h3 className="text-base font-semibold" data-testid="user-settings-api-keys-title">API Keys</h3>
        <p className="mt-2 text-sm text-slate-400" data-testid="user-settings-api-keys-note">API key yönetimi Exchange Connections bloğu üzerinden konsolide edildi.</p>
      </article>

      {loading && <p className="text-xs text-slate-500" data-testid="user-settings-loading-state">loading...</p>}
    </section>
  );
};
