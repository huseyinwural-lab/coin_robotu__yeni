import { useEffect, useMemo, useRef, useState } from "react";
import { createChart, CrosshairMode, CandlestickSeries, LineSeries } from "lightweight-charts";
import { toast } from "sonner";

import { apiClient } from "@/lib/api";

const timeframeOptions = ["5m", "15m", "1h", "4h", "1d"];

const markerFromSignal = (signal) => {
  const timestamp = signal?.created_at || signal?.decided_at;
  if (!timestamp) return null;
  const decision = String(signal.signal || signal.decision || signal.status || "none").toLowerCase();
  const isLong = decision.includes("long") || decision.includes("buy");
  return {
    time: Math.floor(new Date(timestamp).getTime() / 1000),
    position: isLong ? "belowBar" : "aboveBar",
    color: isLong ? "#059669" : "#dc2626",
    shape: isLong ? "arrowUp" : "arrowDown",
    text: `${signal.symbol || "SIG"} ${signal.status || signal.signal || "signal"}`,
  };
};

const markerFromTrade = (trade) => {
  const timestamp = trade?.timestamp || trade?.closed_at || trade?.opened_at;
  if (!timestamp) return null;
  const isBuy = String(trade.side || "").toLowerCase() === "buy";
  return {
    time: Math.floor(new Date(timestamp).getTime() / 1000),
    position: isBuy ? "belowBar" : "aboveBar",
    color: "#f59e0b",
    shape: "circle",
    text: `${trade.symbol || "TRD"} pnl=${trade.pnl ?? trade.realized_pnl ?? 0}`,
  };
};

const buildLineData = (candles, extractor) =>
  (candles || []).map((item) => ({ time: Math.floor(Number(item.close_time || item.open_time) / 1000), value: extractor(item) })).filter((item) => Number.isFinite(item.value));

const average = (values) => values.reduce((sum, value) => sum + value, 0) / Math.max(values.length, 1);

const buildMovingAverage = (candles, period) => {
  const rows = [];
  for (let index = period - 1; index < candles.length; index += 1) {
    const slice = candles.slice(index - period + 1, index + 1).map((item) => Number(item.close));
    rows.push({ time: Math.floor(Number(candles[index].close_time || candles[index].open_time) / 1000), value: average(slice) });
  }
  return rows;
};

