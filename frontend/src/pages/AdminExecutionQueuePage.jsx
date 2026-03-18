import { useCallback, useEffect, useMemo, useState } from "react";
import { toast } from "sonner";

import { LoadingSkeleton } from "@/components/LoadingSkeleton";
import { Button } from "@/components/ui/button";
import { apiClient } from "@/lib/api";

export const AdminExecutionQueuePage = () => {
  const [queueRows, setQueueRows] = useState([]);
  const [rejectionSummary, setRejectionSummary] = useState([]);
  const [queueSnapshot, setQueueSnapshot] = useState(null);
  const [isLoading, setIsLoading] = useState(true);
  const [statusFilter, setStatusFilter] = useState("all");
  const [loadError, setLoadError] = useState("");
  const [decisionIntentId, setDecisionIntentId] = useState("");
  const [ownerRevalidateIntentId, setOwnerRevalidateIntentId] = useState("");

  const extractErrorMessage = (error, fallbackText) => {
    const detail = error?.response?.data?.detail;
    if (typeof detail === "string" && detail.trim()) {
      return detail;
    }
    if (detail && typeof detail === "object") {
      const failureCode = detail.failure_code || detail.code;
      const message = detail.message;
      if (failureCode && message) {
        return `${failureCode}: ${message}`;
      }
      if (failureCode) {
        return String(failureCode);
      }
      if (message) {
        return String(message);
      }
    }
    return fallbackText;
  };

  const load = useCallback(async () => {
    setIsLoading(true);
    setLoadError("");
    try {
      const [{ data }, { data: summaryData }] = await Promise.all([
        apiClient.get("/admin/execution-queue", { params: { status_filter: statusFilter, limit: 200 } }),
        apiClient.get("/admin/execution-queue/rejection-summary", { params: { limit: 500 } }),
      ]);
      setQueueRows(data || []);
      setRejectionSummary(summaryData?.rejection_reason_distribution || []);
      setQueueSnapshot(summaryData?.queue || null);
    } catch (error) {
      const message = error?.response?.data?.detail || "Execution queue verisi yüklenemedi";
      setLoadError(message);
      toast.error(message);
    } finally {
      setIsLoading(false);
    }
  }, [statusFilter]);

  useEffect(() => {
    load();
  }, [load]);

  const summary = useMemo(() => {
    const statusCounts = queueRows.reduce((acc, row) => {
      const key = row.status || "UNKNOWN";
      acc[key] = (acc[key] || 0) + 1;
      return acc;
    }, {});
    const queuedCount = statusCounts.QUEUED || 0;
    const rejectedCount = statusCounts.REJECTED || 0;
    const riskyCount = queueRows.filter((row) => (row.risk_flags || []).length > 0).length;
    return {
      total: queueRows.length,
      queuedCount,
      rejectedCount,
      riskyCount,
    };
  }, [queueRows]);

  const decide = async (intentId, action) => {
    setDecisionIntentId(intentId);
    try {
      await apiClient.post(`/admin/execution-queue/${intentId}/${action}`, { note: `${action}_from_admin_ui` });
      toast.success(`Intent ${action} edildi`);
      await load();
    } catch (error) {
      toast.error(extractErrorMessage(error, `Intent ${action} başarısız`));
    } finally {
      setDecisionIntentId("");
    }
  };

  const retryRejected = async (intentId) => {
    setDecisionIntentId(intentId);
    try {
      await apiClient.post(`/admin/execution-queue/${intentId}/retry`, { note: "retry_from_admin_ui" });
      toast.success("Intent yeniden kuyruğa alındı");
      await load();
    } catch (error) {
      toast.error(extractErrorMessage(error, "Retry başarısız"));
    } finally {
      setDecisionIntentId("");
    }
  };

  const revalidateIntentOwner = async (intentId) => {
    setOwnerRevalidateIntentId(intentId);
    try {
      const { data } = await apiClient.post(`/admin/execution-queue/${intentId}/owner-revalidate`);
      const reasonCodes = (data?.reason_codes || []).join(", ") || "none";
      toast.success(`Owner revalidate: can_trade=${String(Boolean(data?.can_trade))} · reason_codes=${reasonCodes}`);
      await load();
    } catch (error) {
      toast.error(extractErrorMessage(error, "Owner revalidate başarısız"));
    } finally {
      setOwnerRevalidateIntentId("");
    }
  };

  if (isLoading) {
    return <LoadingSkeleton rows={8} testId="admin-execution-queue-loading-skeleton" />;
  }

  if (loadError && queueRows.length === 0) {
    return (
      <section className="space-y-4" data-testid="admin-execution-queue-broken-state">
        <div className="border border-rose-500/40 bg-rose-900/20 p-4" data-testid="admin-execution-queue-broken-alert">
          <p className="text-sm font-semibold text-rose-200" data-testid="admin-execution-queue-broken-title">Execution Queue alınamadı</p>
          <p className="mt-1 text-sm text-rose-100" data-testid="admin-execution-queue-broken-message">{loadError}</p>
          <Button className="mt-3" onClick={load} data-testid="admin-execution-queue-broken-retry-button">Tekrar Dene</Button>
        </div>
      </section>
    );
  }

  return (
    <section className="space-y-4" data-testid="admin-execution-queue-page">
      <header className="border border-slate-800 bg-slate-900 p-4" data-testid="admin-execution-queue-header">
        <div className="flex flex-wrap items-start justify-between gap-3" data-testid="admin-execution-queue-header-row">
          <div data-testid="admin-execution-queue-header-left">
            <h2 className="text-4xl font-black uppercase tracking-tight" data-testid="admin-execution-queue-title">Execution Queue</h2>
            <p className="mt-2 text-sm text-slate-400" data-testid="admin-execution-queue-description">Assisted execution intent kuyruk yönetimi.</p>
          </div>
          <div className="flex items-center gap-2" data-testid="admin-execution-queue-controls">
            <label className="text-xs text-slate-500" htmlFor="admin-execution-queue-status-filter" data-testid="admin-execution-queue-filter-label">Durum</label>
            <select
              id="admin-execution-queue-status-filter"
              value={statusFilter}
              onChange={(event) => setStatusFilter(event.target.value)}
              className="h-9 rounded border border-slate-700 bg-slate-950 px-2 text-sm"
              data-testid="admin-execution-queue-status-filter-select"
            >
              <option value="all" data-testid="admin-execution-queue-status-filter-option-all">All</option>
              <option value="QUEUED" data-testid="admin-execution-queue-status-filter-option-queued">QUEUED</option>
              <option value="RELEASED" data-testid="admin-execution-queue-status-filter-option-released">RELEASED</option>
              <option value="REJECTED" data-testid="admin-execution-queue-status-filter-option-rejected">REJECTED</option>
              <option value="CANCELLED" data-testid="admin-execution-queue-status-filter-option-cancelled">CANCELLED</option>
            </select>
            <Button onClick={load} data-testid="admin-execution-queue-refresh-button">Yenile</Button>
          </div>
        </div>
      </header>

      {loadError && (
        <div className="border border-amber-500/40 bg-amber-950/20 p-3 text-sm text-amber-200" data-testid="admin-execution-queue-warning-alert">
          Son yenileme sırasında hata oluştu: {loadError}
        </div>
      )}

      <div className="grid gap-3 md:grid-cols-4" data-testid="admin-execution-queue-summary-grid">
        <article className="border border-slate-800 bg-slate-900 p-3" data-testid="admin-execution-queue-summary-total-card">
          <p className="text-xs text-slate-500">Toplam Kayıt</p>
          <p className="text-xl font-semibold" data-testid="admin-execution-queue-summary-total-value">{summary.total}</p>
        </article>
        <article className="border border-slate-800 bg-slate-900 p-3" data-testid="admin-execution-queue-summary-queued-card">
          <p className="text-xs text-slate-500">Queued</p>
          <p className="text-xl font-semibold" data-testid="admin-execution-queue-summary-queued-value">{summary.queuedCount}</p>
        </article>
        <article className="border border-slate-800 bg-slate-900 p-3" data-testid="admin-execution-queue-summary-rejected-card">
          <p className="text-xs text-slate-500">Rejected</p>
          <p className="text-xl font-semibold" data-testid="admin-execution-queue-summary-rejected-value">{summary.rejectedCount}</p>
        </article>
        <article className="border border-slate-800 bg-slate-900 p-3" data-testid="admin-execution-queue-summary-risky-card">
          <p className="text-xs text-slate-500">Risk Flag İçeren</p>
          <p className="text-xl font-semibold" data-testid="admin-execution-queue-summary-risky-value">{summary.riskyCount}</p>
        </article>
      </div>

      <section className="border border-slate-800 bg-slate-900 p-4" data-testid="admin-execution-queue-rejection-summary-panel">
        <div className="flex flex-wrap items-center justify-between gap-2" data-testid="admin-execution-queue-rejection-summary-header-row">
          <p className="text-xs uppercase tracking-widest text-slate-500" data-testid="admin-execution-queue-rejection-summary-title">Rejected Intent Root-Cause Summary</p>
          <p className="text-xs text-slate-400" data-testid="admin-execution-queue-rejection-summary-queue-snapshot">queued={queueSnapshot?.queued ?? 0} · rejected={queueSnapshot?.rejected ?? 0} · total={queueSnapshot?.total ?? 0}</p>
        </div>
        <div className="mt-3 grid gap-2 sm:grid-cols-2 lg:grid-cols-3" data-testid="admin-execution-queue-rejection-summary-grid">
          {rejectionSummary.slice(0, 12).map((item, index) => (
            <div key={`${item.reason_code}-${index}`} className="border border-slate-700 p-2 text-xs" data-testid={`admin-execution-queue-rejection-reason-${index}`}>
              {item.reason_code}: {item.count}
            </div>
          ))}
          {rejectionSummary.length === 0 && <p className="text-xs text-slate-400" data-testid="admin-execution-queue-rejection-summary-empty">Rejected reason dağılımı yok.</p>}
        </div>
      </section>

      <div className="overflow-x-auto border border-slate-800 bg-slate-900" data-testid="admin-execution-queue-table-wrapper">
        <table className="min-w-full text-sm" data-testid="admin-execution-queue-table" aria-label="Execution queue tablosu">
          <thead className="sticky top-0 z-20 bg-slate-800 text-left" data-testid="admin-execution-queue-table-head">
            <tr>
              <th className="px-3 py-2">Intent</th>
              <th className="px-3 py-2">User</th>
              <th className="px-3 py-2">Intent Type</th>
              <th className="px-3 py-2">Position</th>
              <th className="px-3 py-2">Symbol</th>
              <th className="px-3 py-2">Market</th>
              <th className="px-3 py-2">Side</th>
              <th className="px-3 py-2">Notional</th>
              <th className="px-3 py-2">Status</th>
              <th className="px-3 py-2">Risk Flags</th>
              <th className="px-3 py-2">Created</th>
              <th className="px-3 py-2">Actions</th>
            </tr>
          </thead>
          <tbody data-testid="admin-execution-queue-table-body">
            {queueRows.map((row) => (
              <tr key={row.id} className="border-t border-slate-800" data-testid={`admin-execution-queue-row-${row.id}`}>
                <td className="px-3 py-2" data-testid={`admin-execution-queue-row-intent-${row.id}`}>{row.id}</td>
                <td className="px-3 py-2" data-testid={`admin-execution-queue-row-user-${row.id}`}>{row.user_email || row.user_id}</td>
                <td className="px-3 py-2" data-testid={`admin-execution-queue-row-intent-type-${row.id}`}>{row.intent_type || "OPEN_POSITION"}</td>
                <td className="px-3 py-2" data-testid={`admin-execution-queue-row-position-${row.id}`}>{row.position_id || "-"}</td>
                <td className="px-3 py-2" data-testid={`admin-execution-queue-row-symbol-${row.id}`}>{row.symbol}</td>
                <td className="px-3 py-2" data-testid={`admin-execution-queue-row-market-${row.id}`}>{row.market_type}</td>
                <td className="px-3 py-2" data-testid={`admin-execution-queue-row-side-${row.id}`}>{row.side}</td>
                <td className="px-3 py-2" data-testid={`admin-execution-queue-row-notional-${row.id}`}>{row.notional}</td>
                <td className="px-3 py-2" data-testid={`admin-execution-queue-row-status-${row.id}`}>{row.status}</td>
                <td className="px-3 py-2" data-testid={`admin-execution-queue-row-risk-flags-${row.id}`}>{(row.risk_flags || []).join(", ") || "-"}</td>
                <td className="px-3 py-2" data-testid={`admin-execution-queue-row-created-at-${row.id}`}>{new Date(row.created_at).toLocaleString()}</td>
                <td className="px-3 py-2">
                  {row.status === "QUEUED" ? (
                    <div className="space-y-2" data-testid={`admin-execution-queue-actions-${row.id}`}>
                      <div className="flex gap-2" data-testid={`admin-execution-queue-actions-primary-${row.id}`}>
                        <Button className="bg-emerald-500 text-black hover:bg-emerald-400" onClick={() => decide(row.id, "approve")} disabled={decisionIntentId === row.id} data-testid={`admin-execution-queue-approve-button-${row.id}`}>Approve</Button>
                        <Button variant="outline" onClick={() => decide(row.id, "reject")} disabled={decisionIntentId === row.id} data-testid={`admin-execution-queue-reject-button-${row.id}`}>Reject</Button>
                      </div>
                      <div className="rounded border border-amber-600/40 bg-amber-950/20 p-2" data-testid={`admin-execution-queue-423-helper-${row.id}`}>
                        <p className="text-[11px] text-amber-100" data-testid={`admin-execution-queue-423-helper-text-${row.id}`}>
                          Neden 423 alırım? Bu intent sahibinin connection readiness/can_trade durumu fail ise approve bloklanır.
                        </p>
                        <Button
                          type="button"
                          size="sm"
                          variant="outline"
                          className="mt-2"
                          onClick={() => revalidateIntentOwner(row.id)}
                          disabled={ownerRevalidateIntentId === row.id}
                          data-testid={`admin-execution-queue-owner-revalidate-button-${row.id}`}
                        >
                          {ownerRevalidateIntentId === row.id ? "Revalidate..." : "Tek Tık Revalidate"}
                        </Button>
                      </div>
                    </div>
                  ) : row.status === "REJECTED" ? (
                    <div className="flex gap-2" data-testid={`admin-execution-queue-retry-actions-${row.id}`}>
                      <Button variant="outline" onClick={() => retryRejected(row.id)} disabled={decisionIntentId === row.id} data-testid={`admin-execution-queue-retry-button-${row.id}`}>
                        Retry
                      </Button>
                    </div>
                  ) : (
                    <span className="text-xs text-slate-400" data-testid={`admin-execution-queue-final-status-${row.id}`}>{row.status}</span>
                  )}
                </td>
              </tr>
            ))}
            {queueRows.length === 0 && (
              <tr className="border-t border-slate-800" data-testid="admin-execution-queue-empty-row">
                <td colSpan={12} className="px-3 py-4 text-center text-sm text-slate-400" data-testid="admin-execution-queue-empty-text">Bu filtre için kuyruk kaydı bulunamadı.</td>
              </tr>
            )}
          </tbody>
        </table>
      </div>
    </section>
  );
};