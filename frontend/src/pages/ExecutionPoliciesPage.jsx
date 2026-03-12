import { useEffect, useState } from "react";
import { toast } from "sonner";

import { LoadingSkeleton } from "@/components/LoadingSkeleton";
import { apiClient } from "@/lib/api";

export const ExecutionPoliciesPage = () => {
  const [payload, setPayload] = useState(null);
  const [isLoading, setIsLoading] = useState(true);

  useEffect(() => {
    const load = async () => {
      setIsLoading(true);
      try {
        const { data } = await apiClient.get("/admin/execution-policies");
        setPayload(data);
      } catch (error) {
        toast.error(error?.response?.data?.detail || "Execution policy verisi alınamadı");
      } finally {
        setIsLoading(false);
      }
    };
    load();
  }, []);

  if (isLoading) {
    return <LoadingSkeleton rows={7} testId="execution-policies-loading-skeleton" />;
  }

  const registry = payload?.registry || {};
  const violations = payload?.recent_policy_violations || [];

  return (
    <section className="space-y-4" data-testid="execution-policies-page">
      <header className="border border-slate-800 bg-slate-900 p-4" data-testid="execution-policies-header">
        <h2 className="text-4xl font-black uppercase tracking-tight text-emerald-300" data-testid="execution-policies-title">Execution Policy View</h2>
        <p className="mt-2 text-sm text-slate-400" data-testid="execution-policies-description">
          Symbol leverage cap, margin mode policy, TP/SL constraints ve son policy ihlalleri.
        </p>
      </header>

      <div className="grid gap-4 lg:grid-cols-2" data-testid="execution-policies-grid">
        <div className="rounded border border-slate-800 bg-slate-900 p-4" data-testid="execution-policies-registry-card">
          <p className="text-xs uppercase tracking-widest text-slate-500" data-testid="execution-policies-registry-title">Registry</p>
          <pre className="mt-3 overflow-x-auto text-xs text-slate-200" data-testid="execution-policies-registry-json">{JSON.stringify(registry, null, 2)}</pre>
        </div>

        <div className="rounded border border-slate-800 bg-slate-900 p-4" data-testid="execution-policies-violations-card">
          <p className="text-xs uppercase tracking-widest text-slate-500" data-testid="execution-policies-violations-title">Recent Violations</p>
          <div className="mt-3 space-y-3" data-testid="execution-policies-violations-list">
            {violations.length === 0 && <p className="text-sm text-slate-400" data-testid="execution-policies-violations-empty">Policy ihlali kaydı yok.</p>}
            {violations.map((item) => (
              <article key={`${item.entity_id}-${item.created_at}`} className="rounded border border-slate-800 p-3" data-testid="execution-policies-violation-row">
                <p className="text-xs text-slate-400" data-testid="execution-policies-violation-entity">intent: {item.entity_id}</p>
                <p className="mt-1 text-xs text-slate-400" data-testid="execution-policies-violation-time">{new Date(item.created_at).toLocaleString()}</p>
                <pre className="mt-2 overflow-x-auto text-[11px] text-slate-200" data-testid="execution-policies-violation-details">{JSON.stringify(item.details, null, 2)}</pre>
              </article>
            ))}
          </div>
        </div>
      </div>
    </section>
  );
};