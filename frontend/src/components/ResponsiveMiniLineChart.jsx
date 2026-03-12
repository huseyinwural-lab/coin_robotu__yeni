export const ResponsiveMiniLineChart = ({ data, xKey, yKey, title, testId }) => {
  const maxValue = Math.max(...(data || []).map((item) => Number(item[yKey] || 0)), 1);

  return (
    <div
      className="rounded border border-slate-800 bg-slate-900 p-3"
      data-testid={testId}
      aria-label={`${title} grafiği`}
      role="img"
    >
      <p className="mb-2 text-xs uppercase tracking-widest text-slate-500" data-testid={`${testId}-title`}>{title}</p>
      <div className="grid gap-2" data-testid={`${testId}-canvas`}>
        {(data || []).map((item) => {
          const value = Number(item[yKey] || 0);
          const widthPct = Math.max(4, (Math.abs(value) / maxValue) * 100);
          return (
            <div key={`${item[xKey]}`} className="grid grid-cols-[120px_1fr_80px] items-center gap-2" data-testid={`${testId}-row`}>
              <span className="truncate text-xs text-slate-400" data-testid={`${testId}-row-label`}>{item[xKey]}</span>
              <div className="h-3 w-full rounded bg-slate-800" data-testid={`${testId}-row-track`}>
                <div
                  className={`h-3 rounded ${value >= 0 ? "bg-emerald-400" : "bg-rose-400"}`}
                  style={{ width: `${widthPct}%` }}
                  data-testid={`${testId}-row-bar`}
                />
              </div>
              <span className="text-right text-xs text-slate-300" data-testid={`${testId}-row-value`}>{value}</span>
            </div>
          );
        })}
      </div>
      <p className="mt-2 text-[11px] text-slate-500" data-testid={`${testId}-mobile-legend`}>Legend: {yKey}</p>
    </div>
  );
};