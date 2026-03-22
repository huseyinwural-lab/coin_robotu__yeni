import { useMemo, useState } from "react";

import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";

export const ConflictActionPanel = ({ conflicts = [], canRequestDecision, isSubmitting, onRequest }) => {
  const [reasonNote, setReasonNote] = useState("conflict_resolution_request");
  const reasonOk = useMemo(() => String(reasonNote || "").trim().length >= 8, [reasonNote]);

  return (
    <section className="col-span-12 lg:col-span-6 border border-slate-800 bg-slate-900 p-4" data-testid="strategy-intelligence-conflict-action-panel">
      <p className="text-xs uppercase tracking-widest text-slate-500" data-testid="strategy-intelligence-conflict-action-title">
        Strategy Conflicts
      </p>
      <Input
        className="mt-2"
        value={reasonNote}
        onChange={(event) => setReasonNote(event.target.value)}
        placeholder="reason_note (min 8 karakter)"
        data-testid="strategy-intelligence-conflict-request-reason-input"
      />

      <div className="mt-2 space-y-2" data-testid="strategy-intelligence-conflict-action-list">
        {conflicts.slice(0, 8).map((item, index) => {
          const targetId = `${item.winning_strategy || "-"}:${item.losing_strategy || "-"}:${item.symbol || "UNKNOWN"}`;
          return (
            <article key={`${targetId}-${index}`} className="border border-slate-800 p-2" data-testid={`strategy-intelligence-conflict-action-item-${index}`}>
              <p className="text-sm" data-testid={`strategy-intelligence-conflict-action-main-${index}`}>
                winner={item.winning_strategy || "-"} · loser={item.losing_strategy || "-"}
              </p>
              <p className="text-xs text-slate-400" data-testid={`strategy-intelligence-conflict-action-reason-${index}`}>
                reason={item.resolution_reason || "-"}
              </p>
              <Button
                type="button"
                className="mt-2"
                disabled={!canRequestDecision || !reasonOk || isSubmitting}
                onClick={() =>
                  onRequest({
                    requestType: "conflict_resolve",
                    targetType: "strategy_conflict",
                    targetId,
                    reasonNote,
                    impactContext: {
                      conflict: {
                        winner: item.winning_strategy || "-",
                        loser: item.losing_strategy || "-",
                        reason: item.resolution_reason || "-",
                      },
                    },
                  })
                }
                data-testid={`strategy-intelligence-conflict-request-button-${index}`}
              >
                {isSubmitting ? "Gönderiliyor..." : "Resolve Request Oluştur"}
              </Button>
            </article>
          );
        })}
        {conflicts.length === 0 && (
          <p className="text-sm text-slate-400" data-testid="strategy-intelligence-conflict-action-empty">
            Aktif strategy conflict bulunmuyor.
          </p>
        )}
      </div>
    </section>
  );
};
