import { Button } from "@/components/ui/button";

export const ConflictDetectionPanel = ({ data, loading, error, onRefresh }) => {
  const blockingAlerts = data?.blocking_alerts || [];
  const warningAlerts = data?.warning_alerts || [];

  return (
    <section className="rounded-2xl border border-red-500/30 bg-slate-950/80 p-4" data-testid="conflict-detection-panel">
      <div className="mb-3 flex items-center justify-between gap-2">
        <div>
          <h3 className="text-base font-semibold text-red-200" data-testid="conflict-detection-title">Conflict Detection Center (P2-402 Skeleton)</h3>
          <p className="text-xs text-slate-400" data-testid="conflict-detection-subtitle">Policy/routing/capability çakışmaları için blocking alert merkezi</p>
        </div>
        <Button type="button" variant="outline" onClick={onRefresh} data-testid="conflict-detection-refresh-button">Yenile</Button>
      </div>

      {loading && <p className="text-sm text-slate-400" data-testid="conflict-detection-loading-state">Yükleniyor...</p>}
      {!loading && error && <p className="text-sm text-red-300" data-testid="conflict-detection-error-state">{error}</p>}

      {!loading && !error && (
        <>
          <p className="mb-2 text-xs text-slate-200" data-testid="conflict-detection-net-status">net_status: {data?.net_status || "PASS"}</p>
          <p className="mb-2 text-xs text-slate-300" data-testid="conflict-detection-summary">total={data?.summary?.total_alerts ?? 0}, block={data?.summary?.block_count ?? 0}, warn={data?.summary?.warn_count ?? 0}</p>

          <div className="mb-3" data-testid="conflict-detection-blocking-alerts-list">
            <p className="text-xs font-semibold text-red-200" data-testid="conflict-detection-blocking-alerts-title">Blocking Alerts</p>
            {blockingAlerts.length === 0 && <p className="text-xs text-slate-400" data-testid="conflict-detection-blocking-alerts-empty">Blocking alert yok.</p>}
            {blockingAlerts.map((item, index) => (
              <p key={`${item.entity_id}-${index}`} className="border-t border-slate-800 py-1 text-xs text-red-200" data-testid={`conflict-detection-blocking-alert-${index}`}>
                [{item.reason_code}] {item.entity_id} — {item.message}
              </p>
            ))}
          </div>

          <div data-testid="conflict-detection-warning-alerts-list">
            <p className="text-xs font-semibold text-yellow-200" data-testid="conflict-detection-warning-alerts-title">Warning Alerts</p>
            {warningAlerts.length === 0 && <p className="text-xs text-slate-400" data-testid="conflict-detection-warning-alerts-empty">Warning alert yok.</p>}
            {warningAlerts.map((item, index) => (
              <p key={`${item.entity_id}-${index}`} className="border-t border-slate-800 py-1 text-xs text-yellow-200" data-testid={`conflict-detection-warning-alert-${index}`}>
                [{item.reason_code}] {item.entity_id} — {item.message}
              </p>
            ))}
          </div>
        </>
      )}
    </section>
  );
};
