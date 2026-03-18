import { useMemo } from "react";
import { useNavigate, useSearchParams } from "react-router-dom";

import { Button } from "@/components/ui/button";

const intervalMap = {
  "1m": "1",
  "5m": "5",
  "15m": "15",
  "1h": "60",
  "4h": "240",
  "1d": "D",
};

export const UserChartPage = () => {
  const navigate = useNavigate();
  const [searchParams] = useSearchParams();

  const symbol = String(searchParams.get("symbol") || "BTCUSDT").trim().toUpperCase();
  const timeframe = String(searchParams.get("tf") || "1h").trim().toLowerCase();

  const chartUrl = useMemo(() => {
    const interval = intervalMap[timeframe] || "60";
    const tvSymbol = `BINANCE:${symbol}`;
    const params = new URLSearchParams({
      symbol: tvSymbol,
      interval,
      theme: "dark",
      style: "1",
      timezone: "Etc/UTC",
      withdateranges: "1",
      hide_side_toolbar: "0",
      allow_symbol_change: "1",
    });
    return `https://s.tradingview.com/widgetembed/?${params.toString()}`;
  }, [symbol, timeframe]);

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

      <div className="aspect-[16/9] w-full overflow-hidden rounded border border-slate-800 bg-black" data-testid="user-chart-embed-container">
        <iframe
          title={`TradingView-${symbol}-${timeframe}`}
          src={chartUrl}
          className="h-full w-full"
          frameBorder="0"
          allowFullScreen
          data-testid="user-chart-tradingview-iframe"
        />
      </div>
    </section>
  );
};
