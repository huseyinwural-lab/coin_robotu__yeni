import { useEffect, useState } from "react";

import { Line, LineChart, ResponsiveContainer, Tooltip, XAxis, YAxis } from "recharts";

export const ResponsiveMiniLineChart = ({ data, xKey, yKey, title, testId }) => {
  const [isChartReady, setIsChartReady] = useState(false);

  useEffect(() => {
    const timer = window.setTimeout(() => setIsChartReady(true), 0);
    return () => window.clearTimeout(timer);
  }, []);

  return (
    <div
      className="rounded border border-slate-800 bg-slate-900 p-3"
      data-testid={testId}
      aria-label={`${title} grafiği`}
      role="img"
      style={{ touchAction: "pan-x pinch-zoom" }}
    >
      <p className="mb-2 text-xs uppercase tracking-widest text-slate-500" data-testid={`${testId}-title`}>{title}</p>
      <div className="h-44 w-full" data-testid={`${testId}-canvas`}>
        {isChartReady ? (
          <ResponsiveContainer width="100%" height="100%" minWidth={240} minHeight={160}>
            <LineChart data={data}>
              <XAxis dataKey={xKey} tick={{ fontSize: 10 }} />
              <YAxis tick={{ fontSize: 10 }} />
              <Tooltip />
              <Line type="monotone" dataKey={yKey} stroke="#34d399" strokeWidth={2} dot={false} />
            </LineChart>
          </ResponsiveContainer>
        ) : (
          <div className="h-full w-full animate-pulse rounded bg-slate-800/60" data-testid={`${testId}-loading-placeholder`} />
        )}
      </div>
      <p className="mt-2 text-[11px] text-slate-500" data-testid={`${testId}-mobile-legend`}>Legend: {yKey}</p>
    </div>
  );
};