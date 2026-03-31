import { useEffect, useState } from "react";
import { Link, useNavigate, useParams } from "react-router-dom";
import { toast } from "sonner";

import { Button } from "@/components/ui/button";
import { buildSessionHeaders, FRONTEND_BACKEND_URL } from "@/lib/api";

const pretty = (value) => JSON.stringify(value || {}, null, 2);
const lifecycleFallback = ["DRAFT", "VALIDATED", "BACKTEST_PASSED", "ACTIVE", "DEPRECATED", "ROLLED_BACK"];

const fmt = (value) => {
  if (!value) return "-";
  const d = new Date(value);
  return Number.isNaN(d.getTime()) ? "-" : d.toLocaleString();
};

const fetchTemplateDetail = async (path) => {
  const controller = new AbortController();
  const timeoutId = window.setTimeout(() => controller.abort(), 30000);
  const token = window.localStorage.getItem("token");
  try {
    const response = await fetch(`${FRONTEND_BACKEND_URL}/api${path}`, {
      method: "GET",
      headers: {
        ...buildSessionHeaders(),
        ...(token ? { Authorization: `Bearer ${token}` } : {}),
      },
      credentials: "include",
      cache: "no-store",
      signal: controller.signal,
    });
    const payload = await response.json().catch(() => null);
    if (!response.ok) {
      const error = new Error((payload && (payload.detail || payload.message)) || `request_failed_${response.status}`);
      error.response = { status: response.status, data: payload };
      throw error;
    }
    return payload;
  } finally {
    window.clearTimeout(timeoutId);
  }
};

