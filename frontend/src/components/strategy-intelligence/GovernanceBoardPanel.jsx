import { useMemo, useState } from "react";

import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { DecisionDetailPanel } from "@/components/strategy-intelligence/DecisionDetailPanel";

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

export const GovernanceBoardPanel = ({
  role,
  queueItems = [],
  escalationData,
  selectedQueueIds = [],
  onToggleQueueSelect,
  onToggleQueueSelectAll,
  queueReviewNote,
  onQueueReviewNoteChange,
  queueOwner,
  onQueueOwnerChange,
  onQueueAssignOwner,
  onQueueAck,
  onQueuePreview,
  onQueueApprove,
  onQueueReject,
  onQueueExecute,
  onQueueRevert,
  onQueueBulkAction,
  queueActionLoadingId,
  previewById,
  escalationTab,
  onEscalationTabChange,
  escalationOwner,
  onEscalationOwnerChange,
  escalationAckReason,
  onEscalationAckReasonChange,
  escalationResolveReason,
  onEscalationResolveReasonChange,
  onEscalationAssignOwner,
  onEscalationAck,
  onEscalationResolve,
  escalationActionLoadingId,
  onRefresh,
}) => {
  const [boardTab, setBoardTab] = useState("queue");
  const [revertModal, setRevertModal] = useState({ open: false, item: null, reason: "" });
  const isSuperAdmin = role === "super_admin";
  const canAck = ["admin", "super_admin"].includes(role);

  const selectedSet = useMemo(() => new Set(selectedQueueIds), [selectedQueueIds]);
  const escalationRows =
    escalationTab === "active"
      ? escalationData?.active_breaches || []
      : escalationTab === "acknowledged"
      ? escalationData?.acknowledged || []
      : escalationData?.resolved || [];

  return (
    <section className="col-span-12 border border-slate-800 bg-slate-900 p-4" data-testid="strategy-intelligence-governance-board-panel">
      <div className="flex flex-wrap items-center justify-between gap-2" data-testid="strategy-intelligence-governance-board-header">
        <p className="text-xs uppercase tracking-widest text-slate-500" data-testid="strategy-intelligence-governance-board-title">
          Governance Board (Queue + Escalation)
        </p>
        <Button size="sm" variant="outline" onClick={onRefresh} data-testid="strategy-intelligence-governance-board-refresh-button">
          Refresh
        </Button>
      </div>

      <div className="mt-2 flex flex-wrap gap-2" data-testid="strategy-intelligence-governance-board-tabs">
        <Button
          size="sm"
          variant={boardTab === "queue" ? "default" : "outline"}
          onClick={() => setBoardTab("queue")}
          data-testid="strategy-intelligence-governance-board-tab-queue"
        >
          Approval Queue
        </Button>
        <Button
          size="sm"
          variant={boardTab === "escalation" ? "default" : "outline"}
          onClick={() => setBoardTab("escalation")}
          data-testid="strategy-intelligence-governance-board-tab-escalation"
        >
          Escalations
        </Button>
      </div>

      {boardTab === "queue" ? (
        <div className="mt-3 space-y-3" data-testid="strategy-intelligence-governance-queue-view">
          <div className="grid gap-2 md:grid-cols-3" data-testid="strategy-intelligence-governance-queue-controls-grid">
            <Input
              value={queueReviewNote}
              onChange={(event) => onQueueReviewNoteChange(event.target.value)}
              placeholder="review note"
              data-testid="strategy-intelligence-governance-queue-review-note-input"
            />
            <Input
              value={queueOwner}
              onChange={(event) => onQueueOwnerChange(event.target.value)}
              placeholder="assigned_to"
              data-testid="strategy-intelligence-governance-queue-owner-input"
            />
            <div className="flex flex-wrap gap-2" data-testid="strategy-intelligence-governance-queue-bulk-actions">
              <Button
                size="sm"
                variant="outline"
                onClick={onToggleQueueSelectAll}
                data-testid="strategy-intelligence-governance-queue-select-all-button"
              >
                Select All
              </Button>
              <Button
                size="sm"
                variant="outline"
                disabled={selectedQueueIds.length === 0}
                onClick={() => onQueueAssignOwner(selectedQueueIds)}
                data-testid="strategy-intelligence-governance-queue-assign-owner-bulk-button"
              >
                Assign Owner
              </Button>
              {isSuperAdmin && (
                <>
                  <Button
                    size="sm"
                    disabled={selectedQueueIds.length === 0}
                    onClick={() => onQueueBulkAction("approve")}
                    data-testid="strategy-intelligence-governance-queue-bulk-approve-button"
                  >
                    Bulk Approve
                  </Button>
                  <Button
                    size="sm"
                    variant="outline"
                    disabled={selectedQueueIds.length === 0}
                    onClick={() => onQueueBulkAction("reject")}
                    data-testid="strategy-intelligence-governance-queue-bulk-reject-button"
                  >
                    Bulk Reject
                  </Button>
                </>
              )}
            </div>
          </div>

          <div className="space-y-2" data-testid="strategy-intelligence-governance-queue-list">
            {queueItems.slice(0, 60).map((item, index) => {
              const isSelected = selectedSet.has(item.request_id);
              const preview = previewById?.[item.request_id] || null;
              const rowClass = item.sla_state === "breach" ? "border-rose-600/70" : "border-slate-800";
              const canRevertAction = ["admin", "super_admin"].includes(role) && item.status === "executed" && !item.reverted_at && item.request_type !== "revert_apply";
              return (
                <article key={item.request_id} className={`border p-2 ${rowClass}`} data-testid={`strategy-intelligence-governance-queue-item-${index}`}>
                  <div className="flex flex-wrap items-center gap-2" data-testid={`strategy-intelligence-governance-queue-row-top-${index}`}>
                    <input
                      type="checkbox"
                      checked={isSelected}
                      onChange={() => onToggleQueueSelect(item.request_id)}
                      data-testid={`strategy-intelligence-governance-queue-select-checkbox-${index}`}
                    />
                    <p className="text-sm" data-testid={`strategy-intelligence-governance-queue-main-${index}`}>
                      {item.request_id} · {item.request_type} · status={item.status}
                    </p>
                    <p className="text-xs text-slate-400" data-testid={`strategy-intelligence-governance-queue-sla-${index}`}>
                      sla={item.sla_state} ({formatCountdown(item.sla_countdown_seconds)})
                    </p>
                  </div>

                  <p className="text-xs text-slate-300" data-testid={`strategy-intelligence-governance-queue-owner-${index}`}>
                    owner={item.assigned_to || "-"} · ack_by={item.ack_by || "-"} · ack_at={formatDate(item.ack_at)}
                  </p>
                  <p className="text-xs text-slate-400" data-testid={`strategy-intelligence-governance-queue-severity-${index}`}>
                    severity={item.severity_band} · risk_delta_score={item.risk_delta_score} · recommendation_rank={item.recommendation_rank || "-"}
                  </p>
                  <p className="text-xs text-cyan-200" data-testid={`strategy-intelligence-governance-queue-why-${index}`}>
                    Why? {item.explanation_summary || item.decision_factors?.why_this_action || "-"}
                  </p>

                  <div className="mt-1 rounded border border-slate-800 bg-slate-950 p-2" data-testid={`strategy-intelligence-governance-queue-inline-impact-card-${index}`}>
                    <p className="text-xs text-slate-400" data-testid={`strategy-intelligence-governance-queue-inline-impact-state-${index}`}>
                      state_change={(item.execution_effect?.state_change || item.state_change || item.deterministic_effect_preview?.state_change || "-")}
                    </p>
                    <p className="text-xs text-slate-400" data-testid={`strategy-intelligence-governance-queue-inline-impact-risk-${index}`}>
                      predicted_risk_reduction={item.deterministic_effect_preview?.predicted_risk_reduction ?? "-"} · realized_risk_drop={item.execution_effect?.realized_risk_drop ?? "-"}
                    </p>
                    <p className="text-xs text-slate-400" data-testid={`strategy-intelligence-governance-queue-inline-impact-allocation-${index}`}>
                      allocation_diff_bps={(item.execution_effect?.allocation_diff_bps ?? item.deterministic_effect_preview?.predicted_allocation_diff_bps) ?? "-"}
                    </p>
                  </div>

                  <DecisionDetailPanel item={item} index={index} />

                  <div className="mt-2 flex flex-wrap gap-2" data-testid={`strategy-intelligence-governance-queue-actions-${index}`}>
                    <Button
                      size="sm"
                      variant="outline"
                      disabled={queueActionLoadingId === item.request_id}
                      onClick={() => onQueuePreview(item.request_id)}
                      data-testid={`strategy-intelligence-governance-queue-preview-button-${index}`}
                    >
                      Preview
                    </Button>
                    {canAck && (
                      <Button
                        size="sm"
                        variant="outline"
                        disabled={queueActionLoadingId === item.request_id}
                        onClick={() => onQueueAck(item.request_id)}
                        data-testid={`strategy-intelligence-governance-queue-ack-button-${index}`}
                      >
                        Ack
                      </Button>
                    )}
                    <Button
                      size="sm"
                      variant="outline"
                      disabled={queueActionLoadingId === item.request_id}
                      onClick={() => onQueueAssignOwner([item.request_id])}
                      data-testid={`strategy-intelligence-governance-queue-assign-owner-button-${index}`}
                    >
                      Assign Owner
                    </Button>
                    {isSuperAdmin && item.status === "pending" && (
                      <>
                        <Button
                          size="sm"
                          disabled={queueActionLoadingId === item.request_id}
                          onClick={() => onQueueApprove(item.request_id)}
                          data-testid={`strategy-intelligence-governance-queue-approve-button-${index}`}
                        >
                          Approve
                        </Button>
                        <Button
                          size="sm"
                          variant="outline"
                          disabled={queueActionLoadingId === item.request_id}
                          onClick={() => onQueueReject(item.request_id)}
                          data-testid={`strategy-intelligence-governance-queue-reject-button-${index}`}
                        >
                          Reject
                        </Button>
                      </>
                    )}
                    {isSuperAdmin && item.status === "approved" && (
                      <Button
                        size="sm"
                        disabled={queueActionLoadingId === item.request_id}
                        onClick={() => onQueueExecute(item)}
                        data-testid={`strategy-intelligence-governance-queue-execute-button-${index}`}
                      >
                        Execute
                      </Button>
                    )}
                    {canRevertAction && (
                      <Button
                        size="sm"
                        variant="outline"
                        disabled={queueActionLoadingId === item.request_id}
                        onClick={() =>
                          setRevertModal({
                            open: true,
                            item,
                            reason: `revert_${item.request_id}`,
                          })
                        }
                        data-testid={`strategy-intelligence-governance-queue-revert-button-${index}`}
                      >
                        Revert
                      </Button>
                    )}
                  </div>

                  {preview && (
                    <p className="mt-1 text-xs text-slate-400" data-testid={`strategy-intelligence-governance-queue-preview-token-${index}`}>
                      preview_token={preview.preview_token}
                    </p>
                  )}
                </article>
              );
            })}

            {queueItems.length === 0 && (
              <p className="text-sm text-slate-400" data-testid="strategy-intelligence-governance-queue-empty">
                Queue boş.
              </p>
            )}
          </div>

          {revertModal.open && (
            <div className="rounded border border-amber-500/40 bg-amber-950/20 p-3" data-testid="strategy-intelligence-governance-revert-modal">
              <p className="text-sm text-amber-200" data-testid="strategy-intelligence-governance-revert-modal-title">
                Revert Confirmation
              </p>
              <p className="mt-1 text-xs text-slate-300" data-testid="strategy-intelligence-governance-revert-modal-impact-preview">
                impact_preview: state_change={revertModal.item?.execution_effect?.state_change || revertModal.item?.state_change || "-"} ·
                risk_drop={revertModal.item?.execution_effect?.realized_risk_drop ?? "-"}
              </p>
              <Input
                className="mt-2"
                value={revertModal.reason}
                onChange={(event) => setRevertModal((prev) => ({ ...prev, reason: event.target.value }))}
                placeholder="revert reason (zorunlu)"
                data-testid="strategy-intelligence-governance-revert-modal-reason-input"
              />
              <div className="mt-2 flex gap-2" data-testid="strategy-intelligence-governance-revert-modal-actions">
                <Button
                  size="sm"
                  onClick={async () => {
                    await onQueueRevert?.(revertModal.item, revertModal.reason);
                    setRevertModal({ open: false, item: null, reason: "" });
                  }}
                  data-testid="strategy-intelligence-governance-revert-modal-confirm-button"
                >
                  {isSuperAdmin ? "Revert Now" : "Revert Request"}
                </Button>
                <Button
                  size="sm"
                  variant="outline"
                  onClick={() => setRevertModal({ open: false, item: null, reason: "" })}
                  data-testid="strategy-intelligence-governance-revert-modal-cancel-button"
                >
                  Vazgeç
                </Button>
              </div>
            </div>
          )}
        </div>
      ) : (
        <div className="mt-3 space-y-3" data-testid="strategy-intelligence-governance-escalation-view">
          <div className="flex flex-wrap gap-2" data-testid="strategy-intelligence-governance-escalation-tabs">
            <Button
              size="sm"
              variant={escalationTab === "active" ? "default" : "outline"}
              onClick={() => onEscalationTabChange("active")}
              data-testid="strategy-intelligence-governance-escalation-tab-active"
            >
              Active Breaches
            </Button>
            <Button
              size="sm"
              variant={escalationTab === "acknowledged" ? "default" : "outline"}
              onClick={() => onEscalationTabChange("acknowledged")}
              data-testid="strategy-intelligence-governance-escalation-tab-acknowledged"
            >
              Acknowledged
            </Button>
            <Button
              size="sm"
              variant={escalationTab === "resolved" ? "default" : "outline"}
              onClick={() => onEscalationTabChange("resolved")}
              data-testid="strategy-intelligence-governance-escalation-tab-resolved"
            >
              Resolved
            </Button>
          </div>

          <div className="grid gap-2 md:grid-cols-3" data-testid="strategy-intelligence-governance-escalation-controls-grid">
            <Input
              value={escalationOwner}
              onChange={(event) => onEscalationOwnerChange(event.target.value)}
              placeholder="current_owner"
              data-testid="strategy-intelligence-governance-escalation-owner-input"
            />
            <Input
              value={escalationAckReason}
              onChange={(event) => onEscalationAckReasonChange(event.target.value)}
              placeholder="ack reason"
              data-testid="strategy-intelligence-governance-escalation-ack-reason-input"
            />
            <Input
              value={escalationResolveReason}
              onChange={(event) => onEscalationResolveReasonChange(event.target.value)}
              placeholder="resolve reason"
              data-testid="strategy-intelligence-governance-escalation-resolve-reason-input"
            />
          </div>

          <div className="space-y-2" data-testid="strategy-intelligence-governance-escalation-list">
            {escalationRows.slice(0, 50).map((item, index) => (
              <article key={item.escalation_id} className="border border-slate-800 p-2" data-testid={`strategy-intelligence-governance-escalation-item-${index}`}>
                <p className="text-sm" data-testid={`strategy-intelligence-governance-escalation-main-${index}`}>
                  {item.escalation_id} · linked_request={item.linked_request_id} · owner={item.current_owner}
                </p>
                <p className="text-xs text-slate-400" data-testid={`strategy-intelligence-governance-escalation-detail-${index}`}>
                  breach_age={item.breach_age_seconds}s · ack_by={item.ack_by || "-"} · ack_at={formatDate(item.ack_at)}
                </p>
                <p className="text-xs text-slate-500" data-testid={`strategy-intelligence-governance-escalation-reason-${index}`}>
                  reason={item.escalation_reason}
                </p>

                <div className="mt-2 flex flex-wrap gap-2" data-testid={`strategy-intelligence-governance-escalation-actions-${index}`}>
                  {canAck && item.state !== "resolved" && (
                    <>
                      <Button
                        size="sm"
                        variant="outline"
                        disabled={escalationActionLoadingId === item.escalation_id}
                        onClick={() => onEscalationAssignOwner(item)}
                        data-testid={`strategy-intelligence-governance-escalation-assign-owner-button-${index}`}
                      >
                        Assign Owner
                      </Button>
                      <Button
                        size="sm"
                        variant="outline"
                        disabled={escalationActionLoadingId === item.escalation_id}
                        onClick={() => onEscalationAck(item)}
                        data-testid={`strategy-intelligence-governance-escalation-ack-button-${index}`}
                      >
                        Ack
                      </Button>
                    </>
                  )}
                  {isSuperAdmin && item.state !== "resolved" && (
                    <Button
                      size="sm"
                      disabled={escalationActionLoadingId === item.escalation_id}
                      onClick={() => onEscalationResolve(item)}
                      data-testid={`strategy-intelligence-governance-escalation-resolve-button-${index}`}
                    >
                      Resolve
                    </Button>
                  )}
                </div>
              </article>
            ))}

            {escalationRows.length === 0 && (
              <p className="text-sm text-slate-400" data-testid="strategy-intelligence-governance-escalation-empty">
                Bu sekmede escalation kaydı yok.
              </p>
            )}
          </div>
        </div>
      )}
    </section>
  );
};
