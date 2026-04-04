import { useEffect, useMemo, useState } from "react";
import { useNavigate } from "react-router-dom";
import { toast } from "sonner";

import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from "@/components/ui/table";
import { SymbolSelectorPanel } from "@/components/SymbolSelectorPanel";
import { apiClient } from "@/lib/api";

const initialForm = {
  name: "",
  exchange: "binance",
  market_type: "spot",
  symbols: "BTCUSDT,ETHUSDT",
  strategy_type: "trend_following",
  mode: "live_ready_disabled",
  symbol_source_type: "manual",
  scanner_id: "",
  timeframe: "15m",
  trend_timeframe: "1h",
  is_enabled: true,
  template_id: "",
  strategy_template_ids: [],
  risk_adaptive_confirmed: false,
};

const STRATEGY_TYPE_OPTIONS = [
  "trend_following",
  "mean_reversion",
  "volatility_breakout",
  "low_vol_scalping",
  "scalping",
  "momentum_ignition",
  "volume_profile_reclaim",
  "range_rotation",
  "funding_rate_carry",
  "basis_arbitrage",
  "orderflow_imbalance",
  "news_sentiment_reaction",
];

const TEMPLATE_BUNDLE_PRESETS = [
  { key: "momentum", label: "Momentum Bundle", strategy_types: ["trend_following", "volatility_breakout", "momentum_ignition"] },
  { key: "neutral", label: "Neutral / Mean-Revert", strategy_types: ["mean_reversion", "range_rotation", "volume_profile_reclaim"] },
  { key: "market_making", label: "Scalp + Flow", strategy_types: ["scalping", "low_vol_scalping", "orderflow_imbalance"] },
  { key: "carry_arb", label: "Carry / Arbitrage", strategy_types: ["funding_rate_carry", "basis_arbitrage"] },
  { key: "event_driven", label: "Event Driven", strategy_types: ["news_sentiment_reaction", "momentum_ignition"] },
];

