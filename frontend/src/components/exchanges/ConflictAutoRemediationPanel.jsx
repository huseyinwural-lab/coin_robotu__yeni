import { Button } from "@/components/ui/button";

export const ConflictAutoRemediationPanel = ({ data, loading, error, onRefresh, onApplyDraft }) => {
  const drafts = data?.drafts || [];
  const summary = data?.summary || {};

  return (
    <section className="rounded-2xl border border-amber-500/30 bg-slate-950/80 p-4" data-testid="conflict-auto-remediation-panel">
      <div className="mb-3 flex items-center justify-between gap-2">
        <div>
          <h3 className="text-base font-semibold text-amber-200" data-testid="conflict-auto-remediation-title">Conflict Auto-Remediation Drafts (P2-405)</h3>
          <p className="text-xs text-slate-400" data-testid="conflict-auto-remediation-subtitle">Çakışma tipine göre önerilen düzeltme taslakları</p>
        </div>
        <Button type="button" variant="outline" onClick={onRefresh} data-testid="conflict-auto-remediation-refresh-button">Yenile</Button>
      </div>

      {loading && <p className="text-sm text-slate-400" data-testid="conflict-auto-remediation-loading-state">Yükleniyor...</p>}
      {!loading && error && <p className="text-sm text-red-300" data-testid="conflict-auto-remediation-error-state">{error}</p>}

      {!loading && !error && (
        <>
          <p className="mb-2 text-xs text-slate-300" data-testid="conflict-auto-remediation-summary">total={summary.total_drafts ?? 0}, block={summary.blocking_draft_count ?? 0}, warn={summary.warning_draft_count ?? 0}</p>

          <div className="space-y-2" data-testid="conflict-auto-remediation-drafts-list">
            {drafts.length === 0 && <p className="text-xs text-slate-400" data-testid="conflict-auto-remediation-drafts-empty">Remediation draft bulunamadı.</p>}
            {drafts.map((draft, index) => (
              <article key={draft.draft_id} className="rounded border border-slate-800 p-2 text-xs" data-testid={`conflict-auto-remediation-draft-${index}`}>
                <p data-testid={`conflict-auto-remediation-draft-header-${index}`}>{draft.reason_code} · {draft.entity_id} · severity={draft.severity}</p>
                <p className="text-slate-300" data-testid={`conflict-auto-remediation-draft-summary-${index}`}>{draft.action_summary}</p>
                <p className="text-slate-400" data-testid={`conflict-auto-remediation-draft-endpoint-${index}`}>{draft.endpoint}</p>
                <pre className="mt-1 overflow-auto rounded bg-slate-900 p-2 text-[11px] text-slate-300" data-testid={`conflict-auto-remediation-draft-payload-${index}`}>
                  {JSON.stringify(draft.payload, null, 2)}
                </pre>
                <Button
                  type="button"
                  variant="outline"
                  className="mt-2"
                  onClick={() => onApplyDraft({ reason_code: draft.reason_code, entity_id: draft.entity_id })}
                  data-testid={`conflict-auto-remediation-draft-apply-button-${index}`}
                >
                  Draft Uygula
                </Button>
              </article>
            ))}
          </div>
        </>
      )}
    </section>
  );
};
