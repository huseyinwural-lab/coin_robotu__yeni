import { useState } from "react";

import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";

const defaultForm = {
  user_id: "",
  strategy_id: "",
  symbol: "BTCUSDT",
  market_type: "spot",
  environment: "testnet",
  order_side: "BUY",
  order_size_usd: 100,
};

export const RoutingPreviewPanel = ({ approvedUsers, previewResult, loading, error, onRunPreview }) => {
  const [form, setForm] = useState(defaultForm);

  const submit = async (event) => {
    event.preventDefault();
    await onRunPreview({ ...form, order_size_usd: Number(form.order_size_usd || 0) });
  };

  return (
    <section className="rounded-2xl border border-slate-700 bg-slate-950/70 p-4" data-testid="routing-preview-panel">
      <h3 className="text-base font-semibold text-orange-200" data-testid="routing-preview-panel-title">Routing Preview v2</h3>
      <p className="mb-3 text-xs text-slate-400" data-testid="routing-preview-panel-subtitle">Explainable route + alternatif path + policy/capability/health etkisi</p>

      <form className="grid gap-2 md:grid-cols-4" onSubmit={submit} data-testid="routing-preview-form">
        <select
          value={form.user_id}
          onChange={(event) => setForm((prev) => ({ ...prev, user_id: event.target.value }))}
          className="rounded-md border border-slate-700 bg-slate-900 px-2 py-2 text-sm"
          data-testid="routing-preview-user-select"
          required
        >
          <option value="">Kullanıcı seç</option>
          {(approvedUsers || []).map((user) => (
            <option key={user.id} value={user.id}>{user.email}</option>
          ))}
        </select>
        <Input value={form.strategy_id} onChange={(event) => setForm((prev) => ({ ...prev, strategy_id: event.target.value }))} placeholder="strategy_id" data-testid="routing-preview-strategy-input" required />
        <Input value={form.symbol} onChange={(event) => setForm((prev) => ({ ...prev, symbol: event.target.value.toUpperCase() }))} placeholder="BTCUSDT" data-testid="routing-preview-symbol-input" required />
        <Input type="number" value={form.order_size_usd} onChange={(event) => setForm((prev) => ({ ...prev, order_size_usd: event.target.value }))} placeholder="100" data-testid="routing-preview-order-size-input" required />

        <select value={form.market_type} onChange={(event) => setForm((prev) => ({ ...prev, market_type: event.target.value }))} className="rounded-md border border-slate-700 bg-slate-900 px-2 py-2 text-sm" data-testid="routing-preview-market-type-select">
          <option value="spot">spot</option>
          <option value="futures">futures</option>
        </select>
        <select value={form.environment} onChange={(event) => setForm((prev) => ({ ...prev, environment: event.target.value }))} className="rounded-md border border-slate-700 bg-slate-900 px-2 py-2 text-sm" data-testid="routing-preview-environment-select">
          <option value="testnet">testnet</option>
          <option value="live">live</option>
        </select>
        <select value={form.order_side} onChange={(event) => setForm((prev) => ({ ...prev, order_side: event.target.value }))} className="rounded-md border border-slate-700 bg-slate-900 px-2 py-2 text-sm" data-testid="routing-preview-order-side-select">
          <option value="BUY">BUY</option>
          <option value="SELL">SELL</option>
        </select>
        <Button disabled={loading} data-testid="routing-preview-run-button">{loading ? "Çalışıyor..." : "Preview Çalıştır"}</Button>
      </form>

      {error && <p className="mt-3 text-sm text-red-300" data-testid="routing-preview-error-state">{error}</p>}
      {!error && !previewResult && !loading && (
        <p className="mt-3 text-sm text-slate-400" data-testid="routing-preview-empty-state">Henüz preview sonucu yok.</p>
      )}

      {previewResult && (
        <div className="mt-3 space-y-2 text-xs text-slate-200" data-testid="routing-preview-result-state">
          <p data-testid="routing-preview-net-status">net_status: {previewResult.net_status}</p>
          <p data-testid="routing-preview-explainability">explainability: {previewResult.explainability || "-"}</p>
          <p data-testid="routing-preview-selected-path">selected: {previewResult.selected_path?.exchange || "-"} / score: {previewResult.selected_path?.route_score ?? "-"}</p>

          <div data-testid="routing-preview-decision-factors-list">
            <p className="font-semibold text-slate-100">Decision Factors</p>
            {(previewResult.decision_factors || []).length === 0 && <p data-testid="routing-preview-decision-factors-empty">-</p>}
            {(previewResult.decision_factors || []).map((factor, index) => (
              <p key={`${factor.name}-${index}`} data-testid={`routing-preview-decision-factor-${index}`}>
                {factor.name}: {factor.status} ({factor.detail})
              </p>
            ))}
          </div>

          <div data-testid="routing-preview-alternative-paths-list">
            <p className="font-semibold text-slate-100">Alternative Paths</p>
            {(previewResult.alternative_paths || []).length === 0 && <p data-testid="routing-preview-alternative-paths-empty">Alternatif path yok.</p>}
            {(previewResult.alternative_paths || []).map((path, index) => (
              <p key={`${path.exchange}-${index}`} data-testid={`routing-preview-alternative-path-${index}`}>
                {path.exchange}: {path.status} / score={path.route_score} / reasons={(path.reason_codes || []).join(", ") || "-"}
              </p>
            ))}
          </div>
        </div>
      )}
    </section>
  );
};
