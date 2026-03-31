import { useEffect, useState } from "react";
import { Link, useNavigate, useParams } from "react-router-dom";
import { toast } from "sonner";

import { Button } from "@/components/ui/button";
import { buildSessionHeaders, FRONTEND_BACKEND_URL } from "@/lib/api";

const pretty = (value) => JSON.stringify(value || {}, null, 2);

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

  return (
    <section className="space-y-4" data-testid="strategy-template-detail-page">
      <header className="border border-slate-800 bg-slate-900 p-4" data-testid="strategy-template-detail-header">
        <div className="flex items-center justify-between gap-3">
          <div>
            <h2 className="text-4xl font-black uppercase tracking-tight">Strategy Template Detail</h2>
            <p className="mt-2 text-sm text-slate-400">Scanner, backtest, bot ve execution compatibility bağlarını tek sayfada gösterir.</p>
          </div>
          <Button variant="outline" onClick={() => navigate('/user/strategies')}>Back</Button>
        </div>
      </header>
      {loading && <p className="text-sm text-slate-400" data-testid="strategy-template-detail-loading">loading...</p>}
      {detail && (
        <div className="grid gap-4 xl:grid-cols-12" data-testid="strategy-template-detail-grid">
          <article className="border border-slate-800 bg-slate-900 p-4 xl:col-span-4" data-testid="strategy-template-detail-basic-panel">
            <h3 className="text-base font-semibold">Basic Metadata</h3>
            <pre className="mt-3 overflow-x-auto bg-slate-950 p-3 text-[11px] text-slate-300">{pretty(detail.template)}</pre>
          </article>
          <article className="border border-slate-800 bg-slate-900 p-4 xl:col-span-4" data-testid="strategy-template-detail-active-version-panel">
            <h3 className="text-base font-semibold">Current Active Version</h3>
            <pre className="mt-3 overflow-x-auto bg-slate-950 p-3 text-[11px] text-slate-300">{pretty(detail.current_active_version)}</pre>
          </article>
          <article className="border border-slate-800 bg-slate-900 p-4 xl:col-span-4" data-testid="strategy-template-detail-backtest-panel">
            <h3 className="text-base font-semibold">Latest Backtest</h3>
            <pre className="mt-3 overflow-x-auto bg-slate-950 p-3 text-[11px] text-slate-300">{pretty(detail.backtest_summary)}</pre>
          </article>
          <article className="border border-slate-800 bg-slate-900 p-4 xl:col-span-6" data-testid="strategy-template-detail-history-panel">
            <h3 className="text-base font-semibold">Version History</h3>
            <pre className="mt-3 overflow-x-auto bg-slate-950 p-3 text-[11px] text-slate-300">{pretty(detail.version_history)}</pre>
          </article>
          <article className="border border-slate-800 bg-slate-900 p-4 xl:col-span-6" data-testid="strategy-template-detail-param-summary-panel">
            <h3 className="text-base font-semibold">Param Editor Summary</h3>
            <pre className="mt-3 overflow-x-auto bg-slate-950 p-3 text-[11px] text-slate-300">{pretty(detail.param_editor_summary)}</pre>
          </article>
          <article className="border border-slate-800 bg-slate-900 p-4 xl:col-span-6" data-testid="strategy-template-detail-scanner-bindings-panel">
            <h3 className="text-base font-semibold">Scanner Bindings</h3>
            <pre className="mt-3 overflow-x-auto bg-slate-950 p-3 text-[11px] text-slate-300">{pretty(detail.scanner_bindings)}</pre>
            <div className="mt-2">
              <Link to="/user/scanner" className="underline text-cyan-300" data-testid="strategy-template-detail-open-scanner-link">Open Scanner</Link>
            </div>
          </article>
          <article className="border border-slate-800 bg-slate-900 p-4 xl:col-span-6" data-testid="strategy-template-detail-bot-bindings-panel">
            <h3 className="text-base font-semibold">Bot Bindings</h3>
            <pre className="mt-3 overflow-x-auto bg-slate-950 p-3 text-[11px] text-slate-300">{pretty(detail.bot_bindings)}</pre>
            <div className="mt-2">
              <Link to="/user/bot-profiles" className="underline text-cyan-300" data-testid="strategy-template-detail-open-bots-link">Open Related Bots</Link>
            </div>
          </article>
          <article className="border border-slate-800 bg-slate-900 p-4 xl:col-span-6" data-testid="strategy-template-detail-execution-compatibility-panel">
            <h3 className="text-base font-semibold">Execution Compatibility</h3>
            <pre className="mt-3 overflow-x-auto bg-slate-950 p-3 text-[11px] text-slate-300">{pretty(detail.execution_compatibility)}</pre>
          </article>
          <article className="border border-slate-800 bg-slate-900 p-4 xl:col-span-6" data-testid="strategy-template-detail-audit-timeline-panel">
            <h3 className="text-base font-semibold">Audit Timeline</h3>
            <pre className="mt-3 overflow-x-auto bg-slate-950 p-3 text-[11px] text-slate-300">{pretty(detail.audit_timeline)}</pre>
          </article>
          <article className="border border-slate-800 bg-slate-900 p-4 xl:col-span-12" data-testid="strategy-template-detail-related-trades-panel">
            <h3 className="text-base font-semibold">Related Trades</h3>
            <pre className="mt-3 overflow-x-auto bg-slate-950 p-3 text-[11px] text-slate-300">{pretty(detail.related_trades)}</pre>
          </article>
        </div>
      )}
    </section>
  );
};