export const UserMarketChartPanel = ({ symbol = "BTCUSDT", initialTimeframe = "1h", signals = [], trades = [], selectedSignal = null, onTimeframeChange, testIdPrefix = "user-market-chart" }) => {
  const containerRef = useRef(null);
  const chartRef = useRef(null);
  const seriesRef = useRef({ candle: null, maFast: null, maSlow: null });
  const [timeframe, setTimeframe] = useState(initialTimeframe);
  const [payload, setPayload] = useState(null);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    setTimeframe(initialTimeframe);
  }, [initialTimeframe]);

  useEffect(() => {
    const load = async () => {
      setLoading(true);
      try {
        const { data } = await apiClient.get("/market/candles", {
          params: {
            symbol,
            timeframe,
            market_type: "futures",
            limit: 220,
          },
        });
        setPayload(data || null);
      } catch (error) {
        toast.error(error?.response?.data?.detail || "Chart candles alınamadı");
      } finally {
        setLoading(false);
      }
    };
    if (symbol) load();
  }, [symbol, timeframe]);

  useEffect(() => {
    if (!containerRef.current) return undefined;
    const chart = createChart(containerRef.current, {
      layout: { background: { color: "#020617" }, textColor: "#cbd5e1" },
      grid: { vertLines: { color: "#1e293b" }, horzLines: { color: "#1e293b" } },
      rightPriceScale: { borderColor: "#334155" },
      timeScale: { borderColor: "#334155", timeVisible: true },
      crosshair: { mode: CrosshairMode.Normal },
      handleScroll: true,
      handleScale: true,
    });
    const candleSeries = chart.addSeries(CandlestickSeries, { upColor: "#22c55e", downColor: "#ef4444", borderVisible: false, wickUpColor: "#22c55e", wickDownColor: "#ef4444" });
    const maFast = chart.addSeries(LineSeries, { color: "#38bdf8", lineWidth: 2, title: "MA20" });
    const maSlow = chart.addSeries(LineSeries, { color: "#f59e0b", lineWidth: 2, title: "MA50" });
    chartRef.current = chart;
    seriesRef.current = { candle: candleSeries, maFast, maSlow };
    const observer = new ResizeObserver((entries) => {
      const entry = entries[0];
      if (!entry) return;
      chart.applyOptions({ width: entry.contentRect.width, height: 420 });
    });
    observer.observe(containerRef.current);
    chart.applyOptions({ width: containerRef.current.clientWidth, height: 420 });
    return () => {
      observer.disconnect();
      chart.remove();
    };
  }, []);

  const chartMarkers = useMemo(() => {
    const selectedMarker = selectedSignal ? markerFromSignal(selectedSignal) : null;
    return [selectedMarker, ...signals.map(markerFromSignal), ...trades.map(markerFromTrade)].filter(Boolean).sort((left, right) => left.time - right.time);
  }, [selectedSignal, signals, trades]);

  useEffect(() => {
    if (!payload?.candles || !seriesRef.current.candle) return;
    const candles = payload.candles.map((item) => ({
      time: Math.floor(Number(item.open_time) / 1000),
      open: Number(item.open),
      high: Number(item.high),
      low: Number(item.low),
      close: Number(item.close),
    }));
    seriesRef.current.candle.setData(candles);
    seriesRef.current.candle.setMarkers(chartMarkers);
    seriesRef.current.maFast.setData(buildMovingAverage(payload.candles, 20));
    seriesRef.current.maSlow.setData(buildMovingAverage(payload.candles, 50));
    chartRef.current?.timeScale().fitContent();
  }, [payload, chartMarkers]);

  return (
    <article className="rounded border border-slate-800 bg-slate-950 p-4" data-testid={`${testIdPrefix}-panel`}>
      <div className="flex flex-wrap items-center justify-between gap-3" data-testid={`${testIdPrefix}-header`}>
        <div>
          <p className="text-xs uppercase tracking-widest text-slate-500" data-testid={`${testIdPrefix}-kicker`}>Market + Signal Chart</p>
          <h3 className="text-lg font-semibold text-slate-100" data-testid={`${testIdPrefix}-title`}>{symbol}</h3>
          <p className="text-xs text-slate-400" data-testid={`${testIdPrefix}-subtitle`}>Lightweight Charts · signal highlight · entry/exit marker · MA20/MA50 overlay</p>
        </div>
        <select
          value={timeframe}
          onChange={(event) => {
            setTimeframe(event.target.value);
            onTimeframeChange?.(event.target.value);
          }}
          className="h-10 rounded border border-slate-700 bg-black px-3 text-sm text-slate-100"
          data-testid={`${testIdPrefix}-timeframe-select`}
        >
          {timeframeOptions.map((option) => (
            <option key={option} value={option} data-testid={`${testIdPrefix}-timeframe-option-${option}`}>{option}</option>
          ))}
        </select>
      </div>
      <div ref={containerRef} className="mt-4 h-[420px] w-full" data-testid={`${testIdPrefix}-canvas`} />
      <div className="mt-3 grid gap-2 md:grid-cols-4 text-xs text-slate-300" data-testid={`${testIdPrefix}-meta-grid`}>
        <p data-testid={`${testIdPrefix}-meta-candle-count`}>candles={payload?.candle_count ?? 0}</p>
        <p data-testid={`${testIdPrefix}-meta-provider`}>provider={payload?.data_source || "-"}</p>
        <p data-testid={`${testIdPrefix}-meta-last-candle`}>last={payload?.last_candle_time || "-"}</p>
        <p data-testid={`${testIdPrefix}-meta-loading`}>loading={String(loading)}</p>
      </div>
    </article>
  );
};
