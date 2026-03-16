import { useCallback, useEffect, useMemo, useState } from "react";
import { useSearchParams } from "react-router-dom";
import { toast } from "sonner";

import { LoadingSkeleton } from "@/components/LoadingSkeleton";
import { SymbolSelectorPanel } from "@/components/SymbolSelectorPanel";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { apiClient } from "@/lib/api";
import { clearExecutionContext, readExecutionContext } from "@/lib/userFlowContext";

const defaultForm = {
  source_type: "manual",
  source_ref_id: "",
  exchange_connection_id: "",
  account_label: "",
  exchange: "binance",
  environment: "testnet",
  market_type: "spot",
  symbol: "",
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

const USER_EXECUTE_SYMBOL_STORAGE_KEY = "user-execute-selected-symbol-v1";

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
  const [flowContext, setFlowContext] = useState(null);
  const [liveMetrics, setLiveMetrics] = useState(null);
  const [autoPreviewEnabled, setAutoPreviewEnabled] = useState(true);
  const [autoPreviewStatus, setAutoPreviewStatus] = useState({
    state: "idle",
    message: "Henüz canlı önizleme çalışmadı",
    updatedAt: null,
  });
  const [symbolSelectorSource, setSymbolSelectorSource] = useState("crypto");
  const [symbolSelectorMode, setSymbolSelectorMode] = useState("all_market_symbols");
  const [symbolSelectorSelection, setSymbolSelectorSelection] = useState(() => {
    if (typeof window === "undefined") {
      return [];
    }
    const stored = String(window.localStorage.getItem(USER_EXECUTE_SYMBOL_STORAGE_KEY) || "").trim().toUpperCase();
    return stored ? [stored] : [];
  });

  const selectedConnection = useMemo(
    () => connections.find((item) => item.id === selectedConnectionId) || null,
    [connections, selectedConnectionId],
  );

  const connectionOptions = useMemo(
    () =>
      connections.map((connection) => ({
        id: connection.id,
        label: `${connection.account_label} | ${connection.exchange}/${connection.market_type}/${connection.environment}`,
      })),
    [connections],
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
      const symbolFromQuery = searchParams.get("symbol") || "";
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
      const hasExplicitQuery = Boolean(searchParams.get("source") || searchParams.get("symbol") || searchParams.get("market_type"));
      const storedContext = readExecutionContext();
      const effectiveContext = !hasExplicitQuery ? storedContext : null;
      const storedSymbol = typeof window !== "undefined" ? String(window.localStorage.getItem(USER_EXECUTE_SYMBOL_STORAGE_KEY) || "").trim().toUpperCase() : "";
      const initialSymbol = (effectiveContext?.symbol || symbolFromQuery || storedSymbol || "").toUpperCase();
      setFlowContext(effectiveContext);

      setForm((prev) => ({
        ...prev,
        source_type: effectiveContext?.source || source,
        source_ref_id: searchParams.get("source_ref_id") || "",
        symbol: initialSymbol,
        side: effectiveContext?.side || side,
        market_type: effectiveContext?.market_type || marketType,
        exchange,
        environment,
        account_label: defaultConnection?.account_label || "default",
        exchange_connection_id: preselectedConnectionId,
      }));
      setIsLoading(false);
      setSymbolSelectorSelection(initialSymbol ? [initialSymbol] : []);
    };
    load();
  }, [searchParams]);

  useEffect(() => {
    const first = (symbolSelectorSelection || [])[0];
    const normalized = first ? first.toUpperCase() : "";
    setForm((prev) => ({ ...prev, symbol: normalized }));

    if (typeof window !== "undefined") {
      if (normalized) {
        window.localStorage.setItem(USER_EXECUTE_SYMBOL_STORAGE_KEY, normalized);
      } else {
        window.localStorage.removeItem(USER_EXECUTE_SYMBOL_STORAGE_KEY);
      }
    }
  }, [symbolSelectorSelection]);

  useEffect(() => {
    if (!selectedConnection) {
      return;
    }

    const ensureVenueDefaultSymbol = async () => {
      try {
        const { data } = await apiClient.get("/symbol-selector/universe", {
          params: {
            source: "crypto",
            exchange: selectedConnection.exchange,
            market_type: selectedConnection.market_type,
            mode: "all_market_symbols",
            selected_symbols: "",
            query: "",
            quote_asset_filter: "USDT",
          },
        });
        const symbols = (data?.selected_symbols || []).map((item) => String(item || "").trim().toUpperCase()).filter(Boolean);
        const active = String(symbolSelectorSelection?.[0] || "").trim().toUpperCase();
        const storedSymbol = typeof window !== "undefined" ? String(window.localStorage.getItem(USER_EXECUTE_SYMBOL_STORAGE_KEY) || "").trim().toUpperCase() : "";
        const preferredSymbol = active && symbols.includes(active)
          ? active
          : storedSymbol && symbols.includes(storedSymbol)
            ? storedSymbol
            : symbols[0] || "";

        setSymbolSelectorSelection(preferredSymbol ? [preferredSymbol] : []);
      } catch {
        setSymbolSelectorSelection([]);
      }
    };

    ensureVenueDefaultSymbol();
  }, [selectedConnection]);

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
    () => Boolean(symbolSelectorSource === "crypto" && preview?.validation_status === "valid" && preview?.intent_status === "PREVIEWED"),
    [preview, symbolSelectorSource],
  );

  const buildPreviewPayload = useCallback(
    () => {
      const scannerSnapshot = flowContext?.intent_payload?.scanner_signal_snapshot || {
        symbol: form.symbol,
        signal: flowContext?.signal || "long",
        score: flowContext?.score || null,
        strategy: flowContext?.strategy_code || form.strategy_binding || null,
        confidence: flowContext?.confidence || null,
        timestamp: flowContext?.timestamp || new Date().toISOString(),
      };

      return {
        ...(flowContext?.intent_payload || {}),
        ...form,
        source_type: flowContext?.source || form.source_type || "manual",
        exchange_connection_id: selectedConnection?.id || form.exchange_connection_id || null,
        account_label: selectedConnection?.account_label || form.account_label || "default",
        exchange: selectedConnection?.exchange || form.exchange || "binance",
        environment: selectedConnection?.environment || form.environment || "testnet",
        signal: flowContext?.signal || flowContext?.intent_payload?.signal || null,
        score: flowContext?.score || flowContext?.intent_payload?.score || null,
        strategy: flowContext?.strategy_code || flowContext?.intent_payload?.strategy || form.strategy_binding || null,
        confidence: flowContext?.confidence || flowContext?.intent_payload?.confidence || null,
        timestamp: flowContext?.timestamp || flowContext?.intent_payload?.timestamp || new Date().toISOString(),
        scanner_signal_snapshot: scannerSnapshot,
      };
    },
    [form, selectedConnection, flowContext],
  );

  const loadDecisionTrace = useCallback(async (intentId) => {
    if (!intentId) {
      setPreviewTrace(null);
      return;
    }
    setPreviewTraceLoading(true);
    try {
      const traceRes = await apiClient.get(`/user/execution/intents/${intentId}/decision-trace`);
      setPreviewTrace(traceRes.data?.latest_trace || null);
    } catch (_error) {
      setPreviewTrace(null);
    } finally {
      setPreviewTraceLoading(false);
    }
  }, []);

  const runPreview = useCallback(async ({ silent = false } = {}) => {
    if (symbolSelectorSource !== "crypto") {
      setAutoPreviewStatus({
        state: "blocked",
        message: "Execute preview şu an sadece crypto source destekliyor",
        updatedAt: new Date().toISOString(),
      });
      if (!silent) {
        toast.error("Execute preview şu an sadece crypto source destekliyor");
      }
      return;
    }

    if (venueAccess && !venueAccess.allowed) {
      if (!silent) {
        toast.error(`Venue blocked: ${(venueAccess.reason_codes || []).join(",") || venueAccess.venue_state || "unknown"}`);
      }
      setAutoPreviewStatus({
        state: "blocked",
        message: "Venue erişimi engelli",
        updatedAt: new Date().toISOString(),
      });
      return;
    }

    if (silent) {
      setAutoPreviewStatus({
        state: "running",
        message: "Canlı önizleme hesaplanıyor...",
        updatedAt: new Date().toISOString(),
      });
    } else {
      setPreviewTrace(null);
    }

    try {
      const payload = buildPreviewPayload();
      const { data } = await apiClient.post("/v1/user/trading/preview", payload);
      const previewPayload = data?.preview || null;
      setPreview(previewPayload);
      setLiveMetrics(data?.metrics || null);
      setAutoPreviewStatus({
        state: "ready",
        message: "Canlı önizleme güncel",
        updatedAt: new Date().toISOString(),
      });

      if (previewPayload?.intent_id) {
        await loadDecisionTrace(previewPayload.intent_id);
      }

      if (!silent) {
        if (previewPayload?.validation_status === "valid") {
          toast.success("Preview başarılı");
        } else {
          toast.error("Preview policy tarafından reddedildi");
        }
      }
    } catch (error) {
      const detail = error?.response?.data?.detail;
      const message = typeof detail === "string" ? detail : detail?.code || "Preview başarısız";
      if (!silent) {
        toast.error(message);
      }
      setAutoPreviewStatus({
        state: "error",
        message,
        updatedAt: new Date().toISOString(),
      });
    }
  }, [buildPreviewPayload, loadDecisionTrace, symbolSelectorSource, venueAccess]);

  useEffect(() => {
    if (!autoPreviewEnabled || isLoading || !selectedConnection) {
      return;
    }
    if (!form.symbol || form.symbol.trim().length < 5) {
      return;
    }

    const timer = setTimeout(() => {
      runPreview({ silent: true });
    }, 900);

    return () => clearTimeout(timer);
  }, [autoPreviewEnabled, form, isLoading, runPreview, selectedConnection]);

  const submitQueue = async () => {
    if (!preview) {
      toast.error("Önce preview çalıştırın");
      return;
    }
    try {
      const { data } = await apiClient.post("/v1/user/trading/execute", {
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
        {flowContext && (
          <div className="mt-3 flex flex-wrap items-center gap-3 rounded border border-emerald-400/40 bg-emerald-400/10 p-2" data-testid="user-execute-flow-context-banner">
            <p className="text-xs text-emerald-200" data-testid="user-execute-flow-context-text">
              Taşınan bağlam: {flowContext.source} / {flowContext.symbol} / {flowContext.market_type}
            </p>
            <Button size="sm" variant="outline" onClick={() => { clearExecutionContext(); setFlowContext(null); }} data-testid="user-execute-clear-flow-context-button">
              Bağlamı Temizle
            </Button>
          </div>
        )}
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
            {connectionOptions.map((optionItem) => (
              <option key={optionItem.id} value={optionItem.id}>
                {optionItem.label}
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

        <div className="col-span-12" data-testid="user-execute-symbol-selector-wrapper">
          <SymbolSelectorPanel
            testIdPrefix="user-execute-symbol-selector"
            exchange={form.exchange}
            marketType={form.market_type}
            source={symbolSelectorSource}
            onSourceChange={(next) => setSymbolSelectorSource(next === "stock" ? "crypto" : next)}
            mode={symbolSelectorMode}
            onModeChange={setSymbolSelectorMode}
            quoteAssetFilter="USDT"
            selectedSymbols={symbolSelectorSelection}
            onSelectedSymbolsChange={setSymbolSelectorSelection}
            multi={false}
          />
        </div>

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
          <Button onClick={() => runPreview({ silent: false })} data-testid="user-execute-preview-button">Preview</Button>
          <Button onClick={submitQueue} disabled={!submitEnabled} data-testid="user-execute-submit-button">Submit to Queue</Button>
          <Button variant="outline" onClick={cancelIntent} disabled={!preview} data-testid="user-execute-cancel-button">Cancel Intent</Button>
          <Button
            variant="outline"
            onClick={() => setAutoPreviewEnabled((previous) => !previous)}
            data-testid="user-execute-auto-preview-toggle-button"
          >
            Auto Preview: {autoPreviewEnabled ? "On" : "Off"}
          </Button>
        </div>
        <div className="mt-3 rounded border border-slate-800 bg-slate-950 px-3 py-2" data-testid="user-execute-auto-preview-status-panel">
          <p className="text-xs text-slate-500" data-testid="user-execute-auto-preview-status-label">Canlı Önizleme Durumu</p>
          <p className="text-sm text-slate-200" data-testid="user-execute-auto-preview-status-value">
            {autoPreviewStatus.state} · {autoPreviewStatus.message}
          </p>
          <p className="text-xs text-slate-400" data-testid="user-execute-auto-preview-status-updated-at">
            updated_at: {autoPreviewStatus.updatedAt || "-"}
          </p>
        </div>
        {!preview && (
          <div className="mt-4 rounded border border-amber-500/40 bg-amber-500/10 p-3" data-testid="user-execute-empty-preview-guidance">
            <p className="text-sm text-slate-300" data-testid="user-execute-no-preview">Henüz preview çalıştırılmadı.</p>
            <p className="mt-1 text-xs text-amber-100" data-testid="user-execute-empty-preview-guidance-text">
              Akış: Connection seç → formu doldur → Preview Intent → validation valid ise Submit to Queue.
            </p>
          </div>
        )}
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
            <div className="border border-slate-800 p-3" data-testid="user-execute-live-metrics-panel">
              <p className="text-xs uppercase tracking-widest text-slate-500" data-testid="user-execute-live-metrics-title">Real-Time Execution Preview</p>
              <div className="mt-2 grid gap-1 text-xs" data-testid="user-execute-live-metrics-content">
                <p data-testid="user-execute-live-metrics-entry-price">entry_price: {liveMetrics?.entry_price ?? "-"}</p>
                <p data-testid="user-execute-live-metrics-estimated-notional">estimated_notional: {liveMetrics?.estimated_notional ?? "-"}</p>
                <p data-testid="user-execute-live-metrics-estimated-quantity">estimated_quantity: {liveMetrics?.estimated_quantity ?? "-"}</p>
                <p data-testid="user-execute-live-metrics-estimated-risk-usdt">estimated_risk_usdt: {liveMetrics?.estimated_risk_usdt ?? "-"}</p>
                <p data-testid="user-execute-live-metrics-stop-distance">stop_distance_pct: {liveMetrics?.stop_distance_pct ?? "-"}</p>
                <p data-testid="user-execute-live-metrics-take-profit-distance">take_profit_distance_pct: {liveMetrics?.take_profit_distance_pct ?? "-"}</p>
                <p data-testid="user-execute-live-metrics-rr-ratio">risk_reward_ratio: {liveMetrics?.risk_reward_ratio ?? "-"}</p>
                <p data-testid="user-execute-live-metrics-liquidity-state">liquidity_guard_ok: {String(liveMetrics?.liquidity_guard?.ok ?? false)}</p>
                <p data-testid="user-execute-live-metrics-liquidity-spread">spread_bps: {liveMetrics?.liquidity_guard?.spread_bps ?? "-"}</p>
                <p data-testid="user-execute-live-metrics-liquidity-volume">quote_volume: {liveMetrics?.liquidity_guard?.quote_volume ?? "-"}</p>
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