export const StrategyTemplateDetailPage = () => {
  const { templateId } = useParams();
  const navigate = useNavigate();
  const [detail, setDetail] = useState(null);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    const load = async () => {
      setLoading(true);
      try {
        const data = await fetchTemplateDetail(`/strategy-templates/${templateId}`);
        setDetail(data || null);
      } catch (error) {
        toast.error(error?.response?.data?.detail || "Template detail yüklenemedi");
      } finally {
        setLoading(false);
      }
    };
    if (templateId) load();
  }, [templateId]);

  const performanceSummary = detail?.outcome_analytics?.performance_summary || {};
  const traceQuality = detail?.outcome_analytics?.trace_quality || {};
  const feedbackItems = detail?.learning_feedback_loop?.recommendations || detail?.outcome_analytics?.learning_feedback?.recommendations || [];
  const lifecycle = (detail?.promotion_lifecycle || []).length
    ? detail.promotion_lifecycle
    : lifecycleFallback.map((state) => ({
      state,
      phase_status: detail?.template?.lifecycle_state === state ? "current" : "pending",
      event_at: null,
      is_current: detail?.template?.lifecycle_state === state,
    }));
  const recentOutcomes = detail?.recent_outcomes || [];

  return (
    <section className="space-y-4" data-testid="strategy-template-detail-page">
      <header className="border border-slate-800 bg-slate-900 p-4" data-testid="strategy-template-detail-header">
        <div className="flex items-center justify-between gap-3">
          <div>
            <h2 className="text-4xl font-black uppercase tracking-tight" data-testid="strategy-template-detail-title">Strategy Template Detail</h2>
            <p className="mt-2 text-sm text-slate-400" data-testid="strategy-template-detail-description">Scanner, backtest, bot ve execution compatibility bağlarını tek sayfada gösterir.</p>
          </div>
          <Button variant="outline" onClick={() => navigate('/user/strategies')} data-testid="strategy-template-detail-back-button">Back</Button>
        </div>
      </header>
      {loading && <p className="text-sm text-slate-400" data-testid="strategy-template-detail-loading">loading...</p>}
      {detail && (
        <div className="grid gap-4 xl:grid-cols-12" data-testid="strategy-template-detail-grid">
          <article className="border border-slate-800 bg-slate-900 p-4 xl:col-span-12" data-testid="strategy-template-detail-performance-summary-panel">
            <h3 className="text-base font-semibold" data-testid="strategy-template-detail-performance-summary-title">Performance Summary</h3>
            <div className="mt-3 grid gap-3 md:grid-cols-3 xl:grid-cols-6" data-testid="strategy-template-detail-performance-summary-cards">
              {[
                { key: "trade_count", label: "Trade Count", value: performanceSummary.trade_count ?? 0 },
                { key: "closed_trade_count", label: "Closed Trades", value: performanceSummary.closed_trade_count ?? 0 },
                { key: "win_rate", label: "Win Rate", value: `${performanceSummary.win_rate ?? 0}%` },
                { key: "profit_factor", label: "Profit Factor", value: performanceSummary.profit_factor ?? 0 },
                { key: "avg_realized_pnl", label: "Avg Realized PnL", value: performanceSummary.avg_realized_pnl ?? 0 },
                { key: "trace_coverage_pct", label: "Trace Coverage", value: `${traceQuality.trace_coverage_pct ?? 0}%` },
              ].map((card) => (
                <div key={card.key} className="rounded border border-slate-800 bg-slate-950 p-3" data-testid={`strategy-template-detail-performance-card-${card.key}`}>
                  <p className="text-xs uppercase tracking-wider text-slate-400">{card.label}</p>
                  <p className="mt-2 text-base font-semibold text-slate-100">{card.value}</p>
                </div>
              ))}
            </div>
          </article>

          <article className="border border-slate-800 bg-slate-900 p-4 xl:col-span-6" data-testid="strategy-template-detail-promotion-lifecycle-panel">
            <h3 className="text-base font-semibold" data-testid="strategy-template-detail-promotion-lifecycle-title">Promotion Lifecycle</h3>
            <ol className="mt-3 space-y-2" data-testid="strategy-template-detail-promotion-lifecycle-list">
              {lifecycle.map((step, idx) => (
                <li key={`${step.state}-${idx}`} className="flex items-start gap-3 rounded border border-slate-800 bg-slate-950 p-3" data-testid={`strategy-template-detail-promotion-step-${idx}`}>
                  <span className={`mt-0.5 rounded px-2 py-1 text-[11px] uppercase tracking-wide ${step.phase_status === "current" ? "bg-cyan-700 text-white" : step.phase_status === "completed" ? "bg-emerald-800 text-emerald-100" : "bg-slate-800 text-slate-300"}`} data-testid={`strategy-template-detail-promotion-step-state-${idx}`}>{step.state}</span>
                  <div className="text-sm text-slate-300">
                    <p data-testid={`strategy-template-detail-promotion-step-status-${idx}`}>Durum: {step.phase_status}</p>
                    <p className="text-xs text-slate-500" data-testid={`strategy-template-detail-promotion-step-date-${idx}`}>Zaman: {fmt(step.event_at)}</p>
                  </div>
                </li>
              ))}
            </ol>
          </article>

          <article className="border border-slate-800 bg-slate-900 p-4 xl:col-span-6" data-testid="strategy-template-detail-learning-feedback-panel">
            <h3 className="text-base font-semibold" data-testid="strategy-template-detail-learning-feedback-title">Learning Feedback Loop</h3>
            <div className="mt-3 space-y-2" data-testid="strategy-template-detail-learning-feedback-list">
              {feedbackItems.length === 0 && <p className="text-sm text-slate-400" data-testid="strategy-template-detail-learning-feedback-empty">Öneri yok.</p>}
              {feedbackItems.map((item, idx) => (
                <div key={`${item.code || "feedback"}-${idx}`} className="rounded border border-slate-800 bg-slate-950 p-3" data-testid={`strategy-template-detail-learning-feedback-item-${idx}`}>
                  <p className="text-xs uppercase tracking-widest text-slate-500" data-testid={`strategy-template-detail-learning-feedback-code-${idx}`}>{item.code || "feedback"}</p>
                  <p className="mt-1 text-sm text-slate-100" data-testid={`strategy-template-detail-learning-feedback-reason-${idx}`}>{item.reason || "-"}</p>
                  <p className="mt-1 text-xs text-slate-400" data-testid={`strategy-template-detail-learning-feedback-priority-${idx}`}>Öncelik: {item.priority || "LOW"}</p>
                </div>
              ))}
            </div>
          </article>

          <article className="border border-slate-800 bg-slate-900 p-4 xl:col-span-12" data-testid="strategy-template-detail-recent-outcomes-panel">
            <div className="flex flex-wrap items-center justify-between gap-3">
              <h3 className="text-base font-semibold" data-testid="strategy-template-detail-recent-outcomes-title">Recent Outcomes</h3>
              <Link to="/user/trades" className="underline text-cyan-300" data-testid="strategy-template-detail-open-trades-link">Open Trades</Link>
            </div>
            <div className="mt-3 grid gap-3" data-testid="strategy-template-detail-recent-outcomes-list">
              {recentOutcomes.length === 0 && <p className="text-sm text-slate-400" data-testid="strategy-template-detail-recent-outcomes-empty">Henüz outcome yok.</p>}
              {recentOutcomes.map((row, idx) => (
                <article key={`${row.trade_id || idx}`} className="rounded border border-slate-800 bg-slate-950 p-3" data-testid={`strategy-template-detail-outcome-item-${idx}`}>
                  <div className="flex flex-wrap items-center justify-between gap-2">
                    <p className="text-sm font-semibold text-slate-100" data-testid={`strategy-template-detail-outcome-symbol-${idx}`}>{row.symbol || "-"} · {row.status || "-"}</p>
                    <Link to={row.trade_id ? `/user/trades/${row.trade_id}` : "/user/trades"} className="text-xs underline text-cyan-300" data-testid={`strategy-template-detail-outcome-open-trade-${idx}`}>Trade Detail</Link>
                  </div>
                  <p className="mt-1 text-xs text-slate-400" data-testid={`strategy-template-detail-outcome-pnl-${idx}`}>Realized: {row.realized_pnl ?? "-"} · Unrealized: {row.unrealized_pnl ?? "-"}</p>
                  <p className="mt-1 text-xs text-slate-500" data-testid={`strategy-template-detail-outcome-trace-${idx}`}>
                    Trace: {row.trace?.strategy_template_id || "-"} → {row.trace?.strategy_version_id || "-"} → {row.trace?.scan_run_id || "-"} → {row.trace?.signal_id || "-"} → {row.trace?.decision_card_id || "-"} → {row.trace?.intent_id || "-"} → {row.trace?.trade_id || "-"} → {row.trace?.execution_trace_id || "-"}
                  </p>
                </article>
              ))}
            </div>
          </article>

          <article className="border border-slate-800 bg-slate-900 p-4 xl:col-span-4" data-testid="strategy-template-detail-basic-panel">
            <h3 className="text-base font-semibold">Basic Metadata</h3>
            <pre className="mt-3 overflow-x-auto bg-slate-950 p-3 text-[11px] text-slate-300" data-testid="strategy-template-detail-basic-json">{pretty(detail.template)}</pre>
          </article>
          <article className="border border-slate-800 bg-slate-900 p-4 xl:col-span-4" data-testid="strategy-template-detail-active-version-panel">
            <h3 className="text-base font-semibold">Current Active Version</h3>
            <pre className="mt-3 overflow-x-auto bg-slate-950 p-3 text-[11px] text-slate-300" data-testid="strategy-template-detail-active-version-json">{pretty(detail.current_active_version)}</pre>
          </article>
          <article className="border border-slate-800 bg-slate-900 p-4 xl:col-span-4" data-testid="strategy-template-detail-backtest-panel">
            <h3 className="text-base font-semibold">Latest Backtest</h3>
            <pre className="mt-3 overflow-x-auto bg-slate-950 p-3 text-[11px] text-slate-300" data-testid="strategy-template-detail-backtest-json">{pretty(detail.backtest_summary)}</pre>
          </article>
          <article className="border border-slate-800 bg-slate-900 p-4 xl:col-span-6" data-testid="strategy-template-detail-history-panel">
            <h3 className="text-base font-semibold">Version History</h3>
            <pre className="mt-3 overflow-x-auto bg-slate-950 p-3 text-[11px] text-slate-300" data-testid="strategy-template-detail-history-json">{pretty(detail.version_history)}</pre>
          </article>
          <article className="border border-slate-800 bg-slate-900 p-4 xl:col-span-6" data-testid="strategy-template-detail-param-summary-panel">
            <h3 className="text-base font-semibold">Param Editor Summary</h3>
            <pre className="mt-3 overflow-x-auto bg-slate-950 p-3 text-[11px] text-slate-300" data-testid="strategy-template-detail-param-summary-json">{pretty(detail.param_editor_summary)}</pre>
          </article>
          <article className="border border-slate-800 bg-slate-900 p-4 xl:col-span-6" data-testid="strategy-template-detail-scanner-bindings-panel">
            <h3 className="text-base font-semibold">Scanner Bindings</h3>
            <pre className="mt-3 overflow-x-auto bg-slate-950 p-3 text-[11px] text-slate-300" data-testid="strategy-template-detail-scanner-bindings-json">{pretty(detail.scanner_bindings)}</pre>
            <div className="mt-2">
              <Link to="/user/scanner" className="underline text-cyan-300" data-testid="strategy-template-detail-open-scanner-link">Open Scanner</Link>
            </div>
          </article>
          <article className="border border-slate-800 bg-slate-900 p-4 xl:col-span-6" data-testid="strategy-template-detail-bot-bindings-panel">
            <h3 className="text-base font-semibold">Bot Bindings</h3>
            <pre className="mt-3 overflow-x-auto bg-slate-950 p-3 text-[11px] text-slate-300" data-testid="strategy-template-detail-bot-bindings-json">{pretty(detail.bot_bindings)}</pre>
            <div className="mt-2">
              <Link to="/user/bot-profiles" className="underline text-cyan-300" data-testid="strategy-template-detail-open-bots-link">Open Related Bots</Link>
            </div>
          </article>
          <article className="border border-slate-800 bg-slate-900 p-4 xl:col-span-6" data-testid="strategy-template-detail-execution-compatibility-panel">
            <h3 className="text-base font-semibold">Execution Compatibility</h3>
            <pre className="mt-3 overflow-x-auto bg-slate-950 p-3 text-[11px] text-slate-300" data-testid="strategy-template-detail-execution-compatibility-json">{pretty(detail.execution_compatibility)}</pre>
          </article>
          <article className="border border-slate-800 bg-slate-900 p-4 xl:col-span-6" data-testid="strategy-template-detail-audit-timeline-panel">
            <h3 className="text-base font-semibold">Audit Timeline</h3>
            <pre className="mt-3 overflow-x-auto bg-slate-950 p-3 text-[11px] text-slate-300" data-testid="strategy-template-detail-audit-timeline-json">{pretty(detail.audit_timeline)}</pre>
          </article>
          <article className="border border-slate-800 bg-slate-900 p-4 xl:col-span-12" data-testid="strategy-template-detail-related-trades-panel">
            <h3 className="text-base font-semibold">Related Trades</h3>
            <pre className="mt-3 overflow-x-auto bg-slate-950 p-3 text-[11px] text-slate-300" data-testid="strategy-template-detail-related-trades-json">{pretty(detail.related_trades)}</pre>
          </article>
          <article className="border border-slate-800 bg-slate-900 p-4 xl:col-span-12" data-testid="strategy-template-detail-global-trace-spine-panel">
            <h3 className="text-base font-semibold" data-testid="strategy-template-detail-global-trace-spine-title">Global Trace Spine</h3>
            <pre className="mt-3 overflow-x-auto bg-slate-950 p-3 text-[11px] text-slate-300" data-testid="strategy-template-detail-global-trace-spine-json">{pretty(detail.global_trace_spine)}</pre>
          </article>
        </div>
      )}
    </section>
  );
};
