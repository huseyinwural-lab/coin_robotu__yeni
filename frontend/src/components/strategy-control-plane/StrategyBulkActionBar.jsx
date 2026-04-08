import { Button } from "@/components/ui/button";

export const StrategyBulkActionBar = ({
  selectedStrategyIds,
  onClearSelection,
  onBulkArchive,
  onBulkValidate,
  onBulkDryRun,
  onBulkTag,
  onBulkAuditExport,
  bulkActionSummary,
}) => {
  const isEmpty = selectedStrategyIds.length === 0;

  return (
    <>
      <div className="flex flex-wrap gap-2" data-testid="admin-strategies-bulk-actions-row">
        <div className="w-full rounded border border-slate-700 bg-slate-950/60 p-2 text-xs" data-testid="admin-strategies-bulk-toolbar-summary-banner">
          <p data-testid="admin-strategies-bulk-toolbar-selected-count">Seçili strategy: {selectedStrategyIds.length}</p>
          <button
            type="button"
            className="mt-1 rounded border border-slate-600 px-2 py-1 text-[11px] text-slate-200"
            onClick={onClearSelection}
            data-testid="admin-strategies-bulk-toolbar-clear-selection-button"
          >
            Seçimi Temizle
          </button>
        </div>

        <Button
          variant="outline"
          className="border-red-500 text-red-200"
          onClick={onBulkArchive}
          disabled={isEmpty}
          title={isEmpty ? "Önce strategy seçin" : "Seçili strategyleri archive et"}
          data-testid="admin-strategies-bulk-archive-button"
        >
          Bulk Archive
        </Button>
        <Button
          variant="outline"
          className="border-slate-500 text-slate-100"
          onClick={onBulkValidate}
          disabled={isEmpty}
          title={isEmpty ? "Önce strategy seçin" : "Seçili strategyleri validate et"}
          data-testid="admin-strategies-bulk-validate-button"
        >
          Bulk Validate
        </Button>
        <Button
          variant="outline"
          className="border-slate-600 text-slate-400"
          onClick={onBulkDryRun}
          disabled
          title="Pure Live modunda simulation kaldırıldı"
          data-testid="admin-strategies-bulk-dry-run-button"
        >
          Simulation Removed
        </Button>
        <Button
          variant="outline"
          className="border-slate-500 text-slate-100"
          onClick={onBulkTag}
          disabled={isEmpty}
          title={isEmpty ? "Önce strategy seçin" : "Seçili strategylerde tag/category güncelle"}
          data-testid="admin-strategies-bulk-tag-button"
        >
          Bulk Tag/Category
        </Button>
        <Button
          variant="outline"
          className="border-slate-500 text-slate-100"
          onClick={onBulkAuditExport}
          disabled={isEmpty}
          title={isEmpty ? "Önce strategy seçin" : "Seçili strategyler için audit snapshot al"}
          data-testid="admin-strategies-bulk-audit-export-button"
        >
          Bulk Audit Snapshot
        </Button>
      </div>

      {bulkActionSummary && (
        <div className="rounded border border-slate-700 p-2 text-xs" data-testid="admin-strategies-bulk-result-panel">
          <p data-testid="admin-strategies-bulk-result-action">action: {bulkActionSummary.action}</p>
          <p data-testid="admin-strategies-bulk-result-success">success: {bulkActionSummary.payload?.success_count ?? bulkActionSummary.payload?.updated_count ?? 0}</p>
          <p data-testid="admin-strategies-bulk-result-fail">fail: {bulkActionSummary.payload?.failed_count ?? 0}</p>
          {!!(bulkActionSummary.payload?.failed || []).length && (
            <div className="text-red-300" data-testid="admin-strategies-bulk-result-fail-list">
              {(bulkActionSummary.payload.failed || []).slice(0, 5).map((item, idx) => (
                <p key={`${item.strategy_id}-${idx}`}>{item.strategy_id}: {item.error}</p>
              ))}
            </div>
          )}
        </div>
      )}
    </>
  );
};
