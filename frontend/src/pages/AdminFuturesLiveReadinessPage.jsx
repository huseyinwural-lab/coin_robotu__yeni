import { useCallback, useEffect, useMemo, useState } from "react";
import { toast } from "sonner";

import { Button } from "@/components/ui/button";
import { apiClient } from "@/lib/api";

export const AdminFuturesLiveReadinessPage = () => {
  const [loading, setLoading] = useState(true);
  const [errorMessage, setErrorMessage] = useState("");
  const [readinessPayload, setReadinessPayload] = useState(null);
  const [scorePayload, setScorePayload] = useState(null);

  const loadData = useCallback(async () => {
    setLoading(true);
    setErrorMessage("");
    try {
      const [readinessResponse, scoreResponse] = await Promise.all([
        apiClient.get("/admin/futures/live-readiness"),
        apiClient.get("/admin/futures/readiness-score"),
      ]);
      setReadinessPayload(readinessResponse.data || null);
      setScorePayload(scoreResponse.data || null);
    } catch (error) {
      const message = error?.response?.data?.detail || "Live readiness verisi alınamadı";
      setErrorMessage(message);
      toast.error(message);
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    loadData();
  }, [loadData]);

  const alerts = useMemo(() => readinessPayload?.alerts || [], [readinessPayload]);

  return (
    <section className="space-y-4" data-testid="admin-futures-live-readiness-page">
      <header className="border border-black/40 bg-orange-300 p-4" data-testid="live-readiness-header">
        <h2 className="text-4xl font-black uppercase tracking-tight text-black" data-testid="live-readiness-title">
          Futures Live Readiness
        </h2>
        <p className="mt-2 text-sm text-black/80" data-testid="live-readiness-description">
          Position/order/balance/latency doğrulaması ile go-live readiness görünümü.
        </p>
      </header>

      <div className="flex flex-wrap items-center gap-3 border border-black/30 bg-orange-100 p-4" data-testid="live-readiness-toolbar">
        <Button className="border border-black bg-black text-orange-400 hover:bg-zinc-800" onClick={loadData} data-testid="live-readiness-refresh-button">
          Yenile
        </Button>
        <p className="text-sm text-black" data-testid="live-readiness-loading-text">loading: {String(loading)}</p>
        <p className="text-sm text-black" data-testid="live-readiness-updated-at-text">
          updated_at: {readinessPayload?.generated_at ? new Date(readinessPayload.generated_at).toLocaleString() : "-"}
        </p>
      </div>

      {loading && <div className="border border-black/25 bg-orange-50 p-4 text-sm" data-testid="live-readiness-loading-state">Live readiness yükleniyor...</div>}
      {!loading && Boolean(errorMessage) && (
        <div className="border border-red-700 bg-red-100 p-4 text-sm text-red-900" data-testid="live-readiness-error-state">
          Hata: {errorMessage}
        </div>
      )}

      {!loading && !errorMessage && (
        <>
          <div className="grid gap-3 md:grid-cols-2 lg:grid-cols-4" data-testid="live-readiness-summary-grid">
            <div className="border border-black/25 bg-orange-100 p-3" data-testid="live-readiness-score-card">
              <p className="text-xs uppercase">Readiness Confidence Score</p>
              <p className="text-xl font-bold" data-testid="live-readiness-score-value">{scorePayload?.readiness_score ?? 0}</p>
            </div>
            <div className="border border-black/25 bg-orange-100 p-3" data-testid="live-readiness-state-card">
              <p className="text-xs uppercase">Readiness State</p>
              <p className="text-xl font-bold" data-testid="live-readiness-state-value">{scorePayload?.readiness_state || "BLOCKED"}</p>
            </div>
            <div className="border border-black/25 bg-orange-100 p-3" data-testid="live-readiness-alert-count-card">
              <p className="text-xs uppercase">Active Alerts</p>
              <p className="text-xl font-bold" data-testid="live-readiness-alert-count-value">{alerts.length}</p>
            </div>
            <div className="border border-black/25 bg-orange-100 p-3" data-testid="live-readiness-guard-card">
              <p className="text-xs uppercase">Guard Action</p>
              <p className="text-xl font-bold" data-testid="live-readiness-guard-value">{readinessPayload?.readiness_guard?.action || "ALLOW"}</p>
            </div>
          </div>

          <div className="grid gap-3 lg:grid-cols-2" data-testid="live-readiness-main-grid">
            <div className="border border-black/25 bg-orange-100 p-4" data-testid="live-readiness-position-sync-panel">
              <h3 className="text-lg font-bold" data-testid="live-readiness-position-sync-title">Position Sync Monitor</h3>
              <p className="mt-3 text-xs" data-testid="live-readiness-position-sync-state">
                state={readinessPayload?.position_sync_state || "UNVERIFIED"} · drifts={(readinessPayload?.position_sync?.position_drifts || []).length}
              </p>
            </div>
            <div className="border border-black/25 bg-orange-100 p-4" data-testid="live-readiness-order-reconciliation-panel">
              <h3 className="text-lg font-bold" data-testid="live-readiness-order-reconciliation-title">Order Reconciliation Monitor</h3>
              <p className="mt-3 text-xs" data-testid="live-readiness-order-reconciliation-state">
                state={readinessPayload?.order_reconciliation_state || "UNVERIFIED"} · issues={(readinessPayload?.order_reconciliation?.order_reconciliation_issues || []).length}
              </p>
            </div>
          </div>

          <div className="grid gap-3 lg:grid-cols-2" data-testid="live-readiness-secondary-grid">
            <div className="border border-black/25 bg-orange-100 p-4" data-testid="live-readiness-balance-integrity-panel">
              <h3 className="text-lg font-bold" data-testid="live-readiness-balance-integrity-title">Balance Integrity Monitor</h3>
              <p className="mt-3 text-xs" data-testid="live-readiness-balance-integrity-state">
                state={readinessPayload?.balance_integrity_state || "UNVERIFIED"} · drifts={(readinessPayload?.balance_integrity?.balance_drift || []).length}
              </p>
            </div>
            <div className="border border-black/25 bg-orange-100 p-4" data-testid="live-readiness-exchange-latency-panel">
              <h3 className="text-lg font-bold" data-testid="live-readiness-exchange-latency-title">Exchange Latency Chart</h3>
              <p className="mt-3 text-xs" data-testid="live-readiness-exchange-latency-state">
                state={readinessPayload?.exchange_latency_state || "ELEVATED"} · metrics={JSON.stringify(readinessPayload?.exchange_latency?.latency_metrics || {})}
              </p>
            </div>
          </div>

          <div className="border border-black/25 bg-orange-100 p-4" data-testid="live-readiness-alerts-panel">
            <h3 className="text-lg font-bold" data-testid="live-readiness-alerts-title">Active Readiness Alerts</h3>
            <div className="mt-3 space-y-1" data-testid="live-readiness-alerts-list">
              {alerts.map((item, index) => (
                <p className="text-xs" key={`${item?.event}-${index}`} data-testid={`live-readiness-alert-item-${index}`}>
                  {item?.event} · {item?.state || item?.readiness_state || "-"}
                </p>
              ))}
              {alerts.length === 0 && <p className="text-xs" data-testid="live-readiness-alert-empty">Aktif readiness alert yok.</p>}
            </div>
          </div>
        </>
      )}
    </section>
  );
};
