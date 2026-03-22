import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";

const SEVERITY_CLASS = {
  critical: "border-rose-500/50 text-rose-300",
  high: "border-orange-500/50 text-orange-300",
  medium: "border-amber-500/50 text-amber-300",
  low: "border-emerald-500/50 text-emerald-300",
};

const SLA_CLASS = {
  breach: "border-rose-500/60 text-rose-300",
  warning: "border-amber-500/60 text-amber-300",
  healthy: "border-emerald-500/60 text-emerald-300",
  "n/a": "border-slate-700 text-slate-400",
};

const formatDate = (value) => {
  if (!value) return "-";
  const date = new Date(value);
  return Number.isNaN(date.getTime()) ? "-" : date.toLocaleString();
};

const formatCountdown = (value) => {
  if (value === null || value === undefined) return "-";
  const total = Math.max(Number(value) || 0, 0);
  const min = Math.floor(total / 60);
  const sec = total % 60;
  return `${String(min).padStart(2, "0")}:${String(sec).padStart(2, "0")}`;
};

export const ApprovalQueuePanel = ({
  items = [],
  role,
  reviewNote,
  onReviewNoteChange,
  actionLoadingId,
  onPreview,
  onApprove,
  onReject,
  onExecute,
  previewById = {},
}) => {
  const isSuperAdmin = role === "super_admin";

  return (
    <section className="col-span-12 border border-slate-800 bg-slate-900 p-4" data-testid="strategy-intelligence-approval-queue-panel">
      <p className="text-xs uppercase tracking-widest text-slate-500" data-testid="strategy-intelligence-approval-queue-title">
        Decision Approval Queue
      </p>
      <Input
        className="mt-2"
        value={reviewNote}
        onChange={(event) => onReviewNoteChange(event.target.value)}
        data-testid="strategy-intelligence-approval-queue-review-note-input"
      />

      <div className="mt-2 space-y-2" data-testid="strategy-intelligence-approval-queue-list">
        {items.slice(0, 20).map((item, index) => {
          const preview = previewById[item.request_id] || null;
          const severity = String(item.severity_band || "low");
          const badgeClass = SEVERITY_CLASS[severity] || SEVERITY_CLASS.low;
          const slaState = String(item.sla_state || "n/a");
          const slaClass = SLA_CLASS[slaState] || SLA_CLASS["n/a"];
          const rowBorderClass = slaState === "breach" ? "border-rose-600/70" : "border-slate-800";
          return (
            <article
              key={item.request_id}
              className={`border p-2 ${rowBorderClass}`}
              data-testid={`strategy-intelligence-approval-queue-item-${index}`}
            >
              <div className="flex flex-wrap items-center gap-2" data-testid={`strategy-intelligence-approval-queue-main-row-${index}`}>
                <p className="text-sm" data-testid={`strategy-intelligence-approval-queue-main-${index}`}>
                  {item.request_id} · {item.request_type} · status={item.status}
                </p>
                <span
                  className={`rounded border px-2 py-0.5 text-xs ${badgeClass}`}
                  data-testid={`strategy-intelligence-approval-queue-severity-${index}`}
                >
                  severity={severity}
                </span>
                <span className="text-xs text-slate-400" data-testid={`strategy-intelligence-approval-queue-risk-score-${index}`}>
                  risk_delta_score={item.risk_delta_score ?? 0}
                </span>
                <span
                  className={`rounded border px-2 py-0.5 text-xs ${slaClass}`}
                  data-testid={`strategy-intelligence-approval-queue-sla-state-${index}`}
                >
                  sla_state={slaState}
                </span>
              </div>

              <p className="text-xs text-slate-300" data-testid={`strategy-intelligence-approval-queue-target-${index}`}>
                target={item.target_type}:{item.target_id}
              </p>
              <p className="text-xs text-slate-400" data-testid={`strategy-intelligence-approval-queue-reason-${index}`}>
                reason={item.reason_note}
              </p>
              <p className="text-xs text-slate-500" data-testid={`strategy-intelligence-approval-queue-created-at-${index}`}>
                created_at={formatDate(item.created_at)}
              </p>
              <p className="text-xs text-slate-400" data-testid={`strategy-intelligence-approval-queue-sla-countdown-${index}`}>
                sla_countdown={formatCountdown(item.sla_countdown_seconds)} · escalation={item.escalation_state || "none"}
              </p>

              <div className="mt-2 flex flex-wrap gap-2" data-testid={`strategy-intelligence-approval-queue-actions-${index}`}>
                <Button
                  variant="outline"
                  size="sm"
                  onClick={() => onPreview(item.request_id)}
                  disabled={actionLoadingId === item.request_id}
                  data-testid={`strategy-intelligence-approval-queue-preview-button-${index}`}
                >
                  Preview
                </Button>
                {isSuperAdmin && item.status === "pending" && (
                  <>
                    <Button
                      size="sm"
                      onClick={() => onApprove(item.request_id)}
                      disabled={actionLoadingId === item.request_id}
                      data-testid={`strategy-intelligence-approval-queue-approve-button-${index}`}
                    >
                      Approve
                    </Button>
                    <Button
                      size="sm"
                      variant="outline"
                      onClick={() => onReject(item.request_id)}
                      disabled={actionLoadingId === item.request_id}
                      data-testid={`strategy-intelligence-approval-queue-reject-button-${index}`}
                    >
                      Reject
                    </Button>
                  </>
                )}
                {isSuperAdmin && item.status === "approved" && (
                  <Button
                    size="sm"
                    onClick={() => onExecute(item)}
                    disabled={actionLoadingId === item.request_id}
                    data-testid={`strategy-intelligence-approval-queue-execute-button-${index}`}
                  >
                    Execute
                  </Button>
                )}
              </div>

              {preview && (
                <div
                  className="mt-2 rounded border border-slate-800 bg-slate-950 p-2"
                  data-testid={`strategy-intelligence-approval-queue-preview-result-${index}`}
                >
                  <p className="text-xs text-slate-300" data-testid={`strategy-intelligence-approval-queue-preview-token-${index}`}>
                    preview_token={preview.preview_token}
                  </p>
                  <p className="text-xs text-slate-400" data-testid={`strategy-intelligence-approval-queue-preview-score-${index}`}>
                    preview_risk_delta_score={preview.risk_delta_score}
                  </p>
                </div>
              )}
            </article>
          );
        })}

        {items.length === 0 && (
          <p className="text-sm text-slate-400" data-testid="strategy-intelligence-approval-queue-empty">
            Queue boş.
          </p>
        )}
      </div>
    </section>
  );
};
