import { useMemo, useState } from "react";

import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";

export const CapabilityDiscoveryPanel = ({ exchanges, result, loading, error, onRunDiscovery }) => {
  const exchangeOptions = useMemo(() => (exchanges || []).map((item) => item.exchange_code), [exchanges]);
  const [form, setForm] = useState({
    exchange_code: exchangeOptions[0] || "binance",
    market_type: "spot",
    environment: "testnet",
    symbols: "BTCUSDT,ETHUSDT",
  });

  const submit = async (event) => {
    event.preventDefault();
    await onRunDiscovery({
      ...form,
      symbols: String(form.symbols || "")
        .split(",")
        .map((item) => item.trim().toUpperCase())
        .filter(Boolean),
    });
  };

  return (
    <section className="rounded-2xl border border-slate-700 bg-slate-950/70 p-4" data-testid="capability-discovery-panel">
      <h3 className="text-base font-semibold text-orange-200" data-testid="capability-discovery-panel-title">Capability Discovery</h3>
      <p className="mb-3 text-xs text-slate-400" data-testid="capability-discovery-panel-subtitle">Adapter üzerinden sembol capability keşfi</p>

      <form className="grid gap-2 md:grid-cols-4" onSubmit={submit} data-testid="capability-discovery-form">
        <select value={form.exchange_code} onChange={(event) => setForm((prev) => ({ ...prev, exchange_code: event.target.value }))} className="rounded-md border border-slate-700 bg-slate-900 px-2 py-2 text-sm" data-testid="capability-discovery-exchange-select">
          {(exchangeOptions.length ? exchangeOptions : ["binance"]).map((code) => (
            <option key={code} value={code}>{code}</option>
          ))}
        </select>
        <select value={form.market_type} onChange={(event) => setForm((prev) => ({ ...prev, market_type: event.target.value }))} className="rounded-md border border-slate-700 bg-slate-900 px-2 py-2 text-sm" data-testid="capability-discovery-market-type-select">
          <option value="spot">spot</option>
          <option value="futures">futures</option>
        </select>
        <select value={form.environment} onChange={(event) => setForm((prev) => ({ ...prev, environment: event.target.value }))} className="rounded-md border border-slate-700 bg-slate-900 px-2 py-2 text-sm" data-testid="capability-discovery-environment-select">
          <option value="testnet">testnet</option>
          <option value="live">live</option>
        </select>
        <Input value={form.symbols} onChange={(event) => setForm((prev) => ({ ...prev, symbols: event.target.value }))} placeholder="BTCUSDT,ETHUSDT" data-testid="capability-discovery-symbols-input" />
        <Button className="md:col-span-4" disabled={loading} data-testid="capability-discovery-run-button">{loading ? "Çalışıyor..." : "Discovery Çalıştır"}</Button>
      </form>

      {loading && <p className="mt-3 text-sm text-slate-400" data-testid="capability-discovery-loading-state">Yükleniyor...</p>}
      {!loading && error && <p className="mt-3 text-sm text-red-300" data-testid="capability-discovery-error-state">{error}</p>}
      {!loading && !error && !result && <p className="mt-3 text-sm text-slate-400" data-testid="capability-discovery-empty-state">Henüz discovery sonucu yok.</p>}
      {!loading && !error && result && (
        <div className="mt-3 space-y-1 text-xs text-slate-200" data-testid="capability-discovery-result-state">
          <p data-testid="capability-discovery-result-net-status">net_status: {result.net_status}</p>
          <p data-testid="capability-discovery-result-reasons">reason_codes: {(result.reason_codes || []).join(", ") || "-"}</p>
          <p data-testid="capability-discovery-result-symbol-count">symbol_count: {(result.capability?.symbol_capabilities || []).length}</p>
        </div>
      )}
    </section>
  );
};
