import { useEffect, useState } from "react";
import { toast } from "sonner";

import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { SymbolSelectorPanel } from "@/components/SymbolSelectorPanel";
import { apiClient } from "@/lib/api";

const initialForm = {
  max_leverage_cap: 5,
  max_open_positions_cap: 10,
  minimum_volume_usd: 1000000,
  max_spread_bps: 40,
  spot_universe: "",
  futures_universe: "",
  whitelist: "",
  blacklist: "",
  emergency_mode: false,
  disable_futures: false,
};

const csvToList = (value) => value.split(",").map((item) => item.trim().toUpperCase()).filter(Boolean);

export const MarketUniversePage = () => {
  const [form, setForm] = useState(initialForm);
  const [preview, setPreview] = useState(null);
  const [spotSymbols, setSpotSymbols] = useState(["BTCUSDT", "ETHUSDT"]);
  const [futuresSymbols, setFuturesSymbols] = useState(["BTCUSDT", "ETHUSDT"]);
  const [stockSymbols, setStockSymbols] = useState([]);
  const [spotSource, setSpotSource] = useState("crypto");
  const [futuresSource, setFuturesSource] = useState("crypto");
  const [stockSource, setStockSource] = useState("stock");
  const [spotMode, setSpotMode] = useState("all_market_symbols");
  const [futuresMode, setFuturesMode] = useState("all_market_symbols");
  const [stockMode, setStockMode] = useState("manual_selection");
  const [alphaKeyInput, setAlphaKeyInput] = useState("");
  const [providerConfig, setProviderConfig] = useState(null);

  const hydrateProviderConfig = async () => {
    try {
      const { data } = await apiClient.get("/symbol-selector/provider-config");
      setProviderConfig(data || null);
    } catch {
      setProviderConfig(null);
    }
  };

  const hydrate = async () => {
    try {
      const [{ data: control }, { data: nextPreview }] = await Promise.all([
        apiClient.get("/admin-control"),
        apiClient.get("/admin-control/universe/preview"),
      ]);
      setForm({
        ...control,
        spot_universe: control.spot_universe.join(","),
        futures_universe: control.futures_universe.join(","),
        whitelist: control.whitelist.join(","),
        blacklist: control.blacklist.join(","),
      });
      setSpotSymbols(control.spot_universe || []);
      setFuturesSymbols(control.futures_universe || []);
      setPreview(nextPreview);
      await hydrateProviderConfig();
    } catch (error) {
      toast.error(error?.response?.data?.detail || "Universe ayarları yüklenemedi");
    }
  };

  useEffect(() => {
    hydrate();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  useEffect(() => {
    setForm((prev) => ({ ...prev, spot_universe: (spotSymbols || []).join(",") }));
  }, [spotSymbols]);

  useEffect(() => {
    setForm((prev) => ({ ...prev, futures_universe: (futuresSymbols || []).join(",") }));
  }, [futuresSymbols]);

  const submit = async (event) => {
    event.preventDefault();
    try {
      await apiClient.put("/admin-control", {
        max_leverage_cap: Number(form.max_leverage_cap),
        max_open_positions_cap: Number(form.max_open_positions_cap),
        minimum_volume_usd: Number(form.minimum_volume_usd),
        max_spread_bps: Number(form.max_spread_bps),
        spot_universe: (spotSymbols || []).length ? spotSymbols : csvToList(form.spot_universe),
        futures_universe: (futuresSymbols || []).length ? futuresSymbols : csvToList(form.futures_universe),
        whitelist: csvToList(form.whitelist),
        blacklist: csvToList(form.blacklist),
        emergency_mode: form.emergency_mode,
        disable_futures: form.disable_futures,
      });
      toast.success("Market universe kuralları güncellendi");
      hydrate();
    } catch (error) {
      toast.error(error?.response?.data?.detail || "Güncelleme başarısız");
    }
  };

  const saveAlphaKey = async () => {
    if (!alphaKeyInput.trim()) {
      toast.error("Alpha Vantage API key zorunlu");
      return;
    }
    try {
      const { data } = await apiClient.put("/symbol-selector/provider-config/alpha-vantage", { api_key: alphaKeyInput.trim() });
      setProviderConfig(data || null);
      setAlphaKeyInput("");
      toast.success("Alpha Vantage key kaydedildi");
    } catch (error) {
      toast.error(error?.response?.data?.detail || "Alpha Vantage key kaydedilemedi");
    }
  };

  return (
    <section className="space-y-4" data-testid="market-universe-page">
      <header className="border border-blue-900 bg-slate-900 p-4" data-testid="market-universe-header">
        <h2 className="text-4xl font-black uppercase tracking-tight text-blue-300" data-testid="market-universe-title">Market Universe Yönetimi</h2>
        <p className="mt-2 text-sm text-slate-400" data-testid="market-universe-description">Universe geniş tutulur; whitelist sadece geçici kısıt için kullanılır. Hacim/spread filtreleri advisory modda confidence/risk etkisi üretir.</p>
      </header>

      <form onSubmit={submit} className="grid gap-3 border border-slate-800 bg-slate-900 p-4 md:grid-cols-2" data-testid="market-universe-form">
        <Input type="number" value={form.minimum_volume_usd} onChange={(event) => setForm((prev) => ({ ...prev, minimum_volume_usd: event.target.value }))} placeholder="Minimum volume USD" data-testid="universe-min-volume-input" />
        <Input type="number" value={form.max_spread_bps} onChange={(event) => setForm((prev) => ({ ...prev, max_spread_bps: event.target.value }))} placeholder="Max spread bps" data-testid="universe-max-spread-input" />
        <Input value={form.spot_universe} onChange={(event) => setForm((prev) => ({ ...prev, spot_universe: event.target.value }))} placeholder="Spot symbols CSV" data-testid="universe-spot-input" />
        <Input value={form.futures_universe} onChange={(event) => setForm((prev) => ({ ...prev, futures_universe: event.target.value }))} placeholder="Futures symbols CSV" data-testid="universe-futures-input" />
        <Input value={form.whitelist} onChange={(event) => setForm((prev) => ({ ...prev, whitelist: event.target.value }))} placeholder="Whitelist CSV" data-testid="universe-whitelist-input" />
        <Input value={form.blacklist} onChange={(event) => setForm((prev) => ({ ...prev, blacklist: event.target.value }))} placeholder="Blacklist CSV" data-testid="universe-blacklist-input" />
        <p className="md:col-span-2 text-xs text-slate-400" data-testid="market-universe-override-hint">
          Spot/Futures Universe alanları boş bırakılırsa exchange market symbols kullanılır (optional override).
        </p>
        <p className="md:col-span-2 text-xs text-slate-400" data-testid="market-universe-liquidity-advisory-hint">
          minimum_volume_usd ve max_spread_bps advisory-only çalışır; symbol elenmez, confidence/risk etkilenir.
        </p>

        <div className="flex flex-wrap gap-3 md:col-span-2" data-testid="universe-toggle-row">
          <label className="flex items-center gap-2 text-sm" data-testid="universe-emergency-toggle-label">
            <input
              type="checkbox"
              checked={form.emergency_mode}
              onChange={(event) => setForm((prev) => ({ ...prev, emergency_mode: event.target.checked }))}
              data-testid="universe-emergency-toggle"
            />
            Emergency Mode
          </label>
          <label className="flex items-center gap-2 text-sm" data-testid="universe-disable-futures-toggle-label">
            <input
              type="checkbox"
              checked={form.disable_futures}
              onChange={(event) => setForm((prev) => ({ ...prev, disable_futures: event.target.checked }))}
              data-testid="universe-disable-futures-toggle"
            />
            Disable Futures
          </label>
        </div>

        <Button className="bg-blue-600 text-white hover:bg-blue-700 md:col-span-2" data-testid="universe-save-button">Kuralları Kaydet</Button>
      </form>

      <section className="grid gap-3 border border-slate-800 bg-slate-900 p-4" data-testid="market-universe-alpha-key-panel">
        <p className="text-xs uppercase tracking-widest text-slate-500" data-testid="market-universe-alpha-key-title">Stock Provider (Alpha Vantage)</p>
        <p className="text-xs text-slate-400" data-testid="market-universe-alpha-key-status">has_key: {String(providerConfig?.has_alpha_vantage_key || false)} {providerConfig?.key_hint ? `(${providerConfig.key_hint})` : ""}</p>
        <div className="flex flex-wrap gap-2" data-testid="market-universe-alpha-key-row">
          <Input value={alphaKeyInput} onChange={(event) => setAlphaKeyInput(event.target.value)} placeholder="Alpha Vantage API Key" data-testid="market-universe-alpha-key-input" />
          <Button onClick={saveAlphaKey} data-testid="market-universe-alpha-key-save-button">Key Kaydet</Button>
        </div>
      </section>

      <section className="grid gap-4 border border-slate-800 bg-slate-900 p-4" data-testid="market-universe-symbol-selector-section">
        <div data-testid="market-universe-spot-selector-wrapper">
          <p className="mb-2 text-xs uppercase tracking-widest text-slate-500" data-testid="market-universe-spot-selector-title">Spot Universe Selector</p>
          <p className="mb-2 text-xs text-slate-400" data-testid="market-universe-spot-selector-count">selected_count: {spotSymbols.length}</p>
          <SymbolSelectorPanel
            testIdPrefix="market-universe-spot-selector"
            exchange="binance"
            marketType="spot"
            source={spotSource}
            onSourceChange={setSpotSource}
            mode={spotMode}
            onModeChange={setSpotMode}
            selectedSymbols={spotSymbols}
            onSelectedSymbolsChange={setSpotSymbols}
            multi
          />
        </div>

        <div data-testid="market-universe-futures-selector-wrapper">
          <p className="mb-2 text-xs uppercase tracking-widest text-slate-500" data-testid="market-universe-futures-selector-title">Futures Universe Selector</p>
          <p className="mb-2 text-xs text-slate-400" data-testid="market-universe-futures-selector-count">selected_count: {futuresSymbols.length}</p>
          <SymbolSelectorPanel
            testIdPrefix="market-universe-futures-selector"
            exchange="binance"
            marketType="futures"
            source={futuresSource}
            onSourceChange={setFuturesSource}
            mode={futuresMode}
            onModeChange={setFuturesMode}
            selectedSymbols={futuresSymbols}
            onSelectedSymbolsChange={setFuturesSymbols}
            multi
          />
        </div>

        <div data-testid="market-universe-stock-selector-wrapper">
          <p className="mb-2 text-xs uppercase tracking-widest text-slate-500" data-testid="market-universe-stock-selector-title">Stock Tracking Selector (NASDAQ+NYSE)</p>
          <SymbolSelectorPanel
            testIdPrefix="market-universe-stock-selector"
            exchange="US"
            marketType="equity"
            source={stockSource}
            onSourceChange={setStockSource}
            mode={stockMode}
            onModeChange={setStockMode}
            selectedSymbols={stockSymbols}
            onSelectedSymbolsChange={setStockSymbols}
            multi
          />
        </div>
      </section>

      <div className="grid gap-3 border border-slate-800 bg-slate-900 p-4 md:grid-cols-2" data-testid="market-universe-preview-panel">
        <div>
          <p className="text-xs uppercase tracking-widest text-slate-500" data-testid="universe-preview-spot-label">Effective Spot Universe</p>
          <p className="mt-2 font-mono text-sm" data-testid="universe-preview-spot-value">{preview?.spot_symbols?.join(", ") || "-"}</p>
        </div>
        <div>
          <p className="text-xs uppercase tracking-widest text-slate-500" data-testid="universe-preview-futures-label">Effective Futures Universe</p>
          <p className="mt-2 font-mono text-sm" data-testid="universe-preview-futures-value">{preview?.futures_symbols?.join(", ") || "-"}</p>
        </div>
      </div>
    </section>
  );
};