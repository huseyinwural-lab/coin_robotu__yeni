import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";

const eventBadgeClass = (action) => {
  const normalized = String(action || "").toLowerCase();
  if (normalized.includes("approve") || normalized.includes("promoted")) return "border-emerald-600 text-emerald-200";
  if (normalized.includes("reject")) return "border-red-600 text-red-200";
  if (normalized.includes("rollback")) return "border-amber-600 text-amber-200";
  return "border-slate-600 text-slate-200";
};

const resolveTargetVersion = (item) => {
  const details = item?.details || {};
  return (
    details.strategy_version_id
    || details.to_version_id
    || details.current_active_version_id
    || details.previous_active_version_id
    || "-"
  );
};

const resolveRollbackStateClass = (item) => {
  const state = String(item?.lifecycle_state || "").toLowerCase();
  if (state === "production") return "border-emerald-600 text-emerald-200";
  if (state === "rolled_back") return "border-red-600 text-red-200";
  if (state === "validated") return "border-amber-600 text-amber-200";
  return "border-slate-600 text-slate-200";
};

export const StrategyAuditHistory = ({
  auditPanelTab,
  setAuditPanelTab,
  auditFilters,
  setAuditFilters,
  filteredTimelineItems,
  onExportAuditHistory,
  rollbackChain,
}) => {
  return (
    <div className="space-y-2 border border-slate-800 bg-slate-900 p-4" data-testid="admin-strategy-audit-panel">
      <p className="text-xs uppercase tracking-widest text-slate-500" data-testid="admin-strategy-audit-title">Audit / History</p>

      <div className="flex flex-wrap gap-2" data-testid="admin-strategy-audit-tab-buttons">
        <Button
          type="button"
          variant="outline"
          className={auditPanelTab === "audit" ? "border-orange-500 text-orange-200" : "border-slate-600 text-slate-200"}
          onClick={() => setAuditPanelTab("audit")}
          data-testid="admin-strategy-audit-tab-audit-button"
        >
          Audit Trail
        </Button>
        <Button
          type="button"
          variant="outline"
          className={auditPanelTab === "history" ? "border-orange-500 text-orange-200" : "border-slate-600 text-slate-200"}
          onClick={() => setAuditPanelTab("history")}
          data-testid="admin-strategy-audit-tab-history-button"
        >
          Rollback History
        </Button>
      </div>

      {auditPanelTab === "audit" ? (
        <>
          <div className="grid gap-2 md:grid-cols-4" data-testid="admin-strategy-audit-filter-row">
            <Input placeholder="event type" value={auditFilters.eventType} onChange={(e) => setAuditFilters((prev) => ({ ...prev, eventType: e.target.value }))} data-testid="admin-strategy-audit-filter-event-type-input" />
            <Input placeholder="user" value={auditFilters.user} onChange={(e) => setAuditFilters((prev) => ({ ...prev, user: e.target.value }))} data-testid="admin-strategy-audit-filter-user-input" />
            <Input type="datetime-local" value={auditFilters.from} onChange={(e) => setAuditFilters((prev) => ({ ...prev, from: e.target.value }))} data-testid="admin-strategy-audit-filter-from-input" />
            <Input type="datetime-local" value={auditFilters.to} onChange={(e) => setAuditFilters((prev) => ({ ...prev, to: e.target.value }))} data-testid="admin-strategy-audit-filter-to-input" />
          </div>

          <div className="flex flex-wrap gap-2" data-testid="admin-strategy-audit-export-actions">
            <Button variant="outline" className="border-slate-500 text-slate-100" onClick={() => onExportAuditHistory("json")} data-testid="admin-strategy-audit-export-json-button">Export JSON</Button>
            <Button variant="outline" className="border-slate-500 text-slate-100" onClick={() => onExportAuditHistory("csv")} data-testid="admin-strategy-audit-export-csv-button">Export CSV</Button>
          </div>

          <div className="space-y-2" data-testid="admin-strategy-audit-list">
            {filteredTimelineItems.map((item, idx) => {
              const isApprovalEvent = String(item.action || "").toLowerCase().includes("approve")
                || String(item.action || "").toLowerCase().includes("promoted");
              return (
                <div
                  key={`${item.audit_id}-${idx}`}
                  className={`border p-2 text-xs ${isApprovalEvent ? "border-emerald-700 bg-emerald-950/20" : "border-slate-700"}`}
                  data-testid={`admin-strategy-audit-row-${idx}`}
                >
                  <div className="mb-1 flex flex-wrap items-center gap-2">
                    <span className={`rounded-full border px-2 py-1 text-[10px] uppercase ${eventBadgeClass(item.action)}`} data-testid={`admin-strategy-audit-action-badge-${idx}`}>
                      {item.action}
                    </span>
                    {isApprovalEvent && (
                      <span className="rounded-full border border-emerald-600 px-2 py-1 text-[10px] uppercase text-emerald-200" data-testid={`admin-strategy-audit-approval-highlight-${idx}`}>
                        APPROVAL TRAIL
                      </span>
                    )}
                  </div>
                  <p className="text-slate-300" data-testid={`admin-strategy-audit-actor-${idx}`}>actor: {item.actor_role || "-"} · {item.actor_user_id || "-"}</p>
                  <p className="text-slate-400" data-testid={`admin-strategy-audit-time-${idx}`}>timestamp: {item.timestamp || "-"}</p>
                  <p className="text-slate-400" data-testid={`admin-strategy-audit-target-version-${idx}`}>target_version: {resolveTargetVersion(item)}</p>
                </div>
              );
            })}
            {filteredTimelineItems.length === 0 && (
              <p className="text-xs text-slate-400" data-testid="admin-strategy-audit-empty">Audit kaydı yok.</p>
            )}
          </div>
        </>
      ) : (
        <div className="space-y-2 border border-slate-700 p-2 text-xs" data-testid="admin-strategy-rollback-chain-panel">
          <p className="uppercase tracking-wider text-slate-400" data-testid="admin-strategy-rollback-chain-title">Rollback Chain</p>
          {rollbackChain.map((item, idx) => (
            <div
              key={`${item.strategy_version_id}-${idx}`}
              className="rounded border border-slate-800 p-2"
              data-testid={`admin-strategy-rollback-chain-item-${idx}`}
            >
              <div className="flex flex-wrap items-center gap-2">
                <span className="font-semibold text-slate-200">{item.strategy_version_id}</span>
                <span className="text-slate-500">←</span>
                <span className="text-slate-400">{item.rolled_back_from_version_id}</span>
                <span className={`rounded-full border px-2 py-1 text-[10px] uppercase ${resolveRollbackStateClass(item)}`} data-testid={`admin-strategy-rollback-state-badge-${idx}`}>
                  {item.lifecycle_state}
                </span>
              </div>
              <p className="mt-1 text-slate-400" data-testid={`admin-strategy-rollback-updated-at-${idx}`}>updated_at: {item.updated_at || "-"}</p>
            </div>
          ))}
          {rollbackChain.length === 0 && <p data-testid="admin-strategy-rollback-chain-empty">Rollback chain bulunamadı.</p>}
        </div>
      )}
    </div>
  );
};
