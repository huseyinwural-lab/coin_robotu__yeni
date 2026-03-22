export const RecommendationStackPanel = ({ items = [] }) => {
  const ranked = [...items]
    .filter((item) => item.status === "pending")
    .sort((a, b) => (a.recommendation_rank || 999) - (b.recommendation_rank || 999))
    .slice(0, 8);

  return (
    <section className="col-span-12 border border-slate-800 bg-slate-900 p-4" data-testid="strategy-intelligence-recommendation-stack-panel">
      <p className="text-xs uppercase tracking-widest text-slate-500" data-testid="strategy-intelligence-recommendation-stack-title">
        Recommendation Stack
      </p>
      <div className="mt-2 space-y-2" data-testid="strategy-intelligence-recommendation-stack-list">
        {ranked.map((item, index) => (
          <article key={item.request_id} className="border border-slate-800 p-2" data-testid={`strategy-intelligence-recommendation-stack-item-${index}`}>
            <p className="text-sm" data-testid={`strategy-intelligence-recommendation-stack-main-${index}`}>
              #{item.recommendation_rank || "-"} · {item.request_type} · {item.request_id}
            </p>
            <p className="text-xs text-slate-400" data-testid={`strategy-intelligence-recommendation-stack-risk-${index}`}>
              severity={item.severity_band} · risk_delta={item.risk_delta_score} · sla={item.sla_state}
            </p>
            <p className="text-xs text-slate-500" data-testid={`strategy-intelligence-recommendation-stack-why-${index}`}>
              why: {item.deterministic_effect_preview?.state_change || "state_change"} ile öngörülen risk iyileşmesi
            </p>
          </article>
        ))}

        {ranked.length === 0 && (
          <p className="text-sm text-slate-400" data-testid="strategy-intelligence-recommendation-stack-empty">
            Öneri sırası için pending kayıt yok.
          </p>
        )}
      </div>
    </section>
  );
};
