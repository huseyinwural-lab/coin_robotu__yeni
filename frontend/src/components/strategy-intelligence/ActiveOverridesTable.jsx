import { Button } from "@/components/ui/button";

export const ActiveOverridesTable = ({ rows = [], canRevoke, revokingId, onRevoke }) => {
  return (
    <section className="border border-slate-800 bg-slate-900 p-4" data-testid="strategy-intelligence-active-overrides-panel">
      <p className="text-xs uppercase tracking-widest text-slate-500" data-testid="strategy-intelligence-active-overrides-title">Active Overrides</p>
      <div className="mt-2 space-y-2" data-testid="strategy-intelligence-active-overrides-list">
        {rows.map((item, index) => (
          <article key={item.override_id} className="border border-slate-800 p-2" data-testid={`strategy-intelligence-active-override-item-${index}`}>
            <p className="text-sm" data-testid={`strategy-intelligence-active-override-action-${index}`}>{item.action_type}</p>
            <p className="text-xs text-slate-300" data-testid={`strategy-intelligence-active-override-target-${index}`}>
              target={item.target_type}:{item.target_id || "-"}
            </p>
            <p className="text-xs text-slate-400" data-testid={`strategy-intelligence-active-override-reason-${index}`}>{item.reason}</p>
            <p className="text-xs text-slate-400" data-testid={`strategy-intelligence-active-override-expiry-${index}`}>
              expires_at={item.expires_at ? new Date(item.expires_at).toLocaleString() : "-"}
            </p>
            <p className="text-xs text-slate-500" data-testid={`strategy-intelligence-active-override-status-${index}`}>
              status={item.current_status}
            </p>
            <div className="mt-2" data-testid={`strategy-intelligence-active-override-actions-${index}`}>
              <Button
                size="sm"
                variant="outline"
                disabled={!canRevoke || revokingId === item.override_id}
                onClick={() => onRevoke(item)}
                data-testid={`strategy-intelligence-active-override-revoke-button-${index}`}
              >
                {revokingId === item.override_id ? "Revoke..." : "Revoke"}
              </Button>
            </div>
          </article>
        ))}
        {rows.length === 0 && <p className="text-sm text-slate-400" data-testid="strategy-intelligence-active-overrides-empty">Aktif override yok.</p>}
      </div>
    </section>
  );
};
