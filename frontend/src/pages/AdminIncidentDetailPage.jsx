import { useCallback, useEffect, useMemo, useState } from "react";
import { useNavigate, useParams } from "react-router-dom";
import { ArrowLeft } from "lucide-react";
import { toast } from "sonner";

import { Button } from "@/components/ui/button";
import { apiClient } from "@/lib/api";

export default function AdminIncidentDetailPage() {
  const navigate = useNavigate();
  const { incidentId } = useParams();
  const [detail, setDetail] = useState(null);
  const [loading, setLoading] = useState(false);

  const loadDetail = useCallback(async () => {
    if (!incidentId) return;
    setLoading(true);
    try {
      const { data } = await apiClient.get(`/admin/incident-intelligence/incidents/${encodeURIComponent(incidentId)}`);
      setDetail(data || null);
    } catch (error) {
      toast.error(error?.response?.data?.detail || "Incident detail alınamadı");
    } finally {
      setLoading(false);
    }
  }, [incidentId]);

  useEffect(() => {
    loadDetail();
  }, [loadDetail]);

  const incident = detail?.incident || null;
  const timeline = useMemo(() => detail?.timeline?.chain || [], [detail?.timeline?.chain]);

  return (
    <section className="space-y-4 bg-[#f9fafb] text-slate-900" data-testid="incident-detail-page">
      <header className="border border-slate-300 bg-white p-4" data-testid="incident-detail-header">
        <div className="flex flex-wrap items-center justify-between gap-3">
          <div>
            <p className="text-xs uppercase tracking-[0.22em] text-slate-500" data-testid="incident-detail-kicker">Incident Detail</p>
            <h1 className="mt-1 text-3xl font-black tracking-tight" data-testid="incident-detail-title">{incident?.title || incidentId}</h1>
          </div>
          <Button variant="outline" onClick={() => navigate("/admin/incident-intelligence")} data-testid="incident-detail-back-button"><ArrowLeft className="mr-2 h-4 w-4" />Geri</Button>
        </div>
      </header>

      <div className="grid gap-4 xl:grid-cols-12" data-testid="incident-detail-main-grid">
        <div className="space-y-4 xl:col-span-8">
          <div className="border border-slate-300 bg-white p-4" data-testid="incident-detail-timeline-panel">
            <h2 className="text-sm font-bold uppercase tracking-[0.2em]" data-testid="incident-detail-timeline-title">Full Timeline</h2>
            <div className="mt-4 space-y-3" data-testid="incident-detail-timeline-list">
              {timeline.map((item, index) => (
                <div key={`${item.kind}-${item.id}-${index}`} className="grid grid-cols-[18px_1fr] gap-3" data-testid={`incident-detail-timeline-item-${index}`}>
                  <div className="flex flex-col items-center"><span className="h-3 w-3 rounded-full bg-slate-900" /><span className="min-h-[56px] w-px bg-slate-200" /></div>
                  <div className="border border-slate-200 p-3">
                    <p className="font-mono text-[11px] uppercase tracking-[0.2em] text-slate-500" data-testid={`incident-detail-timeline-kind-${index}`}>{item.kind}</p>
                    <p className="mt-1 text-sm font-semibold" data-testid={`incident-detail-timeline-id-${index}`}>{item.id}</p>
                    <p className="mt-1 font-mono text-xs text-slate-500" data-testid={`incident-detail-timeline-timestamp-${index}`}>{item.timestamp || "-"}</p>
                    <pre className="mt-2 overflow-x-auto bg-slate-50 p-2 text-[11px] text-slate-700" data-testid={`incident-detail-timeline-payload-${index}`}>{JSON.stringify(item.payload || {}, null, 2)}</pre>
                  </div>
                </div>
              ))}
            </div>
          </div>
        </div>

        <aside className="space-y-4 xl:col-span-4">
          <div className="border border-slate-300 bg-white p-4" data-testid="incident-detail-summary-panel">
            <h2 className="text-sm font-bold uppercase tracking-[0.2em]" data-testid="incident-detail-summary-title">Incident Summary</h2>
            <div className="mt-3 space-y-2 text-sm">
              <p data-testid="incident-detail-state">state: {incident?.state || "-"}</p>
              <p data-testid="incident-detail-owner">owner: {incident?.owner || "-"}</p>
              <p data-testid="incident-detail-root-cause">root_cause: {incident?.root_cause || "-"}</p>
              <p data-testid="incident-detail-confidence">confidence: {incident?.confidence_score ?? 0}</p>
            </div>
          </div>

          <div className="border border-slate-300 bg-white p-4" data-testid="incident-detail-evidence-panel">
            <h2 className="text-sm font-bold uppercase tracking-[0.2em]" data-testid="incident-detail-evidence-title">Linked Artefacts & Evidence</h2>
            <pre className="mt-3 overflow-x-auto bg-slate-50 p-2 text-[11px] text-slate-700" data-testid="incident-detail-evidence-json">{JSON.stringify(incident?.evidence || {}, null, 2)}</pre>
          </div>

          <div className="border border-slate-300 bg-white p-4" data-testid="incident-detail-actions-panel">
            <h2 className="text-sm font-bold uppercase tracking-[0.2em]" data-testid="incident-detail-actions-title">Action History</h2>
            <div className="mt-3 space-y-2" data-testid="incident-detail-actions-list">
              {(incident?.remediation_history || []).map((entry, index) => (
                <div key={`${entry.action}-${index}`} className="border border-slate-200 p-2 text-xs" data-testid={`incident-detail-action-item-${index}`}>
                  <p className="font-mono" data-testid={`incident-detail-action-name-${index}`}>{entry.action}</p>
                  <p data-testid={`incident-detail-action-status-${index}`}>{entry.status}</p>
                </div>
              ))}
            </div>
          </div>
        </aside>
      </div>

      {loading && <p className="font-mono text-xs text-slate-500" data-testid="incident-detail-loading">loading...</p>}
    </section>
  );
}