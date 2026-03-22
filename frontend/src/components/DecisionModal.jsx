import { useEffect, useState } from "react";

import { Button } from "@/components/ui/button";
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from "@/components/ui/dialog";
import { Input } from "@/components/ui/input";
import { Textarea } from "@/components/ui/textarea";

export const DecisionModal = ({
  open,
  onOpenChange,
  title,
  actionType,
  strategyId,
  defaultReason,
  confirmPlaceholder,
  confirmRequired,
  riskSnapshot,
  params,
  requirePreview,
  showThresholdPlaceholder,
  extraContent,
  onRequestPreview,
  onConfirm,
}) => {
  const [reason, setReason] = useState(defaultReason || "");
  const [confirmPhrase, setConfirmPhrase] = useState("");
  const [preview, setPreview] = useState(null);
  const [previewToken, setPreviewToken] = useState("");
  const [previewLoading, setPreviewLoading] = useState(false);
  const [submitting, setSubmitting] = useState(false);

  useEffect(() => {
    if (!open) return;
    setReason(defaultReason || "");
    setConfirmPhrase("");
    setPreview(null);
    setPreviewToken("");
  }, [defaultReason, open, actionType, strategyId]);

  const requestPreview = async () => {
    if (!onRequestPreview) return;
    setPreviewLoading(true);
    try {
      const data = await onRequestPreview({ actionType, strategyId, params, reason });
      setPreview(data?.preview || null);
      setPreviewToken(data?.preview_token || "");
    } finally {
      setPreviewLoading(false);
    }
  };

  const submit = async () => {
    if (reason.trim().length < 3) return;
    if (confirmRequired && confirmPhrase.trim().length < 3) return;
    if (requirePreview && (!preview || !previewToken)) return;
    if (!onConfirm) return;

    setSubmitting(true);
    try {
      await onConfirm({ reason: reason.trim(), confirmPhrase: confirmPhrase.trim(), previewToken, preview });
      onOpenChange(false);
    } finally {
      setSubmitting(false);
    }
  };

  const targetSummary = [
    params?.target_strategy ? `target_strategy=${params.target_strategy}` : null,
    params?.alert_id ? `alert_id=${params.alert_id}` : null,
    params?.snapshot_trace_id ? `snapshot_trace_id=${params.snapshot_trace_id}` : null,
  ]
    .filter(Boolean)
    .join(" · ");

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent className="border border-black/40 bg-orange-50" data-testid="decision-modal-root">
        <DialogHeader>
          <DialogTitle data-testid="decision-modal-title">{title || "Decision Modal"}</DialogTitle>
          <DialogDescription data-testid="decision-modal-description">
            Action={actionType} · Strategy={strategyId}
          </DialogDescription>
          {Boolean(targetSummary) && (
            <p className="text-xs" data-testid="decision-modal-target-summary">
              Target={targetSummary}
            </p>
          )}
        </DialogHeader>

        <Textarea
          value={reason}
          onChange={(e) => setReason(e.target.value)}
          placeholder="Reason (zorunlu)"
          className="border-black/40"
          data-testid="decision-modal-reason-input"
        />

        {confirmRequired && (
          <Input
            value={confirmPhrase}
            onChange={(e) => setConfirmPhrase(e.target.value)}
            placeholder={confirmPlaceholder || "Confirm ifadesi"}
            className="border-black/40"
            data-testid="decision-modal-confirm-input"
          />
        )}

        {extraContent}

        <div className="rounded border border-black/20 bg-orange-100 p-2" data-testid="decision-modal-risk-card">
          <p className="text-xs" data-testid="decision-modal-risk-score">risk_score={riskSnapshot?.risk_score ?? "-"}</p>
          <p className="text-xs" data-testid="decision-modal-risk-level">risk_level={riskSnapshot?.risk_level ?? "-"}</p>
        </div>

        <div className="rounded border border-black/20 bg-orange-100 p-2" data-testid="decision-modal-impact-preview-panel">
          <Button size="sm" variant="outline" onClick={requestPreview} disabled={previewLoading} data-testid="decision-modal-preview-button">
            {previewLoading ? "Hesaplanıyor..." : "Impact Preview Hesapla"}
          </Button>
          {!preview && <p className="mt-1 text-xs" data-testid="decision-modal-preview-empty">Preview zorunlu: aksiyon öncesi impact hesaplanmalı.</p>}
          {preview && (
            <div className="mt-2" data-testid="decision-modal-preview-card">
              <p className="text-xs" data-testid="decision-modal-preview-reject">Reject change={preview.expected_reject_delta}%</p>
              <p className="text-xs" data-testid="decision-modal-preview-pnl">PnL impact={preview.expected_pnl_impact}</p>
              <p className="text-xs" data-testid="decision-modal-preview-risk">Risk={preview.risk_level}</p>
              <p className="text-xs" data-testid="decision-modal-preview-confidence">Confidence={preview.confidence}%</p>
            </div>
          )}
        </div>

        {showThresholdPlaceholder && (
          <div className="rounded border border-dashed border-black/30 bg-orange-100 p-2" data-testid="decision-modal-threshold-placeholder">
            <p className="text-xs">Threshold Edit Placeholder: Bu turda backend hook hazır, gerçek patch sonraki tur.</p>
          </div>
        )}

        <DialogFooter>
          <Button variant="outline" onClick={() => onOpenChange(false)} data-testid="decision-modal-cancel-button">Vazgeç</Button>
          <Button onClick={submit} disabled={submitting || (requirePreview && (!preview || !previewToken))} className="border border-black bg-black text-orange-300" data-testid="decision-modal-submit-button">
            {submitting ? "Uygulanıyor..." : "Confirm & Execute"}
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
};
