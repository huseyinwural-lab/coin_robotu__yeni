import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";

const formatDate = (value) => {
  if (!value) return "-";
  const date = new Date(value);
  return Number.isNaN(date.getTime()) ? "-" : date.toLocaleString();
};

const metricValue = (payload, key) => {
  if (!payload) return "-";
  const value = payload[key];
  return value === null || value === undefined ? "-" : String(value);
};

export const SimulationHistoryPanel = ({
  rows = [],
  comparingRunId,
  compareResult,
  onCompare,
  filters = { run_id: "", status_filter: "", request_mode: "", severity_band: "", request_type: "" },
  onFilterChange = () => {},
  onApplyFilters = () => {},
  onResetFilters = () => {},
}) => {
  return (
    <section className="col-span-12 border border-slate-800 bg-slate-900 p-4" data-testid="strategy-intelligence-simulation-history-panel">
      <p className="text-xs uppercase tracking-widest text-slate-500" data-testid="strategy-intelligence-simulation-history-title">
        Simulation History + Replay Compare
      </p>

      <div className="mt-2 grid gap-2 md:grid-cols-5" data-testid="strategy-intelligence-simulation-history-filters">
        <Input
          value={filters.run_id}
          onChange={(event) => onFilterChange("run_id", event.target.value)}
          placeholder="run_id"
          data-testid="strategy-intelligence-history-filter-run-id-input"
        />
        <select
          className="rounded border border-slate-700 bg-slate-950 px-2 py-2 text-sm"
          value={filters.status_filter}
          onChange={(event) => onFilterChange("status_filter", event.target.value)}
          data-testid="strategy-intelligence-history-filter-status-select"
        >
          <option value="">status: all</option>
          <option value="preview">preview</option>
          <option value="applied">applied</option>
          <option value="superseded">superseded</option>
        </select>
        <select
          className="rounded border border-slate-700 bg-slate-950 px-2 py-2 text-sm"
          value={filters.request_mode}
          onChange={(event) => onFilterChange("request_mode", event.target.value)}
          data-testid="strategy-intelligence-history-filter-request-mode-select"
        >
          <option value="">request_mode: all</option>
          <option value="single">single</option>
          <option value="batch">batch</option>
        </select>
        <select
          className="rounded border border-slate-700 bg-slate-950 px-2 py-2 text-sm"
          value={filters.severity_band}
          onChange={(event) => onFilterChange("severity_band", event.target.value)}
          data-testid="strategy-intelligence-history-filter-severity-band-select"
        >
          <option value="">severity: all</option>
          <option value="critical">critical</option>
          <option value="high">high</option>
          <option value="medium">medium</option>
          <option value="low">low</option>
        </select>
        <select
          className="rounded border border-slate-700 bg-slate-950 px-2 py-2 text-sm"
          value={filters.request_type}
          onChange={(event) => onFilterChange("request_type", event.target.value)}
          data-testid="strategy-intelligence-history-filter-request-type-select"
        >
          <option value="">request_type: all</option>
          <option value="conflict_resolve">conflict_resolve</option>
          <option value="hedge_apply">hedge_apply</option>
          <option value="rebalance_change">rebalance_change</option>
        </select>
      </div>
      <div className="mt-2 flex flex-wrap gap-2" data-testid="strategy-intelligence-history-filter-actions">
        <Button size="sm" variant="outline" onClick={onApplyFilters} data-testid="strategy-intelligence-history-filter-apply-button">
          Apply Filters
        </Button>
        <Button size="sm" variant="outline" onClick={onResetFilters} data-testid="strategy-intelligence-history-filter-reset-button">
          Reset
        </Button>
      </div>

      {compareResult && (
        <div className="mt-2 rounded border border-slate-800 bg-slate-950 p-2" data-testid="strategy-intelligence-simulation-compare-panel">
          <p className="text-sm" data-testid="strategy-intelligence-simulation-compare-run-id">run_id={compareResult.run_id}</p>
          <div className="mt-2 grid gap-2 md:grid-cols-2" data-testid="strategy-intelligence-simulation-compare-side-by-side-grid">
            <div className="rounded border border-slate-800 p-2" data-testid="strategy-intelligence-simulation-compare-before-column">
              <p className="text-xs text-slate-400">Before (history run)</p>
              <p className="text-xs" data-testid="strategy-intelligence-simulation-compare-before-risk">
                projected_risk_score={metricValue(compareResult.before, "projected_risk_score")}
              </p>
              <p className="text-xs" data-testid="strategy-intelligence-simulation-compare-before-adj-risk">
                confidence_adjusted_risk_score={metricValue(compareResult.before, "confidence_adjusted_risk_score")}
              </p>
              <p className="text-xs" data-testid="strategy-intelligence-simulation-compare-before-drawdown">
                projected_drawdown={metricValue(compareResult.before, "projected_drawdown")}
              </p>
              <p className="text-xs" data-testid="strategy-intelligence-simulation-compare-before-decision">
                decision_delta={metricValue(compareResult.before, "decision_delta")}
              </p>
            </div>
            <div className="rounded border border-slate-800 p-2" data-testid="strategy-intelligence-simulation-compare-current-column">
              <p className="text-xs text-slate-400">Current (live context)</p>
              <p className="text-xs" data-testid="strategy-intelligence-simulation-compare-current-risk">
                projected_risk_score={metricValue(compareResult.current, "projected_risk_score")}
              </p>
              <p className="text-xs" data-testid="strategy-intelligence-simulation-compare-current-adj-risk">
                confidence_adjusted_risk_score={metricValue(compareResult.current, "confidence_adjusted_risk_score")}
              </p>
              <p className="text-xs" data-testid="strategy-intelligence-simulation-compare-current-drawdown">
                projected_drawdown={metricValue(compareResult.current, "projected_drawdown")}
              </p>
              <p className="text-xs" data-testid="strategy-intelligence-simulation-compare-current-decision">
                decision_delta={metricValue(compareResult.current, "decision_delta")}
              </p>
            </div>
          </div>
          <p className="mt-2 text-xs text-slate-400" data-testid="strategy-intelligence-simulation-compare-risk-delta">
            risk_delta_vs_history={compareResult.compare_summary?.risk_delta_vs_history ?? "-"}
          </p>
          <p className="text-xs text-slate-400" data-testid="strategy-intelligence-simulation-compare-adj-risk-delta">
            confidence_adjusted_risk_delta_vs_history={compareResult.compare_summary?.confidence_adjusted_risk_delta_vs_history ?? "-"}
          </p>
          <p className="text-xs text-slate-400" data-testid="strategy-intelligence-simulation-compare-decision-delta">
            decision_delta_vs_history={compareResult.compare_summary?.decision_delta_vs_history ?? "-"}
          </p>
        </div>
      )}

      <div className="mt-2 space-y-2" data-testid="strategy-intelligence-simulation-history-list">
        {rows.slice(0, 16).map((item, index) => (
          <article key={item.run_id} className="border border-slate-800 p-2" data-testid={`strategy-intelligence-simulation-history-item-${index}`}>
            <p className="text-sm" data-testid={`strategy-intelligence-simulation-history-main-${index}`}>
              {item.run_id} · mode={item.request_mode} · status={item.status}
            </p>
            <p className="text-xs text-slate-400" data-testid={`strategy-intelligence-simulation-history-symbols-${index}`}>
              symbols={(item.symbols || []).join(", ") || "-"}
            </p>
            <p className="text-xs text-slate-400" data-testid={`strategy-intelligence-simulation-history-request-meta-${index}`}>
              request_type={item.decision_request_type || "-"} · severity_band={item.decision_severity_band || "-"}
            </p>
            <p className="text-xs text-slate-500" data-testid={`strategy-intelligence-simulation-history-created-at-${index}`}>
              created_at={formatDate(item.created_at)}
            </p>
            <Button
              className="mt-2"
              size="sm"
              variant="outline"
              onClick={() => onCompare(item.run_id)}
              disabled={comparingRunId === item.run_id}
              data-testid={`strategy-intelligence-simulation-compare-button-${index}`}
            >
              {comparingRunId === item.run_id ? "Comparing..." : "Compare with Current"}
            </Button>
          </article>
        ))}

        {rows.length === 0 && (
          <p className="text-sm text-slate-400" data-testid="strategy-intelligence-simulation-history-empty">
            No data yet.
          </p>
        )}
      </div>
    </section>
  );
};
