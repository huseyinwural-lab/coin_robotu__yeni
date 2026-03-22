import { useState } from "react";
import { apiClient } from "@/lib/api";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { toast } from "sonner";

export const ExecutionTracePage = () => {
  const [correlationId, setCorrelationId] = useState("");
  const [trace, setTrace] = useState(null);

  const loadTrace = async () => {
    const id = correlationId.trim();
    if (!id) {
      toast.error("correlation_id girin");
      return;
    }
    try {
      const { data } = await apiClient.get(`/admin-phase3/execution-trace/${encodeURIComponent(id)}`);
      setTrace(data);
    } catch (error) {
      toast.error(error?.response?.data?.detail || "Trace bulunamadı");
    }
  };

  return (
    <section className="space-y-4" data-testid="execution-control-trace-page">
      <div className="flex flex-wrap gap-2" data-testid="execution-control-trace-search-row">
        <Input value={correlationId} onChange={(e) => setCorrelationId(e.target.value)} placeholder="correlation_id" data-testid="execution-control-trace-correlation-input" />
        <Button onClick={loadTrace} data-testid="execution-control-trace-load-button">Trace Load</Button>
      </div>

      {trace && (
        <div className="space-y-3" data-testid="execution-control-trace-content">
          <div className="rounded border border-slate-800 bg-slate-900 p-3 text-sm" data-testid="execution-control-trace-summary-card">
            correlation_id={trace.correlation_id} · chain={trace.chain?.length || 0} · events={trace.events?.length || 0} · failures={trace.failures?.length || 0}
          </div>
          <div className="rounded border border-slate-800 bg-slate-950 p-3 text-xs" data-testid="execution-control-trace-timeline">
            {(trace.chain || []).map((item, index) => (
              <div key={`${item.stage}-${index}`} className="mb-2 border-l border-slate-700 pl-3" data-testid={`execution-control-trace-item-${index}`}>
                <p>{new Date(item.created_at).toLocaleString()} · {item.stage} · actor={item.actor}</p>
                <pre className="mt-1 overflow-x-auto rounded bg-black/40 p-2">{JSON.stringify(item.payload || {}, null, 2)}</pre>
              </div>
            ))}
          </div>
        </div>
      )}
    </section>
  );
};
