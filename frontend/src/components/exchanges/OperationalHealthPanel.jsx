import { Button } from "@/components/ui/button";

export const OperationalHealthPanel = ({ data, loading, error, onRefresh }) => {
  const scores = data?.operational_scores || [];

  return (
    <section className="rounded-2xl border border-slate-700 bg-slate-950/70 p-4" data-testid="operational-health-panel">
      <div className="mb-3 flex items-center justify-between gap-3">
        <div>
          <h3 className="text-base font-semibold text-orange-200" data-testid="operational-health-panel-title">Operational Health</h3>
          <p className="text-xs text-slate-400" data-testid="operational-health-panel-subtitle">Gerçek telemetry: latency, validation, rate-limit, websocket, orderbook</p>
        </div>
        <Button type="button" variant="outline" onClick={onRefresh} data-testid="operational-health-refresh-button">Yenile</Button>
      </div>

      <div className="mb-3 grid gap-2 text-xs text-slate-300 md:grid-cols-3" data-testid="operational-health-summary-grid">
        <p data-testid="operational-health-net-status">net_status: {data?.net_status || "n/a"}</p>
        <p data-testid="operational-health-generated-at">generated_at: {data?.generated_at || "n/a"}</p>
        <p data-testid="operational-health-reason-codes">reason_codes: {(data?.reason_codes || []).join(", ") || "-"}</p>
      </div>

      {loading && <p className="text-sm text-slate-400" data-testid="operational-health-loading-state">Yükleniyor...</p>}
      {!loading && error && <p className="text-sm text-red-300" data-testid="operational-health-error-state">{error}</p>}
      {!loading && !error && scores.length === 0 && (
        <p className="text-sm text-slate-400" data-testid="operational-health-empty-state">Operational health verisi bulunamadı.</p>
      )}

      {!loading && !error && scores.length > 0 && (
        <div className="overflow-x-auto" data-testid="operational-health-table-wrapper">
          <table className="min-w-full text-left text-xs" data-testid="operational-health-table">
            <thead className="text-slate-400">
              <tr>
                <th className="py-2 pr-3">Exchange</th>
                <th className="py-2 pr-3">Score</th>
                <th className="py-2 pr-3">Latency p95</th>
                <th className="py-2 pr-3">Validation %</th>
                <th className="py-2 pr-3">Rate Limit</th>
                <th className="py-2 pr-3">WS</th>
                <th className="py-2 pr-3">Orderbook</th>
                <th className="py-2 pr-3">Reason Codes</th>
              </tr>
            </thead>
            <tbody>
              {scores.map((row) => (
                <tr key={row.exchange} className="border-t border-slate-800" data-testid={`operational-health-row-${row.exchange}`}>
                  <td className="py-2 pr-3 font-medium text-slate-100" data-testid={`operational-health-row-exchange-${row.exchange}`}>{row.exchange}</td>
                  <td className="py-2 pr-3" data-testid={`operational-health-row-score-${row.exchange}`}>{row.health_score}</td>
                  <td className="py-2 pr-3" data-testid={`operational-health-row-latency-${row.exchange}`}>{row.latency_ms_p95 ?? "-"}</td>
                  <td className="py-2 pr-3" data-testid={`operational-health-row-validation-${row.exchange}`}>{row.validation_success_rate ?? "-"}</td>
                  <td className="py-2 pr-3" data-testid={`operational-health-row-rate-limit-${row.exchange}`}>{row.rate_limit_pressure ?? "-"}</td>
                  <td className="py-2 pr-3" data-testid={`operational-health-row-ws-${row.exchange}`}>{row.websocket_sync_health || "unknown"}</td>
                  <td className="py-2 pr-3" data-testid={`operational-health-row-orderbook-${row.exchange}`}>{row.orderbook_sync_health || "unknown"}</td>
                  <td className="py-2 pr-3" data-testid={`operational-health-row-reasons-${row.exchange}`}>{(row.reason_codes || []).join(", ") || "-"}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
    </section>
  );
};
