import { useEffect, useState } from "react";

import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";

export const ConflictAutoRemediationPanel = ({ data, loading, error, onRefresh, onRunDraft, onUpdateWorkflowPolicy }) => {
  const drafts = data?.drafts || [];
  const summary = data?.summary || {};
  const approvalRequests = data?.approval_requests || [];
  const workflowPolicy = data?.workflow_policy || {};

  const [requesterRolesText, setRequesterRolesText] = useState("");
  const [approverRolesText, setApproverRolesText] = useState("");
  const [strictActorSeparation, setStrictActorSeparation] = useState(false);

  useEffect(() => {
    setRequesterRolesText((workflowPolicy.requester_roles || []).join(","));
    setApproverRolesText((workflowPolicy.approver_roles || []).join(","));
    setStrictActorSeparation(Boolean(workflowPolicy.strict_actor_separation));
  }, [workflowPolicy.requester_roles, workflowPolicy.approver_roles, workflowPolicy.strict_actor_separation]);

  const updatePolicy = async () => {
    await onUpdateWorkflowPolicy({
      requester_roles: String(requesterRolesText || "")
        .split(",")
        .map((item) => item.trim().toLowerCase())
        .filter(Boolean),
      approver_roles: String(approverRolesText || "")
        .split(",")
        .map((item) => item.trim().toLowerCase())
        .filter(Boolean),
      strict_actor_separation: strictActorSeparation,
    });
  };

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

          <div className="mb-3 rounded border border-slate-800 p-2 text-xs" data-testid="conflict-auto-remediation-workflow-policy-section">
            <p className="font-semibold text-amber-100" data-testid="conflict-auto-remediation-workflow-policy-title">Workflow Policy (P2-409)</p>
            <div className="mt-2 grid gap-2 md:grid-cols-3" data-testid="conflict-auto-remediation-workflow-policy-grid">
              <Input value={requesterRolesText} onChange={(event) => setRequesterRolesText(event.target.value)} placeholder="requester_roles csv" data-testid="conflict-auto-remediation-workflow-requester-roles-input" />
              <Input value={approverRolesText} onChange={(event) => setApproverRolesText(event.target.value)} placeholder="approver_roles csv" data-testid="conflict-auto-remediation-workflow-approver-roles-input" />
              <label className="flex items-center gap-2 text-slate-300" data-testid="conflict-auto-remediation-workflow-strict-row">
                <input type="checkbox" checked={strictActorSeparation} onChange={(event) => setStrictActorSeparation(event.target.checked)} data-testid="conflict-auto-remediation-workflow-strict-checkbox" />
                strict_actor_separation
              </label>
            </div>
            <Button type="button" variant="outline" className="mt-2" onClick={updatePolicy} data-testid="conflict-auto-remediation-workflow-update-button">Workflow Policy Güncelle</Button>
          </div>

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
                  onClick={() => onRunDraft({ reason_code: draft.reason_code, entity_id: draft.entity_id, mode: "dry_run" })}
                  data-testid={`conflict-auto-remediation-draft-dry-run-button-${index}`}
                >
                  Dry Run
                </Button>
                <Button
                  type="button"
                  variant="outline"
                  className="ml-2 mt-2"
                  onClick={() => onRunDraft({ reason_code: draft.reason_code, entity_id: draft.entity_id, mode: "submit", comment: "submitted_from_ui" })}
                  data-testid={`conflict-auto-remediation-draft-submit-button-${index}`}
                >
                  Onaya Gönder
                </Button>
              </article>
            ))}
          </div>

          <div className="mt-3" data-testid="conflict-auto-remediation-approvals-list">
            <p className="text-xs font-semibold text-amber-100" data-testid="conflict-auto-remediation-approvals-title">Approval Queue</p>
            {approvalRequests.filter((item) => item.status === "pending").length === 0 && (
              <p className="text-xs text-slate-400" data-testid="conflict-auto-remediation-approvals-empty">Pending approval yok.</p>
            )}
            {approvalRequests
              .filter((item) => item.status === "pending")
              .slice(0, 20)
              .map((item, index) => (
                <div key={item.id} className="mt-2 rounded border border-slate-800 p-2 text-xs" data-testid={`conflict-auto-remediation-approval-${index}`}>
                  <p data-testid={`conflict-auto-remediation-approval-summary-${index}`}>{item.id} · {item.draft_id} · requested_by={item.requested_by}</p>
                  <Button
                    type="button"
                    variant="outline"
                    className="mt-1"
                    onClick={() =>
                      onRunDraft({
                        reason_code: item.draft?.reason_code,
                        entity_id: item.draft?.entity_id,
                        mode: "approve_apply",
                        approval_request_id: item.id,
                        comment: "approved_from_ui",
                      })
                    }
                    data-testid={`conflict-auto-remediation-approval-apply-button-${index}`}
                  >
                    Onayla ve Uygula
                  </Button>
                </div>
              ))}
          </div>
        </>
      )}
    </section>
  );
};
