import { useEffect, useMemo, useRef, useState } from "react";
import { useNavigate } from "react-router-dom";
import { toast } from "sonner";

import { LoadingSkeleton } from "@/components/LoadingSkeleton";
import { Button } from "@/components/ui/button";
import { apiClient } from "@/lib/api";
import { saveExecutionContext } from "@/lib/userFlowContext";

export const UserSignalsPage = () => {
  const navigate = useNavigate();
  const [signals, setSignals] = useState([]);
  const [signalMode, setSignalMode] = useState(null);
  const [botProfiles, setBotProfiles] = useState([]);
  const [portfolio, setPortfolio] = useState(null);
  const [trades, setTrades] = useState([]);
  const [busyId, setBusyId] = useState("");
  const [isLoading, setIsLoading] = useState(true);
  const [compactMode, setCompactMode] = useState(false);
  const [selectedSignalId, setSelectedSignalId] = useState("");
  const [signalTrace, setSignalTrace] = useState(null);
  const [strategyExplain, setStrategyExplain] = useState(null);
  const [explainLoadingId, setExplainLoadingId] = useState("");
  const [blockedAlertEnabled, setBlockedAlertEnabled] = useState(() => localStorage.getItem("signals-blocked-alerts") !== "off");
  const [diagnoseBusyId, setDiagnoseBusyId] = useState("");
  const [isBulkFixRunning, setIsBulkFixRunning] = useState(false);
  const [isStaleCleanupRunning, setIsStaleCleanupRunning] = useState(false);
  const [animatedSignalIds, setAnimatedSignalIds] = useState([]);
  const alertedSignalIdsRef = useRef(new Set());

  const load = async ({ silent = false } = {}) => {
    if (!silent) {
      setIsLoading(true);
    }
    try {
      const [signalsRes, portfolioRes, tradesRes, modeRes, botsRes] = await Promise.allSettled([
        apiClient.get("/user/signals", { params: { limit: 120 }, timeout: 8000 }),
        apiClient.get("/user/portfolio", { timeout: 8000 }),
        apiClient.get("/user/trades", { params: { limit: 120 }, timeout: 8000 }),
        apiClient.get("/user/signal-mode", { timeout: 8000 }),
        apiClient.get("/bot-profiles", { timeout: 8000 }),
      ]);

      const extractData = (result, fallbackValue) => {
        if (result?.status === "fulfilled") {
          return result.value?.data ?? fallbackValue;
        }
        return fallbackValue;
      };

      setSignals(extractData(signalsRes, []));
      setPortfolio(extractData(portfolioRes, null));
      setTrades(extractData(tradesRes, []));
      setSignalMode(extractData(modeRes, null));
      setBotProfiles(extractData(botsRes, []));

      const firstRejected = [signalsRes, portfolioRes, tradesRes, modeRes, botsRes].find((item) => item?.status === "rejected");
      if (firstRejected && !silent) {
        const detail = firstRejected.reason?.response?.data?.detail || firstRejected.reason?.message || "Signals verisi kısmi yüklendi";
        toast.error(typeof detail === "string" ? detail : "Signals verisi kısmi yüklendi");
      }
    } finally {
      if (!silent) {
        setIsLoading(false);
      }
    }
  };

  useEffect(() => {
    load();
  }, []);

  useEffect(() => {
    const timer = setInterval(() => {
      load({ silent: true });
    }, 15000);
    return () => clearInterval(timer);
  }, []);

  useEffect(() => {
    localStorage.setItem("signals-blocked-alerts", blockedAlertEnabled ? "on" : "off");
  }, [blockedAlertEnabled]);

  useEffect(() => {
    if (!blockedAlertEnabled) {
      return;
    }
    const blockedRows = signals.filter((item) => item.status === "blocked" && item.blocked_reason_code);
    for (const row of blockedRows) {
      if (!alertedSignalIdsRef.current.has(row.id)) {
        alertedSignalIdsRef.current.add(row.id);
        toast.warning(`Signal blocked: ${row.symbol} / ${row.blocked_reason_code}`);
      }
    }
  }, [signals, blockedAlertEnabled]);

  const pendingSignals = useMemo(() => signals.filter((item) => item.status === "pending"), [signals]);
  const funnelMetrics = useMemo(() => {
    const counters = {
      detected: signals.length,
      approved_or_ready: 0,
      intent_created: 0,
      submitted: 0,
      filled: 0,
      blocked: 0,
    };
    signals.forEach((row) => {
      if (["ready", "approved", "queued", "submitted", "filled"].includes(String(row.status))) {
        counters.approved_or_ready += 1;
      }
      if (row.created_order_intent_id) {
        counters.intent_created += 1;
      }
      if (["queued", "submitted", "filled"].includes(String(row.status))) {
        counters.submitted += 1;
      }
      if (String(row.status) === "filled") {
        counters.filled += 1;
      }
      if (String(row.status) === "blocked") {
        counters.blocked += 1;
      }
    });
    return counters;
  }, [signals]);

  const recommendationText = useMemo(() => {
    const blockedByCode = signals.reduce((acc, row) => {
      const code = row.blocked_reason_code || "NONE";
      acc[code] = (acc[code] || 0) + 1;
      return acc;
    }, {});
    if ((blockedByCode.MANUAL_APPROVAL_REQUIRED || 0) > 5) {
      return "MANUAL mode yoğun onay bekliyor; hızlı aksiyon için Semi-Auto düşünebilirsiniz.";
    }
    if ((blockedByCode.BOT_NOT_RUNNING || 0) > 0) {
      return "Bazı sinyaller BOT_NOT_RUNNING nedeniyle bloklu; satırdaki Auto Diagnose + Auto Fix ile toparlayın.";
    }
    if ((blockedByCode.RISK_POLICY_MISSING || 0) > 0) {
      return "RISK_POLICY_MISSING blokajı var; satırdaki Risk Policy Auto-Fix ile başlangıç policy'sini otomatik oluşturun.";
    }
    if ((blockedByCode.ORDER_PRECHECK_FAILED || 0) > 0) {
      return "ORDER_PRECHECK_FAILED görüldü; Execute preview parametrelerini gözden geçirin.";
    }
    return "Signal->Execution hattı sağlıklı. Filled oranını artırmak için confidence >= 0.7 filtreleyin.";
  }, [signals]);

  const modeLabelFromRaw = (rawMode) => {
    const normalized = String(rawMode || "ASSISTED").toUpperCase();
    if (normalized === "MANUAL") {
      return "Manual";
    }
    if (normalized === "AUTO") {
      return "Full Auto";
    }
    return "Semi-Auto";
  };

  const statusBadgeClass = (status, isAnimated = false) => {
    const normalized = String(status || "").toLowerCase();
    const pulseClass = isAnimated ? " ring-2 ring-cyan-300 animate-pulse" : "";
    if (["filled", "submitted", "queued", "ready", "approved"].includes(normalized)) {
      return `bg-emerald-200 text-emerald-900${pulseClass}`;
    }
    if (["blocked", "rejected", "expired"].includes(normalized)) {
      return `bg-rose-200 text-rose-900${pulseClass}`;
    }
    return `bg-amber-200 text-amber-900${pulseClass}`;
  };

  const normalizedStatusText = (signal) => {
    const value = String(signal.status || "pending").toLowerCase();
    if (value === "approved") {
      return "Ready";
    }
    if (value === "info") {
      return "Pending";
    }
    return value.charAt(0).toUpperCase() + value.slice(1);
  };

  const decideSignal = async (signalId, action) => {
    setBusyId(signalId);
    try {
      await apiClient.post(`/user/signal/${signalId}/${action}`, { note: `${action}_from_ui` });
      await load();
      toast.success(action === "approve" ? "Signal approve edildi" : "Signal reject edildi");
    } catch (error) {
      toast.error(error?.response?.data?.detail || "Signal kararı kaydedilemedi");
    } finally {
      setBusyId("");
    }
  };

  const openExecuteFromSignal = (signal) => {
    const side = signal.signal === "short" ? "sell" : "buy";
    const marketType = signal.market_type || "spot";
    saveExecutionContext({
      source: "signal",
      symbol: signal.symbol,
      market_type: marketType,
      side,
      signal_id: signal.signal_id,
      strategy_code: signal.strategy_code,
      blocked_reason_code: signal.blocked_reason_code,
    });
    navigate(
      `/user/execute?source=signal&symbol=${encodeURIComponent(signal.symbol)}&side=${encodeURIComponent(side)}&market_type=${encodeURIComponent(marketType)}&preset=spot_basic`,
    );
  };

  const applyPresetFromSignal = (signal) => {
    const side = signal.signal === "short" ? "sell" : "buy";
    navigate(`/user/execute?source=signal&symbol=${encodeURIComponent(signal.symbol)}&side=${encodeURIComponent(side)}&market_type=${encodeURIComponent(signal.market_type || "spot")}&preset=spot_basic`);
  };

  const runDiagnose = async (signalId, autoFix = false) => {
    setDiagnoseBusyId(signalId);
    try {
      const { data } = await apiClient.post(`/user/signal/${signalId}/diagnose`, null, { params: { auto_fix: autoFix } });
      await load();
      const actions = (data?.actions_applied || []).join(", ");
      if (autoFix) {
        setAnimatedSignalIds((previous) => Array.from(new Set([...previous, signalId])));
        setTimeout(() => {
          setAnimatedSignalIds((previous) => previous.filter((item) => item !== signalId));
        }, 3200);
      }
      toast.success(`Diagnose: ${data.current_state}${actions ? ` / actions: ${actions}` : ""}`);
    } catch (error) {
      toast.error(error?.response?.data?.detail || "Signal diagnose başarısız");
    } finally {
      setDiagnoseBusyId("");
    }
  };

  const runFixAllBlockers = async () => {
    setIsBulkFixRunning(true);
    try {
      const { data } = await apiClient.post("/user/signals/fix-all-blockers", null, { params: { limit: 250 } });
      await load();
      const updatedIds = data?.updated_signal_ids || [];
      if (updatedIds.length > 0) {
        setAnimatedSignalIds((previous) => Array.from(new Set([...previous, ...updatedIds])));
        setTimeout(() => {
          setAnimatedSignalIds((previous) => previous.filter((id) => !updatedIds.includes(id)));
        }, 3600);
      }
      toast.success(`Fix All tamamlandı: fixed=${data?.fixed_count || 0}, remaining=${data?.remaining_blocked || 0}`);
    } catch (error) {
      toast.error(error?.response?.data?.detail || "Fix All Blockers başarısız");
    } finally {
      setIsBulkFixRunning(false);
    }
  };

  const runStaleCleanup = async () => {
    setIsStaleCleanupRunning(true);
    try {
      const { data } = await apiClient.post("/user/signals/cleanup-stale-intents", null, {
        params: { stale_minutes: 25, signal_stale_minutes: 180 },
      });
      await load();
      toast.success(`Stale cleanup: intent=${data?.cancelled_intent_count || 0}, signal=${data?.expired_signal_count || 0}`);
    } catch (error) {
      toast.error(error?.response?.data?.detail || "Stale cleanup başarısız");
    } finally {
      setIsStaleCleanupRunning(false);
    }
  };

  const setSignalModeAuto = async () => {
    try {
      await apiClient.put("/user/signal-mode", { mode: "AUTO" });
      await load();
      toast.success("Signal mode AUTO olarak ayarlandı");
    } catch (error) {
      toast.error(error?.response?.data?.detail || "Signal mode AUTO ayarlanamadı");
    }
  };

  const activeBotCount = useMemo(
    () => (botProfiles || []).filter((item) => item.is_running && item.is_enabled).length,
    [botProfiles],
  );

  const controlPanelState = useMemo(() => {
    const rawMode = String(signalMode?.mode || "ASSISTED").toUpperCase();
    const latestSignal = signals[0] || null;
    const currentBlocker = signals.find((item) => item.status === "blocked" && item.blocked_reason_code) || null;
    let executionPath = "MANUAL_FLOW";
    if (rawMode === "AUTO" && activeBotCount > 0) {
      executionPath = "BOT_AUTO_ACTIVE";
    } else if (rawMode === "ASSISTED") {
      executionPath = "SEMI_AUTO_ACTIVE";
    }
    return {
      rawMode,
      botRuntime: activeBotCount > 0 ? "RUNNING" : "STOPPED",
      activeBotCount,
      latestSignalState: latestSignal ? `${String(latestSignal.status || "-").toUpperCase()} (${latestSignal.symbol})` : "-",
      currentBlocker: currentBlocker?.blocked_reason_code || "-",
      executionPath,
    };
  }, [activeBotCount, signalMode?.mode, signals]);

  const buildIntentPayload = (signal) => ({
    source_type: "signal",
    source_ref_id: signal.signal_id,
    market_type: signal.market_type || "spot",
    symbol: signal.symbol,
    side: signal.signal === "short" ? "sell" : "buy",
    order_type: "market",
    position_size_mode: "fixed_notional",
    position_size_value: 30,
    take_profit_mode: "percent",
    take_profit_value: 2,
    stop_loss_mode: "percent",
    stop_loss_value: 1,
    execution_mode: "signal_follow",
    strategy_binding: signal.strategy_code,
    signal_confidence: signal.confidence,
    exchange_connection_id: signal.exchange_connection_id || null,
  });

  const previewIntentFromSignal = async (signal) => {
    try {
      const { data } = await apiClient.post("/user/execution/intent/preview", buildIntentPayload(signal));
      toast.success(`Preview: ${data.validation_status}`);
    } catch (error) {
      toast.error(error?.response?.data?.detail || "Preview başarısız");
    }
  };

  const followSignalToQueue = async (signal) => {
    try {
      const { data } = await apiClient.post("/user/execution/intent/preview", buildIntentPayload(signal));
      if (data.validation_status !== "valid") {
        toast.error("Signal policy tarafından reddedildi");
        return;
      }
      await apiClient.post("/user/execution/intent/submit", {
        intent_token: data.intent_token,
        preview_hash: data.preview_hash,
      });
      toast.success("Follow Signal kuyruğa eklendi");
    } catch (error) {
      toast.error(error?.response?.data?.detail || "Follow signal başarısız");
    }
  };

  const openSignalExplain = async (signal) => {
    setSelectedSignalId(signal.id);
    setExplainLoadingId(signal.id);
    try {
      const [traceRes, strategyRes] = await Promise.all([
        apiClient.get(`/user/signals/${signal.id}/decision-trace`),
        apiClient.get(`/user/strategies/${encodeURIComponent(signal.strategy_code)}/explain`, { params: { lookback_days: 30 } }),
      ]);
      setSignalTrace(traceRes.data || null);
      setStrategyExplain(strategyRes.data || null);
    } catch (error) {
      toast.error(error?.response?.data?.detail || "Signal açıklaması yüklenemedi");
    } finally {
      setExplainLoadingId("");
    }
  };

  if (isLoading) {
    return <LoadingSkeleton rows={6} testId="user-signals-loading-skeleton" />;
  }

  return (
    <section className="grid grid-cols-12 gap-4" data-testid="user-signals-page">
      <header className="col-span-12 border border-slate-800 bg-slate-900 p-4" data-testid="user-signals-header">
        <div className="flex flex-wrap items-center justify-between gap-3" data-testid="user-signals-header-controls">
          <div>
            <h2 className="text-4xl font-black uppercase tracking-tight" data-testid="user-signals-title">Signals</h2>
            <p className="mt-2 text-sm text-slate-400" data-testid="user-signals-description">ASSISTED queue + responsive card/table layout + compact mode.</p>
          </div>
          <Button type="button" variant="outline" onClick={() => setCompactMode((previous) => !previous)} data-testid="user-signals-compact-mode-toggle" aria-label="Compact mode aç/kapat">
            {compactMode ? "Compact: ON" : "Compact: OFF"}
          </Button>
        </div>
        <p className="mt-3 inline-flex items-center rounded-full bg-emerald-100 px-3 py-1 text-xs font-semibold text-emerald-900" data-testid="user-signals-active-execution-mode-badge">
          Execution Mode: {modeLabelFromRaw(signalMode?.mode)}
        </p>
        <div className="mt-3 flex flex-wrap items-center gap-3" data-testid="user-signals-alert-settings-row">
          <label className="inline-flex items-center gap-2 text-xs text-slate-300" data-testid="user-signals-blocked-alert-toggle-wrapper">
            <input type="checkbox" checked={blockedAlertEnabled} onChange={(event) => setBlockedAlertEnabled(event.target.checked)} data-testid="user-signals-blocked-alert-toggle" />
            blocked sinyal uyarıları aktif
          </label>
          <Button variant="outline" onClick={load} data-testid="user-signals-refresh-button">Yenile</Button>
          <Button variant="outline" disabled={isStaleCleanupRunning} onClick={runStaleCleanup} data-testid="user-signals-stale-cleanup-button">
            {isStaleCleanupRunning ? "Temizleniyor..." : "Stale Temizliği"}
          </Button>
          <Button className="bg-cyan-500 text-black hover:bg-cyan-400" disabled={isBulkFixRunning} onClick={runFixAllBlockers} data-testid="user-signals-fix-all-blockers-button">
            {isBulkFixRunning ? "Fixing..." : "Fix All Blockers"}
          </Button>
          <Button variant="outline" onClick={setSignalModeAuto} data-testid="user-signals-set-auto-mode-button">AUTO'ya Al</Button>
          <span className="text-xs text-slate-400" data-testid="user-signals-auto-refresh-indicator">Auto Refresh: 15s</span>
        </div>
      </header>

      <section className="col-span-12 rounded border border-cyan-800/50 bg-cyan-950/20 p-4" data-testid="user-signals-live-control-status-card">
        <p className="text-xs uppercase tracking-widest text-cyan-300" data-testid="user-signals-live-control-status-title">Live Control Status</p>
        <div className="mt-3 grid gap-2 md:grid-cols-3" data-testid="user-signals-live-control-status-grid">
          <p className="text-sm" data-testid="user-signals-live-control-mode">Signal Mode: {controlPanelState.rawMode}</p>
          <p className="text-sm" data-testid="user-signals-live-control-bot-runtime">Bot Runtime: {controlPanelState.botRuntime} ({controlPanelState.activeBotCount})</p>
          <p className="text-sm" data-testid="user-signals-live-control-execution-path">Execution Path: {controlPanelState.executionPath}</p>
          <p className="text-sm" data-testid="user-signals-live-control-latest-signal-state">Last Signal State: {controlPanelState.latestSignalState}</p>
          <p className="text-sm" data-testid="user-signals-live-control-current-blocker">Current Blocker: {controlPanelState.currentBlocker}</p>
          <p className="text-sm" data-testid="user-signals-live-control-note">Not: ORDER_PRECHECK_FAILED durumunda sinyal güvenlik için blocked kalır.</p>
        </div>
      </section>

      <div className="col-span-12 grid grid-cols-12 gap-3" data-testid="user-signals-metrics-grid">
        <div className="col-span-6 md:col-span-3 border border-slate-800 bg-slate-900 p-3" data-testid="user-signals-pending-count-card"><p className="text-xs text-slate-500">Pending</p><p className="text-xl font-semibold text-orange-400" data-testid="user-signals-pending-count-value">{pendingSignals.length}</p></div>
        <div className="col-span-6 md:col-span-3 border border-slate-800 bg-slate-900 p-3" data-testid="user-signals-open-positions-card"><p className="text-xs text-slate-500">Open Positions</p><p className="text-xl font-semibold" data-testid="user-signals-open-positions-value">{portfolio?.open_positions_count ?? "-"}</p></div>
        <div className="col-span-6 md:col-span-3 border border-slate-800 bg-slate-900 p-3" data-testid="user-signals-open-notional-card"><p className="text-xs text-slate-500">Open Notional</p><p className="text-xl font-semibold" data-testid="user-signals-open-notional-value">{portfolio?.open_notional ?? "-"}</p></div>
        <div className="col-span-6 md:col-span-3 border border-slate-800 bg-slate-900 p-3" data-testid="user-signals-trades-count-card"><p className="text-xs text-slate-500">Trades</p><p className="text-xl font-semibold" data-testid="user-signals-trades-count-value">{trades.length}</p></div>
      </div>

      <div className="col-span-12 grid grid-cols-12 gap-3" data-testid="user-signals-funnel-grid">
        <div className="col-span-6 md:col-span-2 border border-slate-800 bg-slate-900 p-3" data-testid="user-signals-funnel-detected-card"><p className="text-[11px] text-slate-500">Detected</p><p className="text-lg font-semibold">{funnelMetrics.detected}</p></div>
        <div className="col-span-6 md:col-span-2 border border-slate-800 bg-slate-900 p-3" data-testid="user-signals-funnel-approved-card"><p className="text-[11px] text-slate-500">Ready/Approved</p><p className="text-lg font-semibold">{funnelMetrics.approved_or_ready}</p></div>
        <div className="col-span-6 md:col-span-2 border border-slate-800 bg-slate-900 p-3" data-testid="user-signals-funnel-intent-card"><p className="text-[11px] text-slate-500">Intent</p><p className="text-lg font-semibold">{funnelMetrics.intent_created}</p></div>
        <div className="col-span-6 md:col-span-2 border border-slate-800 bg-slate-900 p-3" data-testid="user-signals-funnel-submitted-card"><p className="text-[11px] text-slate-500">Submitted</p><p className="text-lg font-semibold">{funnelMetrics.submitted}</p></div>
        <div className="col-span-6 md:col-span-2 border border-slate-800 bg-slate-900 p-3" data-testid="user-signals-funnel-filled-card"><p className="text-[11px] text-slate-500">Filled</p><p className="text-lg font-semibold text-emerald-400">{funnelMetrics.filled}</p></div>
        <div className="col-span-6 md:col-span-2 border border-slate-800 bg-slate-900 p-3" data-testid="user-signals-funnel-blocked-card"><p className="text-[11px] text-slate-500">Blocked</p><p className="text-lg font-semibold text-rose-400">{funnelMetrics.blocked}</p></div>
      </div>

      <div className="col-span-12 border border-amber-500/40 bg-amber-500/10 p-3" data-testid="user-signals-smart-recommendation-banner">
        <p className="text-xs uppercase tracking-wider text-amber-300" data-testid="user-signals-smart-recommendation-title">Akıllı Öneri</p>
        <p className="mt-1 text-sm text-amber-100" data-testid="user-signals-smart-recommendation-text">{recommendationText}</p>
      </div>

      <aside className="col-span-12 border border-slate-800 bg-slate-900 p-4" data-testid="user-signals-explain-panel">
        <p className="text-xs uppercase tracking-widest text-slate-500" data-testid="user-signals-explain-panel-title">Why this signal?</p>
        {!selectedSignalId && (
          <p className="mt-2 text-sm text-slate-400" data-testid="user-signals-explain-empty-state">Bir sinyal seçerek açıklama panelini açın.</p>
        )}
        {Boolean(selectedSignalId && explainLoadingId === selectedSignalId) && (
          <p className="mt-2 text-sm text-slate-300" data-testid="user-signals-explain-loading-state">Açıklama yükleniyor...</p>
        )}
        {Boolean(selectedSignalId && signalTrace?.latest_trace) && (
          <div className="mt-3 grid gap-3 lg:grid-cols-2" data-testid="user-signals-explain-content">
            <div className="border border-slate-800 p-3" data-testid="user-signals-latest-trace-card">
              <p className="text-xs text-slate-500" data-testid="user-signals-latest-trace-status">Decision: {signalTrace.latest_trace.decision_status}</p>
              <p className="text-xs text-slate-500" data-testid="user-signals-latest-trace-type">Type: {signalTrace.latest_trace.trace_type}</p>
              <p className="text-xs text-slate-500" data-testid="user-signals-latest-trace-meta-decision">Meta: {signalTrace.latest_trace.meta_engine_decision || "-"}</p>
              <p className="text-xs text-slate-500" data-testid="user-signals-latest-trace-allocation-reason">Allocation Reason: {signalTrace.latest_trace.strategy_allocation_reason || "-"}</p>
              <div className="mt-2 space-y-2" data-testid="user-signals-reason-details-list">
                {(signalTrace.latest_trace.reason_details || []).map((reason) => (
                  <article key={reason.code} className="border border-slate-800 p-2" data-testid={`user-signals-reason-item-${reason.code}`}>
                    <p className="text-sm font-semibold" data-testid={`user-signals-reason-title-${reason.code}`}>{reason.title}</p>
                    <p className="text-xs text-slate-400" data-testid={`user-signals-reason-description-${reason.code}`}>{reason.description}</p>
                  </article>
                ))}
              </div>
            </div>

            <div className="border border-slate-800 p-3" data-testid="user-signals-strategy-explain-card">
              <p className="text-xs text-slate-500" data-testid="user-signals-strategy-code">Strategy: {strategyExplain?.strategy_code || "-"}</p>
              <p className="text-xs text-slate-500" data-testid="user-signals-strategy-trace-count">Trace Count: {strategyExplain?.trace_count ?? 0}</p>
              <div className="mt-2 space-y-2" data-testid="user-signals-strategy-top-reasons">
                {(strategyExplain?.top_reason_codes || []).slice(0, 3).map((reason) => (
                  <article key={reason.code} className="border border-slate-800 p-2" data-testid={`user-signals-strategy-reason-${reason.code}`}>
                    <p className="text-sm" data-testid={`user-signals-strategy-reason-title-${reason.code}`}>{reason.title} · {reason.count}</p>
                    <p className="text-xs text-slate-400" data-testid={`user-signals-strategy-reason-desc-${reason.code}`}>{reason.description}</p>
                  </article>
                ))}
              </div>
            </div>
          </div>
        )}
      </aside>

      <div className="col-span-12 grid gap-3 md:hidden" data-testid="user-signals-mobile-cards">
        {signals.map((signal) => (
          <article key={signal.id} className="rounded border border-slate-800 bg-slate-900 p-3" data-testid={`user-signals-mobile-card-${signal.id}`}>
            <p className="text-sm font-semibold" data-testid={`user-signals-mobile-symbol-${signal.id}`}>{signal.symbol}</p>
            <p className="text-xs text-cyan-300" data-testid={`user-signals-mobile-market-type-${signal.id}`}>market: {String(signal.market_type || "spot").toUpperCase()}</p>
            <p className="text-xs" data-testid={`user-signals-mobile-status-${signal.id}`}>
              <span className={`rounded px-2 py-1 font-semibold ${statusBadgeClass(signal.status, animatedSignalIds.includes(signal.id))}`} data-testid={`user-signals-mobile-status-badge-${signal.id}`}>
                {normalizedStatusText(signal)}
              </span>
            </p>
            <p className="text-xs text-slate-500" data-testid={`user-signals-mobile-execution-mode-${signal.id}`}>mode: {signal.execution_mode_label || modeLabelFromRaw(signal.mode)}</p>
            <p className="text-xs text-rose-300" data-testid={`user-signals-mobile-blocked-reason-${signal.id}`}>blocked: {signal.blocked_reason_code || "-"}</p>
            <p className="text-xs text-slate-400" data-testid={`user-signals-mobile-solution-hint-${signal.id}`}>hint: {signal.blocked_solution_hint || "-"}</p>
            <p className="text-xs text-slate-500" data-testid={`user-signals-mobile-strategy-${signal.id}`}>{signal.strategy_code}</p>
            <p className="text-xs text-slate-400" data-testid={`user-signals-mobile-strategy-weight-${signal.id}`}>weight: {signal.strategy_weight ?? "-"}</p>
            <p className="text-xs text-slate-400" data-testid={`user-signals-mobile-allocation-source-${signal.id}`}>source: {signal.allocation_source ?? "-"}</p>
            <p className="text-xs text-slate-400" data-testid={`user-signals-mobile-meta-decision-${signal.id}`}>meta: {signal.meta_engine_decision ?? "-"}</p>
            <div className="mt-2 flex flex-wrap gap-2" data-testid={`user-signals-mobile-actions-${signal.id}`}>
              <Button variant="outline" onClick={() => openSignalExplain(signal)} data-testid={`user-signals-mobile-why-button-${signal.id}`}>Why this signal?</Button>
              {(signal.status === "pending" || signal.status === "ready" || signal.status === "blocked") && (
                <>
                  {(signal.status === "pending" || signal.status === "ready") && (
                    <>
                      <Button className="bg-emerald-500 text-black hover:bg-emerald-400" disabled={busyId === signal.id} onClick={() => decideSignal(signal.id, "approve")} data-testid={`user-signals-mobile-approve-${signal.id}`}>Approve</Button>
                      <Button variant="outline" disabled={busyId === signal.id} onClick={() => decideSignal(signal.id, "reject")} data-testid={`user-signals-mobile-reject-${signal.id}`}>Reject</Button>
                    </>
                  )}
                  <Button variant="outline" onClick={() => openExecuteFromSignal(signal)} data-testid={`user-signals-mobile-open-execute-${signal.id}`}>Execute</Button>
                  <Button variant="outline" onClick={() => applyPresetFromSignal(signal)} data-testid={`user-signals-mobile-apply-preset-${signal.id}`}>Apply Preset</Button>
                  <Button variant="outline" onClick={() => previewIntentFromSignal(signal)} data-testid={`user-signals-mobile-preview-intent-${signal.id}`}>Preview Intent</Button>
                  <Button variant="outline" onClick={() => followSignalToQueue(signal)} data-testid={`user-signals-mobile-follow-signal-${signal.id}`}>Follow Signal</Button>
                  <Button variant="outline" disabled={diagnoseBusyId === signal.id} onClick={() => runDiagnose(signal.id, false)} data-testid={`user-signals-mobile-diagnose-${signal.id}`}>Diagnose</Button>
                  {signal.blocked_reason_code === "RISK_POLICY_MISSING" && (
                    <Button className="bg-amber-500 text-black hover:bg-amber-600" disabled={diagnoseBusyId === signal.id} onClick={() => runDiagnose(signal.id, true)} data-testid={`user-signals-mobile-risk-policy-autofix-${signal.id}`}>
                      Risk Policy Auto-Fix
                    </Button>
                  )}
                  <Button variant="outline" disabled={diagnoseBusyId === signal.id} onClick={() => runDiagnose(signal.id, true)} data-testid={`user-signals-mobile-diagnose-fix-${signal.id}`}>Auto Fix</Button>
                </>
              )}
              {!(signal.status === "pending" || signal.status === "ready") && (
                <span className="text-xs text-slate-400" data-testid={`user-signals-mobile-final-status-${signal.id}`}>{signal.status}</span>
              )}
            </div>
          </article>
        ))}
      </div>

      <div className="col-span-12 hidden overflow-x-auto border border-slate-800 bg-slate-900 md:block" data-testid="user-signals-table-wrapper">
        <table className="min-w-[2200px] text-sm" data-testid="user-signals-table" aria-label="Signals tablosu">
          <thead className="bg-slate-800 text-left" data-testid="user-signals-table-head">
            <tr>
              <th className={compactMode ? "px-2 py-1" : "px-3 py-2"}>Symbol</th>
              <th className={compactMode ? "px-2 py-1" : "px-3 py-2"}>Market</th>
              <th className={compactMode ? "px-2 py-1" : "px-3 py-2"}>Strategy</th>
              <th className={compactMode ? "px-2 py-1" : "px-3 py-2"}>Confidence</th>
              <th className={compactMode ? "px-2 py-1" : "px-3 py-2"}>Weight</th>
              <th className={compactMode ? "px-2 py-1" : "px-3 py-2"}>Allocation</th>
              <th className={compactMode ? "px-2 py-1" : "px-3 py-2"}>Meta</th>
              <th className={compactMode ? "px-2 py-1" : "px-3 py-2"}>Status</th>
              <th className={compactMode ? "px-2 py-1" : "px-3 py-2"}>Execution Mode</th>
              <th className={compactMode ? "px-2 py-1" : "px-3 py-2"}>Blokaj Nedeni</th>
              <th className={compactMode ? "px-2 py-1" : "px-3 py-2"}>Son Uygunluk Kontrolü</th>
              <th className={compactMode ? "px-2 py-1" : "px-3 py-2"}>Intent</th>
              <th className={compactMode ? "px-2 py-1" : "px-3 py-2"}>Runtime Sahibi</th>
              <th className={compactMode ? "px-2 py-1" : "px-3 py-2"}>Time</th>
              <th className={compactMode ? "px-2 py-1" : "px-3 py-2"}>Actions</th>
            </tr>
          </thead>
          <tbody data-testid="user-signals-table-body">
            {signals.map((signal) => (
              <tr key={signal.id} className="border-t border-slate-800" data-testid={`user-signals-table-row-${signal.id}`}>
                <td className={compactMode ? "px-2 py-1" : "px-3 py-2"} data-testid={`user-signals-table-symbol-${signal.id}`}>{signal.symbol}</td>
                <td className={compactMode ? "px-2 py-1" : "px-3 py-2"} data-testid={`user-signals-table-market-type-${signal.id}`}>{String(signal.market_type || "spot").toUpperCase()}</td>
                <td className={compactMode ? "px-2 py-1" : "px-3 py-2"} data-testid={`user-signals-table-strategy-${signal.id}`}>{signal.strategy_code}</td>
                <td className={compactMode ? "px-2 py-1" : "px-3 py-2"} data-testid={`user-signals-table-confidence-${signal.id}`}>{signal.confidence}</td>
                <td className={compactMode ? "px-2 py-1" : "px-3 py-2"} data-testid={`user-signals-table-weight-${signal.id}`}>{signal.strategy_weight ?? "-"}</td>
                <td className={compactMode ? "px-2 py-1" : "px-3 py-2"} data-testid={`user-signals-table-allocation-${signal.id}`}>{signal.allocation_source ?? "-"}</td>
                <td className={compactMode ? "px-2 py-1" : "px-3 py-2"} data-testid={`user-signals-table-meta-${signal.id}`}>{signal.meta_engine_decision ?? "-"}</td>
                <td className={compactMode ? "px-2 py-1" : "px-3 py-2"} data-testid={`user-signals-table-status-${signal.id}`}>
                  <span className={`rounded px-2 py-1 text-xs font-semibold ${statusBadgeClass(signal.status, animatedSignalIds.includes(signal.id))}`} data-testid={`user-signals-table-status-badge-${signal.id}`}>{normalizedStatusText(signal)}</span>
                </td>
                <td className={compactMode ? "px-2 py-1" : "px-3 py-2"} data-testid={`user-signals-table-execution-mode-${signal.id}`}>{signal.execution_mode_label || modeLabelFromRaw(signal.mode)}</td>
                <td className={compactMode ? "px-2 py-1" : "px-3 py-2"} data-testid={`user-signals-table-blocked-reason-${signal.id}`}>
                  <div className="max-w-[260px]">
                    <p className="text-xs font-semibold">{signal.blocked_reason_code || "-"}</p>
                    <p className="text-[11px] text-slate-400 break-words" data-testid={`user-signals-table-blocked-solution-${signal.id}`}>{signal.blocked_solution_hint || "-"}</p>
                  </div>
                </td>
                <td className={compactMode ? "px-2 py-1" : "px-3 py-2"} data-testid={`user-signals-table-last-eligibility-check-${signal.id}`}>{signal.last_eligibility_check_at ? new Date(signal.last_eligibility_check_at).toLocaleString() : "-"}</td>
                <td className={compactMode ? "px-2 py-1" : "px-3 py-2"} data-testid={`user-signals-table-intent-${signal.id}`}>{signal.created_order_intent_id || "-"}</td>
                <td className={compactMode ? "px-2 py-1" : "px-3 py-2"} data-testid={`user-signals-table-runtime-owner-${signal.id}`}>{signal.runtime_owner || "-"}</td>
                <td className={compactMode ? "px-2 py-1" : "px-3 py-2"} data-testid={`user-signals-table-time-${signal.id}`}>{new Date(signal.created_at).toLocaleString()}</td>
                <td className={compactMode ? "px-2 py-1 align-top min-w-[420px]" : "px-3 py-2 align-top min-w-[420px]"}>
                  <div className="flex min-w-max flex-nowrap gap-2 whitespace-nowrap" data-testid={`user-signals-actions-${signal.id}`}>
                    <Button variant="outline" onClick={() => openSignalExplain(signal)} data-testid={`user-signals-why-button-${signal.id}`}>Why this signal?</Button>
                    {(signal.status === "pending" || signal.status === "ready" || signal.status === "blocked") ? (
                      <>
                        {(signal.status === "pending" || signal.status === "ready") && (
                          <>
                            <Button className="bg-emerald-500 text-black hover:bg-emerald-400" disabled={busyId === signal.id} onClick={() => decideSignal(signal.id, "approve")} data-testid={`user-signals-approve-button-${signal.id}`}>Approve</Button>
                            <Button variant="outline" disabled={busyId === signal.id} onClick={() => decideSignal(signal.id, "reject")} data-testid={`user-signals-reject-button-${signal.id}`}>Reject</Button>
                          </>
                        )}
                        <Button variant="outline" onClick={() => openExecuteFromSignal(signal)} data-testid={`user-signals-open-execute-button-${signal.id}`}>Open in Execute</Button>
                        <Button variant="outline" onClick={() => applyPresetFromSignal(signal)} data-testid={`user-signals-apply-preset-button-${signal.id}`}>Apply Preset</Button>
                        <Button variant="outline" onClick={() => previewIntentFromSignal(signal)} data-testid={`user-signals-preview-intent-button-${signal.id}`}>Preview Intent</Button>
                        <Button variant="outline" onClick={() => followSignalToQueue(signal)} data-testid={`user-signals-follow-signal-button-${signal.id}`}>Follow Signal</Button>
                        <Button variant="outline" disabled={diagnoseBusyId === signal.id} onClick={() => runDiagnose(signal.id, false)} data-testid={`user-signals-diagnose-button-${signal.id}`}>Diagnose</Button>
                        {signal.blocked_reason_code === "RISK_POLICY_MISSING" && (
                          <Button className="bg-amber-500 text-black hover:bg-amber-600" disabled={diagnoseBusyId === signal.id} onClick={() => runDiagnose(signal.id, true)} data-testid={`user-signals-risk-policy-autofix-button-${signal.id}`}>
                            Risk Policy Auto-Fix
                          </Button>
                        )}
                        <Button variant="outline" disabled={diagnoseBusyId === signal.id} onClick={() => runDiagnose(signal.id, true)} data-testid={`user-signals-diagnose-fix-button-${signal.id}`}>Auto Fix</Button>
                      </>
                    ) : (
                      <span className="text-xs text-slate-400" data-testid={`user-signals-final-status-text-${signal.id}`}>{signal.status}</span>
                    )}
                  </div>
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </section>
  );
};