import { useMemo, useState } from "react";
import { toast } from "sonner";

import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Textarea } from "@/components/ui/textarea";

const formatSymbolRules = (rules) =>
  (rules || [])
    .map((rule) => `${rule.symbol || ""},${rule.action || "allow"},${rule.max_leverage ?? ""},${rule.risk_tier || ""}`)
    .join("\n");

const parseSymbolRules = (value) =>
  String(value || "")
    .split("\n")
    .map((line) => line.trim())
    .filter(Boolean)
    .map((line) => {
      const [symbol, action, maxLeverage, riskTier] = line.split(",").map((item) => item.trim());
      return {
        symbol: (symbol || "").toUpperCase(),
        action: (action || "allow").toLowerCase() === "deny" ? "deny" : "allow",
        ...(maxLeverage ? { max_leverage: Number(maxLeverage) } : {}),
        ...(riskTier ? { risk_tier: riskTier } : {}),
      };
    })
    .filter((item) => item.symbol);

export const MarketPolicyPanel = ({ exchanges, data, loading, error, onRefresh, onSavePolicy }) => {
  const exchangeOptions = useMemo(() => (exchanges || []).map((item) => item.exchange_code), [exchanges]);
  const [exchangeCode, setExchangeCode] = useState(exchangeOptions[0] || "binance");
  const [marketType, setMarketType] = useState("spot");
  const [environment, setEnvironment] = useState("live");
  const [symbolRulesText, setSymbolRulesText] = useState("BTCUSDT,allow,20,tier1");
  const [restrictedClassesText, setRestrictedClassesText] = useState("meme,leverage_token");
  const [riskTierDefaultsText, setRiskTierDefaultsText] = useState('{"tier1":0.1,"tier2":0.05}');

  const selectedKey = `${exchangeCode}:${marketType}:${environment}`;
  const selectedRule = (data?.rules || {})[selectedKey] || null;

  const applyExisting = () => {
    if (!selectedRule) return;
    setSymbolRulesText(formatSymbolRules(selectedRule.symbol_rules));
    setRestrictedClassesText((selectedRule.restricted_symbol_classes || []).join(","));
    setRiskTierDefaultsText(JSON.stringify(selectedRule.risk_tier_defaults || {}, null, 2));
  };

  const applyBulkAction = (action) => {
    const updated = parseSymbolRules(symbolRulesText).map((item) => ({ ...item, action }));
    setSymbolRulesText(formatSymbolRules(updated));
  };

  const savePolicy = async () => {
    let riskTierDefaults = {};
    try {
      riskTierDefaults = JSON.parse(riskTierDefaultsText || "{}");
    } catch {
      toast.error("risk_tier_defaults JSON formatı hatalı");
      return;
    }
    await onSavePolicy({
      exchange_code: exchangeCode,
      market_type: marketType,
      environment,
      symbol_rules: parseSymbolRules(symbolRulesText),
      restricted_symbol_classes: String(restrictedClassesText || "")
        .split(",")
        .map((item) => item.trim().toLowerCase())
        .filter(Boolean),
      risk_tier_defaults: riskTierDefaults,
    });
  };

  return (
    <section className="rounded-2xl border border-slate-700 bg-slate-950/70 p-4" data-testid="market-policy-panel">
      <div className="mb-3 flex items-center justify-between gap-3">
        <div>
          <h3 className="text-base font-semibold text-orange-200" data-testid="market-policy-panel-title">Market Policy Layer</h3>
          <p className="text-xs text-slate-400" data-testid="market-policy-panel-subtitle">Symbol allow/deny, risk tier, sınıf kısıtları ve bulk aksiyon</p>
        </div>
        <div className="flex gap-2">
          <Button type="button" variant="outline" onClick={onRefresh} data-testid="market-policy-refresh-button">Yenile</Button>
          <Button type="button" variant="outline" onClick={applyExisting} data-testid="market-policy-apply-existing-button">Mevcut Kuralı Yükle</Button>
        </div>
      </div>

      <div className="mb-3 grid gap-2 md:grid-cols-3" data-testid="market-policy-selector-grid">
        <select value={exchangeCode} onChange={(event) => setExchangeCode(event.target.value)} className="rounded-md border border-slate-700 bg-slate-900 px-2 py-2 text-sm" data-testid="market-policy-exchange-select">
          {(exchangeOptions.length ? exchangeOptions : ["binance"]).map((code) => (
            <option key={code} value={code}>{code}</option>
          ))}
        </select>
        <select value={marketType} onChange={(event) => setMarketType(event.target.value)} className="rounded-md border border-slate-700 bg-slate-900 px-2 py-2 text-sm" data-testid="market-policy-market-type-select">
          <option value="spot">spot</option>
          <option value="futures">futures</option>
        </select>
        <select value={environment} onChange={(event) => setEnvironment(event.target.value)} className="rounded-md border border-slate-700 bg-slate-900 px-2 py-2 text-sm" data-testid="market-policy-environment-select">
          <option value="live">live</option>
          <option value="live">live</option>
        </select>
      </div>

      <div className="mb-2 flex gap-2" data-testid="market-policy-bulk-actions-row">
        <Button type="button" variant="outline" onClick={() => applyBulkAction("allow")} data-testid="market-policy-bulk-allow-button">Bulk Allow</Button>
        <Button type="button" variant="outline" onClick={() => applyBulkAction("deny")} data-testid="market-policy-bulk-deny-button">Bulk Deny</Button>
        <Button type="button" onClick={savePolicy} data-testid="market-policy-save-button">Policy Kaydet</Button>
      </div>

      <Textarea value={symbolRulesText} onChange={(event) => setSymbolRulesText(event.target.value)} className="mb-2 min-h-28 text-xs" data-testid="market-policy-symbol-rules-textarea" />
      <Input value={restrictedClassesText} onChange={(event) => setRestrictedClassesText(event.target.value)} className="mb-2" placeholder="meme,leverage_token" data-testid="market-policy-restricted-classes-input" />
      <Textarea value={riskTierDefaultsText} onChange={(event) => setRiskTierDefaultsText(event.target.value)} className="min-h-20 text-xs" data-testid="market-policy-risk-tier-defaults-textarea" />

      {loading && <p className="mt-2 text-sm text-slate-400" data-testid="market-policy-loading-state">Yükleniyor...</p>}
      {!loading && error && <p className="mt-2 text-sm text-red-300" data-testid="market-policy-error-state">{error}</p>}
      {!loading && !error && !selectedRule && (
        <p className="mt-2 text-sm text-slate-400" data-testid="market-policy-empty-state">Seçili anahtar için policy kaydı yok.</p>
      )}
      {!loading && !error && selectedRule && (
        <p className="mt-2 text-xs text-slate-300" data-testid="market-policy-existing-summary">Mevcut policy bulundu: {(selectedRule.symbol_rules || []).length} symbol_rule</p>
      )}
    </section>
  );
};
