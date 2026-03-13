import { useEffect, useMemo, useState } from "react";
import { useSearchParams } from "react-router-dom";
import { toast } from "sonner";

import { LoadingSkeleton } from "@/components/LoadingSkeleton";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { apiClient } from "@/lib/api";

const defaultForm = {
  source_type: "manual",
  source_ref_id: "",
  exchange_connection_id: "",
  account_label: "",
  exchange: "binance",
  environment: "testnet",
  market_type: "spot",
  symbol: "BTCUSDT",
  side: "buy",
  order_type: "market",
  position_size_mode: "fixed_notional",
  position_size_value: 25,
  margin_mode: "isolated",
  leverage: 1,
  take_profit_mode: "none",
  take_profit_value: 0,
  stop_loss_mode: "none",
  stop_loss_value: 0,
  execution_mode: "manual",
  strategy_binding: "",
  holding_profile: "intraday",
};

export const UserExecutePage = () => {
  const [searchParams] = useSearchParams();
  const [isLoading, setIsLoading] = useState(true);
  const [form, setForm] = useState(defaultForm);
  const [presets, setPresets] = useState([]);
  const [connections, setConnections] = useState([]);
  const [selectedConnectionId, setSelectedConnectionId] = useState("");
  const [venueAccess, setVenueAccess] = useState(null);
  const [bridgeContext, setBridgeContext] = useState(null);
  const [selectedPreset, setSelectedPreset] = useState("");
  const [preview, setPreview] = useState(null);
  const [previewTrace, setPreviewTrace] = useState(null);
  const [previewTraceLoading, setPreviewTraceLoading] = useState(false);

  const selectedConnection = useMemo(
    () => connections.find((item) => item.id === selectedConnectionId) || null,
    [connections, selectedConnectionId],
  );

  const isFutures = form.market_type === "futures";

  useEffect(() => {
    const load = async () => {
      setIsLoading(true);
      const [presetRes, connectionRes] = await Promise.all([
        apiClient.get("/user/execution/presets"),
        apiClient.get("/user/exchange-connections"),
      ]);
      const loadedPresets = presetRes.data || [];
      const loadedConnections = connectionRes.data || [];
      setPresets(loadedPresets);
      setConnections(loadedConnections);

      const defaultConnection =
        loadedConnections.find((item) => item.is_default) || loadedConnections[0] || null;
      const preselectedConnectionId =
        searchParams.get("exchange_connection_id") || defaultConnection?.id || "";
      setSelectedConnectionId(preselectedConnectionId);

      const source = searchParams.get("source") || "manual";
      const symbol = searchParams.get("symbol") || "BTCUSDT";
      const side = searchParams.get("side") || "buy";
      const marketType = searchParams.get("market_type") || "spot";
      const exchange = searchParams.get("exchange") || defaultConnection?.exchange || "binance";
      const environment = searchParams.get("environment") || defaultConnection?.environment || "testnet";
      const preset = searchParams.get("preset") || "";
      const bridgeContextEncoded = searchParams.get("bridge_context");
      if (bridgeContextEncoded) {
        try {
          const decoded = JSON.parse(decodeURIComponent(bridgeContextEncoded));
          setBridgeContext(decoded);
        } catch {
          setBridgeContext(null);
        }
      } else {
        setBridgeContext(null);
      }

      setSelectedPreset(preset);
      setForm((prev) => ({
        ...prev,
        source_type: source,
        source_ref_id: searchParams.get("source_ref_id") || "",
        symbol,
        side,
        market_type: marketType,
        exchange,
        environment,
        account_label: defaultConnection?.account_label || "default",
        exchange_connection_id: preselectedConnectionId,
      }));
      setIsLoading(false);
    };
    load();
  }, [searchParams]);

  useEffect(() => {
    if (!selectedConnection) {
      setVenueAccess(null);
      return;
    }

    const updateVenueContext = async () => {
      try {
        const { data } = await apiClient.get("/venues/access-check", {
          params: {
            exchange: selectedConnection.exchange,
            market_type: selectedConnection.market_type,
            environment: selectedConnection.environment,
          },
        });
        setVenueAccess(data);
      } catch {
        setVenueAccess(null);
      }
    };

    setForm((prev) => ({
      ...prev,
      exchange_connection_id: selectedConnection.id,
      account_label: selectedConnection.account_label,
      exchange: selectedConnection.exchange,
      environment: selectedConnection.environment,
      market_type: selectedConnection.market_type || prev.market_type,
    }));

    updateVenueContext();
  }, [selectedConnection]);

  useEffect(() => {
    if (!selectedPreset) {
      return;
    }
    const preset = presets.find((item) => item.preset_code === selectedPreset);
    if (!preset) {
      return;
    }
    setForm((prev) => ({
      ...prev,
      market_type: selectedPreset.startsWith("spot") ? "spot" : "futures",
      order_type: preset.default_order_type,
      take_profit_mode: preset.default_tp_mode,
      stop_loss_mode: preset.default_sl_mode,
      margin_mode: preset.default_margin_mode || prev.margin_mode,
      leverage: preset.default_leverage || prev.leverage,
    }));
  }, [selectedPreset, presets]);

  const submitEnabled = useMemo(
    () => Boolean(preview?.validation_status === "valid" && preview?.intent_status === "PREVIEWED"),
    [preview],
  );

  const runPreview = async () => {
    if (venueAccess && !venueAccess.allowed) {
      toast.error(`Venue blocked: ${(venueAccess.reason_codes || []).join(",") || venueAccess.venue_state || "unknown"}`);
      return;
    }

    setPreviewTrace(null);
    try {
      const payload = {
        ...form,
        exchange_connection_id: selectedConnection?.id || form.exchange_connection_id || null,
        account_label: selectedConnection?.account_label || form.account_label || "default",
        exchange: selectedConnection?.exchange || form.exchange || "binance",
        environment: selectedConnection?.environment || form.environment || "testnet",
      };
      const { data } = await apiClient.post("/user/execution/intent/preview", payload);
      setPreview(data);
      setPreviewTraceLoading(true);
      try {
        const traceRes = await apiClient.get(`/user/execution/intents/${data.intent_id}/decision-trace`);
        setPreviewTrace(traceRes.data?.latest_trace || null);
      } catch (_error) {
        setPreviewTrace(null);
      } finally {
        setPreviewTraceLoading(false);
      }
      if (data.validation_status === "valid") {
        toast.success("Preview başarılı");
      } else {
        toast.error("Preview policy tarafından reddedildi");
      }
    } catch (error) {
      toast.error(error?.response?.data?.detail || "Preview başarısız");
    }
  };

  const submitQueue = async () => {
    if (!preview) {
      toast.error("Önce preview çalıştırın");
      return;
    }
    try {
      const { data } = await apiClient.post("/user/execution/intent/submit", {
        intent_token: preview.intent_token,
        preview_hash: preview.preview_hash,
      });
      toast.success(`Queue status: ${data.intent_status}`);
    } catch (error) {
      toast.error(error?.response?.data?.detail || "Submit başarısız");
    }
  };

  const cancelIntent = async () => {
    if (!preview) {
      return;
    }
    try {
      await apiClient.post("/user/execution/intent/cancel", { intent_token: preview.intent_token });
      toast.success("Intent iptal edildi");
      setPreviewTrace(null);
    } catch (error) {
      toast.error(error?.response?.data?.detail || "Intent iptal edilemedi");
    }
  };

  if (isLoading) {
    return <LoadingSkeleton rows={8} testId="user-execute-loading-skeleton" />;
  }

  return (
    <section className="grid grid-cols-12 gap-4" data-testid="user-execute-page">
      <header className="col-span-12 border border-slate-800 bg-slate-900 p-4" data-testid="user-execute-header">
        <h2 className="text-4xl font-black uppercase tracking-tight" data-testid="user-execute-title">Trade Execution Control</h2>
        <p className="mt-2 text-sm text-slate-400" data-testid="user-execute-description">Preview token zorunlu, submit assisted queue’ya gider.</p>
      </header>

      <div className="col-span-12 lg:col-span-7 grid grid-cols-12 gap-3 border border-slate-800 bg-slate-900 p-4" data-testid="user-execute-form-grid">
        <div className="col-span-12 md:col-span-6">
          <label className="text-xs text-slate-500" htmlFor="execute-connection-select">Exchange Connection</label>
          <select
            id="execute-connection-select"
            className="mt-1 w-full border border-slate-700 bg-slate-950 px-3 py-2 text-sm"
            value={selectedConnectionId}
            onChange={(event) => setSelectedConnectionId(event.target.value)}
            data-testid="execute-connection-select"
          >
            {connections.map((connection) => (
              <option key={connection.id} value={connection.id}>
                {connection.account_label} · {connection.exchange}/{connection.market_type}/{connection.environment}
              </option>
            ))}
            {connections.length === 0 && <option value="">no-connection</option>}
          </select>
        </div>
        <div className="col-span-12 md:col-span-6 border border-slate-800 bg-slate-950 px-3 py-2" data-testid="execute-venue-state-card">
          <p className="text-xs text-slate-500" data-testid="execute-venue-state-label">Venue State</p>
          <p className="text-sm text-slate-100" data-testid="execute-venue-state-value">
            {venueAccess?.venue_state || "unknown"} / allowed={String(venueAccess?.allowed ?? false)}
          </p>
          <p className="text-xs text-slate-400" data-testid="execute-venue-state-reasons">
            {(venueAccess?.reason_codes || []).join(",") || "-"}
          </p>
        </div>

        <div className="col-span-12 md:col-span-6">
          <label className="text-xs text-slate-500">Source</label>
          <Input value={form.source_type} onChange={(e) => setForm((p) => ({ ...p, source_type: e.target.value }))} data-testid="execute-source-type-input" />
        </div>
        <div className="col-span-12 md:col-span-6">
          <label className="text-xs text-slate-500">Preset</label>
          <select className="mt-1 w-full border border-slate-700 bg-slate-950 px-3 py-2 text-sm" value={selectedPreset} onChange={(e) => setSelectedPreset(e.target.value)} data-testid="execute-preset-select">
            <option value="">none</option>
            {presets.map((preset) => (
              <option key={preset.preset_code} value={preset.preset_code}>{preset.preset_code}</option>
            ))}
          </select>
        </div>

        <div className="col-span-6 md:col-span-3"><label className="text-xs text-slate-500">Market</label><select className="mt-1 w-full border border-slate-700 bg-slate-950 px-3 py-2 text-sm" value={form.market_type} onChange={(e) => setForm((p) => ({ ...p, market_type: e.target.value }))} data-testid="execute-market-type-select"><option value="spot">spot</option><option value="futures">futures</option></select></div>
        <div className="col-span-6 md:col-span-3"><label className="text-xs text-slate-500">Side</label><select className="mt-1 w-full border border-slate-700 bg-slate-950 px-3 py-2 text-sm" value={form.side} onChange={(e) => setForm((p) => ({ ...p, side: e.target.value }))} data-testid="execute-side-select"><option value="buy">buy</option><option value="sell">sell</option><option value="long">long</option><option value="short">short</option></select></div>
        <div className="col-span-12 md:col-span-3"><label className="text-xs text-slate-500">Order Type</label><select className="mt-1 w-full border border-slate-700 bg-slate-950 px-3 py-2 text-sm" value={form.order_type} onChange={(e) => setForm((p) => ({ ...p, order_type: e.target.value }))} data-testid="execute-order-type-select"><option value="market">market</option><option value="limit">limit</option><option value="stop_limit">stop_limit</option></select></div>
        <div className="col-span-12 md:col-span-3"><label className="text-xs text-slate-500">Symbol</label><Input value={form.symbol} onChange={(e) => setForm((p) => ({ ...p, symbol: e.target.value.toUpperCase() }))} data-testid="execute-symbol-input" /></div>

        {isFutures && (
          <>
            <div className="col-span-6 md:col-span-3"><label className="text-xs text-slate-500">Margin Mode</label><select className="mt-1 w-full border border-slate-700 bg-slate-950 px-3 py-2 text-sm" value={form.margin_mode} onChange={(e) => setForm((p) => ({ ...p, margin_mode: e.target.value }))} data-testid="execute-margin-mode-select"><option value="isolated">isolated</option><option value="cross">cross</option></select></div>
            <div className="col-span-6 md:col-span-3"><label className="text-xs text-slate-500">Leverage</label><Input type="number" value={form.leverage} onChange={(e) => setForm((p) => ({ ...p, leverage: Number(e.target.value) }))} data-testid="execute-leverage-input" /></div>
          </>
        )}

        <div className="col-span-6 md:col-span-3"><label className="text-xs text-slate-500">Size Mode</label><select className="mt-1 w-full border border-slate-700 bg-slate-950 px-3 py-2 text-sm" value={form.position_size_mode} onChange={(e) => setForm((p) => ({ ...p, position_size_mode: e.target.value }))} data-testid="execute-size-mode-select"><option value="fixed_notional">fixed_notional</option><option value="risk_percent">risk_percent</option></select></div>
        <div className="col-span-6 md:col-span-3"><label className="text-xs text-slate-500">Size Value</label><Input type="number" value={form.position_size_value} onChange={(e) => setForm((p) => ({ ...p, position_size_value: Number(e.target.value) }))} data-testid="execute-size-value-input" /></div>

        <div className="col-span-6 md:col-span-3"><label className="text-xs text-slate-500">TP Mode</label><select className="mt-1 w-full border border-slate-700 bg-slate-950 px-3 py-2 text-sm" value={form.take_profit_mode} onChange={(e) => setForm((p) => ({ ...p, take_profit_mode: e.target.value }))} data-testid="execute-tp-mode-select"><option value="none">none</option><option value="price">price</option><option value="percent">percent</option></select></div>
        <div className="col-span-6 md:col-span-3"><label className="text-xs text-slate-500">TP Value</label><Input type="number" value={form.take_profit_value} onChange={(e) => setForm((p) => ({ ...p, take_profit_value: Number(e.target.value) }))} data-testid="execute-tp-value-input" /></div>
        <div className="col-span-6 md:col-span-3"><label className="text-xs text-slate-500">SL Mode</label><select className="mt-1 w-full border border-slate-700 bg-slate-950 px-3 py-2 text-sm" value={form.stop_loss_mode} onChange={(e) => setForm((p) => ({ ...p, stop_loss_mode: e.target.value }))} data-testid="execute-sl-mode-select"><option value="none">none</option><option value="price">price</option><option value="percent">percent</option></select></div>
        <div className="col-span-6 md:col-span-3"><label className="text-xs text-slate-500">SL Value</label><Input type="number" value={form.stop_loss_value} onChange={(e) => setForm((p) => ({ ...p, stop_loss_value: Number(e.target.value) }))} data-testid="execute-sl-value-input" /></div>

        <div className="col-span-12 md:col-span-4"><label className="text-xs text-slate-500">Execution Mode</label><select className="mt-1 w-full border border-slate-700 bg-slate-950 px-3 py-2 text-sm" value={form.execution_mode} onChange={(e) => setForm((p) => ({ ...p, execution_mode: e.target.value }))} data-testid="execute-mode-select"><option value="manual">manual</option><option value="bot_assisted">bot_assisted</option><option value="signal_follow">signal_follow</option></select></div>
        <div className="col-span-12 md:col-span-4"><label className="text-xs text-slate-500">Strategy Binding</label><Input value={form.strategy_binding} onChange={(e) => setForm((p) => ({ ...p, strategy_binding: e.target.value }))} data-testid="execute-strategy-binding-input" /></div>
        <div className="col-span-12 md:col-span-4"><label className="text-xs text-slate-500">Holding Profile</label><select className="mt-1 w-full border border-slate-700 bg-slate-950 px-3 py-2 text-sm" value={form.holding_profile} onChange={(e) => setForm((p) => ({ ...p, holding_profile: e.target.value }))} data-testid="execute-holding-profile-select"><option value="scalp">scalp</option><option value="intraday">intraday</option><option value="swing">swing</option></select></div>
      </div>

      <div className="col-span-12 lg:col-span-5 rounded border border-slate-800 bg-slate-900 p-4" data-testid="user-execute-preview-panel">
        <p className="text-xs uppercase tracking-widest text-slate-500" data-testid="user-execute-preview-title">Preview Summary</p>
        <div className="mt-3 flex flex-wrap gap-2" data-testid="user-execute-actions">
          <Button onClick={runPreview} data-testid="user-execute-preview-button">Preview</Button>
          <Button onClick={submitQueue} disabled={!submitEnabled} data-testid="user-execute-submit-button">Submit to Queue</Button>
          <Button variant="outline" onClick={cancelIntent} disabled={!preview} data-testid="user-execute-cancel-button">Cancel Intent</Button>
        </div>
        {!preview && <p className="mt-4 text-sm text-slate-400" data-testid="user-execute-no-preview">Henüz preview çalıştırılmadı.</p>}
        {preview && (
          <div className="mt-4 space-y-2 text-sm" data-testid="user-execute-preview-content">
            <p data-testid="user-execute-intent-token">intent_token: {preview.intent_token}</p>
            <p data-testid="user-execute-validation-status">validation_status: {preview.validation_status}</p>
            <p data-testid="user-execute-queue-mode">queue_mode: {preview.queue_mode}</p>
            <p data-testid="user-execute-approval-required">approval_required: {String(preview.approval_required)}</p>
            <p data-testid="user-execute-gate-decision">gate_decision: {preview.gate_decision}</p>
            <p data-testid="user-execute-meta-engine-decision">meta_engine_decision: {preview.meta_engine_decision}</p>
            <div className="border border-slate-800 p-3" data-testid="user-execute-venue-context-panel">
              <p className="text-xs uppercase tracking-widest text-slate-500" data-testid="user-execute-venue-context-title">Venue Context</p>
              <div className="mt-2 grid gap-1 text-xs" data-testid="user-execute-venue-context-content">
                <p data-testid="user-execute-venue-context-account-label">account_label: {preview.venue_context?.account_label || form.account_label || "default"}</p>
                <p data-testid="user-execute-venue-context-exchange">exchange: {preview.venue_context?.exchange || form.exchange}</p>
                <p data-testid="user-execute-venue-context-market-type">market_type: {preview.venue_context?.market_type || form.market_type}</p>
                <p data-testid="user-execute-venue-context-environment">environment: {preview.venue_context?.environment || form.environment}</p>
                <p data-testid="user-execute-venue-context-state">venue_state: {preview.venue_context?.venue_state || venueAccess?.venue_state || "unknown"}</p>
                <p data-testid="user-execute-venue-context-allowed">allowed: {String(preview.venue_context?.allowed ?? venueAccess?.allowed ?? false)}</p>
              </div>
            </div>

            {bridgeContext && (
              <div className="border border-slate-800 p-3" data-testid="user-execute-bridge-context-panel">
                <p className="text-xs uppercase tracking-widest text-slate-500" data-testid="user-execute-bridge-context-title">Bridge Context</p>
                <p className="text-xs text-slate-300" data-testid="user-execute-bridge-context-source">source: {form.source_type}</p>
                <p className="text-xs text-slate-300" data-testid="user-execute-bridge-context-query">query: {bridgeContext.query_expression || "-"}</p>
                <p className="text-xs text-slate-300" data-testid="user-execute-bridge-context-filter-snapshot">
                  filter_snapshot: {JSON.stringify(bridgeContext.filter_payload || {})}
                </p>
              </div>
            )}

            <div data-testid="user-execute-reason-codes">
              <p className="text-xs uppercase tracking-widest text-slate-500">reason_codes</p>
              {(preview.reject_reason_codes || []).length === 0 ? <p className="text-slate-400">none</p> : preview.reject_reason_codes.map((code) => <p key={code}>{code}</p>)}
            </div>
            <div data-testid="user-execute-risk-flags">
              <p className="text-xs uppercase tracking-widest text-slate-500">risk_flags</p>
              {(preview.risk_flags || []).length === 0 ? <p className="text-slate-400">none</p> : preview.risk_flags.map((flag) => <p key={flag}>{flag}</p>)}
            </div>
            <div className="border border-slate-800 p-3" data-testid="user-execute-portfolio-risk-impact-panel">
              <p className="text-xs uppercase tracking-widest text-slate-500" data-testid="user-execute-portfolio-risk-impact-title">Portfolio Risk Impact</p>
              <div className="mt-2 grid gap-1 text-xs" data-testid="user-execute-portfolio-risk-impact-content">
                <p data-testid="user-execute-risk-score">risk_score: {preview.portfolio_risk_impact?.risk_score ?? 0}</p>
                <p data-testid="user-execute-current-portfolio-leverage">current_portfolio_leverage: {preview.portfolio_risk_impact?.current_portfolio_leverage ?? 0}</p>
                <p data-testid="user-execute-symbol-exposure">symbol_exposure_pct: {preview.portfolio_risk_impact?.symbol_exposure_pct ?? 0}</p>
                <p data-testid="user-execute-cluster-exposure">cluster_exposure_pct: {preview.portfolio_risk_impact?.cluster_exposure_pct ?? 0}</p>
                <p data-testid="user-execute-strategy-exposure">strategy_exposure_pct: {preview.portfolio_risk_impact?.strategy_exposure_pct ?? 0}</p>
                <p data-testid="user-execute-single-trade-risk">single_trade_risk_pct: {preview.portfolio_risk_impact?.single_trade_risk_pct ?? 0}</p>
              </div>
            </div>
            <div className="border border-slate-800 p-3" data-testid="user-execute-meta-strategy-panel">
              <p className="text-xs uppercase tracking-widest text-slate-500" data-testid="user-execute-meta-strategy-title">Meta Strategy Attribution</p>
              <div className="mt-2 grid gap-1 text-xs" data-testid="user-execute-meta-strategy-content">
                <p data-testid="user-execute-meta-strategy-weight">strategy_weight: {preview.meta_strategy_summary?.strategy_weight ?? "-"}</p>
                <p data-testid="user-execute-meta-strategy-source">allocation_source: {preview.meta_strategy_summary?.allocation_source ?? "-"}</p>
                <p data-testid="user-execute-meta-strategy-reason">allocation_reason: {preview.meta_strategy_summary?.strategy_allocation_reason ?? "-"}</p>
                <p data-testid="user-execute-meta-strategy-state">strategy_state: {preview.meta_strategy_summary?.state ?? "-"}</p>
              </div>
            </div>
            <div className="border border-slate-800 p-3" data-testid="user-execute-strategy-intelligence-panel">
              <p className="text-xs uppercase tracking-widest text-slate-500" data-testid="user-execute-strategy-intelligence-title">Strategy Intelligence</p>
              <div className="mt-2 grid gap-1 text-xs" data-testid="user-execute-strategy-intelligence-content">
                <p data-testid="user-execute-strategy-conflict-warning">strategy_conflict_warning: {preview.strategy_conflict_warning || "none"}</p>
                <p data-testid="user-execute-allocation-adjustment-notice">allocation_adjustment_notice: {preview.allocation_adjustment_notice || "none"}</p>
                <p data-testid="user-execute-risk-reduction-score">risk_reduction_score: {preview.risk_reduction_score ?? 0}</p>
                <p data-testid="user-execute-hedge-suggestion">hedge_suggestion: {preview.hedge_suggestion?.hedge_symbol ? `${preview.hedge_suggestion.hedge_symbol} ${preview.hedge_suggestion.hedge_direction} ${preview.hedge_suggestion.hedge_size}` : "none"}</p>
              </div>
            </div>
            <div className="border border-slate-800 p-3" data-testid="user-execute-preview-explain-panel">
              <p className="text-xs uppercase tracking-widest text-slate-500" data-testid="user-execute-preview-explain-title">Preview Explain</p>
              {previewTraceLoading && <p className="text-xs text-slate-400" data-testid="user-execute-preview-explain-loading">Açıklama yükleniyor...</p>}
              {!previewTraceLoading && !previewTrace && <p className="text-xs text-slate-400" data-testid="user-execute-preview-explain-empty">Preview trace bulunamadı.</p>}
              {!previewTraceLoading && previewTrace && (
                <div className="space-y-2 text-xs" data-testid="user-execute-preview-explain-content">
                  <p data-testid="user-execute-preview-explain-status">decision_status: {previewTrace.decision_status}</p>
                  <p data-testid="user-execute-preview-explain-type">trace_type: {previewTrace.trace_type}</p>
                  <div data-testid="user-execute-preview-explain-reasons">
                    {(previewTrace.reason_details || []).map((reason) => (
                      <article key={reason.code} className="border border-slate-800 p-2" data-testid={`user-execute-preview-explain-reason-${reason.code}`}>
                        <p className="text-sm" data-testid={`user-execute-preview-explain-reason-title-${reason.code}`}>{reason.title}</p>
                        <p className="text-xs text-slate-400" data-testid={`user-execute-preview-explain-reason-desc-${reason.code}`}>{reason.description}</p>
                      </article>
                    ))}
                  </div>
                </div>
              )}
            </div>
          </div>
        )}
      </div>
    </section>
  );
};