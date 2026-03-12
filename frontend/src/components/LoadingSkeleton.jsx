export const LoadingSkeleton = ({ rows = 3, testId = "loading-skeleton" }) => {
  return (
    <div className="space-y-2" data-testid={testId} aria-live="polite" aria-label="Yükleniyor">
      {Array.from({ length: rows }).map((_, index) => (
        <div
          key={`${testId}-${index}`}
          className="h-10 animate-pulse rounded border border-slate-700 bg-slate-800/60"
          data-testid={`${testId}-row`}
        />
      ))}
    </div>
  );
};