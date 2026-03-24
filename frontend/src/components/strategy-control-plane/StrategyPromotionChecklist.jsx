const readinessBadgeClassMap = {
  READY: "border-emerald-500 bg-emerald-500/10 text-emerald-300",
  BLOCKED: "border-red-500 bg-red-500/10 text-red-300",
  NEEDS_VALIDATION: "border-amber-500 bg-amber-500/10 text-amber-300",
  NEEDS_DRY_RUN: "border-orange-500 bg-orange-500/10 text-orange-200",
  AWAITING_APPROVAL: "border-sky-500 bg-sky-500/10 text-sky-200",
};

export const StrategyPromotionChecklist = ({ promotionReadiness, selectedVersionReadiness }) => {
  const state = selectedVersionReadiness?.state || "BLOCKED";
  const badgeClass = readinessBadgeClassMap[state] || readinessBadgeClassMap.BLOCKED;

  return (
    <div className="space-y-2 border border-slate-800 bg-slate-900 p-4" data-testid="admin-strategy-promotion-readiness-panel">
      <p className="text-xs uppercase tracking-widest text-slate-500" data-testid="admin-strategy-promotion-readiness-title">One-click Promote Checklist</p>
      <div className={`inline-flex rounded-full border px-3 py-1 text-[10px] font-semibold uppercase tracking-wide ${badgeClass}`} data-testid="admin-strategy-promotion-readiness-state-badge">
        {state}
      </div>

      {promotionReadiness ? (
        <div className="space-y-2 text-xs" data-testid="admin-strategy-promotion-readiness-content">
          {(promotionReadiness.checklist || []).map((item) => (
            <p key={item.key} data-testid={`admin-strategy-promotion-readiness-item-${item.key}`}>
              {item.key}: {item.status} ({item.pass ? "PASS" : "FAIL"})
            </p>
          ))}
          <p data-testid="admin-strategy-promotion-readiness-ready">ready_for_production: {String(Boolean(promotionReadiness.ready_for_production))}</p>
          {Boolean((promotionReadiness.blockers || []).length) && (
            <div className="text-red-300" data-testid="admin-strategy-promotion-readiness-blockers">
              {(promotionReadiness.blockers || []).map((item, idx) => (
                <p key={`${item}-${idx}`}>{item}</p>
              ))}
            </div>
          )}
        </div>
      ) : (
        <p className="text-xs text-slate-400" data-testid="admin-strategy-promotion-readiness-empty">Readiness verisi yok.</p>
      )}
    </div>
  );
};
