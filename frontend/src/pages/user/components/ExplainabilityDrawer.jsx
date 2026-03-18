import {
  Sheet,
  SheetContent,
  SheetDescription,
  SheetHeader,
  SheetTitle,
} from "@/components/ui/sheet";

export const ExplainabilityDrawer = ({
  isOpen,
  onOpenChange,
  selectedSymbol,
  isLoading,
  explainability,
  formatDateLabel,
}) => {
  const familyScores = Object.entries(explainability?.family_scores || {});
  const sourceStrategies = Array.isArray(explainability?.source_strategies) ? explainability.source_strategies : [];
  const timeline = Array.isArray(explainability?.blocked_reason_timeline) ? explainability.blocked_reason_timeline : [];
  const confidenceValue = Number(explainability?.decision_confidence ?? 0);
  const confidenceLevel = confidenceValue >= 0.75 ? "HIGH" : confidenceValue >= 0.5 ? "MEDIUM" : "LOW";
  const riskSeverity = String(explainability?.final_decision || "").toUpperCase() === "BLOCKED"
    ? "HIGH"
    : confidenceLevel === "LOW"
      ? "MEDIUM"
      : "LOW";
  const confidenceTone = confidenceLevel === "HIGH"
    ? "border-emerald-500/60 bg-emerald-500/20 text-emerald-200"
    : confidenceLevel === "MEDIUM"
      ? "border-amber-500/60 bg-amber-500/20 text-amber-200"
      : "border-rose-500/60 bg-rose-500/20 text-rose-200";
  const riskTone = riskSeverity === "HIGH"
    ? "border-rose-500/60 bg-rose-500/20 text-rose-200"
    : riskSeverity === "MEDIUM"
      ? "border-amber-500/60 bg-amber-500/20 text-amber-200"
      : "border-emerald-500/60 bg-emerald-500/20 text-emerald-200";

  return (
    <Sheet open={isOpen} onOpenChange={onOpenChange}>
      <SheetContent side="right" className="w-full overflow-y-auto border-slate-800 bg-slate-950 text-slate-100 sm:max-w-2xl" data-testid="user-explainability-drawer-content">
        <SheetHeader data-testid="user-explainability-drawer-header">
          <SheetTitle data-testid="user-explainability-drawer-title">Explainability Drawer</SheetTitle>
          <SheetDescription data-testid="user-explainability-drawer-description">
            {selectedSymbol ? `${selectedSymbol} için karar izi ve katkı detayları` : "Önce bir symbol seçin"}
          </SheetDescription>
        </SheetHeader>

        {!selectedSymbol && <p className="mt-4 text-sm" data-testid="user-explainability-drawer-empty">Karttan bir symbol seçtiğinizde detaylar burada açılır.</p>}
        {selectedSymbol && isLoading && <p className="mt-4 text-sm" data-testid="user-explainability-drawer-loading">Yükleniyor...</p>}

        {selectedSymbol && !isLoading && explainability && (
          <div className="mt-4 space-y-4" data-testid="user-explainability-drawer-body">
            <div className="rounded border border-fuchsia-700/50 bg-fuchsia-950/20 p-3" data-testid="user-explainability-summary-block">
              <p className="text-xs" data-testid="user-explainability-final-decision">Final Decision: {explainability.final_decision}</p>
              <p className="text-xs" data-testid="user-explainability-score">Long/Short Score: {explainability.long_score} / {explainability.short_score}</p>
              <p className="text-xs" data-testid="user-explainability-winning-side">Winning Side: {explainability.winning_side}</p>
              <p className="text-xs" data-testid="user-explainability-confidence">Decision Confidence: {explainability.decision_confidence}</p>
              <div className="mt-2 flex flex-wrap items-center gap-2" data-testid="user-explainability-summary-chips">
                <span className={`inline-flex rounded-full border px-2 py-0.5 text-[11px] font-semibold ${confidenceTone}`} data-testid="user-explainability-confidence-chip">
                  confidence: {confidenceLevel}
                </span>
                <span className={`inline-flex rounded-full border px-2 py-0.5 text-[11px] font-semibold ${riskTone}`} data-testid="user-explainability-risk-severity-chip">
                  risk: {riskSeverity}
                </span>
              </div>
            </div>

            <div data-testid="user-explainability-template-list">
              <p className="text-xs font-semibold">Explanation Templates</p>
              {(explainability.explanation_templates || []).map((item, idx) => (
                <div key={`${selectedSymbol}-tpl-${idx}`} className="mt-1 rounded border border-fuchsia-700/40 bg-fuchsia-950/10 p-2" data-testid={`user-explainability-template-row-${idx}`}>
                  <div className="mb-1 flex flex-wrap items-center gap-1" data-testid={`user-explainability-template-chips-${idx}`}>
                    <span className={`inline-flex rounded-full border px-2 py-0.5 text-[10px] font-semibold ${confidenceTone}`} data-testid={`user-explainability-template-confidence-chip-${idx}`}>
                      confidence: {confidenceLevel}
                    </span>
                    <span className={`inline-flex rounded-full border px-2 py-0.5 text-[10px] font-semibold ${riskTone}`} data-testid={`user-explainability-template-risk-chip-${idx}`}>
                      risk: {riskSeverity}
                    </span>
                  </div>
                  <p className="text-xs text-fuchsia-100" data-testid={`user-explainability-template-${idx}`}>{item}</p>
                </div>
              ))}
            </div>

            <div data-testid="user-explainability-family-gates">
              <p className="text-xs font-semibold">Family Gate Durumları</p>
              <div className="mt-1 grid gap-1 md:grid-cols-2">
                {familyScores.map(([family, gate]) => (
                  <p key={`${selectedSymbol}-gate-${family}`} className="text-xs" data-testid={`user-explainability-family-gate-${family}`}>
                    {family}: score(L/S)={gate.long_score ?? 0}/{gate.short_score ?? 0} · threshold(L/S)={gate.long_threshold ?? "-"}/{gate.short_threshold ?? "-"} · {gate.gate_status} ({gate.gate_reason})
                  </p>
                ))}
                {familyScores.length === 0 && <p className="text-xs" data-testid="user-explainability-family-gates-empty">Family gate detayı yok.</p>}
              </div>
            </div>

            <div data-testid="user-explainability-source-strategies">
              <p className="text-xs font-semibold">Source Strategy Katkıları</p>
              <div className="max-h-48 space-y-1 overflow-y-auto rounded border border-slate-800 p-2" data-testid="user-explainability-source-strategies-list">
                {sourceStrategies.map((item) => (
                  <p key={`${selectedSymbol}-${item.strategy_id}`} className="text-xs" data-testid={`user-explainability-strategy-${item.strategy_id}`}>
                    {item.strategy_id} · {item.family} · direction={item.direction || "-"} · raw={item.raw_signal} · normalized={item.normalized_score ?? "-"} · weight={item.weight ?? "-"} · contrib={item.contribution_score} · status={item.status}
                  </p>
                ))}
                {sourceStrategies.length === 0 && <p className="text-xs" data-testid="user-explainability-source-strategies-empty">Source strategy detayı yok.</p>}
              </div>
            </div>

            <div data-testid="user-explainability-blocked-timeline">
              <p className="text-xs font-semibold">Blocked Reason Timeline</p>
              <div className="max-h-52 space-y-1 overflow-y-auto rounded border border-slate-800 p-2" data-testid="user-explainability-blocked-timeline-list">
                {timeline.map((event, idx) => (
                  <p key={`${selectedSymbol}-timeline-${idx}`} className="text-xs" data-testid={`user-explainability-timeline-item-${idx}`}>
                    {formatDateLabel(event.event_time)} · {event.layer} · {event.reason_code} · {event.reason_detail || "-"} · {event.previous_state}→{event.new_state}
                  </p>
                ))}
                {timeline.length === 0 && <p className="text-xs" data-testid="user-explainability-timeline-empty">Timeline kaydı yok.</p>}
              </div>
            </div>
          </div>
        )}
      </SheetContent>
    </Sheet>
  );
};
