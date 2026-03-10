export const MetricCard = ({ label, value, tone = "neutral", testId }) => {
  const toneStyles = {
    neutral: "border-slate-700 text-slate-100",
    blue: "border-blue-500/40 text-blue-200",
    red: "border-red-500/40 text-red-200",
    orange: "border-orange-500/40 text-orange-200",
  };

  return (
    <div className={`border bg-slate-900 p-3 ${toneStyles[tone]}`} data-testid={testId}>
      <p className="text-xs uppercase tracking-widest text-slate-400" data-testid={`${testId}-label`}>{label}</p>
      <p className="mt-2 font-mono text-2xl font-semibold" data-testid={`${testId}-value`}>{value}</p>
    </div>
  );
};
