import { useEffect, useMemo, useState } from "react";
import { toast } from "sonner";

import { Input } from "@/components/ui/input";
import { apiClient } from "@/lib/api";

export const BacktestInsightsPage = () => {
  const [cards, setCards] = useState([]);
  const [marketFilter, setMarketFilter] = useState("all");
  const [strategyFilter, setStrategyFilter] = useState("all");
  const [sortBy, setSortBy] = useState("win_rate_desc");
  const [benchmarkWinRate, setBenchmarkWinRate] = useState(55);

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

  const filteredCards = useMemo(() => {
    const rows = cards.filter((card) => {
      const marketMatch = marketFilter === "all" || card.market_type === marketFilter;
      const strategyMatch = strategyFilter === "all" || card.strategy_type === strategyFilter;
      return marketMatch && strategyMatch;
    });

    const sorted = [...rows];
    if (sortBy === "win_rate_desc") {
      sorted.sort((a, b) => Number(b.win_rate || 0) - Number(a.win_rate || 0));
    }
    if (sortBy === "profit_factor_desc") {
      sorted.sort((a, b) => Number(b.profit_factor || 0) - Number(a.profit_factor || 0));
    }
    if (sortBy === "drawdown_asc") {
      sorted.sort((a, b) => Number(a.max_drawdown || 0) - Number(b.max_drawdown || 0));
    }
    return sorted;
  }, [cards, marketFilter, strategyFilter, sortBy]);

  const strategyOptions = useMemo(() => [...new Set(cards.map((card) => card.strategy_type).filter(Boolean))], [cards]);

  return (
    <section className="space-y-4" data-testid="backtest-insights-page">
      <header className="border border-slate-800 bg-slate-900 p-4" data-testid="backtest-insights-header">
        <h2 className="text-4xl font-black uppercase tracking-tight" data-testid="backtest-insights-title">Backtest Insights</h2>
        <p className="mt-2 text-sm text-slate-400" data-testid="backtest-insights-description">
          Strateji seçiminde karar desteği için read-only performans kartları.
        </p>
        <div className="mt-3 grid gap-2 md:grid-cols-4" data-testid="backtest-insights-controls-grid">
          <select className="rounded-md border border-slate-700 bg-slate-950 px-3 py-2 text-sm" value={marketFilter} onChange={(event) => setMarketFilter(event.target.value)} data-testid="backtest-insights-market-filter-select">
            <option value="all">all markets</option>
            <option value="spot">spot</option>
            <option value="futures">futures</option>
          </select>
          <select className="rounded-md border border-slate-700 bg-slate-950 px-3 py-2 text-sm" value={strategyFilter} onChange={(event) => setStrategyFilter(event.target.value)} data-testid="backtest-insights-strategy-filter-select">
            <option value="all">all strategies</option>
            {strategyOptions.map((value) => (
              <option key={value} value={value}>{value}</option>
            ))}
          </select>
          <select className="rounded-md border border-slate-700 bg-slate-950 px-3 py-2 text-sm" value={sortBy} onChange={(event) => setSortBy(event.target.value)} data-testid="backtest-insights-sort-select">
            <option value="win_rate_desc">Win Rate ↓</option>
            <option value="profit_factor_desc">Profit Factor ↓</option>
            <option value="drawdown_asc">Drawdown ↑ (lower better)</option>
          </select>
          <Input type="number" value={benchmarkWinRate} onChange={(event) => setBenchmarkWinRate(Number(event.target.value) || 0)} data-testid="backtest-insights-benchmark-winrate-input" placeholder="Benchmark Win Rate" />
        </div>
      </header>

      <div className="grid gap-3 md:grid-cols-2 xl:grid-cols-3" data-testid="backtest-insights-grid">
        {filteredCards.map((card) => (
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
            <p className="mt-2 text-xs text-emerald-300" data-testid={`backtest-insight-benchmark-delta-${card.id}`}>
              Benchmark Delta: {(Number(card.win_rate || 0) - Number(benchmarkWinRate || 0)).toFixed(2)}
            </p>
          </article>
        ))}
        {filteredCards.length === 0 && (
          <article className="border border-slate-800 bg-slate-900 p-4" data-testid="backtest-insights-empty-state">
            <p className="text-sm text-slate-400">Filtreye uygun backtest kartı bulunamadı.</p>
          </article>
        )}
      </div>
    </section>
  );
};
