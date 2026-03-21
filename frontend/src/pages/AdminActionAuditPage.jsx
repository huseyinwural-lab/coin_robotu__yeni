import { useCallback, useEffect, useState } from "react";
import { toast } from "sonner";

import { Button } from "@/components/ui/button";
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogHeader,
  DialogTitle,
} from "@/components/ui/dialog";
import { Input } from "@/components/ui/input";
import { apiClient } from "@/lib/api";

export const AdminActionAuditPage = () => {
  const [items, setItems] = useState([]);
  const [loading, setLoading] = useState(false);
  const [filters, setFilters] = useState({ user_id: "", action_type: "", since_hours: "24" });
  const [detailOpen, setDetailOpen] = useState(false);
  const [selectedDetail, setSelectedDetail] = useState(null);

  const load = useCallback(async () => {
    setLoading(true);
    try {
      const { data } = await apiClient.get("/admin/live-trading/control-layer/action-audit", {
        params: {
          user_id: filters.user_id || undefined,
          action_type: filters.action_type || undefined,
          since_hours: Number(filters.since_hours || 24),
          limit: 200,
        },
      });
      setItems(data?.items || []);
    } catch (error) {
      const detail = error?.response?.data?.detail;
      toast.error(typeof detail === "string" ? detail : "Action audit verisi alınamadı");
    } finally {
      setLoading(false);
    }
  }, [filters]);

  useEffect(() => {
    load();
  }, [load]);

  const openDetail = async (auditId) => {
    try {
      const { data } = await apiClient.get(`/admin/live-trading/control-layer/action-audit/${auditId}`);
      setSelectedDetail(data || null);
      setDetailOpen(true);
    } catch (error) {
      const detail = error?.response?.data?.detail;
      toast.error(typeof detail === "string" ? detail : "Audit detay alınamadı");
    }
  };

  return (
    <section className="space-y-4" data-testid="admin-action-audit-page">
      <header className="rounded border border-violet-700/60 bg-violet-950/20 p-4" data-testid="admin-action-audit-header">
        <h1 className="text-4xl font-black uppercase tracking-tight text-violet-300" data-testid="admin-action-audit-title">Global Action Audit Panel</h1>
        <p className="mt-2 text-sm text-slate-400" data-testid="admin-action-audit-description">mode switch, kill switch, risk update, retry/override dahil tüm kritik aksiyonlar.</p>
      </header>

      <div className="grid gap-2 rounded border border-slate-700 bg-slate-900 p-3 md:grid-cols-5" data-testid="admin-action-audit-filter-grid">
        <Input
          value={filters.user_id}
          onChange={(e) => setFilters((prev) => ({ ...prev, user_id: e.target.value }))}
          placeholder="user_id"
          data-testid="admin-action-audit-user-filter-input"
        />
        <Input
          value={filters.action_type}
          onChange={(e) => setFilters((prev) => ({ ...prev, action_type: e.target.value }))}
          placeholder="action type"
          data-testid="admin-action-audit-action-filter-input"
        />
        <Input
          value={filters.since_hours}
          onChange={(e) => setFilters((prev) => ({ ...prev, since_hours: e.target.value }))}
          placeholder="since_hours"
          data-testid="admin-action-audit-time-filter-input"
        />
        <Button onClick={load} data-testid="admin-action-audit-apply-filter-button">Filtrele</Button>
        <p className="self-center text-xs text-slate-400" data-testid="admin-action-audit-loading-state">loading={String(loading)} · count={items.length}</p>
      </div>

      <div className="space-y-2" data-testid="admin-action-audit-list">
        {items.map((item, idx) => (
          <article key={item.id} className="rounded border border-slate-700 bg-slate-900 p-3" data-testid={`admin-action-audit-item-${idx}`}>
            <div className="flex flex-wrap items-center justify-between gap-2" data-testid={`admin-action-audit-item-head-${idx}`}>
              <p className="text-sm font-semibold" data-testid={`admin-action-audit-item-action-${idx}`}>{item.action}</p>
              <Button variant="outline" size="sm" onClick={() => openDetail(item.id)} data-testid={`admin-action-audit-item-detail-${idx}`}>Detay</Button>
            </div>
            <p className="mt-1 text-xs text-slate-400" data-testid={`admin-action-audit-item-meta-${idx}`}>
              {item.created_at} · {item.actor_role} · {item.actor_user_id}
            </p>
            <p className="mt-1 text-xs text-slate-500" data-testid={`admin-action-audit-item-entity-${idx}`}>
              {item.entity_type}:{item.entity_id} · severity={item.severity}
            </p>
          </article>
        ))}
        {items.length === 0 && <p className="text-sm text-slate-500" data-testid="admin-action-audit-empty">Kayıt bulunamadı.</p>}
      </div>

      <Dialog open={detailOpen} onOpenChange={setDetailOpen}>
        <DialogContent className="max-w-2xl border border-slate-700 bg-slate-950" data-testid="admin-action-audit-detail-modal">
          <DialogHeader>
            <DialogTitle data-testid="admin-action-audit-detail-title">Audit Detail</DialogTitle>
            <DialogDescription data-testid="admin-action-audit-detail-description">Payload drill-down</DialogDescription>
          </DialogHeader>
          <pre className="max-h-80 overflow-auto rounded border border-slate-700 bg-black p-3 text-[11px]" data-testid="admin-action-audit-detail-json">
            {JSON.stringify(selectedDetail || {}, null, 2)}
          </pre>
        </DialogContent>
      </Dialog>
    </section>
  );
};
