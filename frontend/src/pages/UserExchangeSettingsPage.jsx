import { useCallback, useEffect, useMemo, useState } from "react";
import { toast } from "sonner";

import { MetricCard } from "@/components/MetricCard";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { apiClient } from "@/lib/api";

const initialForm = {
  exchange: "binance",
  mode: "testnet",
  api_key: "",
  api_secret: "",
};

const fallbackVenue = {
  exchange: "binance",
  market_type: "futures",
  environment: "testnet",
};

const initialFuturesContext = {
  leverage: 3,
  margin_mode: "cross",
  position_side: "BOTH",
};

export const UserExchangeSettingsPage = () => {
  const [activeTab, setActiveTab] = useState("overview");
  const [settings, setSettings] = useState(null);
  const [permission, setPermission] = useState(null);
  const [validateResult, setValidateResult] = useState(null);
  const [readiness, setReadiness] = useState(null);
  const [ticker, setTicker] = useState(null);
  const [latestQuality, setLatestQuality] = useState(null);
  const [form, setForm] = useState(initialForm);
  const [isSaving, setIsSaving] = useState(false);
  const [isValidating, setIsValidating] = useState(false);
  const [isTesting, setIsTesting] = useState(false);
  const [testOrderResult, setTestOrderResult] = useState(null);
  const [lifecycleEvidence, setLifecycleEvidence] = useState(null);
  const [testOrderBanner, setTestOrderBanner] = useState("");
  const [riskSettings, setRiskSettings] = useState(null);
  const [riskPreview, setRiskPreview] = useState(null);
  const [portfolioOverview, setPortfolioOverview] = useState(null);
  const [futuresContext, setFuturesContext] = useState(initialFuturesContext);
  const [venueOptions, setVenueOptions] = useState([]);
  const [selectedVenue, setSelectedVenue] = useState(fallbackVenue);
  const [venueAccess, setVenueAccess] = useState(null);

  const exchangeOptions = useMemo(() => {
    const list = [...new Set(venueOptions.map((item) => item.exchange))];
    return list.length ? list : [fallbackVenue.exchange];
  }, [venueOptions]);

  const marketTypeOptions = useMemo(() => {
    const list = [
      ...new Set(
        venueOptions
          .filter((item) => item.exchange === selectedVenue.exchange)
          .map((item) => item.market_type),
      ),
    ];
    return list.length ? list : [fallbackVenue.market_type];
  }, [selectedVenue.exchange, venueOptions]);

  const environmentOptions = useMemo(() => {
    const list = [
      ...new Set(
        venueOptions
          .filter((item) => item.exchange === selectedVenue.exchange && item.market_type === selectedVenue.market_type)
          .map((item) => item.environment),
      ),
    ];
    return list.length ? list : [fallbackVenue.environment];
  }, [selectedVenue.exchange, selectedVenue.market_type, venueOptions]);

  const loadAll = useCallback(async () => {
    try {
      const [settingsRes, permissionRes, tickerRes, readinessRes, riskRes, overviewRes, venueOptionsRes] = await Promise.all([
        apiClient.get("/phase4/exchange-settings"),
        apiClient.get("/phase4/permission-status"),
        apiClient.get("/market/ticker?symbol=BTCUSDT"),
        apiClient.get("/exchange/readiness-checklist", {
          params: {
            exchange: selectedVenue.exchange,
            market_type: selectedVenue.market_type,
            environment: selectedVenue.environment,
          },
        }),
        apiClient.get("/user-risk/settings"),
        apiClient.get("/user-risk/overview"),
        apiClient.get("/venues/options"),
      ]);
      setSettings(settingsRes.data);
      setPermission(permissionRes.data);
      setTicker(tickerRes.data);
      setReadiness(readinessRes.data);
      setRiskSettings(riskRes.data);
      setPortfolioOverview(overviewRes.data);
      const allowedVenueOptions = (venueOptionsRes.data || []).filter((item) => item.exchange !== "-");
      setVenueOptions(allowedVenueOptions);
      setSelectedVenue((prev) => {
        const previousStillAvailable = allowedVenueOptions.find(
          (item) => item.exchange === prev.exchange && item.market_type === prev.market_type && item.environment === prev.environment,
        );
        if (previousStillAvailable) {
          return prev;
        }
        return allowedVenueOptions[0] || fallbackVenue;
      });
      setForm((prev) => ({
        ...prev,
        exchange: settingsRes.data?.exchange || prev.exchange,
        mode: settingsRes.data?.mode || prev.mode,
      }));
    } catch (error) {
      toast.error(error?.response?.data?.detail || "Exchange ayarları yüklenemedi");
    }

    setLatestQuality((prev) => prev || null);
    setLifecycleEvidence((prev) => prev || null);
  }, [selectedVenue.environment, selectedVenue.exchange, selectedVenue.market_type]);

  useEffect(() => {
    loadAll();
  }, [loadAll]);

  useEffect(() => {
    setForm((prev) => ({
      ...prev,
      exchange: selectedVenue.exchange,
      mode: selectedVenue.environment,
    }));
  }, [selectedVenue.environment, selectedVenue.exchange]);

  useEffect(() => {
    const runAccessCheck = async () => {
      try {
        const { data } = await apiClient.get("/venues/access-check", {
          params: {
            exchange: selectedVenue.exchange,
            market_type: selectedVenue.market_type,
            environment: selectedVenue.environment,
          },
        });
        setVenueAccess(data);
      } catch {
        setVenueAccess(null);
      }
    };
    runAccessCheck();
  }, [selectedVenue.environment, selectedVenue.exchange, selectedVenue.market_type]);

  useEffect(() => {
    const fetchPreview = async () => {
      try {
        const { data } = await apiClient.get("/user-risk/preview", {
          params: {
            market_type: selectedVenue.market_type,
            leverage: futuresContext.leverage,
            margin_mode: futuresContext.margin_mode,
            position_side: futuresContext.position_side,
          },
        });
        setRiskPreview(data);
      } catch (error) {
        toast.error(error?.response?.data?.detail || "Risk preview alınamadı");
      }
    };
    fetchPreview();
  }, [futuresContext.leverage, futuresContext.margin_mode, futuresContext.position_side, selectedVenue.market_type]);

  const onExchangeChange = (nextExchange) => {
    const markets = [
      ...new Set(
        venueOptions.filter((item) => item.exchange === nextExchange).map((item) => item.market_type),
      ),
    ];
    const nextMarket = markets[0] || fallbackVenue.market_type;
    const environments = [
      ...new Set(
        venueOptions
          .filter((item) => item.exchange === nextExchange && item.market_type === nextMarket)
          .map((item) => item.environment),
      ),
    ];
    const nextEnvironment = environments[0] || fallbackVenue.environment;
    setSelectedVenue({ exchange: nextExchange, market_type: nextMarket, environment: nextEnvironment });
  };

  const onMarketTypeChange = (nextMarketType) => {
    const environments = [
      ...new Set(
        venueOptions
          .filter((item) => item.exchange === selectedVenue.exchange && item.market_type === nextMarketType)
          .map((item) => item.environment),
      ),
    ];
    const nextEnvironment = environments[0] || fallbackVenue.environment;
    setSelectedVenue((prev) => ({ ...prev, market_type: nextMarketType, environment: nextEnvironment }));
  };

  const onEnvironmentChange = (nextEnvironment) => {
    setSelectedVenue((prev) => ({ ...prev, environment: nextEnvironment }));
  };

  const saveSettings = async (event) => {
    event.preventDefault();
    setIsSaving(true);
    try {
      const { data } = await apiClient.put("/phase4/exchange-settings", form);
      setSettings(data);
      setForm(() => ({
        ...initialForm,
        exchange: selectedVenue.exchange,
        mode: selectedVenue.environment,
      }));
      toast.success("API key bilgileri şifreli olarak kaydedildi");
      await loadAll();
    } catch (error) {
      toast.error(error?.response?.data?.detail || "Ayarlar kaydedilemedi");
    } finally {
      setIsSaving(false);
    }
  };

  const saveRiskSettings = async () => {
    if (!riskSettings) {
      return;
    }
    try {
      const { data } = await apiClient.put("/user-risk/settings", {
        allocation_pct: Number(riskSettings.allocation_pct),
        trade_risk_pct: Number(riskSettings.trade_risk_pct),
        daily_loss_limit_pct: Number(riskSettings.daily_loss_limit_pct),
        compounding_enabled: Boolean(riskSettings.compounding_enabled),
      });
      setRiskSettings(data);
      toast.success("Risk ayarları kaydedildi");
      await loadAll();
    } catch (error) {
      toast.error(error?.response?.data?.detail || "Risk ayarları kaydedilemedi");
    }
  };

  const runPermission = async () => {
    setIsValidating(true);
    try {
      const { data } = await apiClient.get("/exchange/validate", {
        params: {
          exchange: selectedVenue.exchange,
          market_type: selectedVenue.market_type,
          environment: selectedVenue.environment,
        },
      });
      setValidateResult(data);
      toast.success("Exchange doğrulaması tamamlandı");
      await loadAll();
    } catch (error) {
      const detail = error?.response?.data?.detail;
      setValidateResult(typeof detail === "object" ? detail : null);
      if (typeof detail === "object") {
        const context = [detail.exchange, detail.market_type, detail.environment].filter(Boolean).join("/");
        const reason = Array.isArray(detail.reason_codes) ? detail.reason_codes.join(",") : detail.failure_code || detail.status || "validation_failed";
        setTestOrderBanner(context ? `${context}: ${reason}` : reason);
      }
      toast.error("Exchange doğrulaması başarısız");
    } finally {
      setIsValidating(false);
    }
  };

  const runFirstTestOrder = async () => {
    const venueEligible = selectedVenue.exchange === "binance" && selectedVenue.environment === "testnet";
    if (!venueEligible) {
      setTestOrderBanner("unsupported_venue_for_test_order: İlk kontrollü test emri sadece binance/testnet için açık.");
      toast.error("İlk kontrollü test emri yalnızca binance/testnet için desteklenir");
      return;
    }

    setIsTesting(true);
    setTestOrderBanner("");
    try {
      const { data } = await apiClient.post("/exchange/test-order", null, {
        params: {
          exchange: selectedVenue.exchange,
          market_type: selectedVenue.market_type,
          environment: selectedVenue.environment,
          leverage: futuresContext.leverage,
          margin_mode: futuresContext.margin_mode,
          position_side: futuresContext.position_side,
        },
      });
      setTestOrderResult(data);
      setLatestQuality({
        execution_id: data.order_id,
        symbol: "BTCUSDT",
        status: data.status,
        strategy_type: data.strategy_type,
        volatility_regime: data.volatility_regime,
        volatility_pct: data.volatility_pct,
        expected_price: ticker?.mid_price,
        fill_price: data.price_avg,
        slippage: data.slippage_pct,
        execution_latency: data.execution_time_ms,
        execution_quality_score: data.execution_quality_score,
        timestamp: new Date().toISOString(),
      });
      try {
        const evidenceRes = await apiClient.get("/exchange/lifecycle-evidence/latest");
        setLifecycleEvidence(evidenceRes.data);
      } catch (_) {
        setLifecycleEvidence(null);
      }
      toast.success("İlk kontrollü test emri gönderildi");
      await loadAll();
    } catch (error) {
      const detail = error?.response?.data?.detail;
      if (typeof detail === "object") {
        const context = [detail.exchange, detail.market_type, detail.environment].filter(Boolean).join("/");
        const reason = `${detail.failure_code || "unknown_exchange_error"}: ${detail.message || "awaiting valid key"}`;
        setTestOrderBanner(context ? `${context}: ${reason}` : reason);
      }
      toast.error(typeof detail === "object" ? detail.message : (detail || "Test emri başarısız"));
    } finally {
      setIsTesting(false);
    }
  };

  const readinessTone = readiness?.readiness_status === "ready_for_test_order"
    ? "orange"
    : readiness?.readiness_status === "awaiting_valid_key"
      ? "blue"
      : "red";

  const actionState = isTesting
    ? "executing"
    : isValidating
      ? "validating"
      : testOrderResult?.final_status
        ? "completed"
      : readiness?.readiness_status === "ready_for_test_order"
        ? "ready"
        : readiness?.readiness_status || "blocked";

  const testOrderEligible = selectedVenue.exchange === "binance" && selectedVenue.environment === "testnet";

  return (
    <section className="space-y-4" data-testid="user-exchange-settings-page">
      <header className="border border-slate-800 bg-slate-900 p-4" data-testid="user-exchange-settings-header">
        <h2 className="text-4xl font-black uppercase tracking-tight" data-testid="user-exchange-settings-title">Exchange Settings</h2>
        <p className="mt-2 text-sm text-slate-400" data-testid="user-exchange-settings-description">
          Spot/Futures venue seçimine göre API doğrulama ve test-order akışı. Bilgiler plaintext değil, şifreli saklanır.
        </p>
      </header>

      <div className="flex flex-wrap gap-2" data-testid="user-tabs-nav">
        <Button className={activeTab === "overview" ? "bg-orange-500 text-black" : "bg-slate-800 text-slate-200"} onClick={() => setActiveTab("overview")} data-testid="user-tab-overview-button">Overview</Button>
        <Button className={activeTab === "risk" ? "bg-orange-500 text-black" : "bg-slate-800 text-slate-200"} onClick={() => setActiveTab("risk")} data-testid="user-tab-risk-settings-button">Risk Settings</Button>
        <Button className={activeTab === "test" ? "bg-orange-500 text-black" : "bg-slate-800 text-slate-200"} onClick={() => setActiveTab("test")} data-testid="user-tab-test-validation-button">Test & Validation</Button>
      </div>

      {activeTab === "overview" && (
        <div className="space-y-4" data-testid="user-overview-tab-content">
          <div className="grid gap-3 sm:grid-cols-2 lg:grid-cols-6" data-testid="user-overview-metrics-grid">
            <MetricCard label="Güncel Ana Para" value={portfolioOverview?.current_capital ?? "-"} tone="orange" testId="user-overview-current-capital" />
            <MetricCard label="Kullanılabilir" value={portfolioOverview?.available_balance ?? "-"} tone="blue" testId="user-overview-available-balance" />
            <MetricCard label="Açık Pozisyon" value={portfolioOverview?.open_position_balance ?? "-"} tone="orange" testId="user-overview-open-balance" />
            <MetricCard label="Kapanmış PnL" value={portfolioOverview?.closed_pnl ?? "-"} tone="blue" testId="user-overview-closed-pnl" />
            <MetricCard label="Compounding" value={String(portfolioOverview?.compounding_enabled ?? false)} tone="orange" testId="user-overview-compounding" />
            <MetricCard label="Sonraki Baz" value={portfolioOverview?.next_base_capital ?? "-"} tone="blue" testId="user-overview-next-base" />
          </div>
        </div>
      )}

      {activeTab === "risk" && (
        <div className="space-y-4" data-testid="user-risk-settings-tab-content">
          <div className="grid gap-2 border border-slate-800 bg-slate-900 p-4 md:grid-cols-3" data-testid="user-risk-venue-selection-grid">
            <select value={selectedVenue.exchange} onChange={(event) => onExchangeChange(event.target.value)} className="border border-slate-700 bg-slate-950 px-3 py-2 text-sm" data-testid="user-risk-venue-exchange-select">
              {exchangeOptions.map((item) => (
                <option key={item} value={item}>{item}</option>
              ))}
            </select>
            <select value={selectedVenue.market_type} onChange={(event) => onMarketTypeChange(event.target.value)} className="border border-slate-700 bg-slate-950 px-3 py-2 text-sm" data-testid="user-risk-venue-market-type-select">
              {marketTypeOptions.map((item) => (
                <option key={item} value={item}>{item}</option>
              ))}
            </select>
            <select value={selectedVenue.environment} onChange={(event) => onEnvironmentChange(event.target.value)} className="border border-slate-700 bg-slate-950 px-3 py-2 text-sm" data-testid="user-risk-venue-environment-select">
              {environmentOptions.map((item) => (
                <option key={item} value={item}>{item}</option>
              ))}
            </select>
            <p className="md:col-span-3 text-xs text-slate-400" data-testid="user-risk-selected-venue-summary">Seçili venue: {selectedVenue.exchange} / {selectedVenue.market_type} / {selectedVenue.environment}</p>
            {venueOptions.length === 0 && (
              <p className="md:col-span-3 text-xs text-yellow-300" data-testid="user-risk-no-assignment-warning">Henüz venue assignment yok. Admin panelden kullanıcıya venue atanmalı.</p>
            )}
          </div>

          <div className="grid gap-3 border border-slate-800 bg-slate-900 p-4 md:grid-cols-4" data-testid="user-risk-dual-mode-panel">
            <p className="md:col-span-4 text-xs uppercase tracking-widest text-slate-500" data-testid="user-risk-dual-mode-title">
              Mod: {selectedVenue.market_type === "futures" ? "Futures" : "Spot"}
            </p>

            {selectedVenue.market_type === "futures" && (
              <>
                <Input
                  type="number"
                  min={1}
                  max={20}
                  value={futuresContext.leverage}
                  onChange={(event) => setFuturesContext((prev) => ({ ...prev, leverage: Number(event.target.value) || 1 }))}
                  data-testid="user-futures-leverage-input"
                  placeholder="Leverage"
                />
                <select
                  value={futuresContext.margin_mode}
                  onChange={(event) => setFuturesContext((prev) => ({ ...prev, margin_mode: event.target.value }))}
                  className="border border-slate-700 bg-slate-950 px-3 py-2 text-sm"
                  data-testid="user-futures-margin-mode-select"
                >
                  <option value="cross">cross</option>
                  <option value="isolated">isolated</option>
                </select>
                <select
                  value={futuresContext.position_side}
                  onChange={(event) => setFuturesContext((prev) => ({ ...prev, position_side: event.target.value }))}
                  className="border border-slate-700 bg-slate-950 px-3 py-2 text-sm"
                  data-testid="user-futures-position-side-select"
                >
                  <option value="BOTH">BOTH</option>
                  <option value="LONG">LONG</option>
                  <option value="SHORT">SHORT</option>
                </select>
                <p className="text-sm text-yellow-300" data-testid="user-futures-liquidation-risk-text">
                  liquidation risk: leverage arttıkça likidasyon buffer düşer.
                </p>
              </>
            )}

            {selectedVenue.market_type === "spot" && (
              <p className="md:col-span-4 text-sm text-emerald-300" data-testid="user-spot-fields-hidden-text">
                Spot modda leverage / margin_mode / position_side / liquidation risk alanları gizlenir. Test order quoteQty ile çalışır.
              </p>
            )}
          </div>

          <div className="grid gap-3 border border-slate-800 bg-slate-900 p-4 md:grid-cols-2" data-testid="user-risk-settings-form-grid">
            <Input type="number" min={1} max={50} value={riskSettings?.allocation_pct ?? 20} onChange={(event) => setRiskSettings((prev) => ({ ...(prev || {}), allocation_pct: event.target.value }))} data-testid="user-risk-allocation-input" placeholder="İşleme Ayrılan Ana Para (%)" />
            <Input type="number" min={1} max={25} value={riskSettings?.trade_risk_pct ?? 10} onChange={(event) => setRiskSettings((prev) => ({ ...(prev || {}), trade_risk_pct: event.target.value }))} data-testid="user-risk-trade-risk-input" placeholder="İşlemdeki Paranın Risk Oranı (%)" />
            <Input type="number" min={1} max={10} value={riskSettings?.daily_loss_limit_pct ?? 3} onChange={(event) => setRiskSettings((prev) => ({ ...(prev || {}), daily_loss_limit_pct: event.target.value }))} data-testid="user-risk-daily-loss-input" placeholder="Günlük Zarar Limiti (%)" />
            <label className="flex items-center gap-2 text-sm" data-testid="user-risk-compounding-toggle-row">
              <input type="checkbox" checked={Boolean(riskSettings?.compounding_enabled)} onChange={(event) => setRiskSettings((prev) => ({ ...(prev || {}), compounding_enabled: event.target.checked }))} data-testid="user-risk-compounding-toggle" />
              Kâr/Zararı Ana Paraya Ekle
            </label>
            <Button className="md:col-span-2 bg-orange-500 text-black hover:bg-orange-600" onClick={saveRiskSettings} data-testid="user-risk-save-button">Risk Ayarlarını Kaydet</Button>
          </div>

          <div className="border border-slate-800 bg-slate-900 p-4" data-testid="user-risk-live-preview-card">
            <p className="text-xs uppercase tracking-widest text-slate-500" data-testid="user-risk-live-preview-title">Canlı İşlem Önizlemesi</p>
            <div className="mt-3 grid gap-2 sm:grid-cols-2" data-testid="user-risk-live-preview-grid">
              <p data-testid="user-risk-preview-market-type">Market Type: {riskPreview?.market_type ?? "-"}</p>
              <p data-testid="user-risk-preview-current-capital">Güncel ana para: {riskPreview?.current_capital ?? "-"} USDT</p>
              <p data-testid="user-risk-preview-position-size">Position size: {riskPreview?.position_size ?? "-"} USDT</p>
              <p data-testid="user-risk-preview-risk-amount">Risk amount: {riskPreview?.risk_amount ?? "-"} USDT</p>
              <p data-testid="user-risk-preview-allocation-pct">İşleme ayrılan oran: %{riskPreview?.allocation_pct ?? "-"}</p>
              <p data-testid="user-risk-preview-allocation-amount">İşleme girecek tutar: {riskPreview?.trade_allocation_amount ?? "-"} USDT</p>
              <p data-testid="user-risk-preview-trade-risk-pct">İşlemde risk oranı: %{riskPreview?.trade_risk_pct ?? "-"}</p>
              <p data-testid="user-risk-preview-max-loss">Maksimum bu işlem kaybı: {riskPreview?.max_trade_loss_amount ?? "-"} USDT</p>
              <p data-testid="user-risk-preview-capital-impact">Toplam ana paraya etkisi: %{riskPreview?.total_capital_impact_pct ?? "-"}</p>
              <p data-testid="user-risk-preview-next-base">Sonraki işlem baz hesabı: {riskPreview?.next_trade_base_capital ?? "-"}</p>
              <p data-testid="user-risk-preview-compounding">Compounding: {String(riskPreview?.compounding_enabled ?? false)}</p>

              {selectedVenue.market_type === "futures" && (
                <>
                  <p data-testid="user-risk-preview-futures-leverage">Leverage: x{riskPreview?.leverage ?? "-"}</p>
                  <p data-testid="user-risk-preview-futures-margin-mode">Margin mode: {riskPreview?.margin_mode ?? "-"}</p>
                  <p data-testid="user-risk-preview-futures-position-side">Position side: {riskPreview?.position_side ?? "-"}</p>
                  <p data-testid="user-risk-preview-futures-margin-usage">Margin usage: %{riskPreview?.margin_usage_pct ?? "-"}</p>
                  <p data-testid="user-risk-preview-futures-liquidation-buffer">Estimated liquidation buffer: %{riskPreview?.estimated_liquidation_buffer_pct ?? "-"}</p>
                </>
              )}
            </div>
            <div className="mt-2 space-y-1" data-testid="user-risk-preview-warnings-list">
              {(riskPreview?.warnings || []).map((warning) => (
                <p key={warning} className="text-xs text-yellow-300" data-testid={`user-risk-preview-warning-${warning}`}>High risk configuration: {warning}</p>
              ))}
            </div>
          </div>
        </div>
      )}

      {activeTab === "test" && (
        <div className="space-y-4" data-testid="user-test-validation-tab-content">

      <div className="grid gap-2 border border-slate-800 bg-slate-900 p-4 md:grid-cols-3" data-testid="user-test-venue-selection-grid">
        <select value={selectedVenue.exchange} onChange={(event) => onExchangeChange(event.target.value)} className="border border-slate-700 bg-slate-950 px-3 py-2 text-sm" data-testid="user-test-venue-exchange-select">
          {exchangeOptions.map((item) => (
            <option key={item} value={item}>{item}</option>
          ))}
        </select>
        <select value={selectedVenue.market_type} onChange={(event) => onMarketTypeChange(event.target.value)} className="border border-slate-700 bg-slate-950 px-3 py-2 text-sm" data-testid="user-test-venue-market-type-select">
          {marketTypeOptions.map((item) => (
            <option key={item} value={item}>{item}</option>
          ))}
        </select>
        <select value={selectedVenue.environment} onChange={(event) => onEnvironmentChange(event.target.value)} className="border border-slate-700 bg-slate-950 px-3 py-2 text-sm" data-testid="user-test-venue-environment-select">
          {environmentOptions.map((item) => (
            <option key={item} value={item}>{item}</option>
          ))}
        </select>
        <p className="md:col-span-3 text-xs text-slate-400" data-testid="user-test-selected-venue-summary">Seçili venue: {selectedVenue.exchange} / {selectedVenue.market_type} / {selectedVenue.environment}</p>
        {venueOptions.length === 0 && (
          <p className="md:col-span-3 text-xs text-yellow-300" data-testid="user-test-no-assignment-warning">Henüz venue assignment yok. Admin panelden kullanıcıya venue atanmalı.</p>
        )}
      </div>

      {selectedVenue.market_type === "futures" && (
        <div className="grid gap-2 border border-slate-800 bg-slate-900 p-4 md:grid-cols-3" data-testid="user-test-futures-context-grid">
          <Input type="number" min={1} max={20} value={futuresContext.leverage} onChange={(event) => setFuturesContext((prev) => ({ ...prev, leverage: Number(event.target.value) || 1 }))} data-testid="user-test-futures-leverage-input" placeholder="Leverage" />
          <select value={futuresContext.margin_mode} onChange={(event) => setFuturesContext((prev) => ({ ...prev, margin_mode: event.target.value }))} className="border border-slate-700 bg-slate-950 px-3 py-2 text-sm" data-testid="user-test-futures-margin-mode-select">
            <option value="cross">cross</option>
            <option value="isolated">isolated</option>
          </select>
          <select value={futuresContext.position_side} onChange={(event) => setFuturesContext((prev) => ({ ...prev, position_side: event.target.value }))} className="border border-slate-700 bg-slate-950 px-3 py-2 text-sm" data-testid="user-test-futures-position-side-select">
            <option value="BOTH">BOTH</option>
            <option value="LONG">LONG</option>
            <option value="SHORT">SHORT</option>
          </select>
        </div>
      )}

      {selectedVenue.market_type === "spot" && (
        <div className="border border-slate-800 bg-slate-900 p-4" data-testid="user-test-spot-context-card">
          <p className="text-sm text-emerald-300" data-testid="user-test-spot-quote-qty-text">Spot test order quoteQty=10 USDT semantiği ile gönderilir.</p>
        </div>
      )}

      <div className="grid gap-3 sm:grid-cols-2 lg:grid-cols-5" data-testid="user-exchange-settings-metrics-grid">
        <MetricCard label="Exchange" value={settings?.exchange || "-"} tone="orange" testId="user-exchange-metric-exchange" />
        <MetricCard label="Mode" value={settings?.mode || "-"} tone="orange" testId="user-exchange-metric-mode" />
        <MetricCard label="Permission" value={permission?.overall_status || "-"} tone={permission?.overall_status === "pass" ? "orange" : "red"} testId="user-exchange-metric-permission" />
        <MetricCard label="Live Activation" value={permission?.live_activation || "blocked"} tone={permission?.live_activation === "ready" ? "orange" : "red"} testId="user-exchange-metric-live-activation" />
        <MetricCard label="Execution Quality" value={latestQuality?.execution_quality_score ?? "-"} tone="orange" testId="user-exchange-metric-quality" />
      </div>

      <div className="grid gap-3 sm:grid-cols-4" data-testid="user-exchange-action-state-grid">
        <MetricCard label="Readiness" value={readiness?.readiness_status || "-"} tone={readinessTone} testId="user-exchange-readiness-status" />
        <MetricCard label="Action State" value={actionState} tone={readinessTone} testId="user-exchange-action-state" />
        <MetricCard label="Last Validation" value={readiness?.validation_timestamp || "-"} tone="blue" testId="user-exchange-last-validation-at" />
        <MetricCard label="Last Error" value={readiness?.last_error_reason || "-"} tone="red" testId="user-exchange-last-error-reason" />
      </div>

      <div className="border border-slate-800 bg-slate-900 p-4" data-testid="user-venue-access-panel">
        <p className="text-xs uppercase tracking-widest text-slate-500" data-testid="user-venue-access-title">Venue Access Check</p>
        <p className="mt-2 text-sm text-slate-300" data-testid="user-venue-access-allowed">allowed={String(venueAccess?.allowed ?? false)}</p>
        <p className="mt-1 text-sm text-slate-300" data-testid="user-venue-access-state">venue_state={venueAccess?.venue_state || "-"}</p>
        <p className="mt-1 text-sm text-slate-300" data-testid="user-venue-access-capability">capability_match={String(venueAccess?.capability_match ?? false)}</p>
        <p className="mt-1 text-sm text-slate-300" data-testid="user-venue-access-reasons">reason_codes={(venueAccess?.reason_codes || []).join(",") || "-"}</p>
      </div>

      <div className="grid gap-3 sm:grid-cols-3" data-testid="user-exchange-validate-grid">
        <MetricCard label="Validate is_valid" value={String(validateResult?.is_valid ?? false)} tone={validateResult?.is_valid ? "orange" : "red"} testId="user-exchange-validate-is-valid" />
        <MetricCard label="can_trade" value={String(validateResult?.can_trade ?? false)} tone={validateResult?.can_trade ? "orange" : "red"} testId="user-exchange-validate-can-trade" />
        <MetricCard label="mid_price" value={ticker?.mid_price ?? "-"} tone="blue" testId="user-exchange-mid-price" />
      </div>

      <div className="border border-slate-800 bg-slate-900 p-4" data-testid="user-readiness-checklist-card">
        <p className="text-xs uppercase tracking-widest text-slate-500" data-testid="user-readiness-checklist-title">Readiness Checklist</p>
        <div className="mt-3 grid gap-2 sm:grid-cols-2" data-testid="user-readiness-checklist-grid">
          <p data-testid="user-readiness-has-api-key">API key mevcut: {String(readiness?.has_api_key ?? false)}</p>
          <p data-testid="user-readiness-has-api-secret">Secret mevcut: {String(readiness?.has_api_secret ?? false)}</p>
          <p data-testid="user-readiness-validation-success">Validation başarılı: {String(readiness?.validation_success ?? false)}</p>
          <p data-testid="user-readiness-can-trade">can_trade=true: {String(readiness?.can_trade ?? false)}</p>
          <p data-testid="user-readiness-testnet-env">testnet environment: {String(readiness?.is_testnet_environment ?? false)}</p>
          <p data-testid="user-readiness-validation-stale">snapshot stale: {String(readiness?.is_validation_stale ?? true)}</p>
        </div>
      </div>

      {readiness?.readiness_status === "awaiting_valid_key" && (
        <div className="border border-blue-700 bg-blue-950/20 p-4 text-sm text-blue-200" data-testid="user-readiness-awaiting-valid-key-banner">
          awaiting valid key — Binance Testnet API key ve secret doğrulanmadan gerçek test-order çalıştırılamaz.
        </div>
      )}

      {(testOrderBanner || readiness?.is_validation_stale) && (
        <div className="border border-red-700 bg-red-950/20 p-4 text-sm text-red-200" data-testid="user-readiness-failure-banner">
          {testOrderBanner || "Validation snapshot stale. Lütfen Revalidate yapın."}
        </div>
      )}

      <div className="border border-slate-800 bg-slate-900 p-4" data-testid="user-exchange-quality-regime-panel">
        <p className="text-xs uppercase tracking-widest text-slate-500" data-testid="user-exchange-quality-regime-title">Quality Normalization</p>
        <p className="mt-2 text-sm text-slate-300" data-testid="user-exchange-quality-strategy">strategy={latestQuality?.strategy_type || "-"}</p>
        <p className="mt-1 text-sm text-slate-300" data-testid="user-exchange-quality-volatility-regime">volatility_regime={latestQuality?.volatility_regime || "-"}</p>
        <p className="mt-1 text-sm text-slate-300" data-testid="user-exchange-quality-volatility-pct">volatility_pct={latestQuality?.volatility_pct ?? "-"}</p>
      </div>

      <form className="grid gap-3 border border-slate-800 bg-slate-900 p-4 md:grid-cols-2" onSubmit={saveSettings} data-testid="user-exchange-settings-form">
        <select value={selectedVenue.exchange} onChange={(event) => onExchangeChange(event.target.value)} className="border border-slate-700 bg-slate-950 px-3 py-2 text-sm" data-testid="user-exchange-settings-exchange-select">
          {exchangeOptions.map((item) => (
            <option key={item} value={item}>{item}</option>
          ))}
        </select>
        <select value={selectedVenue.environment} onChange={(event) => onEnvironmentChange(event.target.value)} className="border border-slate-700 bg-slate-950 px-3 py-2 text-sm" data-testid="user-exchange-settings-environment-select">
          {environmentOptions.map((item) => (
            <option key={item} value={item}>{item}</option>
          ))}
        </select>
        <Input value={form.api_key} onChange={(event) => setForm((prev) => ({ ...prev, api_key: event.target.value }))} placeholder="API Key" data-testid="user-exchange-settings-api-key-input" required />
        <Input value={form.api_secret} onChange={(event) => setForm((prev) => ({ ...prev, api_secret: event.target.value }))} placeholder="API Secret" data-testid="user-exchange-settings-api-secret-input" required />
        <Button className="md:col-span-2 bg-orange-500 text-black hover:bg-orange-600" data-testid="user-exchange-settings-save-button" disabled={isSaving}>
          {isSaving ? "Kaydediliyor..." : "API Bilgilerini Kaydet"}
        </Button>
      </form>

      <div className="border border-slate-800 bg-slate-900 p-4" data-testid="user-exchange-actions-panel">
        <div className="flex flex-wrap gap-3" data-testid="user-exchange-actions-buttons">
          <Button className="bg-orange-500 text-black hover:bg-orange-600" onClick={runPermission} data-testid="user-exchange-check-permission-button" disabled={isValidating}>
            {isValidating ? "Validating..." : "Revalidate"}
          </Button>
          <Button
            className="bg-black text-orange-400 hover:bg-zinc-900"
            onClick={runFirstTestOrder}
            data-testid="user-exchange-first-test-order-button"
            disabled={isTesting || readiness?.readiness_status !== "ready_for_test_order" || !testOrderEligible}
          >
            {isTesting ? "Gönderiliyor..." : "İlk Kontrollü Test Emri"}
          </Button>
        </div>

        {!testOrderEligible && (
          <p className="mt-2 text-xs text-yellow-300" data-testid="user-test-order-venue-constraint-text">
            Test order şu an yalnızca binance/testnet kombinasyonu için destekleniyor.
          </p>
        )}

        <div className="mt-4 space-y-1" data-testid="user-exchange-permission-controls-list">
          {(permission?.controls || []).map((item) => (
            <p key={item.key} className="text-xs font-mono text-slate-300" data-testid={`user-exchange-permission-control-${item.key}`}>
              {item.key}: {item.status} ({item.reason})
            </p>
          ))}
          <p className="pt-2 text-xs font-mono text-slate-300" data-testid="user-exchange-validate-permissions-line">
            permissions: {(validateResult?.permissions || []).join(",") || "-"}
          </p>
          <p className="text-xs font-mono text-slate-300" data-testid="user-exchange-validate-reason-codes-line">
            reason_codes: {(validateResult?.reason_codes || []).join(",") || "-"}
          </p>
        </div>
      </div>

      <div className="border border-slate-800 bg-slate-900 p-4" data-testid="user-test-order-result-card">
        <p className="text-xs uppercase tracking-widest text-slate-500" data-testid="user-test-order-result-title">Test Order Result</p>
        <div className="mt-3 grid gap-2 sm:grid-cols-2" data-testid="user-test-order-result-grid">
          <p data-testid="user-test-order-exchange">exchange: {testOrderResult?.exchange || selectedVenue.exchange}</p>
          <p data-testid="user-test-order-market-type">market_type: {testOrderResult?.market_type || selectedVenue.market_type}</p>
          <p data-testid="user-test-order-environment">environment: {testOrderResult?.environment || selectedVenue.environment}</p>
          <p data-testid="user-test-order-status">order status: {testOrderResult?.status || "awaiting_valid_key"}</p>
          <p data-testid="user-test-order-final-status">final status: {testOrderResult?.final_status || "-"}</p>
          <p data-testid="user-test-order-exchange-order-id">exchange order id: {testOrderResult?.exchange_order_id || "-"}</p>
          <p data-testid="user-test-order-client-order-id">client order id: {testOrderResult?.client_order_id || "-"}</p>
          <p data-testid="user-test-order-average-fill-price">average fill price: {testOrderResult?.price_avg ?? "-"}</p>
          <p data-testid="user-test-order-executed-qty">executed quantity: {testOrderResult?.executed_qty ?? "-"}</p>
          <p data-testid="user-test-order-slippage-pct">slippage pct: {testOrderResult?.slippage_pct ?? "-"}</p>
          <p data-testid="user-test-order-execution-time-ms">execution time ms: {testOrderResult?.execution_time_ms ?? "-"}</p>
          <p data-testid="user-test-order-volatility-regime">volatility regime: {testOrderResult?.volatility_regime || "-"}</p>
          <p data-testid="user-test-order-strategy-type">strategy type: {testOrderResult?.strategy_type || "-"}</p>
          <p data-testid="user-test-order-failure-code">failure code: {testOrderResult?.failure_code || "-"}</p>
          <p data-testid="user-test-order-submitted-at">submitted_at: {testOrderResult?.submitted_at || "-"}</p>
          <p data-testid="user-test-order-ack-at">ack_at: {testOrderResult?.ack_at || "-"}</p>
          <p data-testid="user-test-order-final-at">final_at: {testOrderResult?.final_at || "-"}</p>
          <p className="sm:col-span-2" data-testid="user-test-order-validation-timestamp">validation timestamp: {readiness?.validation_timestamp || "-"}</p>
          <p className="sm:col-span-2" data-testid="user-test-order-validation-snapshot-id">validation snapshot id: {readiness?.validation_snapshot_id || "-"}</p>
        </div>
      </div>

      <div className="border border-slate-800 bg-slate-900 p-4" data-testid="user-lifecycle-evidence-panel">
        <p className="text-xs uppercase tracking-widest text-slate-500" data-testid="user-lifecycle-evidence-title">Lifecycle Evidence Timeline</p>
        <div className="mt-3 space-y-2" data-testid="user-lifecycle-evidence-list">
          {(lifecycleEvidence?.timeline || []).map((item, index) => (
            <div key={`${item.event_name}-${index}`} className="border border-slate-700 p-2 text-xs" data-testid={`user-lifecycle-evidence-item-${index}`}>
              {item.event_name} — {item.event_timestamp}
            </div>
          ))}
          {(!lifecycleEvidence || (lifecycleEvidence.timeline || []).length === 0) && (
            <p className="text-xs text-slate-400" data-testid="user-lifecycle-evidence-empty">Henüz lifecycle evidence yok.</p>
          )}
        </div>
      </div>
        </div>
      )}
    </section>
  );
};