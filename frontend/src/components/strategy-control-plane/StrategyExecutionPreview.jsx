import { Button } from "@/components/ui/button";
import { Dialog, DialogContent, DialogDescription, DialogHeader, DialogTitle } from "@/components/ui/dialog";

const buildTraceSteps = (preview, bindingPreview) => {
  if (!preview) return [];
  const reasonCodes = (preview?.decision?.reason_codes || []).map((item) => String(item || "").trim()).filter(Boolean);
  return [
    {
      step: 1,
      title: "Input context alındı",
      detail: `symbol=${preview?.order_preview?.symbol || "-"}, context_hash=${preview?.decision?.context_hash || "-"}`,
      reasonMatch: reasonCodes.filter((code) => code.includes("momentum") || code.includes("risk") || code.includes("volatility")),
    },
    {
      step: 2,
      title: "Regime/binding çözüldü",
      detail: `regime=${bindingPreview?.regime_label || "-"}, winner_binding=${bindingPreview?.winner_binding_id || "-"}`,
      reasonMatch: [],
    },
    {
      step: 3,
      title: "Decision üretildi",
      detail: `result=${preview?.decision?.result || "-"}, action=${preview?.explainability_trace?.selection?.selected_action || "-"}`,
      reasonMatch: reasonCodes,
    },
    {
      step: 4,
      title: "Strategy output üretildi",
      detail: `score=${preview?.decision?.score ?? "-"}, decision_hash=${preview?.decision?.decision_hash || "-"}`,
      reasonMatch: reasonCodes,
    },
    {
      step: 5,
      title: "Risk checks değerlendirildi",
      detail: (preview?.risk_checks || []).map((item) => `${item.check}:${item.status}`).join(" | ") || "-",
      reasonMatch: reasonCodes.filter((code) => code.includes("risk") || code.includes("volatility")),
    },
    {
      step: 6,
      title: "Execution intent map edildi",
      detail: `intent_id=${preview?.execution_intent?.intent_id || "none"}`,
      reasonMatch: [],
    },
    {
      step: 7,
      title: "Order preview hesaplandı",
      detail: `side=${preview?.order_preview?.side || "-"}, notional=${preview?.order_preview?.estimated_notional ?? "-"}`,
      reasonMatch: [],
    },
    {
      step: 8,
      title: "Final outcome",
      detail: `blocked_reasons=${(preview?.blocked_reasons || []).join(", ") || "-"}`,
      reasonMatch: preview?.blocked_reasons || [],
    },
  ];
};

