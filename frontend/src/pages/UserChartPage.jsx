import { useEffect, useState } from "react";
import { useNavigate, useSearchParams } from "react-router-dom";
import { toast } from "sonner";

import { Button } from "@/components/ui/button";
import { UserMarketChartPanel } from "@/components/UserMarketChartPanel";
import { apiClient } from "@/lib/api";

export const UserChartPage = () => {
  const navigate = useNavigate();
  const [searchParams] = useSearchParams();
  const [signals, setSignals] = useState([]);
  const [trades, setTrades] = useState([]);

  const symbol = String(searchParams.get("symbol") || "BTCUSDT").trim().toUpperCase();
  const timeframe = String(searchParams.get("tf") || "1h").trim().toLowerCase();

  useEffect(() => {
    const loadContext = async () => {
      try {
        const [signalsRes, tradesRes] = await Promise.all([
          apiClient.get("/user/signals", { params: { limit: 40 } }),
          apiClient.get("/user/live/trades", { params: { window: "24h", limit: 40 } }),
        ]);
        setSignals((signalsRes.data || []).filter((item) => String(item.symbol || "").toUpperCase() === symbol));
        setTrades((tradesRes.data?.items || []).filter((item) => String(item.symbol || "").toUpperCase() === symbol));
      } catch (error) {
        toast.error(error?.response?.data?.detail || "Chart context yüklenemedi");
      }
    };
    loadContext();
  }, [symbol]);

  return (
    <section className="space-y-4" data-testid="user-chart-page">
      <header className="rounded border border-slate-800 bg-slate-900 p-4" data-testid="user-chart-header">
        <div className="flex flex-wrap items-center justify-between gap-3" data-testid="user-chart-header-row">
          <div data-testid="user-chart-title-wrap">
            <h2 className="text-4xl font-black uppercase tracking-tight" data-testid="user-chart-title">Market Chart</h2>
            <p className="mt-2 text-sm text-slate-400" data-testid="user-chart-subtitle">
              symbol: {symbol} · timeframe: {timeframe}
            </p>
          </div>
          <Button
            type="button"
            variant="outline"
            onClick={() => navigate("/user/scanner")}
            data-testid="user-chart-back-to-scanner-button"
          >
            Scanner’a Dön
          </Button>
        </div>
      </header>

      <UserMarketChartPanel symbol={symbol} initialTimeframe={timeframe} signals={signals} trades={trades} testIdPrefix="user-chart-lightweight" />
    </section>
  );
};
