import { useEffect, useState } from "react";
import { toast } from "sonner";

import { apiClient } from "@/lib/api";

export const BacktestInsightsPage = () => {
  const [cards, setCards] = useState([]);

  useEffect(() => {
    const loadCards = async () => {
      try {
        const { data } = await apiClient.get("/backtest/cards");
        setCards(data);
      } catch (error) {
        toast.error(error?.response?.data?.detail || "Backtest insights alınamadı");
      }
    };
    loadCards();
  }, []);

  return (
    <section className="space-y-4" data-testid="backtest-insights-page">
      <header className="border border-slate-800 bg-slate-900 p-4" data-testid="backtest-insights-header">
        <h2 className="text-4xl font-black uppercase tracking-tight" data-testid="backtest-insights-title">Backtest Insights</h2>
        <p className="mt-2 text-sm text-slate-400" data-testid="backtest-insights-description">
          Strateji seçiminde karar desteği için read-only performans kartları.
        </p>
      </header>

      <div className="grid gap-3 md:grid-cols-2 xl:grid-cols-3" data-testid="backtest-insights-grid">
        {cards.map((card) => (
          <article key={card.id} className="border border-slate-800 bg-slate-900 p-4" data-testid={`backtest-insight-card-${card.id}`}>
            <p className="text-xs uppercase tracking-widest text-slate-500" data-testid={`backtest-insight-strategy-${card.id}`}>{card.strategy_type}</p>
            <p className="mt-2 text-sm" data-testid={`backtest-insight-timeframe-${card.id}`}>{card.market_type} / {card.timeframe}</p>
            <div className="mt-3 grid grid-cols-2 gap-2 text-xs font-mono">
              <p data-testid={`backtest-insight-winrate-${card.id}`}>Win: {card.win_rate}%</p>
              <p data-testid={`backtest-insight-dd-${card.id}`}>DD: {card.max_drawdown}%</p>
              <p data-testid={`backtest-insight-pf-${card.id}`}>PF: {card.profit_factor}</p>
              <p data-testid={`backtest-insight-sharpe-${card.id}`}>Sharpe*: {card.sharpe_like_score}</p>
            </div>
            <p className="mt-3 text-xs text-slate-300" data-testid={`backtest-insight-summary-${card.id}`}>{card.performance_summary}</p>
            <p className="mt-2 text-xs" data-testid={`backtest-insight-risk-${card.id}`}>Risk: {card.risk_label}</p>
          </article>
        ))}
      </div>
    </section>
  );
};
