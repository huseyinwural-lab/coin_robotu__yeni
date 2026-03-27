import { useState } from "react";

import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";

const defaultFilters = {
  entity_type: "",
  entity_id: "",
  actor_user_id: "",
  action: "",
  from_date: "",
  to_date: "",
  limit: 50,
};

export const AuditTimelinePanel = ({ data, loading, error, onLoad }) => {
  const [filters, setFilters] = useState(defaultFilters);
  const items = data?.items || [];

  const apply = async (event) => {
    event.preventDefault();
    await onLoad({
      ...filters,
      limit: Number(filters.limit || 50),
    });
  };

  return (
    <section className="rounded-2xl border border-slate-700 bg-slate-950/70 p-4" data-testid="audit-timeline-panel">
      <div className="mb-3 flex items-center justify-between gap-3">
        <div>
          <h3 className="text-base font-semibold text-orange-200" data-testid="audit-timeline-panel-title">Audit Timeline</h3>
          <p className="text-xs text-slate-400" data-testid="audit-timeline-panel-subtitle">Entity / user / action / date filtreleme + diff highlights</p>
        </div>
        <Button type="button" variant="outline" onClick={() => onLoad({ limit: 50 })} data-testid="audit-timeline-reset-button">Sıfırla</Button>
      </div>

      <form className="mb-3 grid gap-2 md:grid-cols-3" onSubmit={apply} data-testid="audit-timeline-filter-form">
        <Input value={filters.entity_type} onChange={(event) => setFilters((prev) => ({ ...prev, entity_type: event.target.value }))} placeholder="entity_type" data-testid="audit-timeline-filter-entity-type-input" />
        <Input value={filters.entity_id} onChange={(event) => setFilters((prev) => ({ ...prev, entity_id: event.target.value }))} placeholder="entity_id" data-testid="audit-timeline-filter-entity-id-input" />
        <Input value={filters.actor_user_id} onChange={(event) => setFilters((prev) => ({ ...prev, actor_user_id: event.target.value }))} placeholder="actor_user_id" data-testid="audit-timeline-filter-actor-user-id-input" />
        <Input value={filters.action} onChange={(event) => setFilters((prev) => ({ ...prev, action: event.target.value }))} placeholder="action" data-testid="audit-timeline-filter-action-input" />
        <Input type="datetime-local" value={filters.from_date} onChange={(event) => setFilters((prev) => ({ ...prev, from_date: event.target.value }))} data-testid="audit-timeline-filter-from-date-input" />
        <Input type="datetime-local" value={filters.to_date} onChange={(event) => setFilters((prev) => ({ ...prev, to_date: event.target.value }))} data-testid="audit-timeline-filter-to-date-input" />
        <Input type="number" value={filters.limit} onChange={(event) => setFilters((prev) => ({ ...prev, limit: event.target.value }))} placeholder="limit" data-testid="audit-timeline-filter-limit-input" />
        <Button disabled={loading} data-testid="audit-timeline-filter-apply-button">{loading ? "Yükleniyor..." : "Filtreyi Uygula"}</Button>
      </form>

      {error && <p className="text-sm text-red-300" data-testid="audit-timeline-error-state">{error}</p>}
      {!error && !loading && items.length === 0 && <p className="text-sm text-slate-400" data-testid="audit-timeline-empty-state">Timeline kaydı bulunamadı.</p>}

      <div className="max-h-80 space-y-2 overflow-auto" data-testid="audit-timeline-items-list">
        {items.map((item, index) => (
          <article key={item.id || index} className="rounded-md border border-slate-800 p-2 text-xs text-slate-200" data-testid={`audit-timeline-item-${index}`}>
            <p data-testid={`audit-timeline-item-summary-${index}`}>{item.action} · {item.entity_type} · {item.created_at}</p>
            <p className="text-slate-400" data-testid={`audit-timeline-item-actor-${index}`}>actor={item.actor_user_id || "system"}</p>
            <p className="text-slate-400" data-testid={`audit-timeline-item-diff-keys-${index}`}>diff_keys: {(item.diff_keys || []).join(", ") || "-"}</p>

            {(item.diff_highlights || []).length > 0 && (
              <div className="mt-1 space-y-1" data-testid={`audit-timeline-item-diff-highlights-${index}`}>
                {(item.diff_highlights || []).map((diff, diffIndex) => (
                  <p key={`${diff.field}-${diffIndex}`} data-testid={`audit-timeline-item-diff-highlight-${index}-${diffIndex}`}>
                    {diff.field}: {JSON.stringify(diff.old)} → {JSON.stringify(diff.new)}
                  </p>
                ))}
              </div>
            )}
          </article>
        ))}
      </div>
    </section>
  );
};
