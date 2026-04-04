import { useEffect, useMemo, useState } from "react";
import { useLocation, useNavigate } from "react-router-dom";
import { toast } from "sonner";

import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { apiClient } from "@/lib/api";

const STEP_LIST = [
  { id: 1, title: "Strateji Seç/Kur" },
  { id: 2, title: "Bot Ayarla" },
  { id: 3, title: "Onayla ve Başlat" },
];

const ERROR_TRANSLATION_MAP = {
  ORDER_PRECHECK_FAILED: "Cüzdan bakiyesi yetersiz",
  API_PERMISSION_DENIED: "Borsa API izni geçersiz veya eksik",
  MIN_NOTIONAL_ERROR: "İşlem tutarı borsa limitinin altında",
  NETWORK_TIMEOUT: "Borsa ağına ulaşılamadı, tekrar deneniyor",
  INVALID_STRATEGY_PARAMS: "Strateji kuralları geçersiz, parametreleri kontrol edin",
};

const FALLBACK_READY_STRATEGY_NAMES = [
  "Trend Follower",
  "Mean Reversion",
  "Volatility Breakout",
  "Low Vol Scalping",
  "Momentum Ignition",
  "Range Rotation",
  "Orderflow Imbalance",
  "Volume Profile Reclaim",
  "Funding Carry",
  "Basis Arbitrage",
  "News Sentiment Reaction",
  "MACD Trend Catch",
];

const defaultCustomBuilder = {
  name: "Özel Stratejim",
  timeframe: "15m",
  ema_fast: 20,
  ema_slow: 50,
  rsi_low: 30,
  rsi_high: 70,
  macd_fast: 12,
  macd_slow: 26,
  macd_signal: 9,
  bb_period: 20,
  bb_std: 2,
  adx_min: 20,
};

const toFriendlyError = (error, fallback = "İşlem başarısız") => {
  const detail = error?.response?.data?.detail;
  const text = typeof detail === "string" ? detail : JSON.stringify(detail || "");
  const upper = String(text || "").toUpperCase();

  if (upper.includes("ORDER_PRECHECK_FAILED") || upper.includes("INSUFFICIENT") || upper.includes("BALANCE")) {
    return ERROR_TRANSLATION_MAP.ORDER_PRECHECK_FAILED;
  }
  if (upper.includes("PERMISSION") || upper.includes("API_PERMISSION_DENIED") || upper.includes("TRADE_DISABLED")) {
    return ERROR_TRANSLATION_MAP.API_PERMISSION_DENIED;
  }
  if (upper.includes("MIN_NOTIONAL") || upper.includes("NOTIONAL")) {
    return ERROR_TRANSLATION_MAP.MIN_NOTIONAL_ERROR;
  }
  if (upper.includes("TIMEOUT") || upper.includes("NETWORK") || upper.includes("ECONN")) {
    return ERROR_TRANSLATION_MAP.NETWORK_TIMEOUT;
  }
  if (upper.includes("INVALID_STRATEGY") || upper.includes("STRATEGY") || upper.includes("PARAM")) {
    return ERROR_TRANSLATION_MAP.INVALID_STRATEGY_PARAMS;
  }
  return fallback;
};

const toActiveReadyTemplates = (items = []) => {
  const latestByCode = new Map();
  for (const item of items || []) {
    const state = String(item?.lifecycle_state || "").toUpperCase();
    if (!(state === "ACTIVE" || item?.is_active)) continue;
    const key = String(item?.template_code || item?.id || "");
    const prev = latestByCode.get(key);
    if (!prev || Number(item.version_num || 0) >= Number(prev.version_num || 0)) {
      latestByCode.set(key, item);
    }
  }
  return Array.from(latestByCode.values()).slice(0, 12);
};

const readStepFromSearch = (search) => {
  const params = new URLSearchParams(search || "");
  const parsed = Number(params.get("step") || 1);
  if (Number.isNaN(parsed)) return 1;
  return Math.max(1, Math.min(3, parsed));
};

