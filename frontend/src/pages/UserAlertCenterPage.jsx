import { useEffect, useMemo, useState } from "react";
import { Link } from "react-router-dom";
import { toast } from "sonner";

import { Button } from "@/components/ui/button";
import { apiClient } from "@/lib/api";

const toneMap = {
  info: "border-blue-700 bg-blue-950/20",
  warning: "border-amber-700 bg-amber-950/20",
  critical: "border-rose-700 bg-rose-950/30",
};

export const UserAlertCenterPage = () => {
  const [items, setItems] = useState([]);
  const [filters, setFilters] = useState({ severity: "all", category: "all", query: "" });
  const [noteById, setNoteById] = useState({});
  const [loading, setLoading] = useState(true);

  const load = async () => {
    setLoading(true);
    try {
      const params = { limit: 100 };
      if (filters.severity !== "all") params.severity = filters.severity;
      if (filters.category !== "all") params.category = filters.category;
      if (filters.query.trim()) params.query = filters.query.trim();
      const { data } = await apiClient.get("/user/alerts", { params });
      setItems(data?.items || []);
    } catch (error) {
      toast.error(error?.response?.data?.detail || "Alert center yüklenemedi");
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    load();
  }, [filters.severity, filters.category, filters.query]);

  const updateAlert = async (alertId, action) => {
    try {
      await apiClient.post(`/user/alerts/${alertId}/${action}`, { note: noteById[alertId] || "" });
      toast.success(`Alert ${action} edildi`);
      await load();
    } catch (error) {
      toast.error(error?.response?.data?.detail || `Alert ${action} başarısız`);
    }
  };

  const grouped = useMemo(() => items, [items]);

  return (
    <section className="space-y-4" data-testid="user-alert-center-page">
      <header className="border border-slate-800 bg-slate-900 p-4" data-testid="user-alert-center-header">
        <h2 className="text-4xl font-black uppercase tracking-tight" data-testid="user-alert-center-title">Alert Center</h2>
        <p className="mt-2 text-sm text-slate-400" data-testid="user-alert-center-description">Severity, kategori, history, backend persist acknowledge/dismiss ve drill-down bağlantıları tek yerde.</p>
      </header>

      <div className="grid gap-3 md:grid-cols-3" data-testid="user-alert-center-filter-grid">
        <select value={filters.severity} onChange={(event) => setFilters((prev) => ({ ...prev, severity: event.target.value }))} className="border border-slate-700 bg-slate-950 px-3 py-2 text-sm" data-testid="user-alert-center-severity-filter"><option value="all">all severity</option><option value="info">info</option><option value="warning">warning</option><option value="critical">critical</option></select>
        <select value={filters.category} onChange={(event) => setFilters((prev) => ({ ...prev, category: event.target.value }))} className="border border-slate-700 bg-slate-950 px-3 py-2 text-sm" data-testid="user-alert-center-category-filter"><option value="all">all category</option><option value="risk">risk</option><option value="execution">execution</option><option value="system">system</option></select>
        <input value={filters.query} onChange={(event) => setFilters((prev) => ({ ...prev, query: event.target.value }))} className="border border-slate-700 bg-slate-950 px-3 py-2 text-sm" placeholder="search" data-testid="user-alert-center-search-input" />
      </div>

      <div className="space-y-3" data-testid="user-alert-center-alerts-list">
        {grouped.map((item, idx) => (
          <article key={item.id} className={`border p-4 ${toneMap[item.severity] || toneMap.info}`} data-testid={`user-alert-center-alert-item-${idx}`}>
            <div className="flex flex-wrap items-center justify-between gap-2">
              <div>
                <p className="text-xs uppercase tracking-wide text-slate-300" data-testid={`user-alert-center-alert-meta-${idx}`}>{item.severity} · {item.category}</p>
                <h3 className="mt-1 font-semibold text-slate-100" data-testid={`user-alert-center-alert-message-${idx}`}>{item.message}</h3>
                <p className="mt-1 text-xs text-slate-400" data-testid={`user-alert-center-alert-timestamp-${idx}`}>{String(item.timestamp || "-")}</p>
              </div>
              <p className="rounded border border-slate-700 px-2 py-1 text-xs text-slate-200" data-testid={`user-alert-center-alert-status-${idx}`}>{item.status}</p>
            </div>

            <div className="mt-3 flex flex-wrap gap-2 text-xs" data-testid={`user-alert-center-alert-drilldown-${idx}`}>
              {item.drilldown?.execution_ref && <Link to="/user/execution" className="underline" data-testid={`user-alert-center-drilldown-execution-${idx}`}>execution</Link>}
              {item.drilldown?.activity_log_ref && <Link to="/user/activity-log" className="underline" data-testid={`user-alert-center-drilldown-activity-${idx}`}>activity log</Link>}
              {item.drilldown?.strategy_ref && <Link to="/user/bot-profiles" className="underline" data-testid={`user-alert-center-drilldown-strategy-${idx}`}>strategy</Link>}
              {item.drilldown?.symbol && <Link to={`/user/chart?symbol=${encodeURIComponent(item.drilldown.symbol)}&tf=1h`} className="underline" data-testid={`user-alert-center-drilldown-symbol-${idx}`}>symbol detail</Link>}
            </div>

            <textarea value={noteById[item.id] || ""} onChange={(event) => setNoteById((prev) => ({ ...prev, [item.id]: event.target.value }))} className="mt-3 min-h-[70px] w-full border border-slate-700 bg-slate-950 px-3 py-2 text-sm text-slate-100" placeholder="note (optional)" data-testid={`user-alert-center-note-input-${idx}`} />
            <div className="mt-3 flex flex-wrap gap-2" data-testid={`user-alert-center-alert-actions-${idx}`}>
              <Button type="button" variant="outline" onClick={() => updateAlert(item.id, 'ack')} data-testid={`user-alert-center-ack-button-${idx}`}>Acknowledge</Button>
              <Button type="button" variant="outline" onClick={() => updateAlert(item.id, 'dismiss')} data-testid={`user-alert-center-dismiss-button-${idx}`}>Dismiss</Button>
            </div>

            <pre className="mt-3 overflow-x-auto bg-slate-950 p-2 text-[11px] text-slate-300" data-testid={`user-alert-center-history-${idx}`}>{JSON.stringify(item.history || [], null, 2)}</pre>
          </article>
        ))}
      </div>

      {(grouped || []).length === 0 && !loading && <div className="border border-slate-800 bg-slate-900 p-4 text-sm text-slate-400" data-testid="user-alert-center-empty-state">Bu filtrelerle alert bulunamadı.</div>}
      {loading && <p className="text-xs text-slate-500" data-testid="user-alert-center-loading-state">loading...</p>}
    </section>
  );
};
