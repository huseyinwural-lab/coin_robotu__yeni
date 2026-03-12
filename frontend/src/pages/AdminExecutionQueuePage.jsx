import { useEffect, useState } from "react";
import { toast } from "sonner";

import { LoadingSkeleton } from "@/components/LoadingSkeleton";
import { Button } from "@/components/ui/button";
import { apiClient } from "@/lib/api";

export const AdminExecutionQueuePage = () => {
  const [queueRows, setQueueRows] = useState([]);
  const [isLoading, setIsLoading] = useState(true);

  const load = async () => {
    setIsLoading(true);
    const { data } = await apiClient.get("/admin/execution-queue", { params: { status_filter: "all", limit: 200 } });
    setQueueRows(data || []);
    setIsLoading(false);
  };

  useEffect(() => {
    load();
  }, []);

  const decide = async (intentId, action) => {
    try {
      await apiClient.post(`/admin/execution-queue/${intentId}/${action}`, { note: `${action}_from_admin_ui` });
      toast.success(`Intent ${action} edildi`);
      await load();
    } catch (error) {
      toast.error(error?.response?.data?.detail || `Intent ${action} başarısız`);
    }
  };

  if (isLoading) {
    return <LoadingSkeleton rows={8} testId="admin-execution-queue-loading-skeleton" />;
  }

  return (
    <section className="space-y-4" data-testid="admin-execution-queue-page">
      <header className="border border-slate-800 bg-slate-900 p-4" data-testid="admin-execution-queue-header">
        <h2 className="text-4xl font-black uppercase tracking-tight" data-testid="admin-execution-queue-title">Execution Queue</h2>
        <p className="mt-2 text-sm text-slate-400" data-testid="admin-execution-queue-description">Assisted execution intent kuyruk yönetimi.</p>
      </header>

      <div className="overflow-x-auto border border-slate-800 bg-slate-900" data-testid="admin-execution-queue-table-wrapper">
        <table className="min-w-full text-sm" data-testid="admin-execution-queue-table" aria-label="Execution queue tablosu">
          <thead className="bg-slate-800 text-left" data-testid="admin-execution-queue-table-head">
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
                <td className="px-3 py-2">
                  {row.status === "QUEUED" ? (
                    <div className="flex gap-2" data-testid={`admin-execution-queue-actions-${row.id}`}>
                      <Button className="bg-emerald-500 text-black hover:bg-emerald-400" onClick={() => decide(row.id, "approve")} data-testid={`admin-execution-queue-approve-button-${row.id}`}>Approve</Button>
                      <Button variant="outline" onClick={() => decide(row.id, "reject")} data-testid={`admin-execution-queue-reject-button-${row.id}`}>Reject</Button>
                    </div>
                  ) : (
                    <span className="text-xs text-slate-400" data-testid={`admin-execution-queue-final-status-${row.id}`}>{row.status}</span>
                  )}
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </section>
  );
};