export const BotProfilesPage = () => {
  const navigate = useNavigate();
  const [items, setItems] = useState([]);
  const [strategyPerformance, setStrategyPerformance] = useState({ items: [] });
  const [userRisk, setUserRisk] = useState(null);
  const [templates, setTemplates] = useState([]);
  const [selectedBot, setSelectedBot] = useState(null);
  const [detailTab, setDetailTab] = useState("overview");
  const [botStatus, setBotStatus] = useState(null);
  const [botPerformance, setBotPerformance] = useState(null);
  const [botLogs, setBotLogs] = useState([]);
  const [botTrades, setBotTrades] = useState([]);
  const [editingId, setEditingId] = useState(null);
  const [deletingBotId, setDeletingBotId] = useState("");
  const [form, setForm] = useState(initialForm);
  const [formErrors, setFormErrors] = useState({});
  const [symbolSource, setSymbolSource] = useState("crypto");
  const [symbolMode, setSymbolMode] = useState("all_market_symbols");
  const [selectedSymbols, setSelectedSymbols] = useState(["BTCUSDT", "ETHUSDT"]);
  const [selectedBundleKey, setSelectedBundleKey] = useState("");

  const parseApiErrorMessage = (error, fallback) => {
    const detail = error?.response?.data?.detail;
    if (Array.isArray(detail)) {
      const text = detail.map((item) => item?.msg || item?.message || "").filter(Boolean).join(", ");
      if (text) return text;
    }
    if (typeof detail === "string" && detail.trim()) {
      return detail;
    }
    if (detail && typeof detail === "object") {
      return detail.message || detail.code || fallback;
    }
    return fallback;
  };

  const fetchItems = async () => {
    try {
      const [profilesRes, strategyPerfRes, templatesRes, riskRes] = await Promise.all([
        apiClient.get("/bot-profiles"),
        apiClient.get("/user/live/strategy-performance", { params: { window: "24h" } }),
        apiClient.get("/strategy-templates"),
        apiClient.get("/user/live/risk"),
      ]);
      const nextItems = profilesRes.data || [];
      setItems(nextItems);
      setStrategyPerformance(strategyPerfRes.data || { items: [] });
      setTemplates(templatesRes.data || []);
      setUserRisk(riskRes.data || null);
      setSelectedBot((prev) => {
        if (!prev?.id) return prev;
        return nextItems.find((item) => item.id === prev.id) || null;
      });
    } catch (error) {
      toast.error(error?.response?.data?.detail || "Bot listesi yüklenemedi");
    }
  };

  const findStrategyParity = (strategyType) => (strategyPerformance?.items || []).find((item) => item.strategy_id === strategyType);

  const strategyLabelMap = useMemo(
    () => ({
      trend_following: "Agresif / Trend Takipçisi",
      mean_reversion: "Muhafazakar / Arbitraj",
      volatility_breakout: "Agresif / Kırılım",
      low_vol_scalping: "Düşük Volatilite / Scalping",
      scalping: "Düşük Volatilite / Scalping",
      momentum_ignition: "Momentum / Ignition",
      volume_profile_reclaim: "Volume Profile / Reclaim",
      range_rotation: "Range Rotation",
      funding_rate_carry: "Funding Carry",
      basis_arbitrage: "Basis Arbitrage",
      orderflow_imbalance: "Orderflow Imbalance",
      news_sentiment_reaction: "News Sentiment",
    }),
    [],
  );

  const strategyRiskFactor = useMemo(
    () => ({
      trend_following: 1.2,
      volatility_breakout: 1.15,
      mean_reversion: 0.8,
      low_vol_scalping: 0.75,
      scalping: 0.8,
      momentum_ignition: 1.1,
      volume_profile_reclaim: 0.9,
      range_rotation: 0.85,
      funding_rate_carry: 0.7,
      basis_arbitrage: 0.65,
      orderflow_imbalance: 1.05,
      news_sentiment_reaction: 1.25,
    }),
    [],
  );

  const activeTemplateOptions = useMemo(() => {
    const latestByCode = new Map();
    for (const item of templates || []) {
      const isActive = String(item?.lifecycle_state || "").toUpperCase() === "ACTIVE";
      if (!isActive) continue;
      const key = String(item.template_code || item.id || "");
      const prev = latestByCode.get(key);
      if (!prev || Number(item.version_num || 0) >= Number(prev.version_num || 0)) {
        latestByCode.set(key, item);
      }
    }
    return Array.from(latestByCode.values())
      .sort((a, b) => Number(b.version_num || 0) - Number(a.version_num || 0))
      .slice(0, 12)
      .map((item) => ({
        id: item.id,
        name: item.name,
        strategy_type: item.strategy_type,
        label: strategyLabelMap[item.strategy_type] || "Nötr / Genel",
      }));
  }, [templates, strategyLabelMap]);

  const selectedBasketTemplates = useMemo(
    () => activeTemplateOptions.filter((item) => (form.strategy_template_ids || []).includes(item.id)),
    [activeTemplateOptions, form.strategy_template_ids],
  );

  const templateBundleOptions = useMemo(() => {
    return TEMPLATE_BUNDLE_PRESETS
      .map((bundle) => {
        const matches = (activeTemplateOptions || []).filter((item) => bundle.strategy_types.includes(item.strategy_type));
        return {
          ...bundle,
          templateIds: matches.map((item) => item.id).slice(0, 12),
          count: matches.length,
        };
      })
      .filter((bundle) => bundle.count > 0);
  }, [activeTemplateOptions]);

  const correlationWarnings = useMemo(() => {
    const types = new Set(selectedBasketTemplates.map((item) => item.strategy_type));
    const warnings = [];
    if (types.has("trend_following") && types.has("mean_reversion")) {
      warnings.push("Trend takip + mean reversion birlikte verimliliği düşürebilir.");
    }
    if (types.has("volatility_breakout") && (types.has("scalping") || types.has("low_vol_scalping"))) {
      warnings.push("Kırılım + düşük volatilite scalping kombinasyonu zıt sinyal üretebilir.");
    }
    return warnings;
  }, [selectedBasketTemplates]);

  const riskAdaptiveRecommendation = useMemo(() => {
    const baseCapital = Number(userRisk?.base_capital || 0);
    const baseRiskPct = Number(userRisk?.risk_per_trade_used || 1);
    if (!selectedBasketTemplates.length) {
      return { recommendedRiskPct: baseRiskPct || 1, recommendedLeverage: 1, note: "Strateji seçimi bekleniyor." };
    }
    const avgFactor =
      selectedBasketTemplates.reduce((acc, item) => acc + Number(strategyRiskFactor[item.strategy_type] || 1), 0) /
      Math.max(1, selectedBasketTemplates.length);
    const recommendedRiskPct = Math.max(0.25, Math.min(5, Number((baseRiskPct * avgFactor).toFixed(2))));
    const baseLeverage = baseCapital >= 10000 ? 2 : 1;
    const recommendedLeverage = Math.max(1, Math.min(10, Math.round(baseLeverage * avgFactor)));
    return {
      recommendedRiskPct,
      recommendedLeverage,
      note: `Bakiyen (${baseCapital || 0}) ve User Risk Policy baz alınarak önerildi.`,
    };
  }, [selectedBasketTemplates, strategyRiskFactor, userRisk?.base_capital, userRisk?.risk_per_trade_used]);

  useEffect(() => {
    const loadDetail = async () => {
      if (!selectedBot?.id) return;
      try {
        const [statusRes, perfRes, logsRes, tradesRes] = await Promise.all([
          apiClient.get(`/bot-profiles/${selectedBot.id}/detail`),
          apiClient.get(`/bot-profiles/${selectedBot.id}/performance`),
          apiClient.get(`/bot-profiles/${selectedBot.id}/logs`),
          apiClient.get(`/bot-profiles/${selectedBot.id}/trades`),
        ]);
        setBotStatus(statusRes.data || null);
        setBotPerformance(perfRes.data || null);
        setBotLogs(logsRes.data || []);
        setBotTrades(tradesRes.data || []);
      } catch (error) {
        toast.error(error?.response?.data?.detail || 'Bot detail yüklenemedi');
      }
    };
    loadDetail();
  }, [selectedBot]);

  const applyTemplate = (templateId) => {
    const template = (activeTemplateOptions || []).find((item) => item.id === templateId);
    if (!template) return;
    setForm((prev) => ({
      ...prev,
      name: prev.name || `${template.name} Bot`,
      strategy_type: template.strategy_type || prev.strategy_type,
      template_id: template.id,
      strategy_template_ids: prev.strategy_template_ids?.length ? prev.strategy_template_ids : [template.id],
    }));
    toast.success("Template bot formuna aktarıldı");
  };

  useEffect(() => {
    fetchItems();
  }, []);

  useEffect(() => {
    if (!activeTemplateOptions.length) return;
    setForm((prev) => {
      if (prev.template_id || (prev.strategy_template_ids || []).length > 0) {
        return prev;
      }
      const first = activeTemplateOptions[0];
      return {
        ...prev,
        template_id: first.id,
        strategy_template_ids: [first.id],
        strategy_type: first.strategy_type || prev.strategy_type,
      };
    });
  }, [activeTemplateOptions]);

  const handleSubmit = async (event) => {
    event.preventDefault();

    const parsedSymbols = (selectedSymbols || []).length
      ? selectedSymbols
      : form.symbols
          .split(",")
          .map((value) => value.trim().toUpperCase())
          .filter(Boolean);
    const nextErrors = {};

    if (!form.name.trim()) {
      nextErrors.name = "Bot Name zorunludur.";
    }
    if (parsedSymbols.length === 0) {
      nextErrors.symbols = "En az bir sembol girin.";
    }
    if (String(form.symbol_source_type || "manual") === "scanner" && !String(form.scanner_id || "").trim()) {
      nextErrors.scanner_id = "Scanner source için scanner_id zorunlu.";
    }
    if (!(form.template_id || (form.strategy_template_ids || []).length > 0)) {
      nextErrors.template_id = "En az bir aktif template seçin.";
    }
    setFormErrors(nextErrors);
    if (Object.keys(nextErrors).length > 0) {
      toast.error("Form alanlarını kontrol edin");
      return;
    }

    const payload = {
      name: form.name.trim(),
      exchange: form.exchange,
      market_type: form.market_type,
      symbol_source_type: form.symbol_source_type || 'manual',
      scanner_id: form.symbol_source_type === 'scanner' ? (form.scanner_id || null) : null,
      symbols: parsedSymbols,
      strategy_type: form.strategy_type,
      strategy_template_id: form.template_id || (form.strategy_template_ids?.[0] || null),
      strategy_template_ids: form.strategy_template_ids || [],
      timeframe: form.timeframe,
      trend_timeframe: form.trend_timeframe,
      mode: form.mode || "live_ready_disabled",
      leverage: form.risk_adaptive_confirmed ? Number(riskAdaptiveRecommendation.recommendedLeverage || 1) : 1,
      is_enabled: Boolean(form.is_enabled),
      risk_adaptive_confirmed: Boolean(form.risk_adaptive_confirmed),
    };

    try {
      if (editingId) {
        await apiClient.put(`/bot-profiles/${editingId}`, payload);
        toast.success("Bot profili güncellendi");
      } else {
        await apiClient.post("/bot-profiles", payload);
        toast.success("Bot profili oluşturuldu");
      }
      setEditingId(null);
      setForm(initialForm);
      setSelectedBundleKey("");
      setSelectedSymbols(["BTCUSDT", "ETHUSDT"]);
      setSymbolMode("all_market_symbols");
      setFormErrors({});
      fetchItems();
    } catch (error) {
      toast.error(parseApiErrorMessage(error, "Bot profili işlemi başarısız"));
    }
  };

  const onEdit = (item) => {
    setEditingId(item.id);
    setSelectedBundleKey("");
    setForm({
      ...item,
      symbols: (item.symbols || []).join(","),
      mode: item.mode || "live_ready_disabled",
      symbol_source_type: item.symbol_source_type || item.symbol_source || "manual",
      scanner_id: item.scanner_id || item.symbol_source_summary?.scanner_id || "",
      template_id: item.strategy_template_id || item.template_id || "",
      strategy_template_ids: item.strategy_template_ids || (item.strategy_template_id ? [item.strategy_template_id] : []),
      risk_adaptive_confirmed: Boolean(item.risk_adaptive_confirmed),
    });
    setSymbolSource("crypto");
    setSymbolMode("manual_selection");
    setSelectedSymbols(item.symbols || []);
    setFormErrors({});
  };

  const applyTemplateBundle = () => {
    const selectedBundle = templateBundleOptions.find((item) => item.key === selectedBundleKey);
    if (!selectedBundle || (selectedBundle.templateIds || []).length === 0) {
      toast.error("Seçili bundle için aktif template bulunamadı");
      return;
    }
    const firstTemplate = (activeTemplateOptions || []).find((item) => item.id === selectedBundle.templateIds[0]);
    setForm((prev) => ({
      ...prev,
      strategy_template_ids: selectedBundle.templateIds,
      template_id: selectedBundle.templateIds[0] || "",
      strategy_type: firstTemplate?.strategy_type || prev.strategy_type,
    }));
    toast.success(`${selectedBundle.label} uygulandı`);
  };

  const toggleRunning = async (item) => {
    try {
      const endpoint = item.status === "RUNNING" ? "stop" : "start";
      await apiClient.post(`/bot-profiles/${item.id}/${endpoint}`);
      toast.success(endpoint === "stop" ? "Bot durduruldu" : "Bot başlatıldı");
      fetchItems();
    } catch (error) {
      toast.error(error?.response?.data?.detail || "Bot durumu değiştirilemedi");
    }
  };

  const deleteBot = async (item) => {
    if (!window.confirm(`"${item.name}" bot profilini silmek istediğinize emin misiniz?`)) {
      return;
    }

    setDeletingBotId(item.id);
    try {
      await apiClient.delete(`/bot-profiles/${item.id}`);
      if (editingId === item.id) {
        setEditingId(null);
        setForm(initialForm);
        setSelectedSymbols(["BTCUSDT", "ETHUSDT"]);
        setSymbolMode("all_market_symbols");
        setFormErrors({});
      }
      toast.success("Bot profili silindi");
      await fetchItems();
    } catch (error) {
      toast.error(error?.response?.data?.detail || "Bot profili silinemedi");
    } finally {
      setDeletingBotId("");
    }
  };

  return (
    <section className="space-y-4" data-testid="bot-profiles-page">
      <header className="border border-slate-800 bg-slate-900 p-4" data-testid="bot-profiles-header">
        <h2 className="text-4xl font-black uppercase tracking-tight" data-testid="bot-profiles-title">Bot Profile Yönetimi</h2>
        <p className="mt-2 text-sm text-slate-400" data-testid="bot-profiles-description">Create / Update iskeleti hazır. Gerçek trade açılmaz.</p>
        <div className="mt-3">
          <Button type="button" variant="outline" onClick={() => navigate("/user/strategies?step=2")} data-testid="bot-profiles-open-wizard-button">
            Wizard Moduna Dön
          </Button>
        </div>
      </header>

      <form onSubmit={handleSubmit} className="grid gap-3 border border-slate-800 bg-slate-900 p-4 md:grid-cols-2" data-testid="bot-profile-form">
        <div className="form-group" data-testid="bot-form-group-name">
          <label className="form-label" htmlFor="bot-form-name-input" data-testid="bot-form-name-label">Bot Name</label>
          <Input
            id="bot-form-name-input"
            value={form.name}
            onChange={(event) => setForm((prev) => ({ ...prev, name: event.target.value }))}
            data-testid="bot-form-name-input"
            aria-label="Bot Name"
            aria-describedby="bot-form-name-helper bot-form-name-error"
            required
          />
          <p className="form-helper-text" id="bot-form-name-helper" data-testid="bot-form-name-helper">Botu ayırt etmek için benzersiz bir ad girin.</p>
          {formErrors.name && <p className="form-error-text" id="bot-form-name-error" data-testid="bot-form-name-error">{formErrors.name}</p>}
        </div>

        <div className="form-group" data-testid="bot-form-group-exchange">
          <label className="form-label" htmlFor="bot-form-exchange-select" data-testid="bot-form-exchange-label">Exchange</label>
          <select
            id="bot-form-exchange-select"
            value={form.exchange}
            onChange={(event) => setForm((prev) => ({ ...prev, exchange: event.target.value }))}
            className="h-10 w-full rounded-md border border-slate-700 bg-slate-950 px-3 py-2 text-sm"
            data-testid="bot-form-exchange-select"
            aria-label="Exchange"
            aria-describedby="bot-form-exchange-helper"
            required
          >
            <option value="binance">binance</option>
          </select>
          <p className="form-helper-text" id="bot-form-exchange-helper" data-testid="bot-form-exchange-helper">Botun işlem yapacağı borsayı seçin.</p>
        </div>

        <div className="form-group" data-testid="bot-form-group-market-type">
          <label className="form-label" htmlFor="bot-form-market-type-select" data-testid="bot-form-market-type-label">Market Type</label>
          <select
            id="bot-form-market-type-select"
            value={form.market_type}
            onChange={(event) => setForm((prev) => ({ ...prev, market_type: event.target.value }))}
            className="h-10 w-full rounded-md border border-slate-700 bg-slate-950 px-3 py-2 text-sm"
            data-testid="bot-form-market-type-select"
            aria-label="Market Type"
            aria-describedby="bot-form-market-type-helper"
            required
          >
            <option value="spot">spot</option>
            <option value="futures">futures</option>
          </select>
          <p className="form-helper-text" id="bot-form-market-type-helper" data-testid="bot-form-market-type-helper">Spot veya futures işlem tipini belirleyin.</p>
        </div>

        <div className="form-group" data-testid="bot-form-group-symbols">
          <label className="form-label" htmlFor="bot-form-symbols-input" data-testid="bot-form-symbols-label">Symbols</label>
          <SymbolSelectorPanel
            testIdPrefix="bot-form-symbol-selector"
            exchange={form.exchange}
            marketType={form.market_type}
            source={symbolSource}
            onSourceChange={setSymbolSource}
            mode={symbolMode}
            onModeChange={setSymbolMode}
            selectedSymbols={selectedSymbols}
            onSelectedSymbolsChange={setSelectedSymbols}
            multi
          />
          <Input id="bot-form-symbols-input" value={selectedSymbols.join(",")} readOnly data-testid="bot-form-symbols-input" aria-label="Symbols" aria-describedby="bot-form-symbols-helper bot-form-symbols-error" required />
          <p className="form-helper-text" id="bot-form-symbols-helper" data-testid="bot-form-symbols-helper">Select modları: tüm borsa / top 50-100 / custom list + watchlist.</p>
          {formErrors.symbols && <p className="form-error-text" id="bot-form-symbols-error" data-testid="bot-form-symbols-error">{formErrors.symbols}</p>}
        </div>

        <div className="form-group" data-testid="bot-form-group-symbol-source">
          <label className="form-label" htmlFor="bot-form-symbol-source-select" data-testid="bot-form-symbol-source-label">Symbol Source</label>
          <select id="bot-form-symbol-source-select" value={form.symbol_source_type || "manual"} onChange={(event) => setForm((prev) => ({ ...prev, symbol_source_type: event.target.value }))} className="h-10 w-full rounded-md border border-slate-700 bg-slate-950 px-3 py-2 text-sm" data-testid="bot-form-symbol-source-select">
            <option value="manual">manual</option>
            <option value="scanner">scanner</option>
          </select>
          {String(form.symbol_source_type || "manual") === "scanner" && <Input className="mt-2" value={form.scanner_id || ""} onChange={(event) => setForm((prev) => ({ ...prev, scanner_id: event.target.value }))} placeholder="scanner_id" data-testid="bot-form-scanner-id-input" />}
          {formErrors.scanner_id && <p className="form-error-text" data-testid="bot-form-scanner-id-error">{formErrors.scanner_id}</p>}
        </div>

        <div className="form-group" data-testid="bot-form-group-strategy">
          <label className="form-label" htmlFor="bot-form-strategy-select" data-testid="bot-form-strategy-label">Strategy</label>
          <select
            id="bot-form-strategy-select"
            value={form.strategy_type}
            onChange={(event) => setForm((prev) => ({ ...prev, strategy_type: event.target.value }))}
            className="h-10 w-full rounded-md border border-slate-700 bg-slate-950 px-3 py-2 text-sm"
            data-testid="bot-form-strategy-select"
            aria-label="Strategy"
            aria-describedby="bot-form-strategy-helper"
            required
          >
            {STRATEGY_TYPE_OPTIONS.map((item) => (
              <option key={item} value={item}>{item}</option>
            ))}
          </select>
          <p className="form-helper-text" id="bot-form-strategy-helper" data-testid="bot-form-strategy-helper">Botun sinyal üretim metodunu seçin.</p>
        </div>

        <div className="form-group" data-testid="bot-form-group-template">
          <label className="form-label" htmlFor="bot-form-template-select" data-testid="bot-form-template-label">Create from template</label>
          <select
            id="bot-form-template-select"
            value={form.template_id}
            onChange={(event) => {
              const value = event.target.value;
              setForm((prev) => ({ ...prev, template_id: value, strategy_template_ids: value ? [value] : [] }));
              applyTemplate(value);
            }}
            className="h-10 w-full rounded-md border border-slate-700 bg-slate-950 px-3 py-2 text-sm"
            data-testid="bot-form-template-select"
          >
            <option value="">no template</option>
            {(activeTemplateOptions || []).map((item) => (
              <option key={item.id} value={item.id}>{item.name}</option>
            ))}
          </select>
          <p className="form-helper-text" data-testid="bot-form-template-helper">Aktif template’lerden otomatik listelenir (max 12).</p>
          {formErrors.template_id && <p className="form-error-text" data-testid="bot-form-template-error">{formErrors.template_id}</p>}

          <div className="mt-2 flex flex-wrap items-center gap-2" data-testid="bot-form-template-bundle-row">
            <select
              value={selectedBundleKey}
              onChange={(event) => setSelectedBundleKey(event.target.value)}
              className="h-10 min-w-52 rounded-md border border-slate-700 bg-slate-950 px-3 py-2 text-sm"
              data-testid="bot-form-template-bundle-select"
            >
              <option value="">Bundle seç</option>
              {templateBundleOptions.map((bundle) => (
                <option key={bundle.key} value={bundle.key}>
                  {bundle.label} ({bundle.count})
                </option>
              ))}
            </select>
            <Button
              type="button"
              variant="outline"
              onClick={applyTemplateBundle}
              disabled={!selectedBundleKey}
              data-testid="bot-form-template-bundle-apply-button"
            >
              Bundle Uygula
            </Button>
          </div>

          <label className="mt-2 block text-xs text-slate-300" htmlFor="bot-form-template-multi-select" data-testid="bot-form-template-multi-label">
            Basket Mode (çoklu strateji seçimi)
          </label>
          <select
            id="bot-form-template-multi-select"
            multiple
            value={form.strategy_template_ids || []}
            onChange={(event) => {
              const selectedIds = Array.from(event.target.selectedOptions).map((option) => option.value);
              setForm((prev) => ({
                ...prev,
                strategy_template_ids: selectedIds,
                template_id: selectedIds[0] || prev.template_id || "",
              }));
            }}
            className="mt-2 h-28 w-full rounded-md border border-slate-700 bg-slate-950 px-3 py-2 text-sm"
            data-testid="bot-form-template-multi-select"
          >
            {(activeTemplateOptions || []).map((item) => (
              <option key={item.id} value={item.id}>
                {item.name} · {item.label}
              </option>
            ))}
          </select>

          <div className="mt-2 rounded border border-slate-700/60 bg-slate-950/60 p-2" data-testid="bot-form-performance-labeling-box">
            <p className="text-xs text-slate-300" data-testid="bot-form-performance-labeling-title">Performance Labeling</p>
            <div className="mt-1 flex flex-wrap gap-1" data-testid="bot-form-performance-labeling-tags">
              {(selectedBasketTemplates || []).length === 0 ? (
                <span className="text-xs text-slate-500" data-testid="bot-form-performance-labeling-empty">Henüz strateji seçilmedi</span>
              ) : (
                selectedBasketTemplates.map((item) => (
                  <span key={item.id} className="rounded border border-cyan-500/40 bg-cyan-900/20 px-2 py-0.5 text-[11px] text-cyan-200" data-testid={`bot-form-performance-labeling-tag-${item.id}`}>
                    {item.name} · {item.label}
                  </span>
                ))
              )}
            </div>
          </div>

          <div className="mt-2 rounded border border-emerald-600/30 bg-emerald-950/20 p-2" data-testid="bot-form-risk-adaptive-box">
            <p className="text-xs text-emerald-200" data-testid="bot-form-risk-adaptive-title">Risk-Adaptive Scaling</p>
            <p className="mt-1 text-xs text-emerald-100" data-testid="bot-form-risk-adaptive-recommendation">
              Öneri: kaldıraç <strong>{riskAdaptiveRecommendation.recommendedLeverage}x</strong> · risk/trade <strong>%{riskAdaptiveRecommendation.recommendedRiskPct}</strong>
            </p>
            <p className="mt-1 text-[11px] text-emerald-300" data-testid="bot-form-risk-adaptive-note">{riskAdaptiveRecommendation.note}</p>
            <label className="mt-2 inline-flex items-center gap-2 text-xs text-emerald-100" data-testid="bot-form-risk-adaptive-confirm-label">
              <input
                type="checkbox"
                checked={Boolean(form.risk_adaptive_confirmed)}
                onChange={(event) => setForm((prev) => ({ ...prev, risk_adaptive_confirmed: event.target.checked }))}
                data-testid="bot-form-risk-adaptive-confirm-checkbox"
              />
              Bu öneriyi onaylıyorum
            </label>
          </div>

          {correlationWarnings.length > 0 ? (
            <div className="mt-2 rounded border border-amber-500/40 bg-amber-950/20 p-2" data-testid="bot-form-correlation-warning-box">
              <p className="text-xs font-medium text-amber-200" data-testid="bot-form-correlation-warning-title">Combo/Basket Uyarısı</p>
              <ul className="mt-1 list-disc pl-4 text-xs text-amber-100" data-testid="bot-form-correlation-warning-list">
                {correlationWarnings.map((warning, idx) => (
                  <li key={`${warning}-${idx}`} data-testid={`bot-form-correlation-warning-item-${idx}`}>{warning}</li>
                ))}
              </ul>
            </div>
          ) : null}
        </div>

        <div className="form-group" data-testid="bot-form-group-mode">
          <label className="form-label" htmlFor="bot-form-mode-select" data-testid="bot-form-mode-label">Mode</label>
          <select id="bot-form-mode-select" value={form.mode} onChange={(event) => setForm((prev) => ({ ...prev, mode: event.target.value }))} className="h-10 w-full rounded-md border border-slate-700 bg-slate-950 px-3 py-2 text-sm" data-testid="bot-form-mode-select">
            <option value="live_ready_disabled">LIVE-READY (disabled)</option>
            <option value="paper">PAPER</option>
            <option value="mock">MOCK</option>
          </select>
          <p className="form-helper-text" data-testid="bot-form-mode-helper">Bot varsayılan olarak canlıya hazır ama kapalı başlar.</p>
        </div>

        <div className="flex gap-2 md:col-span-2">
          <Button className="bg-orange-500 text-black hover:bg-orange-600" type="submit" data-testid="bot-form-submit-button">
            {editingId ? "Güncelle" : "Oluştur"}
          </Button>
          {editingId && (
            <Button
              type="button"
              variant="outline"
              className="border-slate-700 bg-transparent text-slate-200"
              onClick={() => {
                setEditingId(null);
                setForm(initialForm);
                setSelectedBundleKey("");
                setSelectedSymbols(["BTCUSDT", "ETHUSDT"]);
                setSymbolMode("all_market_symbols");
                setFormErrors({});
              }}
              data-testid="bot-form-cancel-edit-button"
            >
              İptal
            </Button>
          )}
        </div>
      </form>

      <div className="border border-slate-800 bg-slate-900" data-testid="bot-profiles-table-wrapper">
        <Table data-testid="bot-profiles-table">
          <TableHeader>
            <TableRow>
              <TableHead data-testid="bot-table-head-name">Ad</TableHead>
              <TableHead data-testid="bot-table-head-market">Market</TableHead>
              <TableHead data-testid="bot-table-head-strategy">Strateji</TableHead>
              <TableHead data-testid="bot-table-head-parity">Backtest ↔ Live</TableHead>
              <TableHead data-testid="bot-table-head-status">Status</TableHead>
              <TableHead data-testid="bot-table-head-health">Health</TableHead>
              <TableHead data-testid="bot-table-head-mode">Mode</TableHead>
              <TableHead data-testid="bot-table-head-symbols">Semboller</TableHead>
              <TableHead data-testid="bot-table-head-runtime">Runtime</TableHead>
              <TableHead data-testid="bot-table-head-action">Aksiyon</TableHead>
            </TableRow>
          </TableHeader>
          <TableBody>
            {items.map((item) => (
              <TableRow key={item.id} data-testid={`bot-table-row-${item.id}`}>
                {(() => {
                  const parity = findStrategyParity(item.strategy_type);
                  return (
                    <>
                <TableCell data-testid={`bot-table-name-${item.id}`}>{item.name}</TableCell>
                <TableCell data-testid={`bot-table-market-${item.id}`}>{item.market_type}</TableCell>
                <TableCell data-testid={`bot-table-strategy-${item.id}`}>{item.strategy_id || item.strategy_type}</TableCell>
                <TableCell data-testid={`bot-table-parity-${item.id}`}>{parity ? `${parity.backtest?.win_rate ?? 0} / ${parity.live?.win_rate ?? 0} / ${parity.deviation_pct ?? 0}%` : "-"}</TableCell>
                <TableCell data-testid={`bot-table-status-${item.id}`}>{item.status || (item.is_running ? "RUNNING" : "IDLE")}</TableCell>
                <TableCell data-testid={`bot-table-health-${item.id}`}>{item.health || "HEALTHY"}</TableCell>
                <TableCell data-testid={`bot-table-mode-${item.id}`}>{item.mode || "live_ready_disabled"}</TableCell>
                <TableCell className="font-mono text-xs" data-testid={`bot-table-symbols-${item.id}`}>{item.symbol_source_summary?.summary || (item.symbols || []).join(", ")}</TableCell>
                <TableCell data-testid={`bot-table-runtime-${item.id}`}>{item.last_heartbeat || (item.is_running ? "running" : "stopped")}</TableCell>
                <TableCell>
                  <div className="flex flex-wrap gap-2">
                    <Button size="sm" variant="outline" className="border-cyan-400 bg-transparent text-cyan-200" onClick={() => setSelectedBot(item)} data-testid={`bot-table-open-detail-${item.id}`}>Detail</Button>
                    <Button size="sm" variant="outline" className="border-slate-600 bg-transparent" onClick={() => onEdit(item)} data-testid={`bot-table-edit-${item.id}`}>
                      Düzenle
                    </Button>
                    <Button
                      size="sm"
                      variant="outline"
                      className={`bg-transparent ${item.status === "RUNNING" ? "border-red-400 text-red-300" : "border-green-400 text-green-300"}`}
                      onClick={() => toggleRunning(item)}
                      data-testid={`bot-table-toggle-running-${item.id}`}
                    >
                      {item.status === "RUNNING" ? "Stop" : "Start"}
                    </Button>
                    <Button
                      size="sm"
                      variant="outline"
                      className="border-amber-400 bg-transparent text-amber-200"
                      onClick={async () => {
                        try {
                          await apiClient.post(`/bot-profiles/${item.id}/pause`);
                          toast.success('Bot pause edildi');
                          await fetchItems();
                        } catch (error) {
                          toast.error(error?.response?.data?.detail || 'Bot pause işlemi başarısız');
                        }
                      }}
                      data-testid={`bot-table-pause-${item.id}`}
                    >
                      Pause
                    </Button>
                    <Button
                      size="sm"
                      variant="outline"
                      className="border-rose-500 bg-transparent text-rose-300"
                      onClick={() => deleteBot(item)}
                      data-testid={`bot-table-delete-${item.id}`}
                      disabled={deletingBotId === item.id}
                    >
                      {deletingBotId === item.id ? "Siliniyor..." : "Sil"}
                    </Button>
                  </div>
                </TableCell>
                    </>
                  );
                })()}
              </TableRow>
            ))}
          </TableBody>
        </Table>
      </div>

      {selectedBot && (
        <section className="space-y-3 rounded-2xl border border-black/20 bg-white/10 p-4" data-testid="bot-detail-panel">
          <div className="flex flex-wrap items-center justify-between gap-3">
            <div>
              <h3 className="text-xl font-bold text-slate-100" data-testid="bot-detail-title">{selectedBot.name}</h3>
              <p className="text-sm text-slate-300" data-testid="bot-detail-subtitle">{selectedBot.strategy_id || selectedBot.strategy_type} · {selectedBot.mode}</p>
            </div>
            <div className="flex flex-wrap gap-2" data-testid="bot-detail-tabs">
              {['overview','runtime','bindings','performance','logs','trades'].map((tab) => (
                <Button key={tab} size="sm" variant={detailTab === tab ? 'default' : 'outline'} onClick={() => setDetailTab(tab)} data-testid={`bot-detail-tab-${tab}`}>{tab}</Button>
              ))}
            </div>
          </div>
          {detailTab === 'overview' && <pre className="overflow-x-auto rounded-xl border border-black/10 bg-white/70 p-3 text-xs text-black" data-testid="bot-detail-overview-json">{JSON.stringify((botStatus || {}).runtime_summary || selectedBot, null, 2)}</pre>}
          {detailTab === 'overview' && (
            <div className="rounded-xl border border-black/10 bg-white/70 p-3 text-sm text-black" data-testid="bot-detail-strategy-source-card">
              <p className="font-semibold" data-testid="bot-detail-strategy-source-title">Strategy Source</p>
              <p data-testid="bot-detail-strategy-template-name">template: {botStatus?.strategy_binding?.selected_template_code || botStatus?.strategy_binding?.selected_strategy_template_id || '-'}</p>
              <p data-testid="bot-detail-strategy-template-version">version: {botStatus?.strategy_binding?.selected_template_version || '-'}</p>
              <p data-testid="bot-detail-strategy-template-state">state: {botStatus?.strategy_binding?.selected_template_lifecycle_state || '-'}</p>
              <p data-testid="bot-detail-strategy-runtime-id">runtime strategy: {botStatus?.strategy_binding?.effective_runtime_strategy_id || '-'}</p>
              <p data-testid="bot-detail-strategy-lifecycle">compatibility: {botStatus?.compatibility?.parity || '-'}</p>
              <p data-testid="bot-detail-strategy-last-resolved">last_resolved_at: {botStatus?.strategy_binding?.last_resolved_at || '-'}</p>
              <pre className="mt-2 overflow-x-auto bg-white/60 p-2 text-[11px]" data-testid="bot-detail-strategy-effective-config">{JSON.stringify(botStatus?.strategy_binding?.effective_params || {}, null, 2)}</pre>
            </div>
          )}
          {detailTab === 'runtime' && <pre className="overflow-x-auto rounded-xl border border-black/10 bg-white/70 p-3 text-xs text-black" data-testid="bot-detail-runtime-json">{JSON.stringify((botStatus || {}).runtime_summary || {}, null, 2)}</pre>}
          {detailTab === 'bindings' && <pre className="overflow-x-auto rounded-xl border border-black/10 bg-white/70 p-3 text-xs text-black" data-testid="bot-detail-bindings-json">{JSON.stringify({ strategy_binding: botStatus?.strategy_binding, risk_binding: botStatus?.risk_binding, execution_binding: botStatus?.execution_binding, binding_validation: botStatus?.binding_validation, compatibility: botStatus?.compatibility, last_execution_summary: botStatus?.last_execution_summary }, null, 2)}</pre>}
          {detailTab === 'performance' && <pre className="overflow-x-auto rounded-xl border border-black/10 bg-white/70 p-3 text-xs text-black" data-testid="bot-detail-performance-json">{JSON.stringify(botPerformance || {}, null, 2)}</pre>}
          {detailTab === 'logs' && <pre className="overflow-x-auto rounded-xl border border-black/10 bg-white/70 p-3 text-xs text-black" data-testid="bot-detail-logs-json">{JSON.stringify(botLogs || [], null, 2)}</pre>}
          {detailTab === 'trades' && <pre className="overflow-x-auto rounded-xl border border-black/10 bg-white/70 p-3 text-xs text-black" data-testid="bot-detail-trades-json">{JSON.stringify(botTrades || [], null, 2)}</pre>}
        </section>
      )}
    </section>
  );
};
