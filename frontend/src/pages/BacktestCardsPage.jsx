import { useEffect, useState } from "react";
import { toast } from "sonner";

import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from "@/components/ui/table";
import { apiClient } from "@/lib/api";

const initialForm = {
  strategy_type: "trend_following",
  market_type: "spot",
  timeframe: "15m",
  sample_size: 120,
  win_rate: 52,
  max_drawdown: 10,
  profit_factor: 1.2,
  sharpe_like_score: 0.7,
  performance_summary: "Stable baseline performance.",
  risk_label: "medium",
  period_start: "2025-01-01",
  period_end: "2025-12-31",
};

export const BacktestCardsPage = () => {
  const [cards, setCards] = useState([]);
  const [editingId, setEditingId] = useState(null);
  const [form, setForm] = useState(initialForm);

  const loadCards = async () => {
    try {
      const { data } = await apiClient.get("/admin-phase3/backtest-cards");
      setCards(data);
    } catch (error) {
      toast.error(error?.response?.data?.detail || "Backtest card verisi alınamadı");
    }
  };

  useEffect(() => {
    loadCards();
  }, []);

  const submitCard = async (event) => {
    event.preventDefault();
    const payload = {
      ...form,
      sample_size: Number(form.sample_size),
      win_rate: Number(form.win_rate),
      max_drawdown: Number(form.max_drawdown),
      profit_factor: Number(form.profit_factor),
      sharpe_like_score: Number(form.sharpe_like_score),
    };

    try {
      if (editingId) {
        await apiClient.put(`/admin-phase3/backtest-cards/${editingId}`, payload);
        toast.success("Backtest card güncellendi");
      } else {
        await apiClient.post("/admin-phase3/backtest-cards", payload);
        toast.success("Backtest card eklendi");
      }
      setForm(initialForm);
      setEditingId(null);
      loadCards();
    } catch (error) {
      toast.error(error?.response?.data?.detail || "Backtest card işlemi başarısız");
    }
  };

  return (
    <section className="space-y-4" data-testid="backtest-cards-page">
      <header className="border border-blue-900 bg-slate-900 p-4" data-testid="backtest-cards-header">
        <h2 className="text-4xl font-black uppercase tracking-tight text-blue-300" data-testid="backtest-cards-title">Backtest Sonuç Kartları</h2>
        <p className="mt-2 text-sm text-slate-400" data-testid="backtest-cards-description">Win rate, drawdown, profit factor ve risk etiketi ile karar destek görünümü.</p>
      </header>

      <form onSubmit={submitCard} className="grid gap-3 border border-slate-800 bg-slate-900 p-4 md:grid-cols-2" data-testid="backtest-card-form">
        <Input placeholder="strategy_type" value={form.strategy_type} onChange={(event) => setForm((prev) => ({ ...prev, strategy_type: event.target.value }))} data-testid="backtest-form-strategy-input" required />
        <Input placeholder="market_type" value={form.market_type} onChange={(event) => setForm((prev) => ({ ...prev, market_type: event.target.value }))} data-testid="backtest-form-market-input" required />
        <Input placeholder="timeframe" value={form.timeframe} onChange={(event) => setForm((prev) => ({ ...prev, timeframe: event.target.value }))} data-testid="backtest-form-timeframe-input" required />
        <Input type="number" placeholder="sample_size" value={form.sample_size} onChange={(event) => setForm((prev) => ({ ...prev, sample_size: event.target.value }))} data-testid="backtest-form-sample-size-input" required />
        <Input type="number" step="0.1" placeholder="win_rate" value={form.win_rate} onChange={(event) => setForm((prev) => ({ ...prev, win_rate: event.target.value }))} data-testid="backtest-form-winrate-input" required />
        <Input type="number" step="0.1" placeholder="max_drawdown" value={form.max_drawdown} onChange={(event) => setForm((prev) => ({ ...prev, max_drawdown: event.target.value }))} data-testid="backtest-form-drawdown-input" required />
        <Input type="number" step="0.01" placeholder="profit_factor" value={form.profit_factor} onChange={(event) => setForm((prev) => ({ ...prev, profit_factor: event.target.value }))} data-testid="backtest-form-profit-factor-input" required />
        <Input type="number" step="0.01" placeholder="sharpe_like_score" value={form.sharpe_like_score} onChange={(event) => setForm((prev) => ({ ...prev, sharpe_like_score: event.target.value }))} data-testid="backtest-form-sharpe-input" required />
        <Input placeholder="risk_label" value={form.risk_label} onChange={(event) => setForm((prev) => ({ ...prev, risk_label: event.target.value }))} data-testid="backtest-form-risk-label-input" required />
        <Input placeholder="period_start" value={form.period_start} onChange={(event) => setForm((prev) => ({ ...prev, period_start: event.target.value }))} data-testid="backtest-form-period-start-input" required />
        <Input placeholder="period_end" value={form.period_end} onChange={(event) => setForm((prev) => ({ ...prev, period_end: event.target.value }))} data-testid="backtest-form-period-end-input" required />
        <Input placeholder="performance_summary" value={form.performance_summary} onChange={(event) => setForm((prev) => ({ ...prev, performance_summary: event.target.value }))} data-testid="backtest-form-summary-input" required className="md:col-span-2" />
        <div className="md:col-span-2">
          <Button className="bg-blue-600 text-white hover:bg-blue-700" data-testid="backtest-form-submit-button">
            {editingId ? "Güncelle" : "Kart Ekle"}
          </Button>
        </div>
      </form>

      <div className="border border-slate-800 bg-slate-900" data-testid="backtest-cards-table-wrapper">
        <Table data-testid="backtest-cards-table">
          <TableHeader>
            <TableRow>
              <TableHead data-testid="backtest-head-strategy">Strategy</TableHead>
              <TableHead data-testid="backtest-head-winrate">Win %</TableHead>
              <TableHead data-testid="backtest-head-dd">Max DD</TableHead>
              <TableHead data-testid="backtest-head-pf">PF</TableHead>
              <TableHead data-testid="backtest-head-risk">Risk</TableHead>
              <TableHead data-testid="backtest-head-action">Aksiyon</TableHead>
            </TableRow>
          </TableHeader>
          <TableBody>
            {cards.map((card) => (
              <TableRow key={card.id} data-testid={`backtest-row-${card.id}`}>
                <TableCell data-testid={`backtest-strategy-${card.id}`}>{card.strategy_type}</TableCell>
                <TableCell className="font-mono" data-testid={`backtest-winrate-${card.id}`}>{card.win_rate}</TableCell>
                <TableCell className="font-mono" data-testid={`backtest-dd-${card.id}`}>{card.max_drawdown}</TableCell>
                <TableCell className="font-mono" data-testid={`backtest-pf-${card.id}`}>{card.profit_factor}</TableCell>
                <TableCell data-testid={`backtest-risk-${card.id}`}>{card.risk_label}</TableCell>
                <TableCell>
                  <Button
                    size="sm"
                    variant="outline"
                    className="border-slate-700 bg-transparent"
                    onClick={() => {
                      setEditingId(card.id);
                      setForm({
                        strategy_type: card.strategy_type,
                        market_type: card.market_type,
                        timeframe: card.timeframe,
                        sample_size: card.sample_size,
                        win_rate: card.win_rate,
                        max_drawdown: card.max_drawdown,
                        profit_factor: card.profit_factor,
                        sharpe_like_score: card.sharpe_like_score,
                        performance_summary: card.performance_summary,
                        risk_label: card.risk_label,
                        period_start: card.period_start,
                        period_end: card.period_end,
                      });
                    }}
                    data-testid={`backtest-edit-${card.id}`}
                  >
                    Düzenle
                  </Button>
                </TableCell>
              </TableRow>
            ))}
          </TableBody>
        </Table>
      </div>
    </section>
  );
};