export default function UserStrategyBotWizardPage() {
  const location = useLocation();
  const navigate = useNavigate();

  const [step, setStep] = useState(() => readStepFromSearch(location.search));
  const [loading, setLoading] = useState(true);
  const [strategyMode, setStrategyMode] = useState("ready");
  const [allTemplates, setAllTemplates] = useState([]);
  const [selectedReadyTemplateId, setSelectedReadyTemplateId] = useState("");
  const [readyStrategyOverrides, setReadyStrategyOverrides] = useState({});
  const [customBuilder, setCustomBuilder] = useState(defaultCustomBuilder);
  const [savedCustomTemplate, setSavedCustomTemplate] = useState(null);
  const [exchangeConnections, setExchangeConnections] = useState([]);
  const [botForm, setBotForm] = useState({
    bot_name: "",
    exchange_connection_id: "",
    symbols: "BTCUSDT,ETHUSDT",
    budget_usdt: "500",
  });
  const [createdBot, setCreatedBot] = useState(null);
  const [humanLogStatus, setHumanLogStatus] = useState("Strateji seçimi bekleniyor");
  const [humanLogEvents, setHumanLogEvents] = useState([]);
  const [starting, setStarting] = useState(false);

  const readyTemplates = useMemo(() => {
    const active = toActiveReadyTemplates(allTemplates);
    if (active.length > 0) return active;
    return FALLBACK_READY_STRATEGY_NAMES.map((name, idx) => ({
      id: `fallback-${idx}`,
      name,
      strategy_type: "trend_following",
      template_code: `fallback_${idx}`,
      version_num: 1,
      parameters: { rsi_low: 30, rsi_high: 70 },
      indicator_schema: { timeframe: "15m", params: { rsi_low: 30, rsi_high: 70 } },
      logic_schema: {
        entry_rules: { long_condition: "ema_fast > ema_slow", threshold: 0 },
        exit_rules: { stop_loss_pct: 1.5, take_profit_pct: 2.5, exit_condition: "ema_fast < ema_slow" },
        risk_hints: { position_size_hint_pct: 1.5, max_exposure_hint_pct: 20 },
      },
    }));
  }, [allTemplates]);

  const selectedReadyTemplate = useMemo(
    () => readyTemplates.find((item) => item.id === selectedReadyTemplateId) || null,
    [readyTemplates, selectedReadyTemplateId],
  );

  const editableReadyParams = useMemo(() => {
    if (!selectedReadyTemplate) return {};
    return {
      ...(selectedReadyTemplate.parameters || {}),
      ...((selectedReadyTemplate.indicator_schema || {}).params || {}),
      ...(readyStrategyOverrides[selectedReadyTemplate.id] || {}),
    };
  }, [selectedReadyTemplate, readyStrategyOverrides]);

  useEffect(() => {
    const nextStep = readStepFromSearch(location.search);
    setStep(nextStep);
  }, [location.search]);

  useEffect(() => {
    const load = async () => {
      setLoading(true);
      try {
        const [templatesRes, exchangeRes] = await Promise.all([
          apiClient.get("/strategy-templates"),
          apiClient.get("/user/exchange-connections"),
        ]);
        const templateItems = templatesRes.data || [];
        const connectionItems = exchangeRes.data || [];
        setAllTemplates(templateItems);
        setExchangeConnections(connectionItems);

        const active = toActiveReadyTemplates(templateItems);
        if (active[0]?.id) {
          setSelectedReadyTemplateId(active[0].id);
        }
        if (connectionItems[0]?.id) {
          setBotForm((prev) => ({ ...prev, exchange_connection_id: connectionItems[0].id }));
        }
      } catch (error) {
        toast.error(toFriendlyError(error, "Sihirbaz verileri yüklenemedi"));
      } finally {
        setLoading(false);
      }
    };
    load();
  }, []);

  const goStep = (nextStep) => {
    const clamped = Math.max(1, Math.min(3, Number(nextStep || 1)));
    setStep(clamped);
    navigate(`/user/strategies?step=${clamped}`, { replace: false });
  };

  const handleReadyParamChange = (key, value) => {
    if (!selectedReadyTemplateId) return;
    setReadyStrategyOverrides((prev) => ({
      ...prev,
      [selectedReadyTemplateId]: {
        ...(prev[selectedReadyTemplateId] || {}),
        [key]: value,
      },
    }));
  };

  const createUserTemplate = async (payload) => {
    const { data } = await apiClient.post("/user/strategy-templates", payload);
    return data;
  };

  const ensureSelectedTemplate = async () => {
    if (strategyMode === "custom") {
      if (savedCustomTemplate?.id) return savedCustomTemplate;
      const payload = {
        name: customBuilder.name,
        strategy_type: "custom_logic",
        indicator_schema: {
          indicators: ["ema", "rsi", "macd", "bb", "adx"],
          timeframe: customBuilder.timeframe,
          params: {
            ema_fast: Number(customBuilder.ema_fast),
            ema_slow: Number(customBuilder.ema_slow),
            rsi_low: Number(customBuilder.rsi_low),
            rsi_high: Number(customBuilder.rsi_high),
            macd_fast: Number(customBuilder.macd_fast),
            macd_slow: Number(customBuilder.macd_slow),
            macd_signal: Number(customBuilder.macd_signal),
            bb_period: Number(customBuilder.bb_period),
            bb_std: Number(customBuilder.bb_std),
            adx_min: Number(customBuilder.adx_min),
          },
        },
        param_schema: {
          ema_fast: { type: "int", default: Number(customBuilder.ema_fast) },
          ema_slow: { type: "int", default: Number(customBuilder.ema_slow) },
          rsi_low: { type: "int", default: Number(customBuilder.rsi_low) },
          rsi_high: { type: "int", default: Number(customBuilder.rsi_high) },
          macd_fast: { type: "int", default: Number(customBuilder.macd_fast) },
          macd_slow: { type: "int", default: Number(customBuilder.macd_slow) },
          bb_period: { type: "int", default: Number(customBuilder.bb_period) },
          adx_min: { type: "int", default: Number(customBuilder.adx_min) },
        },
        logic_schema: {
          entry_rules: { long_condition: "ema_fast > ema_slow AND rsi_low < rsi_high AND adx > adx_min", threshold: 0 },
          exit_rules: { stop_loss_pct: 1.5, take_profit_pct: 3.0, exit_condition: "ema_fast < ema_slow" },
          risk_hints: { position_size_hint_pct: 2.0, max_exposure_hint_pct: 20.0 },
        },
        parameters: {
          ema_fast: Number(customBuilder.ema_fast),
          ema_slow: Number(customBuilder.ema_slow),
          rsi_low: Number(customBuilder.rsi_low),
          rsi_high: Number(customBuilder.rsi_high),
          macd_fast: Number(customBuilder.macd_fast),
          macd_slow: Number(customBuilder.macd_slow),
          bb_period: Number(customBuilder.bb_period),
          adx_min: Number(customBuilder.adx_min),
        },
        reason_note: "wizard_custom_builder",
      };
      const template = await createUserTemplate(payload);
      setSavedCustomTemplate(template);
      toast.success("Özel strateji şablonu kaydedildi");
      return template;
    }

    if (!selectedReadyTemplate) {
      throw new Error("READY_TEMPLATE_REQUIRED");
    }

    const overrides = readyStrategyOverrides[selectedReadyTemplate.id] || {};
    if (!Object.keys(overrides).length || String(selectedReadyTemplate.id || "").startsWith("fallback-")) {
      return selectedReadyTemplate;
    }

    const mergedParams = {
      ...(selectedReadyTemplate.parameters || {}),
      ...((selectedReadyTemplate.indicator_schema || {}).params || {}),
      ...overrides,
    };
    const payload = {
      name: `${selectedReadyTemplate.name} - Özel`,
      strategy_type: selectedReadyTemplate.strategy_type,
      indicator_schema: {
        ...(selectedReadyTemplate.indicator_schema || {}),
        params: mergedParams,
      },
      param_schema: selectedReadyTemplate.param_schema || {},
      logic_schema: selectedReadyTemplate.logic_schema || {},
      parameters: mergedParams,
      reason_note: "wizard_ready_override",
    };
    const template = await createUserTemplate(payload);
    toast.success("Hazır strateji, yeni şablon olarak özelleştirildi");
    return template;
  };

  const selectedConnection = useMemo(
    () => exchangeConnections.find((item) => item.id === botForm.exchange_connection_id) || null,
    [exchangeConnections, botForm.exchange_connection_id],
  );

  const runBotStart = async () => {
    if (!botForm.bot_name.trim()) {
      toast.error("Bot adı zorunlu");
      return;
    }
    if (!botForm.exchange_connection_id) {
      toast.error("Önce borsa/cüzdan seçin");
      return;
    }
    setStarting(true);
    try {
      const attachedTemplate = await ensureSelectedTemplate();
      if (!attachedTemplate?.id) {
        throw new Error("INVALID_STRATEGY_PARAMS");
      }

      const symbols = String(botForm.symbols || "BTCUSDT")
        .split(",")
        .map((value) => value.trim().toUpperCase())
        .filter(Boolean);

      const payload = {
        name: botForm.bot_name.trim(),
        exchange: selectedConnection?.exchange || "binance",
        market_type: selectedConnection?.market_type || "spot",
        symbol_source_type: "manual",
        scanner_id: null,
        symbols: symbols.length ? symbols : ["BTCUSDT"],
        strategy_type: attachedTemplate.strategy_type || "trend_following",
        strategy_template_id: attachedTemplate.id,
        strategy_template_ids: [attachedTemplate.id],
        timeframe: (attachedTemplate.indicator_schema || {}).timeframe || "15m",
        trend_timeframe: "1h",
        mode: "live_ready_disabled",
        leverage: 1,
        is_enabled: true,
        risk_adaptive_confirmed: false,
      };

      const { data } = await apiClient.post("/bot-profiles", payload);
      await apiClient.post(`/bot-profiles/${data.id}/start`);
      const logsRes = await apiClient.get(`/bot-profiles/${data.id}/logs`).catch(() => ({ data: [] }));
      const mappedEvents = (logsRes.data || []).slice(0, 5).map((item) => {
        const raw = String(item?.event || item?.message || item?.action || "").toUpperCase();
        if (raw.includes("BUY") || raw.includes("LONG") || raw.includes("FILLED")) return "Alındı";
        if (raw.includes("SELL") || raw.includes("SHORT")) return "Satıldı";
        return "Bekleniyor";
      });
      setCreatedBot(data);
      setHumanLogStatus("Stratejiye göre alım noktası bekleniyor");
      setHumanLogEvents(mappedEvents.length ? mappedEvents : ["Bekleniyor"]);
      toast.success("Bot başlatıldı");
    } catch (error) {
      toast.error(toFriendlyError(error, "Bot başlatılamadı"));
      setHumanLogStatus("Borsa bağlantısı veya bakiye kontrolü bekleniyor");
      setHumanLogEvents(["Bekleniyor"]);
    } finally {
      setStarting(false);
    }
  };

  return (
    <section className="mx-auto w-full max-w-6xl space-y-6 p-4 sm:p-6" data-testid="strategy-bot-wizard-page">
      <header className="rounded-xl border border-slate-200 bg-white p-5" data-testid="strategy-bot-wizard-header">
        <div className="flex flex-wrap items-start justify-between gap-3">
          <div>
            <p className="text-xs font-semibold uppercase tracking-[0.2em] text-slate-500" data-testid="strategy-bot-wizard-label">Wizard Mod</p>
            <h1 className="text-4xl font-black tracking-tight text-slate-900" data-testid="strategy-bot-wizard-title">Strateji → Bot → Başlat</h1>
            <p className="mt-2 text-sm text-slate-600" data-testid="strategy-bot-wizard-subtitle">Karmaşık panel yerine adım adım kurulum. Teknik detaylar profesyonel görünümde.</p>
          </div>
          <Button
            type="button"
            variant="outline"
            onClick={() => navigate(step === 2 ? "/user/pro-bot-profiles" : "/user/pro-strategies")}
            data-testid="strategy-bot-wizard-professional-view-button"
          >
            Profesyonel Görünüm
          </Button>
        </div>
        <div className="mt-4 grid gap-2 sm:grid-cols-3" data-testid="strategy-bot-wizard-stepper-grid">
          {STEP_LIST.map((item) => (
            <button
              key={item.id}
              type="button"
              className={`rounded border p-3 text-left transition-all ${step === item.id ? "border-blue-700 bg-blue-50 text-blue-900" : "border-slate-200 bg-slate-50 text-slate-600"}`}
              onClick={() => goStep(item.id)}
              data-testid={`strategy-bot-wizard-step-${item.id}`}
            >
              <p className="text-xs font-bold uppercase tracking-[0.18em]">Adım {item.id}</p>
              <p className="mt-1 text-sm font-semibold">{item.title}</p>
            </button>
          ))}
        </div>
      </header>

      {loading && <p className="text-sm text-slate-500" data-testid="strategy-bot-wizard-loading">Yükleniyor...</p>}

      {!loading && step === 1 && (
        <section className="rounded-xl border border-slate-200 bg-white p-5" data-testid="wizard-step-strategy">
          <div className="flex flex-wrap gap-2" data-testid="wizard-strategy-mode-toggle-row">
            <Button type="button" variant={strategyMode === "ready" ? "default" : "outline"} onClick={() => setStrategyMode("ready")} data-testid="wizard-strategy-mode-ready-button">12 Hazır Strateji</Button>
            <Button type="button" variant={strategyMode === "custom" ? "default" : "outline"} onClick={() => setStrategyMode("custom")} data-testid="wizard-strategy-mode-custom-button">Kendi Stratejini Yap</Button>
          </div>

          {strategyMode === "ready" ? (
            <>
              <div className="mt-4 grid gap-3 sm:grid-cols-2 lg:grid-cols-3" data-testid="wizard-ready-strategy-grid">
                {readyTemplates.map((item, idx) => (
                  <button
                    key={item.id}
                    type="button"
                    className={`rounded border p-3 text-left transition-all hover:-translate-y-0.5 ${selectedReadyTemplateId === item.id ? "border-blue-700 bg-blue-50" : "border-slate-200 bg-slate-50"}`}
                    onClick={() => setSelectedReadyTemplateId(item.id)}
                    data-testid={`wizard-ready-strategy-card-${idx}`}
                  >
                    <p className="text-sm font-semibold text-slate-900">{item.name}</p>
                    <p className="mt-1 text-xs text-slate-600">{item.strategy_type}</p>
                  </button>
                ))}
              </div>

              {selectedReadyTemplate && (
                <div className="mt-4 rounded-lg border border-slate-200 bg-slate-50 p-4" data-testid="wizard-ready-strategy-override-panel">
                  <p className="text-sm font-semibold text-slate-800" data-testid="wizard-ready-strategy-override-title">Parametreleri Düzenle</p>
                  <div className="mt-3 grid gap-3 sm:grid-cols-2" data-testid="wizard-ready-strategy-override-grid">
                    {Object.entries(editableReadyParams).slice(0, 8).map(([key, value]) => (
                      <label key={key} className="space-y-1" data-testid={`wizard-ready-param-field-${key}`}>
                        <span className="text-xs font-semibold uppercase tracking-wide text-slate-500">{key}</span>
                        <Input value={String(value ?? "")} onChange={(event) => handleReadyParamChange(key, event.target.value)} data-testid={`wizard-ready-param-input-${key}`} />
                      </label>
                    ))}
                  </div>
                </div>
              )}
            </>
          ) : (
            <div className="mt-4 grid gap-3 sm:grid-cols-2 lg:grid-cols-3" data-testid="wizard-custom-builder-grid">
              {Object.entries(customBuilder).map(([key, value]) => (
                <label key={key} className="space-y-1" data-testid={`wizard-custom-builder-field-${key}`}>
                  <span className="text-xs font-semibold uppercase tracking-wide text-slate-500">{key}</span>
                  <Input value={String(value)} onChange={(event) => setCustomBuilder((prev) => ({ ...prev, [key]: event.target.value }))} data-testid={`wizard-custom-builder-input-${key}`} />
                </label>
              ))}
            </div>
          )}

          <div className="mt-5 flex flex-wrap gap-2" data-testid="wizard-step1-actions-row">
            <Button type="button" onClick={() => goStep(2)} data-testid="wizard-step1-next-button">Bot Ayarla</Button>
          </div>
        </section>
      )}

      {!loading && step === 2 && (
        <section className="rounded-xl border border-slate-200 bg-white p-5" data-testid="wizard-step-bot-config">
          <h2 className="text-xl font-bold text-slate-900" data-testid="wizard-step2-title">Bot Ayarla</h2>
          <div className="mt-4 grid gap-3 sm:grid-cols-2" data-testid="wizard-step2-form-grid">
            <label className="space-y-1" data-testid="wizard-bot-name-field">
              <span className="text-xs font-semibold uppercase tracking-wide text-slate-500">Bot Adı</span>
              <Input value={botForm.bot_name} onChange={(event) => setBotForm((prev) => ({ ...prev, bot_name: event.target.value }))} data-testid="wizard-bot-name-input" />
            </label>
            <label className="space-y-1" data-testid="wizard-bot-budget-field">
              <span className="text-xs font-semibold uppercase tracking-wide text-slate-500">Bütçe (USDT)</span>
              <Input value={botForm.budget_usdt} onChange={(event) => setBotForm((prev) => ({ ...prev, budget_usdt: event.target.value }))} data-testid="wizard-bot-budget-input" />
            </label>
            <label className="space-y-1 sm:col-span-2" data-testid="wizard-bot-connection-field">
              <span className="text-xs font-semibold uppercase tracking-wide text-slate-500">Cüzdan / Borsa</span>
              <select
                className="h-10 w-full rounded border border-slate-300 bg-white px-3"
                value={botForm.exchange_connection_id}
                onChange={(event) => setBotForm((prev) => ({ ...prev, exchange_connection_id: event.target.value }))}
                data-testid="wizard-bot-connection-select"
              >
                <option value="">Bağlantı seçin</option>
                {exchangeConnections.map((item) => (
                  <option key={item.id} value={item.id}>{item.account_label} · {item.exchange} · {item.market_type}</option>
                ))}
              </select>
            </label>
            <label className="space-y-1 sm:col-span-2" data-testid="wizard-bot-symbols-field">
              <span className="text-xs font-semibold uppercase tracking-wide text-slate-500">Semboller</span>
              <Input value={botForm.symbols} onChange={(event) => setBotForm((prev) => ({ ...prev, symbols: event.target.value }))} data-testid="wizard-bot-symbols-input" />
            </label>
          </div>

          <div className="mt-5 flex flex-wrap gap-2" data-testid="wizard-step2-actions-row">
            <Button type="button" variant="outline" onClick={() => goStep(1)} data-testid="wizard-step2-back-button">Geri</Button>
            <Button type="button" onClick={() => goStep(3)} data-testid="wizard-step2-next-button">Onayla</Button>
          </div>
        </section>
      )}

      {!loading && step === 3 && (
        <section className="rounded-xl border border-slate-200 bg-white p-5" data-testid="wizard-step-confirm-start">
          <h2 className="text-xl font-bold text-slate-900" data-testid="wizard-step3-title">Onayla ve Başlat</h2>
          <div className="mt-4 space-y-2 text-sm text-slate-700" data-testid="wizard-step3-summary">
            <p data-testid="wizard-summary-active-strategy">Aktif Strateji: <strong>{strategyMode === "custom" ? (savedCustomTemplate?.name || customBuilder.name) : (selectedReadyTemplate?.name || "Seçilmedi")}</strong></p>
            <p data-testid="wizard-summary-bot-name">Bot Adı: <strong>{botForm.bot_name || "-"}</strong></p>
            <p data-testid="wizard-summary-budget">Bütçe: <strong>{botForm.budget_usdt || "-"} USDT</strong></p>
            <p data-testid="wizard-summary-status">Durum: <strong>{humanLogStatus}</strong></p>
          </div>

          <div className="mt-5 flex flex-wrap gap-2" data-testid="wizard-step3-actions-row">
            <Button type="button" variant="outline" onClick={() => goStep(2)} data-testid="wizard-step3-back-button">Geri</Button>
            <Button type="button" onClick={runBotStart} disabled={starting} data-testid="wizard-step3-start-bot-button">{starting ? "Başlatılıyor..." : "Onayla ve Başlat"}</Button>
          </div>

          {createdBot && (
            <div className="mt-4 rounded border border-emerald-300 bg-emerald-50 p-3 text-sm text-emerald-800" data-testid="wizard-step3-start-success-panel">
              <p data-testid="wizard-step3-start-success-bot">Bot oluşturuldu: {createdBot.name}</p>
              <p data-testid="wizard-step3-start-success-human-log">Temiz log: Stratejiye göre alım noktası bekleniyor.</p>
              <div className="mt-2 flex flex-wrap gap-2" data-testid="wizard-step3-human-events-row">
                {humanLogEvents.map((event, idx) => (
                  <span key={`${event}-${idx}`} className="rounded border border-emerald-300 bg-white px-2 py-1 text-xs" data-testid={`wizard-step3-human-event-${idx}`}>
                    {event}
                  </span>
                ))}
              </div>
            </div>
          )}
        </section>
      )}
    </section>
  );
}
