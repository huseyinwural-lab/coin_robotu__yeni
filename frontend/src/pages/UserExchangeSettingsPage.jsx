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
  const [validateResult, setValidateResult] = useState(null);
  const [readiness, setReadiness] = useState(null);
  const [ticker, setTicker] = useState(null);
  const [latestQuality, setLatestQuality] = useState(null);
  const [form, setForm] = useState(initialForm);
  const [isSaving, setIsSaving] = useState(false);
  const [isValidating, setIsValidating] = useState(false);
  const [isTesting, setIsTesting] = useState(false);
  const [testOrderResult, setTestOrderResult] = useState(null);
  const [testOrderBanner, setTestOrderBanner] = useState("");

  const loadAll = useCallback(async () => {
    try {
      const [settingsRes, permissionRes, tickerRes, readinessRes] = await Promise.all([
        apiClient.get("/phase4/exchange-settings"),
        apiClient.get("/phase4/permission-status"),
        apiClient.get("/market/ticker?symbol=BTCUSDT"),
        apiClient.get("/exchange/readiness-checklist"),
      ]);
      setSettings(settingsRes.data);
      setPermission(permissionRes.data);
      setTicker(tickerRes.data);
      setReadiness(readinessRes.data);
    } catch (error) {
      toast.error(error?.response?.data?.detail || "Exchange ayarları yüklenemedi");
    }

    try {
      const { data } = await apiClient.get("/exchange/validate");
      setValidateResult(data);
    } catch (error) {
      const detail = error?.response?.data?.detail;
      setValidateResult(typeof detail === "object" ? detail : null);
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
    setIsValidating(true);
    try {
      const { data } = await apiClient.get("/exchange/validate");
      setValidateResult(data);
      toast.success("Exchange doğrulaması tamamlandı");
      await loadAll();
    } catch (error) {
      const detail = error?.response?.data?.detail;
      setValidateResult(typeof detail === "object" ? detail : null);
      toast.error("Exchange doğrulaması başarısız");
    } finally {
      setIsValidating(false);
    }
  };

  const runFirstTestOrder = async () => {
    setIsTesting(true);
    setTestOrderBanner("");
    try {
      const { data } = await apiClient.post("/exchange/test-order");
      setTestOrderResult(data);
      setLatestQuality({
        execution_id: data.order_id,
        symbol: "BTCUSDT",
        status: data.status,
        strategy_type: data.strategy_type,
        volatility_regime: data.volatility_regime,
        volatility_pct: data.volatility_pct,
        expected_price: ticker?.mid_price,
        fill_price: data.price_avg,
        slippage: data.slippage_pct,
        execution_latency: data.execution_time_ms,
        execution_quality_score: data.execution_quality_score,
        timestamp: new Date().toISOString(),
      });
      toast.success("İlk kontrollü test emri gönderildi");
      await loadAll();
    } catch (error) {
      const detail = error?.response?.data?.detail;
      if (typeof detail === "object") {
        setTestOrderBanner(detail.message || "awaiting valid key");
      }
      toast.error(typeof detail === "object" ? detail.message : (detail || "Test emri başarısız"));
    } finally {
      setIsTesting(false);
    }
  };

  const readinessTone = readiness?.readiness_status === "ready_for_test_order"
    ? "orange"
    : readiness?.readiness_status === "awaiting_valid_key"
      ? "blue"
      : "red";

  const actionState = isTesting
    ? "executing"
    : isValidating
      ? "validating"
      : readiness?.readiness_status === "ready_for_test_order"
        ? "ready"
        : readiness?.readiness_status || "blocked";

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

      <div className="grid gap-3 sm:grid-cols-4" data-testid="user-exchange-action-state-grid">
        <MetricCard label="Readiness" value={readiness?.readiness_status || "-"} tone={readinessTone} testId="user-exchange-readiness-status" />
        <MetricCard label="Action State" value={actionState} tone={readinessTone} testId="user-exchange-action-state" />
        <MetricCard label="Last Validation" value={readiness?.validation_timestamp || "-"} tone="blue" testId="user-exchange-last-validation-at" />
        <MetricCard label="Last Error" value={readiness?.last_error_reason || "-"} tone="red" testId="user-exchange-last-error-reason" />
      </div>

      <div className="grid gap-3 sm:grid-cols-3" data-testid="user-exchange-validate-grid">
        <MetricCard label="Validate is_valid" value={String(validateResult?.is_valid ?? false)} tone={validateResult?.is_valid ? "orange" : "red"} testId="user-exchange-validate-is-valid" />
        <MetricCard label="can_trade" value={String(validateResult?.can_trade ?? false)} tone={validateResult?.can_trade ? "orange" : "red"} testId="user-exchange-validate-can-trade" />
        <MetricCard label="mid_price" value={ticker?.mid_price ?? "-"} tone="blue" testId="user-exchange-mid-price" />
      </div>

      <div className="border border-slate-800 bg-slate-900 p-4" data-testid="user-readiness-checklist-card">
        <p className="text-xs uppercase tracking-widest text-slate-500" data-testid="user-readiness-checklist-title">Readiness Checklist</p>
        <div className="mt-3 grid gap-2 sm:grid-cols-2" data-testid="user-readiness-checklist-grid">
          <p data-testid="user-readiness-has-api-key">API key mevcut: {String(readiness?.has_api_key ?? false)}</p>
          <p data-testid="user-readiness-has-api-secret">Secret mevcut: {String(readiness?.has_api_secret ?? false)}</p>
          <p data-testid="user-readiness-validation-success">Validation başarılı: {String(readiness?.validation_success ?? false)}</p>
          <p data-testid="user-readiness-can-trade">can_trade=true: {String(readiness?.can_trade ?? false)}</p>
          <p data-testid="user-readiness-testnet-env">testnet environment: {String(readiness?.is_testnet_environment ?? false)}</p>
          <p data-testid="user-readiness-validation-stale">snapshot stale: {String(readiness?.is_validation_stale ?? true)}</p>
        </div>
      </div>

      {readiness?.readiness_status === "awaiting_valid_key" && (
        <div className="border border-blue-700 bg-blue-950/20 p-4 text-sm text-blue-200" data-testid="user-readiness-awaiting-valid-key-banner">
          awaiting valid key — Binance Testnet API key ve secret doğrulanmadan gerçek test-order çalıştırılamaz.
        </div>
      )}

      {(testOrderBanner || readiness?.is_validation_stale) && (
        <div className="border border-red-700 bg-red-950/20 p-4 text-sm text-red-200" data-testid="user-readiness-failure-banner">
          {testOrderBanner || "Validation snapshot stale. Lütfen Revalidate yapın."}
        </div>
      )}

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
          <Button className="bg-orange-500 text-black hover:bg-orange-600" onClick={runPermission} data-testid="user-exchange-check-permission-button" disabled={isValidating}>
            {isValidating ? "Validating..." : "Revalidate"}
          </Button>
          <Button
            className="bg-black text-orange-400 hover:bg-zinc-900"
            onClick={runFirstTestOrder}
            data-testid="user-exchange-first-test-order-button"
            disabled={isTesting || readiness?.readiness_status !== "ready_for_test_order"}
          >
            {isTesting ? "Gönderiliyor..." : "İlk Kontrollü Test Emri"}
          </Button>
        </div>

        <div className="mt-4 space-y-1" data-testid="user-exchange-permission-controls-list">
          {(permission?.controls || []).map((item) => (
            <p key={item.key} className="text-xs font-mono text-slate-300" data-testid={`user-exchange-permission-control-${item.key}`}>
              {item.key}: {item.status} ({item.reason})
            </p>
          ))}
          <p className="pt-2 text-xs font-mono text-slate-300" data-testid="user-exchange-validate-permissions-line">
            permissions: {(validateResult?.permissions || []).join(",") || "-"}
          </p>
          <p className="text-xs font-mono text-slate-300" data-testid="user-exchange-validate-reason-codes-line">
            reason_codes: {(validateResult?.reason_codes || []).join(",") || "-"}
          </p>
        </div>
      </div>

      <div className="border border-slate-800 bg-slate-900 p-4" data-testid="user-test-order-result-card">
        <p className="text-xs uppercase tracking-widest text-slate-500" data-testid="user-test-order-result-title">Test Order Result</p>
        <div className="mt-3 grid gap-2 sm:grid-cols-2" data-testid="user-test-order-result-grid">
          <p data-testid="user-test-order-status">order status: {testOrderResult?.status || "awaiting_valid_key"}</p>
          <p data-testid="user-test-order-exchange-order-id">exchange order id: {testOrderResult?.exchange_order_id || "-"}</p>
          <p data-testid="user-test-order-average-fill-price">average fill price: {testOrderResult?.price_avg ?? "-"}</p>
          <p data-testid="user-test-order-executed-qty">executed quantity: {testOrderResult?.executed_qty ?? "-"}</p>
          <p data-testid="user-test-order-slippage-pct">slippage pct: {testOrderResult?.slippage_pct ?? "-"}</p>
          <p data-testid="user-test-order-execution-time-ms">execution time ms: {testOrderResult?.execution_time_ms ?? "-"}</p>
          <p data-testid="user-test-order-volatility-regime">volatility regime: {testOrderResult?.volatility_regime || "-"}</p>
          <p data-testid="user-test-order-strategy-type">strategy type: {testOrderResult?.strategy_type || "-"}</p>
          <p className="sm:col-span-2" data-testid="user-test-order-validation-timestamp">validation timestamp: {readiness?.validation_timestamp || "-"}</p>
        </div>
      </div>
    </section>
  );
};