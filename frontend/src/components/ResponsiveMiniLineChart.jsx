import { Line, LineChart, ResponsiveContainer, Tooltip, XAxis, YAxis } from "recharts";

export const ResponsiveMiniLineChart = ({ data, xKey, yKey, title, testId }) => {
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
        <ResponsiveContainer width="100%" height="100%" minWidth={220} minHeight={160}>
          <LineChart data={data}>
            <XAxis dataKey={xKey} tick={{ fontSize: 10 }} />
            <YAxis tick={{ fontSize: 10 }} />
            <Tooltip />
            <Line type="monotone" dataKey={yKey} stroke="#34d399" strokeWidth={2} dot={false} />
          </LineChart>
        </ResponsiveContainer>
      </div>
      <p className="mt-2 text-[11px] text-slate-500" data-testid={`${testId}-mobile-legend`}>Legend: {yKey}</p>
    </div>
  );
};