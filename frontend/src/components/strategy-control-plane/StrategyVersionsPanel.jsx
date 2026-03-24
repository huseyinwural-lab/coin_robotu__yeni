import { Button } from "@/components/ui/button";

const readinessBadgeClassMap = {
  READY: "border-emerald-500 bg-emerald-500/10 text-emerald-300",
  BLOCKED: "border-red-500 bg-red-500/10 text-red-300",
  NEEDS_VALIDATION: "border-amber-500 bg-amber-500/10 text-amber-300",
  NEEDS_DRY_RUN: "border-orange-500 bg-orange-500/10 text-orange-200",
  AWAITING_APPROVAL: "border-sky-500 bg-sky-500/10 text-sky-200",
};

export const StrategyVersionsPanel = ({
  versions,
  lifecycleMap,
  activeVersionId,
  selectedVersionReadiness,
  buildReadinessState,
  onValidate,
  onDryRun,
  onActivate,
  onRollback,
  onExecutionPreview,
  onPromoteRequest,
  onSetRolloutStage,
  onOpenDiff,
}) => {
  return (
    <div className="space-y-2" data-testid="admin-strategy-versions-list">
      {activeVersionId && selectedVersionReadiness.blockers.length > 0 && (
        <div className="rounded border border-red-700 bg-red-950/40 p-2 text-xs text-red-200" data-testid="admin-strategy-promote-disable-banner">
          Promote disable: {selectedVersionReadiness.blockers.join(" • ")}
        </div>
      )}

      {(versions || []).map((item) => {
        const readiness = buildReadinessState(item.version_id);
        const badgeClass = readinessBadgeClassMap[readiness.state] || readinessBadgeClassMap.BLOCKED;
        const isPromoteDisabled = readiness.state !== "READY";

        return (
          <div key={item.version_id} className="space-y-2 border border-slate-700 p-3" data-testid={`admin-strategy-version-row-${item.version_id}`}>
            <div className="flex flex-wrap items-center justify-between gap-2">
              <p className="text-sm" data-testid={`admin-strategy-version-number-${item.version_id}`}>v{item.version_number} · schema={item.config_schema_version}</p>
              <span
                className={`rounded-full border px-2 py-1 text-[10px] font-semibold uppercase tracking-wide ${badgeClass}`}
                title={readiness.tooltip}
                data-testid={`admin-strategy-version-readiness-badge-${item.version_id}`}
              >
                {readiness.state}
              </span>
            </div>

            <p className="text-xs text-slate-400 break-all" data-testid={`admin-strategy-version-hash-${item.version_id}`}>hash: {item.version_hash}</p>
            <div className="flex flex-wrap gap-2 text-xs" data-testid={`admin-strategy-version-lifecycle-badges-${item.version_id}`}>
              <span className="border border-slate-700 px-2 py-1" data-testid={`admin-strategy-version-lifecycle-state-${item.version_id}`}>
                state: {lifecycleMap[item.version_id]?.lifecycle_state || "draft"}
              </span>
              <span className="border border-slate-700 px-2 py-1" data-testid={`admin-strategy-version-validation-status-${item.version_id}`}>
                validation: {lifecycleMap[item.version_id]?.validation_status || "pending"}
              </span>
              <span className="border border-slate-700 px-2 py-1" data-testid={`admin-strategy-version-dry-run-status-${item.version_id}`}>
                dry_run: {lifecycleMap[item.version_id]?.dry_run_status || "pending"}
              </span>
              <span className="border border-slate-700 px-2 py-1" data-testid={`admin-strategy-version-production-status-${item.version_id}`}>
                production: {String(Boolean(lifecycleMap[item.version_id]?.is_production))}
              </span>
            </div>

            {readiness.blockers.length > 0 && (
              <div className="rounded border border-red-700 bg-red-950/30 p-2 text-xs text-red-200" data-testid={`admin-strategy-version-promote-blockers-${item.version_id}`}>
                {readiness.blockers.map((blocker, idx) => (
                  <p key={`${item.version_id}-blocker-${idx}`} data-testid={`admin-strategy-version-promote-blocker-item-${item.version_id}-${idx}`}>
                    • {blocker}
                  </p>
                ))}
                <div className="mt-2 flex flex-wrap gap-2" data-testid={`admin-strategy-version-quick-actions-${item.version_id}`}>
                  <Button variant="outline" className="border-slate-500 text-slate-100" onClick={() => onValidate(item.version_id)} data-testid={`admin-strategy-version-quick-validate-${item.version_id}`}>validate çalıştır</Button>
                  <Button variant="outline" className="border-slate-500 text-slate-100" onClick={() => onDryRun(item.version_id)} data-testid={`admin-strategy-version-quick-dry-run-${item.version_id}`}>dry-run çalıştır</Button>
                  <Button
                    variant="outline"
                    className="border-blue-500 text-blue-200"
                    onClick={() => onPromoteRequest(item.version_id)}
                    disabled={isPromoteDisabled}
                    title={readiness.tooltip}
                    data-testid={`admin-strategy-version-quick-approval-request-${item.version_id}`}
                  >
                    approval isteği oluştur
                  </Button>
                  <Button variant="outline" className="border-violet-500 text-violet-200" onClick={() => onOpenDiff(item.version_id)} data-testid={`admin-strategy-version-quick-open-diff-${item.version_id}`}>diff aç</Button>
                  <Button variant="outline" className="border-amber-500 text-amber-200" onClick={() => onRollback(item.version_id)} data-testid={`admin-strategy-version-quick-open-rollback-${item.version_id}`}>rollback aç</Button>
                </div>
              </div>
            )}

            <div className="flex flex-wrap gap-2" data-testid={`admin-strategy-version-actions-${item.version_id}`}>
              <Button variant="outline" className="border-slate-500 text-slate-100" onClick={() => onValidate(item.version_id)} data-testid={`admin-strategy-version-validate-button-${item.version_id}`}>Validate</Button>
              <Button variant="outline" className="border-slate-500 text-slate-100" onClick={() => onDryRun(item.version_id)} data-testid={`admin-strategy-version-dry-run-button-${item.version_id}`}>Dry-Run</Button>
              <Button className="bg-orange-500 text-black hover:bg-orange-600" onClick={() => onActivate(item.version_id)} data-testid={`admin-strategy-version-activate-button-${item.version_id}`}>Activate</Button>
              <Button variant="outline" className="border-amber-500 text-amber-200" onClick={() => onRollback(item.version_id)} data-testid={`admin-strategy-version-rollback-button-${item.version_id}`}>Rollback</Button>
              <Button variant="outline" className="border-emerald-500 text-emerald-200" onClick={() => onExecutionPreview(item.version_id)} data-testid={`admin-strategy-version-execution-preview-button-${item.version_id}`}>Execution Preview</Button>
              <Button
                variant="outline"
                className="border-blue-500 text-blue-200"
                onClick={() => onPromoteRequest(item.version_id)}
                title={readiness.tooltip}
                disabled={isPromoteDisabled}
                data-testid={`admin-strategy-version-promote-request-button-${item.version_id}`}
              >
                Promote Request
              </Button>
              <Button variant="outline" className="border-fuchsia-500 text-fuchsia-200" onClick={() => onSetRolloutStage(item.version_id, "shadow")} data-testid={`admin-strategy-version-shadow-button-${item.version_id}`}>Stage: Shadow</Button>
              <Button variant="outline" className="border-fuchsia-500 text-fuchsia-200" onClick={() => onSetRolloutStage(item.version_id, "canary")} data-testid={`admin-strategy-version-canary-button-${item.version_id}`}>Stage: Canary</Button>
            </div>
          </div>
        );
      })}
    </div>
  );
};
