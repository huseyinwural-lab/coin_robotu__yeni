import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";

const TAB_CONFIG = [
  { key: "active", label: "Active Breaches" },
  { key: "acknowledged", label: "Acknowledged" },
  { key: "resolved", label: "Resolved" },
];

const formatDate = (value) => {
  if (!value) return "-";
  const date = new Date(value);
  return Number.isNaN(date.getTime()) ? "-" : date.toLocaleString();
};

export const EscalationCenterPanel = ({
  role,
  data,
  activeTab,
  onTabChange,
  ackReason,
  onAckReasonChange,
  resolveReason,
  onResolveReasonChange,
  actionLoadingId,
  onAcknowledge,
  onResolve,
  onRefresh,
}) => {
  const canAck = ["admin", "super_admin"].includes(role);
  const canResolve = role === "super_admin";
  const rows =
    activeTab === "active"
      ? data?.active_breaches || []
      : activeTab === "acknowledged"
      ? data?.acknowledged || []
      : data?.resolved || [];

  return (
    <section className="col-span-12 border border-slate-800 bg-slate-900 p-4" data-testid="strategy-intelligence-escalation-center-panel">
      <div className="flex flex-wrap items-center justify-between gap-2" data-testid="strategy-intelligence-escalation-center-header">
        <p className="text-xs uppercase tracking-widest text-slate-500" data-testid="strategy-intelligence-escalation-center-title">
          Escalation Center
        </p>
        <Button size="sm" variant="outline" onClick={onRefresh} data-testid="strategy-intelligence-escalation-refresh-button">
          Refresh
        </Button>
      </div>

      <div className="mt-2 flex flex-wrap gap-2" data-testid="strategy-intelligence-escalation-tabs">
        {TAB_CONFIG.map((tab) => (
          <Button
            key={tab.key}
            size="sm"
            variant={activeTab === tab.key ? "default" : "outline"}
            onClick={() => onTabChange(tab.key)}
            data-testid={`strategy-intelligence-escalation-tab-${tab.key}`}
          >
            {tab.label}
          </Button>
        ))}
      </div>

      <div className="mt-2 grid gap-2 md:grid-cols-2" data-testid="strategy-intelligence-escalation-reason-inputs">
        <Input
          value={ackReason}
          onChange={(event) => onAckReasonChange(event.target.value)}
          placeholder="ack reason (min 8)"
          data-testid="strategy-intelligence-escalation-ack-reason-input"
        />
        <Input
          value={resolveReason}
          onChange={(event) => onResolveReasonChange(event.target.value)}
          placeholder="resolve reason (min 8)"
          data-testid="strategy-intelligence-escalation-resolve-reason-input"
        />
      </div>

      <div className="mt-2 space-y-2" data-testid="strategy-intelligence-escalation-list">
        {rows.slice(0, 24).map((item, index) => (
          <article key={item.escalation_id} className="border border-slate-800 p-2" data-testid={`strategy-intelligence-escalation-item-${index}`}>
            <p className="text-sm" data-testid={`strategy-intelligence-escalation-main-${index}`}>
              escalation_id={item.escalation_id} · linked_request_id={item.linked_request_id}
            </p>
            <p className="text-xs text-slate-400" data-testid={`strategy-intelligence-escalation-level-${index}`}>
              escalation_level={item.escalation_level} · breach_age={item.breach_age_seconds}s
            </p>
            <p className="text-xs text-slate-400" data-testid={`strategy-intelligence-escalation-owner-${index}`}>
              current_owner={item.current_owner} · ack_by={item.ack_by || "-"} · ack_at={formatDate(item.ack_at)}
            </p>
            <p className="text-xs text-slate-500" data-testid={`strategy-intelligence-escalation-reason-${index}`}>
              reason={item.escalation_reason}
            </p>

            <div className="mt-2 flex flex-wrap gap-2" data-testid={`strategy-intelligence-escalation-actions-${index}`}>
              {canAck && item.state !== "resolved" && (
                <Button
                  size="sm"
                  variant="outline"
                  disabled={actionLoadingId === item.escalation_id}
                  onClick={() => onAcknowledge(item)}
                  data-testid={`strategy-intelligence-escalation-ack-button-${index}`}
                >
                  Ack
                </Button>
              )}
              {canResolve && item.state !== "resolved" && (
                <Button
                  size="sm"
                  disabled={actionLoadingId === item.escalation_id}
                  onClick={() => onResolve(item)}
                  data-testid={`strategy-intelligence-escalation-resolve-button-${index}`}
                >
                  Resolve
                </Button>
              )}
            </div>
          </article>
        ))}

        {rows.length === 0 && (
          <p className="text-sm text-slate-400" data-testid="strategy-intelligence-escalation-empty">
            Bu sekmede kayıt yok.
          </p>
        )}
      </div>
    </section>
  );
};
