import { useMemo, useState } from "react";
import { toast } from "sonner";

import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Textarea } from "@/components/ui/textarea";

const parseCsv = (value) =>
  String(value || "")
    .split(",")
    .map((item) => item.trim().toLowerCase())
    .filter(Boolean);

export const RoutingPolicyPanel = ({
  approvedUsers,
  exchanges,
  data,
  failoverData,
  loading,
  error,
  onRefresh,
  onRefreshFailover,
  onSavePolicy,
  onSaveFailoverPolicy,
  onApplyManualOverride,
}) => {
  const userOptions = useMemo(() => approvedUsers || [], [approvedUsers]);
  const exchangeCodes = useMemo(() => (exchanges || []).map((item) => item.exchange_code), [exchanges]);

  const [userId, setUserId] = useState("");
  const [strategyId, setStrategyId] = useState("");
  const [marketType, setMarketType] = useState("spot");
  const [environment, setEnvironment] = useState("testnet");
  const [defaultVenue, setDefaultVenue] = useState(exchangeCodes[0] || "binance");
  const [preferredVenuesText, setPreferredVenuesText] = useState("binance,bybit");
  const [blockedVenuesText, setBlockedVenuesText] = useState("okx");
  const [capitalAllocationText, setCapitalAllocationText] = useState('[{"venue":"binance","weight":0.7},{"venue":"bybit","weight":0.3}]');
  const [executionPolicyText, setExecutionPolicyText] = useState('{"max_slippage":0.01}');

  const [primaryVenue, setPrimaryVenue] = useState("binance");
  const [secondaryVenue, setSecondaryVenue] = useState("bybit");
  const [fallbackChainText, setFallbackChainText] = useState("okx");
  const [autoRerouteEnabled, setAutoRerouteEnabled] = useState(true);
  const [latencyThreshold, setLatencyThreshold] = useState(1200);
  const [errorRateThreshold, setErrorRateThreshold] = useState(20);
  const [validationFailureThreshold, setValidationFailureThreshold] = useState(25);
  const [manualForceRoute, setManualForceRoute] = useState("");
  const [manualDisableText, setManualDisableText] = useState("");
  const [manualReason, setManualReason] = useState("");

  const selectedKey = `${userId}:${strategyId}`;
  const existingRule = (data?.rules || {})[selectedKey] || null;
  const failoverKey = `${userId}:${strategyId}:${marketType}:${environment}`;
  const existingFailoverRule = (failoverData?.rules || {})[failoverKey] || null;
  const failoverRuntimeState = (failoverData?.runtime_state || {})[failoverKey] || null;
  const failoverTransitionLogs = (failoverData?.transition_logs || []).filter((item) => item.key === failoverKey).slice(0, 5);

  const loadRule = () => {
    if (!existingRule) return;
    setDefaultVenue(existingRule.default_venue || "binance");
    setPreferredVenuesText((existingRule.preferred_venues || []).join(","));
    setBlockedVenuesText((existingRule.blocked_venues || []).join(","));
    setCapitalAllocationText(JSON.stringify(existingRule.capital_allocation || [], null, 2));
    setExecutionPolicyText(JSON.stringify(existingRule.execution_policy_override || {}, null, 2));

    if (existingFailoverRule) {
      setPrimaryVenue(existingFailoverRule.primary_venue || defaultVenue || "binance");
      setSecondaryVenue(existingFailoverRule.secondary_venue || "");
      setFallbackChainText((existingFailoverRule.fallback_chain || []).join(","));
      setAutoRerouteEnabled(Boolean(existingFailoverRule.auto_reroute_enabled));
      setLatencyThreshold(existingFailoverRule?.auto_trigger_thresholds?.latency_ms ?? 1200);
      setErrorRateThreshold(existingFailoverRule?.auto_trigger_thresholds?.error_rate_pct ?? 20);
      setValidationFailureThreshold(existingFailoverRule?.auto_trigger_thresholds?.validation_failure_pct ?? 25);
      setManualForceRoute(existingFailoverRule?.manual_override?.force_route || "");
      setManualDisableText((existingFailoverRule?.manual_override?.force_disable || []).join(","));
      setManualReason(existingFailoverRule?.manual_override?.reason || "");
    }
  };

  const save = async () => {
    let capitalAllocation = [];
    let executionPolicy = {};
    try {
      capitalAllocation = JSON.parse(capitalAllocationText || "[]");
      executionPolicy = JSON.parse(executionPolicyText || "{}");
    } catch {
      toast.error("Routing policy JSON formatı hatalı");
      return;
    }

    await onSavePolicy({
      user_id: userId,
      strategy_id: strategyId,
      default_venue: defaultVenue,
      preferred_venues: parseCsv(preferredVenuesText),
      blocked_venues: parseCsv(blockedVenuesText),
      capital_allocation: capitalAllocation,
      execution_policy_override: executionPolicy,
    });

    await onSaveFailoverPolicy({
      user_id: userId,
      strategy_id: strategyId,
      market_type: marketType,
      environment,
      primary_venue: primaryVenue,
      secondary_venue: secondaryVenue || null,
      fallback_chain: parseCsv(fallbackChainText),
      auto_reroute_enabled: autoRerouteEnabled,
      auto_trigger_thresholds: {
        latency_ms: Number(latencyThreshold),
        error_rate_pct: Number(errorRateThreshold),
        validation_failure_pct: Number(validationFailureThreshold),
      },
      manual_override: {
        force_route: manualForceRoute || null,
        force_disable: parseCsv(manualDisableText),
        reason: manualReason || null,
      },
    });
  };

  const applyManualOverride = async () => {
    if (!userId || !strategyId) {
      toast.error("Önce user ve strategy seçin");
      return;
    }
    await onApplyManualOverride({
      user_id: userId,
      strategy_id: strategyId,
      market_type: marketType,
      environment,
      force_route: manualForceRoute || null,
      force_disable: parseCsv(manualDisableText),
      reason: manualReason || null,
      clear_override: false,
    });
  };

  const clearManualOverride = async () => {
    if (!userId || !strategyId) {
      toast.error("Önce user ve strategy seçin");
      return;
    }
    await onApplyManualOverride({
      user_id: userId,
      strategy_id: strategyId,
      market_type: marketType,
      environment,
      clear_override: true,
    });
  };

  return (
    <section className="rounded-2xl border border-slate-700 bg-slate-950/70 p-4" data-testid="routing-policy-panel">
      <div className="mb-3 flex items-center justify-between gap-3">
        <div>
          <h3 className="text-base font-semibold text-orange-200" data-testid="routing-policy-panel-title">Routing Policy Management</h3>
          <p className="text-xs text-slate-400" data-testid="routing-policy-panel-subtitle">Priority + failover chain + deterministic orchestration</p>
        </div>
        <div className="flex gap-2">
          <Button type="button" variant="outline" onClick={onRefresh} data-testid="routing-policy-refresh-button">Yenile</Button>
          <Button type="button" variant="outline" onClick={onRefreshFailover} data-testid="routing-policy-failover-refresh-button">Failover Yenile</Button>
          <Button type="button" variant="outline" onClick={loadRule} data-testid="routing-policy-load-existing-button">Kural Yükle</Button>
        </div>
      </div>

      <div className="grid gap-2 md:grid-cols-4" data-testid="routing-policy-form-grid">
        <select value={userId} onChange={(event) => setUserId(event.target.value)} className="rounded-md border border-slate-700 bg-slate-900 px-2 py-2 text-sm" data-testid="routing-policy-user-select" required>
          <option value="">Kullanıcı seç</option>
          {userOptions.map((user) => (
            <option key={user.id} value={user.id}>{user.email}</option>
          ))}
        </select>
        <Input value={strategyId} onChange={(event) => setStrategyId(event.target.value)} placeholder="strategy_id" data-testid="routing-policy-strategy-id-input" required />
        <select value={defaultVenue} onChange={(event) => setDefaultVenue(event.target.value)} className="rounded-md border border-slate-700 bg-slate-900 px-2 py-2 text-sm" data-testid="routing-policy-default-venue-select">
          {(exchangeCodes.length ? exchangeCodes : ["binance"]).map((code) => (
            <option key={code} value={code}>{code}</option>
          ))}
        </select>
        <select value={marketType} onChange={(event) => setMarketType(event.target.value)} className="rounded-md border border-slate-700 bg-slate-900 px-2 py-2 text-sm" data-testid="routing-policy-market-type-select">
          <option value="spot">spot</option>
          <option value="futures">futures</option>
        </select>
        <select value={environment} onChange={(event) => setEnvironment(event.target.value)} className="rounded-md border border-slate-700 bg-slate-900 px-2 py-2 text-sm" data-testid="routing-policy-environment-select">
          <option value="testnet">testnet</option>
          <option value="live">live</option>
        </select>
      </div>

      <Input value={preferredVenuesText} onChange={(event) => setPreferredVenuesText(event.target.value)} className="mt-2" placeholder="preferred venues csv" data-testid="routing-policy-preferred-venues-input" />
      <Input value={blockedVenuesText} onChange={(event) => setBlockedVenuesText(event.target.value)} className="mt-2" placeholder="blocked venues csv" data-testid="routing-policy-blocked-venues-input" />
      <Textarea value={capitalAllocationText} onChange={(event) => setCapitalAllocationText(event.target.value)} className="mt-2 min-h-20 text-xs" data-testid="routing-policy-capital-allocation-textarea" />
      <Textarea value={executionPolicyText} onChange={(event) => setExecutionPolicyText(event.target.value)} className="mt-2 min-h-20 text-xs" data-testid="routing-policy-execution-policy-textarea" />

      <div className="mt-3 rounded-lg border border-slate-800 p-3" data-testid="routing-policy-failover-section">
        <p className="text-xs font-semibold text-slate-200" data-testid="routing-policy-failover-section-title">Failover Policy (P2.1)</p>
        <div className="mt-2 grid gap-2 md:grid-cols-3" data-testid="routing-policy-failover-grid">
          <select value={primaryVenue} onChange={(event) => setPrimaryVenue(event.target.value)} className="rounded-md border border-slate-700 bg-slate-900 px-2 py-2 text-sm" data-testid="routing-policy-primary-venue-select">
            {(exchangeCodes.length ? exchangeCodes : ["binance"]).map((code) => <option key={code} value={code}>{code}</option>)}
          </select>
          <select value={secondaryVenue} onChange={(event) => setSecondaryVenue(event.target.value)} className="rounded-md border border-slate-700 bg-slate-900 px-2 py-2 text-sm" data-testid="routing-policy-secondary-venue-select">
            <option value="">secondary (opsiyonel)</option>
            {(exchangeCodes.length ? exchangeCodes : ["binance"]).map((code) => <option key={code} value={code}>{code}</option>)}
          </select>
          <Input value={fallbackChainText} onChange={(event) => setFallbackChainText(event.target.value)} placeholder="fallback chain csv" data-testid="routing-policy-fallback-chain-input" />
          <Input type="number" value={latencyThreshold} onChange={(event) => setLatencyThreshold(event.target.value)} placeholder="latency threshold" data-testid="routing-policy-latency-threshold-input" />
          <Input type="number" value={errorRateThreshold} onChange={(event) => setErrorRateThreshold(event.target.value)} placeholder="error rate threshold" data-testid="routing-policy-error-rate-threshold-input" />
          <Input type="number" value={validationFailureThreshold} onChange={(event) => setValidationFailureThreshold(event.target.value)} placeholder="validation failure threshold" data-testid="routing-policy-validation-failure-threshold-input" />
          <label className="flex items-center gap-2 text-xs text-slate-300" data-testid="routing-policy-auto-reroute-row">
            <input type="checkbox" checked={autoRerouteEnabled} onChange={(event) => setAutoRerouteEnabled(event.target.checked)} data-testid="routing-policy-auto-reroute-checkbox" />
            auto_reroute_enabled
          </label>
        </div>

        <div className="mt-2 grid gap-2 md:grid-cols-3" data-testid="routing-policy-manual-override-grid">
          <Input value={manualForceRoute} onChange={(event) => setManualForceRoute(event.target.value)} placeholder="manual force route" data-testid="routing-policy-manual-force-route-input" />
          <Input value={manualDisableText} onChange={(event) => setManualDisableText(event.target.value)} placeholder="manual disable csv" data-testid="routing-policy-manual-disable-input" />
          <Input value={manualReason} onChange={(event) => setManualReason(event.target.value)} placeholder="manual reason" data-testid="routing-policy-manual-reason-input" />
        </div>

        <div className="mt-2 flex flex-wrap gap-2" data-testid="routing-policy-manual-override-actions">
          <Button type="button" variant="outline" onClick={applyManualOverride} data-testid="routing-policy-manual-override-apply-button">Manual Override Uygula</Button>
          <Button type="button" variant="outline" onClick={clearManualOverride} data-testid="routing-policy-manual-override-clear-button">Manual Override Temizle</Button>
        </div>

        <p className="mt-2 text-xs text-slate-300" data-testid="routing-policy-failover-runtime-summary">
          runtime active={failoverRuntimeState?.active_venue || "-"} / reason={failoverRuntimeState?.selection_reason || "-"} / version={failoverRuntimeState?.version ?? "-"}
        </p>

        <div className="mt-1 space-y-1 text-xs text-slate-400" data-testid="routing-policy-failover-transition-logs">
          {failoverTransitionLogs.length === 0 && <p data-testid="routing-policy-failover-transition-logs-empty">Geçiş logu bulunamadı.</p>}
          {failoverTransitionLogs.map((item, index) => (
            <p key={item.id || index} data-testid={`routing-policy-failover-transition-log-${index}`}>
              {item.created_at} · {item.from_venue || "-"} → {item.to_venue || "-"} ({item.selection_reason})
            </p>
          ))}
        </div>
      </div>

      <Button type="button" className="mt-2" onClick={save} data-testid="routing-policy-save-button">Routing Policy Kaydet</Button>

      {loading && <p className="mt-2 text-sm text-slate-400" data-testid="routing-policy-loading-state">Yükleniyor...</p>}
      {!loading && error && <p className="mt-2 text-sm text-red-300" data-testid="routing-policy-error-state">{error}</p>}
      {!loading && !error && !existingRule && (
        <p className="mt-2 text-sm text-slate-400" data-testid="routing-policy-empty-state">Seçili user/strategy için policy bulunamadı.</p>
      )}
      {!loading && !error && existingRule && (
        <p className="mt-2 text-xs text-slate-300" data-testid="routing-policy-existing-summary">Mevcut kural bulundu: default={existingRule.default_venue || "-"}</p>
      )}
      {!loading && !error && existingFailoverRule && (
        <p className="mt-1 text-xs text-slate-300" data-testid="routing-policy-failover-existing-summary">Mevcut failover kuralı bulundu: primary={existingFailoverRule.primary_venue || "-"}</p>
      )}
    </section>
  );
};