export const StrategyExecutionPreview = ({
  executionPreviewResult,
  bindingPreview,
  explainModalOpen,
  setExplainModalOpen,
}) => {
  const traceSteps = buildTraceSteps(executionPreviewResult, bindingPreview);

  return (
    <>
      <div className="space-y-2 border border-slate-800 bg-slate-900 p-4" data-testid="admin-strategy-execution-preview-panel">
        <p className="text-xs uppercase tracking-widest text-slate-500" data-testid="admin-strategy-execution-preview-title">Execution Preview</p>
        {executionPreviewResult ? (
          <div className="space-y-2 text-xs" data-testid="admin-strategy-execution-preview-content">
            <p data-testid="admin-strategy-execution-preview-signal">Signal: {executionPreviewResult?.explainability_trace?.selection?.signal || "-"}</p>
            <p data-testid="admin-strategy-execution-preview-action">Decision/Action: {executionPreviewResult?.explainability_trace?.selection?.selected_action || "-"}</p>
            <p data-testid="admin-strategy-execution-preview-intent">Execution intent: {executionPreviewResult?.execution_intent?.intent_id || "none"}</p>
            <p data-testid="admin-strategy-execution-preview-order">Order preview: {executionPreviewResult?.order_preview?.side || "-"} / notional {executionPreviewResult?.order_preview?.estimated_notional ?? "-"}</p>
            <p data-testid="admin-strategy-execution-preview-capital">Capital impact: {executionPreviewResult?.capital_impact?.allocation_pct ?? "-"}%</p>
            <p data-testid="admin-strategy-execution-preview-risk">Risk checks: {(executionPreviewResult?.risk_checks || []).map((item) => `${item.check}:${item.status}`).join(", ")}</p>
            <p className="text-slate-400" data-testid="admin-strategy-execution-preview-blocked-reasons">Block reason: {(executionPreviewResult?.blocked_reasons || []).join(", ") || "-"}</p>
            <Button
              type="button"
              variant="outline"
              className="border-slate-500 text-slate-100"
              onClick={() => setExplainModalOpen(true)}
              data-testid="admin-strategy-execution-explain-open-modal-button"
            >
              Explain Deep Dive
            </Button>
          </div>
        ) : (
          <p className="text-xs text-slate-400" data-testid="admin-strategy-execution-preview-empty">Version aksiyonlarından “Execution Preview” çalıştırın.</p>
        )}
      </div>

      <Dialog open={explainModalOpen} onOpenChange={setExplainModalOpen}>
        <DialogContent className="max-h-[85vh] max-w-5xl overflow-y-auto border-slate-700 bg-slate-950 text-slate-100" data-testid="admin-strategy-execution-explain-modal">
          <DialogHeader>
            <DialogTitle data-testid="admin-strategy-execution-explain-modal-title">Execution Explain — Adım Adım Trace</DialogTitle>
            <DialogDescription data-testid="admin-strategy-execution-explain-modal-description">
              Bu modal, trade üretim veya block nedenini decision’dan order preview’e kadar adım adım açıklar.
            </DialogDescription>
          </DialogHeader>

          {!executionPreviewResult ? (
            <p className="text-sm text-slate-400" data-testid="admin-strategy-execution-explain-modal-empty">Önce Execution Preview üretin.</p>
          ) : (
            <div className="space-y-4 text-xs" data-testid="admin-strategy-execution-explain-modal-content">
              <div className="grid gap-3 md:grid-cols-2">
                <section className="rounded border border-slate-700 p-3" data-testid="admin-strategy-explain-section-decision">
                  <p className="mb-2 text-[11px] font-semibold uppercase tracking-wide text-slate-400">decision</p>
                  <p>result: {executionPreviewResult?.decision?.result || "-"}</p>
                  <p>score: {executionPreviewResult?.decision?.score ?? "-"}</p>
                  <p>decision_hash: {executionPreviewResult?.decision?.decision_hash || "-"}</p>
                </section>

                <section className="rounded border border-slate-700 p-3" data-testid="admin-strategy-explain-section-input-context">
                  <p className="mb-2 text-[11px] font-semibold uppercase tracking-wide text-slate-400">input context</p>
                  <p>context_hash: {executionPreviewResult?.decision?.context_hash || "-"}</p>
                  <p>signal: {executionPreviewResult?.explainability_trace?.selection?.signal || "-"}</p>
                </section>

                <section className="rounded border border-slate-700 p-3" data-testid="admin-strategy-explain-section-regime-binding">
                  <p className="mb-2 text-[11px] font-semibold uppercase tracking-wide text-slate-400">selected regime/binding</p>
                  <p>regime_label: {bindingPreview?.regime_label || "-"}</p>
                  <p>winner_binding_id: {bindingPreview?.winner_binding_id || "-"}</p>
                  <p>winner_priority: {bindingPreview?.winner_priority ?? "-"}</p>
                </section>

                <section className="rounded border border-slate-700 p-3" data-testid="admin-strategy-explain-section-strategy-output">
                  <p className="mb-2 text-[11px] font-semibold uppercase tracking-wide text-slate-400">strategy output</p>
                  <p>action: {executionPreviewResult?.explainability_trace?.selection?.selected_action || "-"}</p>
                  <p>reason_codes: {(executionPreviewResult?.decision?.reason_codes || []).join(", ") || "-"}</p>
                </section>

                <section className="rounded border border-slate-700 p-3" data-testid="admin-strategy-explain-section-risk-checks">
                  <p className="mb-2 text-[11px] font-semibold uppercase tracking-wide text-slate-400">risk checks</p>
                  {(executionPreviewResult?.risk_checks || []).map((item, idx) => (
                    <p key={`${item.check}-${idx}`}>{item.check}: {item.status}</p>
                  ))}
                </section>

                <section className="rounded border border-slate-700 p-3" data-testid="admin-strategy-explain-section-execution-intent">
                  <p className="mb-2 text-[11px] font-semibold uppercase tracking-wide text-slate-400">execution intent</p>
                  <p>intent_id: {executionPreviewResult?.execution_intent?.intent_id || "none"}</p>
                  <p>status: {executionPreviewResult?.execution_intent?.status || "-"}</p>
                </section>

                <section className="rounded border border-slate-700 p-3" data-testid="admin-strategy-explain-section-order-preview">
                  <p className="mb-2 text-[11px] font-semibold uppercase tracking-wide text-slate-400">order preview</p>
                  <p>side: {executionPreviewResult?.order_preview?.side || "-"}</p>
                  <p>quantity: {executionPreviewResult?.order_preview?.quantity ?? "-"}</p>
                  <p>estimated_notional: {executionPreviewResult?.order_preview?.estimated_notional ?? "-"}</p>
                </section>

                <section className="rounded border border-slate-700 p-3 md:col-span-2" data-testid="admin-strategy-explain-section-blocked-reasons">
                  <p className="mb-2 text-[11px] font-semibold uppercase tracking-wide text-slate-400">blocked reasons</p>
                  <p>{(executionPreviewResult?.blocked_reasons || []).join(", ") || "-"}</p>
                </section>
              </div>

              <section className="rounded border border-slate-700 p-3" data-testid="admin-strategy-explain-section-final-trace-steps">
                <p className="mb-2 text-[11px] font-semibold uppercase tracking-wide text-slate-400">final trace steps</p>
                <div className="space-y-2">
                  {traceSteps.map((item) => (
                    <div key={item.step} className="rounded border border-slate-800 p-2" data-testid={`admin-strategy-explain-trace-step-${item.step}`}>
                      <p className="font-semibold">{item.step}. {item.title}</p>
                      <p className="text-slate-300">{item.detail}</p>
                      <p className="text-[11px] text-orange-300">
                        reason_code eşleşmesi: {item.reasonMatch.length ? item.reasonMatch.join(", ") : "-"}
                      </p>
                    </div>
                  ))}
                </div>
              </section>
            </div>
          )}
        </DialogContent>
      </Dialog>
    </>
  );
};
