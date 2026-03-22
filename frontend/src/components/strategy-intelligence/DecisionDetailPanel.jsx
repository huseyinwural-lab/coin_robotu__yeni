import React from "react";

export const DecisionDetailPanel = ({ item, index }) => {
  const factors = item?.decision_factors || {};
  return (
    <div className="mt-2 rounded border border-slate-800 bg-slate-950 p-2" data-testid={`strategy-intelligence-decision-detail-panel-${index}`}>
      <p className="text-xs text-cyan-300" data-testid={`strategy-intelligence-decision-why-inline-${index}`}>
        Why? {item?.explanation_summary || factors?.why_this_action || "Açıklama yok"}
      </p>
      <div className="mt-1 grid gap-1 text-[11px] text-slate-400 md:grid-cols-2" data-testid={`strategy-intelligence-decision-factors-grid-${index}`}>
        <p data-testid={`strategy-intelligence-decision-factor-volatility-${index}`}>volatility={String(factors?.volatility ?? "-")}</p>
        <p data-testid={`strategy-intelligence-decision-factor-exposure-${index}`}>exposure={String(factors?.exposure ?? "-")}</p>
        <p data-testid={`strategy-intelligence-decision-factor-risk-score-${index}`}>risk_score={String(factors?.risk_score ?? "-")}</p>
        <p data-testid={`strategy-intelligence-decision-factor-signal-confidence-${index}`}>signal_confidence={String(factors?.signal_confidence ?? "-")}</p>
      </div>
      <p className="mt-1 text-[11px] text-slate-400" data-testid={`strategy-intelligence-decision-expected-outcome-${index}`}>
        expected_outcome={factors?.expected_outcome || "-"}
      </p>
      <p className="text-[11px] text-slate-500" data-testid={`strategy-intelligence-decision-target-${index}`}>
        target={item?.target_type || "-"}:{item?.target_id || "-"}
      </p>
      {item?.source_request_id && (
        <p className="text-[11px] text-amber-300" data-testid={`strategy-intelligence-decision-source-link-${index}`}>
          source_request_id={item.source_request_id}
        </p>
      )}
      {item?.linked_revert_request_id && (
        <p className="text-[11px] text-emerald-300" data-testid={`strategy-intelligence-decision-revert-link-${index}`}>
          linked_revert_request_id={item.linked_revert_request_id}
        </p>
      )}
    </div>
  );
};
