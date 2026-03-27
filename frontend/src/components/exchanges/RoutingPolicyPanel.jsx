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

export const RoutingPolicyPanel = ({ approvedUsers, exchanges, data, loading, error, onRefresh, onSavePolicy }) => {
  const userOptions = useMemo(() => approvedUsers || [], [approvedUsers]);
  const exchangeCodes = useMemo(() => (exchanges || []).map((item) => item.exchange_code), [exchanges]);

  const [userId, setUserId] = useState("");
  const [strategyId, setStrategyId] = useState("");
  const [defaultVenue, setDefaultVenue] = useState(exchangeCodes[0] || "binance");
  const [preferredVenuesText, setPreferredVenuesText] = useState("binance,bybit");
  const [blockedVenuesText, setBlockedVenuesText] = useState("okx");
  const [capitalAllocationText, setCapitalAllocationText] = useState('[{"venue":"binance","weight":0.7},{"venue":"bybit","weight":0.3}]');
  const [executionPolicyText, setExecutionPolicyText] = useState('{"max_slippage":0.01}');

  const selectedKey = `${userId}:${strategyId}`;
  const existingRule = (data?.rules || {})[selectedKey] || null;

  const loadRule = () => {
    if (!existingRule) return;
    setDefaultVenue(existingRule.default_venue || "binance");
    setPreferredVenuesText((existingRule.preferred_venues || []).join(","));
    setBlockedVenuesText((existingRule.blocked_venues || []).join(","));
    setCapitalAllocationText(JSON.stringify(existingRule.capital_allocation || [], null, 2));
    setExecutionPolicyText(JSON.stringify(existingRule.execution_policy_override || {}, null, 2));
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
  };

  return (
    <section className="rounded-2xl border border-slate-700 bg-slate-950/70 p-4" data-testid="routing-policy-panel">
      <div className="mb-3 flex items-center justify-between gap-3">
        <div>
          <h3 className="text-base font-semibold text-orange-200" data-testid="routing-policy-panel-title">Routing Policy Management</h3>
          <p className="text-xs text-slate-400" data-testid="routing-policy-panel-subtitle">Priority + preferred/fallback path + execution override</p>
        </div>
        <div className="flex gap-2">
          <Button type="button" variant="outline" onClick={onRefresh} data-testid="routing-policy-refresh-button">Yenile</Button>
          <Button type="button" variant="outline" onClick={loadRule} data-testid="routing-policy-load-existing-button">Kural Yükle</Button>
        </div>
      </div>

      <div className="grid gap-2 md:grid-cols-3" data-testid="routing-policy-form-grid">
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
      </div>

      <Input value={preferredVenuesText} onChange={(event) => setPreferredVenuesText(event.target.value)} className="mt-2" placeholder="preferred venues csv" data-testid="routing-policy-preferred-venues-input" />
      <Input value={blockedVenuesText} onChange={(event) => setBlockedVenuesText(event.target.value)} className="mt-2" placeholder="blocked venues csv" data-testid="routing-policy-blocked-venues-input" />
      <Textarea value={capitalAllocationText} onChange={(event) => setCapitalAllocationText(event.target.value)} className="mt-2 min-h-20 text-xs" data-testid="routing-policy-capital-allocation-textarea" />
      <Textarea value={executionPolicyText} onChange={(event) => setExecutionPolicyText(event.target.value)} className="mt-2 min-h-20 text-xs" data-testid="routing-policy-execution-policy-textarea" />

      <Button type="button" className="mt-2" onClick={save} data-testid="routing-policy-save-button">Routing Policy Kaydet</Button>

      {loading && <p className="mt-2 text-sm text-slate-400" data-testid="routing-policy-loading-state">Yükleniyor...</p>}
      {!loading && error && <p className="mt-2 text-sm text-red-300" data-testid="routing-policy-error-state">{error}</p>}
      {!loading && !error && !existingRule && (
        <p className="mt-2 text-sm text-slate-400" data-testid="routing-policy-empty-state">Seçili user/strategy için policy bulunamadı.</p>
      )}
      {!loading && !error && existingRule && (
        <p className="mt-2 text-xs text-slate-300" data-testid="routing-policy-existing-summary">Mevcut kural bulundu: default={existingRule.default_venue || "-"}</p>
      )}
    </section>
  );
};
