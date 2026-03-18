import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";

const decisionBadgeClass = {
  LONG: "border-emerald-500/60 bg-emerald-500/20 text-emerald-200",
  SHORT: "border-rose-500/60 bg-rose-500/20 text-rose-200",
  BLOCKED: "border-amber-500/60 bg-amber-500/20 text-amber-200",
  NO_TRADE: "border-slate-500/60 bg-slate-500/20 text-slate-200",
};

const confidenceChipClass = {
  HIGH: "border-emerald-500/60 bg-emerald-500/20 text-emerald-200",
  MEDIUM: "border-amber-500/60 bg-amber-500/20 text-amber-200",
  LOW: "border-rose-500/60 bg-rose-500/20 text-rose-200",
};

const riskChipClass = {
  LOW: "border-emerald-500/60 bg-emerald-500/20 text-emerald-200",
  MEDIUM: "border-amber-500/60 bg-amber-500/20 text-amber-200",
  HIGH: "border-rose-500/60 bg-rose-500/20 text-rose-200",
};

export const DecisionCard = ({ card, onOpenExplainability, onOpenSymbolDetail, onOpenImpactSimulator }) => {
  const decision = String(card?.decision || "NO_TRADE").toUpperCase();
  const badgeClass = decisionBadgeClass[decision] || decisionBadgeClass.NO_TRADE;
  const confidenceValue = Number(card?.confidence ?? 0);
  const confidenceLevel = confidenceValue >= 0.75 ? "HIGH" : confidenceValue >= 0.5 ? "MEDIUM" : "LOW";
  const riskSeverity = card?.risk_block || card?.blocked_reason ? "HIGH" : confidenceLevel === "LOW" ? "MEDIUM" : "LOW";
  const topContributors = Array.isArray(card?.top_contributors) ? card.top_contributors.slice(0, 2) : [];

  return (
    <article className="rounded border border-blue-700/70 bg-black/20 p-3" data-testid={`user-decision-card-${card.symbol}`}>
      <div className="flex items-center justify-between gap-2" data-testid={`user-decision-card-head-${card.symbol}`}>
        <p className="text-sm font-semibold" data-testid={`user-decision-card-symbol-${card.symbol}`}>{card.symbol}</p>
        <div className="flex flex-wrap items-center justify-end gap-1" data-testid={`user-decision-card-head-badges-${card.symbol}`}>
          <Badge className={badgeClass} data-testid={`user-decision-card-decision-${card.symbol}`}>{decision}</Badge>
          <Badge className={confidenceChipClass[confidenceLevel]} data-testid={`user-decision-card-confidence-chip-${card.symbol}`}>
            confidence: {confidenceLevel}
          </Badge>
          <Badge className={riskChipClass[riskSeverity]} data-testid={`user-decision-card-risk-severity-chip-${card.symbol}`}>
            risk: {riskSeverity}
          </Badge>
        </div>
      </div>

      <p className="mt-1 text-xs text-slate-300" data-testid={`user-decision-card-regime-${card.symbol}`}>Regime: {card.market_regime}</p>
      <p className="text-xs text-slate-300" data-testid={`user-decision-card-confidence-${card.symbol}`}>Confidence: {card.confidence}</p>
      <p className="text-xs text-slate-300" data-testid={`user-decision-card-score-${card.symbol}`}>L/S: {card.long_score} / {card.short_score}</p>
      <p className="text-xs text-slate-300" data-testid={`user-decision-card-dominant-family-${card.symbol}`}>Dominant Family: {card.dominant_family || "-"}</p>
      <p className="text-xs text-slate-300" data-testid={`user-decision-card-entry-zone-${card.symbol}`}>
        Entry Zone: {card.entry_zone?.min ?? "-"} / {card.entry_zone?.max ?? "-"}
      </p>
      <p className="text-xs text-slate-300" data-testid={`user-decision-card-stop-${card.symbol}`}>Stop: {card.stop_loss ?? "-"}</p>
      <p className="text-xs text-slate-300" data-testid={`user-decision-card-tp1-${card.symbol}`}>TP1: {card.take_profit_1 ?? "-"}</p>
      <p className="text-xs text-slate-300" data-testid={`user-decision-card-tp2-${card.symbol}`}>TP2: {card.take_profit_2 ?? "-"}</p>
      <p className="text-xs text-slate-300" data-testid={`user-decision-card-invalidation-${card.symbol}`}>
        Invalidation: {card.invalidation?.type || card.invalidation?.reason || "-"}
      </p>
      <p className="text-xs text-slate-300" data-testid={`user-decision-card-risk-block-${card.symbol}`}>Risk Block: {card.risk_block || card.blocked_reason || "clear"}</p>
      <p className="text-xs text-slate-300" data-testid={`user-decision-card-blocked-reason-${card.symbol}`}>Blocked Reason: {card.blocked_reason || "-"}</p>
      <p className="text-xs text-slate-300" data-testid={`user-decision-card-cooldown-${card.symbol}`}>Cooldown (sec): {card.cooldown_remaining ?? 0}</p>
      <p className="text-xs text-slate-300" data-testid={`user-decision-card-risk-state-${card.symbol}`}>Risk State: {card.risk_block ? "blocked" : "clear"}</p>
      <p className="text-xs text-slate-300" data-testid={`user-decision-card-confidence-adjustment-${card.symbol}`}>Confidence Adj: {card.confidence_adjustment || 0}</p>
      <p className="text-xs text-slate-300" data-testid={`user-decision-card-updated-at-${card.symbol}`}>Updated At: {card.updated_at || card.generated_at || "-"}</p>

      <div className="mt-1 flex flex-wrap gap-1" data-testid={`user-decision-card-learning-badges-${card.symbol}`}>
        {(card.learning_badges || []).map((badge, idx) => (
          <span
            key={`${card.symbol}-badge-${idx}`}
            className="rounded border border-blue-700 px-1 py-0.5 text-[10px]"
            data-testid={`user-decision-card-learning-badge-${card.symbol}-${idx}`}
          >
            {badge}
          </span>
        ))}
      </div>

      <div className="mt-2" data-testid={`user-decision-card-top-contributors-${card.symbol}`}>
        {topContributors.map((item, idx) => (
          <p key={`${card.symbol}-contrib-${idx}`} className="text-[11px] text-slate-400" data-testid={`user-decision-card-top-contributor-${card.symbol}-${idx}`}>
            {item.strategy_id} · {item.family} · score={item.contribution_score}
          </p>
        ))}
      </div>

      <div className="mt-2 flex gap-2" data-testid={`user-decision-card-actions-${card.symbol}`}>
        <Button
          type="button"
          size="sm"
          variant="outline"
          onClick={() => onOpenExplainability(card.symbol)}
          data-testid={`user-decision-card-open-explainability-button-${card.symbol}`}
        >
          Explainability
        </Button>
        {typeof onOpenSymbolDetail === "function" && (
          <Button
            type="button"
            size="sm"
            variant="outline"
            onClick={() => onOpenSymbolDetail(card.symbol)}
            data-testid={`user-decision-card-open-symbol-detail-button-${card.symbol}`}
          >
            Symbol Detail
          </Button>
        )}
        {typeof onOpenImpactSimulator === "function" && (
          <Button
            type="button"
            size="sm"
            variant="outline"
            onClick={() => onOpenImpactSimulator(card)}
            data-testid={`user-decision-card-open-impact-simulator-button-${card.symbol}`}
          >
            Impact Simulate
          </Button>
        )}
      </div>
    </article>
  );
};
