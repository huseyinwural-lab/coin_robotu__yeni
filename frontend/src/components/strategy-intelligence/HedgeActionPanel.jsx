import { useMemo, useState } from "react";

import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";

export const HedgeActionPanel = ({ hedgeSuggestions = [], canRequestDecision, isSubmitting, onRequest }) => {
  const [reasonNote, setReasonNote] = useState("hedge_apply_request");
  const reasonOk = useMemo(() => String(reasonNote || "").trim().length >= 8, [reasonNote]);

  return (
    <section className="col-span-12 lg:col-span-6 border border-slate-800 bg-slate-900 p-4" data-testid="strategy-intelligence-hedge-action-panel">
      <p className="text-xs uppercase tracking-widest text-slate-500" data-testid="strategy-intelligence-hedge-action-title">
        Hedge Suggestions
      </p>
      <Input
        className="mt-2"
        value={reasonNote}
        onChange={(event) => setReasonNote(event.target.value)}
        placeholder="reason_note (min 8 karakter)"
        data-testid="strategy-intelligence-hedge-request-reason-input"
      />

      <div className="mt-2 space-y-2" data-testid="strategy-intelligence-hedge-action-list">
        {hedgeSuggestions.slice(0, 8).map((item, index) => {
          const targetId = `${item.hedge_symbol || "none"}:${item.hedge_direction || "-"}`;
          return (
            <article key={`${targetId}-${index}`} className="border border-slate-800 p-2" data-testid={`strategy-intelligence-hedge-action-item-${index}`}>
              <p className="text-sm" data-testid={`strategy-intelligence-hedge-action-main-${index}`}>
                symbol={item.hedge_symbol || "none"} · direction={item.hedge_direction || "-"}
              </p>
              <p className="text-xs text-slate-400" data-testid={`strategy-intelligence-hedge-action-size-${index}`}>
                size={item.hedge_size}
              </p>
              <Button
                type="button"
                className="mt-2"
                disabled={!canRequestDecision || !reasonOk || isSubmitting}
                onClick={() =>
                  onRequest({
                    requestType: "hedge_apply",
                    targetType: "hedge_suggestion",
                    targetId,
                    reasonNote,
                    impactContext: {
                      hedge: {
                        hedge_symbol: item.hedge_symbol || "none",
                        hedge_size: item.hedge_size,
                        hedge_direction: item.hedge_direction || "-",
                      },
                    },
                  })
                }
                data-testid={`strategy-intelligence-hedge-request-button-${index}`}
              >
                {isSubmitting ? "Gönderiliyor..." : "Hedge Apply Request Oluştur"}
              </Button>
            </article>
          );
        })}
        {hedgeSuggestions.length === 0 && (
          <p className="text-sm text-slate-400" data-testid="strategy-intelligence-hedge-action-empty">
            Aktif hedge önerisi bulunmuyor.
          </p>
        )}
      </div>
    </section>
  );
};
