import { useMemo, useState } from "react";

import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";

export const RebalanceActionPanel = ({ rebalanceEvents = [], canRequestDecision, isSubmitting, onRequest }) => {
  const [reasonNote, setReasonNote] = useState("rebalance_change_request");
  const reasonOk = useMemo(() => String(reasonNote || "").trim().length >= 8, [reasonNote]);

  return (
    <section className="col-span-12 border border-slate-800 bg-slate-900 p-4" data-testid="strategy-intelligence-rebalance-action-panel">
      <p className="text-xs uppercase tracking-widest text-slate-500" data-testid="strategy-intelligence-rebalance-action-title">
        Rebalance Governance Events
      </p>
      <Input
        className="mt-2"
        value={reasonNote}
        onChange={(event) => setReasonNote(event.target.value)}
        placeholder="reason_note (min 8 karakter)"
        data-testid="strategy-intelligence-rebalance-request-reason-input"
      />

      <div className="mt-2 space-y-2" data-testid="strategy-intelligence-rebalance-action-list">
        {rebalanceEvents.slice(0, 8).map((item, index) => {
          const strategyId = item.strategy_id || `rebalance_${index}`;
          return (
            <article key={`${strategyId}-${index}`} className="border border-slate-800 p-2" data-testid={`strategy-intelligence-rebalance-action-item-${index}`}>
              <p className="text-sm" data-testid={`strategy-intelligence-rebalance-action-main-${index}`}>
                strategy={strategyId} · drift={item.allocation_drift ?? "-"}
              </p>
              <p className="text-xs text-slate-400" data-testid={`strategy-intelligence-rebalance-action-weight-${index}`}>
                old_weight={item.old_strategy_weight ?? "-"} · new_weight={item.new_strategy_weight ?? "-"}
              </p>
              <Button
                type="button"
                className="mt-2"
                disabled={!canRequestDecision || !reasonOk || isSubmitting}
                onClick={() =>
                  onRequest({
                    requestType: "rebalance_change",
                    targetType: "rebalance_event",
                    targetId: strategyId,
                    reasonNote,
                    impactContext: {
                      rebalance: {
                        strategy_id: strategyId,
                        allocation_drift: item.allocation_drift ?? 0,
                        old_strategy_weight: item.old_strategy_weight ?? null,
                        new_strategy_weight: item.new_strategy_weight ?? null,
                      },
                    },
                  })
                }
                data-testid={`strategy-intelligence-rebalance-request-button-${index}`}
              >
                {isSubmitting ? "Gönderiliyor..." : "Rebalance Request Oluştur"}
              </Button>
            </article>
          );
        })}
        {rebalanceEvents.length === 0 && (
          <p className="text-sm text-slate-400" data-testid="strategy-intelligence-rebalance-action-empty">
            Rebalance event bulunmuyor.
          </p>
        )}
      </div>
    </section>
  );
};
