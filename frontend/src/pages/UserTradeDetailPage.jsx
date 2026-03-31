import { useEffect, useState } from "react";
import { useNavigate, useParams } from "react-router-dom";
import { toast } from "sonner";

import { Button } from "@/components/ui/button";
import { apiClient } from "@/lib/api";

const monoBox = "overflow-x-auto bg-slate-50 p-2 text-[11px] text-slate-700";

export const UserTradeDetailPage = () => {
  const { tradeId } = useParams();
  const navigate = useNavigate();
  const [detail, setDetail] = useState(null);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    const load = async () => {
      setLoading(true);
      try {
        const { data } = await apiClient.get(`/user/trades/${tradeId}`);
        setDetail(data || null);
      } catch (error) {
        toast.error(error?.response?.data?.detail || "Trade detail yüklenemedi");
      } finally {
        setLoading(false);
      }
    };
    if (tradeId) load();
  }, [tradeId]);

  return (
    <section className="space-y-4" data-testid="user-trade-detail-page">
      <header className="border border-slate-800 bg-slate-900 p-4" data-testid="user-trade-detail-header">
        <div className="flex items-center justify-between gap-3">
          <div>
            <h2 className="text-4xl font-black uppercase tracking-tight" data-testid="user-trade-detail-title">Trade Replay</h2>
            <p className="mt-2 text-sm text-slate-400" data-testid="user-trade-detail-description">Trade lifecycle, fills, queue trace, risk/policy summary ve reconciliation görünürlüğü.</p>
          </div>
          <Button type="button" variant="outline" onClick={() => navigate('/user/trades')} data-testid="user-trade-detail-back-button">Back to Trades</Button>
        </div>
      </header>

      {loading && <p className="text-sm text-slate-400" data-testid="user-trade-detail-loading">loading...</p>}

      {detail && (
        <div className="grid gap-4 xl:grid-cols-12" data-testid="user-trade-detail-grid">
          <article className="border border-slate-800 bg-slate-900 p-4 xl:col-span-4" data-testid="user-trade-detail-basic-panel">
            <h3 className="text-base font-semibold">Trade Basic Info</h3>
            <pre className={`${monoBox} mt-3`} data-testid="user-trade-detail-basic-json">{JSON.stringify(detail.trade || {}, null, 2)}</pre>
          </article>
          <article className="border border-slate-800 bg-slate-900 p-4 xl:col-span-4" data-testid="user-trade-detail-fills-panel">
            <h3 className="text-base font-semibold">Fills / Fee / Slippage</h3>
            <pre className={`${monoBox} mt-3`} data-testid="user-trade-detail-fills-json">{JSON.stringify({ fills: detail.fills, avg_fill: detail.trade?.avg_fill_price, total_fee: detail.trade?.fees, slippage: detail.trade?.slippage }, null, 2)}</pre>
          </article>
          <article className="border border-slate-800 bg-slate-900 p-4 xl:col-span-4" data-testid="user-trade-detail-reconciliation-panel">
            <h3 className="text-base font-semibold">PnL Reconciliation</h3>
            <pre className={`${monoBox} mt-3`} data-testid="user-trade-detail-reconciliation-json">{JSON.stringify(detail.reconciliation || {}, null, 2)}</pre>
          </article>
          <article className="border border-slate-800 bg-slate-900 p-4 xl:col-span-6" data-testid="user-trade-detail-timeline-panel">
            <h3 className="text-base font-semibold">Lifecycle Timeline</h3>
            <pre className={`${monoBox} mt-3`} data-testid="user-trade-detail-timeline-json">{JSON.stringify(detail.timeline || [], null, 2)}</pre>
          </article>
          <article className="border border-slate-800 bg-slate-900 p-4 xl:col-span-6" data-testid="user-trade-detail-why-panel">
            <h3 className="text-base font-semibold">Why this trade happened</h3>
            <pre className={`${monoBox} mt-3`} data-testid="user-trade-detail-why-json">{JSON.stringify(detail.why_this_trade_happened || {}, null, 2)}</pre>
            <pre className={`${monoBox} mt-3`} data-testid="user-trade-detail-risk-policy-json">{JSON.stringify(detail.risk_policy_summary || {}, null, 2)}</pre>
            <pre className={`${monoBox} mt-3`} data-testid="user-trade-detail-queue-trace-json">{JSON.stringify(detail.queue_execution_trace || {}, null, 2)}</pre>
          </article>
        </div>
      )}
    </section>
  );
};
