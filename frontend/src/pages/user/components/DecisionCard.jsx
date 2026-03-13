import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";

const decisionBadgeClass = {
  LONG: "border-emerald-500/60 bg-emerald-500/20 text-emerald-200",
  SHORT: "border-rose-500/60 bg-rose-500/20 text-rose-200",
  BLOCKED: "border-amber-500/60 bg-amber-500/20 text-amber-200",
  NO_TRADE: "border-slate-500/60 bg-slate-500/20 text-slate-200",
};

export const DecisionCard = ({ card, onOpenExplainability }) => {
  const decision = String(card?.decision || "NO_TRADE").toUpperCase();
  const badgeClass = decisionBadgeClass[decision] || decisionBadgeClass.NO_TRADE;
  const topContributors = Array.isArray(card?.top_contributors) ? card.top_contributors.slice(0, 2) : [];

  return (
    <article className="rounded border border-blue-700/70 bg-black/20 p-3" data-testid={`user-decision-card-${card.symbol}`}>
      <div className="flex items-center justify-between gap-2" data-testid={`user-decision-card-head-${card.symbol}`}>
        <p className="text-sm font-semibold" data-testid={`user-decision-card-symbol-${card.symbol}`}>{card.symbol}</p>
        <Badge className={badgeClass} data-testid={`user-decision-card-decision-${card.symbol}`}>{decision}</Badge>
      </div>

      <p className="mt-1 text-xs text-slate-300" data-testid={`user-decision-card-regime-${card.symbol}`}>Regime: {card.market_regime}</p>
      <p className="text-xs text-slate-300" data-testid={`user-decision-card-score-${card.symbol}`}>L/S: {card.long_score} / {card.short_score}</p>
      <p className="text-xs text-slate-300" data-testid={`user-decision-card-dominant-family-${card.symbol}`}>Dominant Family: {card.dominant_family || "-"}</p>
      <p className="text-xs text-slate-300" data-testid={`user-decision-card-risk-block-${card.symbol}`}>Risk Block: {card.risk_block || card.blocked_reason || "clear"}</p>
      <p className="text-xs text-slate-300" data-testid={`user-decision-card-confidence-adjustment-${card.symbol}`}>Confidence Adj: {card.confidence_adjustment || 0}</p>

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
      </div>
    </article>
  );
};
