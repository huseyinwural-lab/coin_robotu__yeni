import { useCallback, useEffect, useState } from "react";
import { toast } from "sonner";

import { MetricCard } from "@/components/MetricCard";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { apiClient } from "@/lib/api";

const initialForm = {
  exchange: "binance",
  mode: "testnet",
  api_key: "",
  api_secret: "",
};

export const UserExchangeSettingsPage = () => {
  const [settings, setSettings] = useState(null);
  const [permission, setPermission] = useState(null);
  const [latestQuality, setLatestQuality] = useState(null);
  const [form, setForm] = useState(initialForm);
  const [isSaving, setIsSaving] = useState(false);
  const [isTesting, setIsTesting] = useState(false);

  const loadAll = useCallback(async () => {
    try {
      const [settingsRes, permissionRes] = await Promise.all([
        apiClient.get("/phase4/exchange-settings"),
        apiClient.get("/phase4/permission-status"),
      ]);
      setSettings(settingsRes.data);
      setPermission(permissionRes.data);
    } catch (error) {
      toast.error(error?.response?.data?.detail || "Exchange ayarları yüklenemedi");
    }

    try {
      const { data } = await apiClient.get("/phase4/execution-quality/latest");
      setLatestQuality(data);
    } catch (_) {
      setLatestQuality(null);
    }
  }, []);

  useEffect(() => {
    loadAll();
  }, [loadAll]);

  const saveSettings = async (event) => {
    event.preventDefault();
    setIsSaving(true);
    try {
      const { data } = await apiClient.put("/phase4/exchange-settings", form);
      setSettings(data);
      setForm(initialForm);
      toast.success("API key bilgileri şifreli olarak kaydedildi");
      await loadAll();
    } catch (error) {
      toast.error(error?.response?.data?.detail || "Ayarlar kaydedilemedi");
    } finally {
      setIsSaving(false);
    }
  };

  const runPermission = async () => {
    try {
      const { data } = await apiClient.get("/phase4/permission-status");
      setPermission(data);
      toast.success("Permission kontrolü tamamlandı");
    } catch (error) {
      toast.error(error?.response?.data?.detail || "Permission kontrolü başarısız");
    }
  };

  const runFirstTestOrder = async () => {
    setIsTesting(true);
    try {
      const { data } = await apiClient.post("/phase4/test-order");
      setLatestQuality({
        execution_id: data.execution_id,
        symbol: data.symbol,
        status: data.status,
        strategy_type: data.strategy_type,
        volatility_regime: data.volatility_regime,
        volatility_pct: data.volatility_pct,
        expected_price: data.expected_price,
        fill_price: data.fill_price,
        slippage: data.slippage,
        execution_latency: data.execution_latency,
        execution_quality_score: data.execution_quality_score,
        timestamp: data.timestamp,
      });
      toast.success("İlk kontrollü test emri gönderildi");
      await loadAll();
    } catch (error) {
      toast.error(error?.response?.data?.detail || "Test emri başarısız");
    } finally {
      setIsTesting(false);
    }
  };

  return (
    <section className="space-y-4" data-testid="user-exchange-settings-page">
      <header className="border border-slate-800 bg-slate-900 p-4" data-testid="user-exchange-settings-header">
        <h2 className="text-4xl font-black uppercase tracking-tight" data-testid="user-exchange-settings-title">Exchange Settings</h2>
        <p className="mt-2 text-sm text-slate-400" data-testid="user-exchange-settings-description">
          Binance Futures Testnet API bilgilerini girin. Bilgiler plaintext değil, şifreli saklanır.
        </p>
      </header>

      <div className="grid gap-3 sm:grid-cols-2 lg:grid-cols-5" data-testid="user-exchange-settings-metrics-grid">
        <MetricCard label="Exchange" value={settings?.exchange || "-"} tone="orange" testId="user-exchange-metric-exchange" />
        <MetricCard label="Mode" value={settings?.mode || "-"} tone="orange" testId="user-exchange-metric-mode" />
        <MetricCard label="Permission" value={permission?.overall_status || "-"} tone={permission?.overall_status === "pass" ? "orange" : "red"} testId="user-exchange-metric-permission" />
        <MetricCard label="Live Activation" value={permission?.live_activation || "blocked"} tone={permission?.live_activation === "ready" ? "orange" : "red"} testId="user-exchange-metric-live-activation" />
        <MetricCard label="Execution Quality" value={latestQuality?.execution_quality_score ?? "-"} tone="orange" testId="user-exchange-metric-quality" />
      </div>

      <div className="border border-slate-800 bg-slate-900 p-4" data-testid="user-exchange-quality-regime-panel">
        <p className="text-xs uppercase tracking-widest text-slate-500" data-testid="user-exchange-quality-regime-title">Quality Normalization</p>
        <p className="mt-2 text-sm text-slate-300" data-testid="user-exchange-quality-strategy">strategy={latestQuality?.strategy_type || "-"}</p>
        <p className="mt-1 text-sm text-slate-300" data-testid="user-exchange-quality-volatility-regime">volatility_regime={latestQuality?.volatility_regime || "-"}</p>
        <p className="mt-1 text-sm text-slate-300" data-testid="user-exchange-quality-volatility-pct">volatility_pct={latestQuality?.volatility_pct ?? "-"}</p>
      </div>

      <form className="grid gap-3 border border-slate-800 bg-slate-900 p-4 md:grid-cols-2" onSubmit={saveSettings} data-testid="user-exchange-settings-form">
        <Input value={form.exchange} onChange={(event) => setForm((prev) => ({ ...prev, exchange: event.target.value }))} data-testid="user-exchange-settings-exchange-input" />
        <Input value={form.mode} onChange={(event) => setForm((prev) => ({ ...prev, mode: event.target.value }))} data-testid="user-exchange-settings-mode-input" />
        <Input value={form.api_key} onChange={(event) => setForm((prev) => ({ ...prev, api_key: event.target.value }))} placeholder="API Key" data-testid="user-exchange-settings-api-key-input" required />
        <Input value={form.api_secret} onChange={(event) => setForm((prev) => ({ ...prev, api_secret: event.target.value }))} placeholder="API Secret" data-testid="user-exchange-settings-api-secret-input" required />
        <Button className="md:col-span-2 bg-orange-500 text-black hover:bg-orange-600" data-testid="user-exchange-settings-save-button" disabled={isSaving}>
          {isSaving ? "Kaydediliyor..." : "API Bilgilerini Kaydet"}
        </Button>
      </form>

      <div className="border border-slate-800 bg-slate-900 p-4" data-testid="user-exchange-actions-panel">
        <div className="flex flex-wrap gap-3" data-testid="user-exchange-actions-buttons">
          <Button className="bg-orange-500 text-black hover:bg-orange-600" onClick={runPermission} data-testid="user-exchange-check-permission-button">
            Permission Doğrula
          </Button>
          <Button className="bg-black text-orange-400 hover:bg-zinc-900" onClick={runFirstTestOrder} data-testid="user-exchange-first-test-order-button" disabled={isTesting}>
            {isTesting ? "Gönderiliyor..." : "İlk Kontrollü Test Emri"}
          </Button>
        </div>

        <div className="mt-4 space-y-1" data-testid="user-exchange-permission-controls-list">
          {(permission?.controls || []).map((item) => (
            <p key={item.key} className="text-xs font-mono text-slate-300" data-testid={`user-exchange-permission-control-${item.key}`}>
              {item.key}: {item.status} ({item.reason})
            </p>
          ))}
        </div>
      </div>
    </section>
  );
};