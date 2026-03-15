import { useEffect, useMemo, useState } from "react";
import { toast } from "sonner";

import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { apiClient } from "@/lib/api";

const MODE_OPTIONS = [
  { value: "all_market_symbols", label: "Tüm market sembolleri" },
  { value: "top_volume", label: "Hacme göre üst semboller" },
  { value: "manual_selection", label: "Manual seçim" },
];

const SOURCE_OPTIONS = [
  { value: "crypto", label: "Kripto" },
  { value: "stock", label: "Senet" },
];

const normalizeModeValue = (mode) => {
  const raw = String(mode || "all_market_symbols").toLowerCase();
  if (raw === "all_exchange") {
    return "all_market_symbols";
  }
  if (raw === "top_active_50" || raw === "top_active_100") {
    return "top_volume";
  }
  if (raw === "custom_list" || raw === "bot_scope") {
    return "manual_selection";
  }
  if (["all_market_symbols", "top_volume", "manual_selection"].includes(raw)) {
    return raw;
  }
  return "all_market_symbols";
};

const normalizeSymbols = (symbols) => {
  if (!Array.isArray(symbols)) {
    return [];
  }
  const normalized = symbols.map((item) => String(item || "").trim().toUpperCase()).filter(Boolean);
  return Array.from(new Set(normalized));
};

export const SymbolSelectorPanel = ({
  testIdPrefix,
  exchange = "binance",
  marketType = "spot",
  quoteAssetFilter = "ALL",
  multi = true,
  selectedSymbols,
  onSelectedSymbolsChange,
  source,
  onSourceChange,
  mode,
  onModeChange,
}) => {
  const [search, setSearch] = useState("");
  const [rows, setRows] = useState([]);
  const [isLoading, setIsLoading] = useState(false);
  const [watchlists, setWatchlists] = useState([]);
  const [selectedWatchlistId, setSelectedWatchlistId] = useState("");
  const [watchlistName, setWatchlistName] = useState("");
  const [providerConfig, setProviderConfig] = useState(null);

  const normalizedSelectedSymbols = useMemo(() => normalizeSymbols(selectedSymbols), [selectedSymbols]);
  const normalizedMode = useMemo(() => normalizeModeValue(mode), [mode]);

  const loadProviderConfig = async () => {
    try {
      const { data } = await apiClient.get("/symbol-selector/provider-config");
      setProviderConfig(data || null);
    } catch {
      setProviderConfig(null);
    }
  };

  const loadWatchlists = async () => {
    try {
      const { data } = await apiClient.get("/symbol-selector/watchlists", { params: { source } });
      setWatchlists(data || []);
    } catch {
      setWatchlists([]);
    }
  };

  const loadUniverse = async ({ forceMode } = {}) => {
    setIsLoading(true);
    try {
      const activeMode = normalizeModeValue(forceMode || normalizedMode);
      const { data } = await apiClient.get("/symbol-selector/universe", {
        params: {
          source,
          exchange,
          market_type: marketType,
          mode: activeMode,
          selected_symbols: normalizedSelectedSymbols.join(","),
          query: search,
          quote_asset_filter: quoteAssetFilter,
        },
      });
      setRows(data?.rows || []);

      if (Array.isArray(data?.warnings) && data.warnings.includes("alpha_vantage_key_missing") && source === "stock") {
        toast.warning("Senet listesi için Alpha Vantage API key gerekli (Admin > Market Universe). ");
      }

      if (activeMode !== "manual_selection") {
        const next = normalizeSymbols(data?.selected_symbols || []);
        if (multi) {
          onSelectedSymbolsChange(next);
        } else {
          onSelectedSymbolsChange(next.slice(0, 1));
        }
      }
    } catch (error) {
      toast.error(error?.response?.data?.detail || "Sembol evreni yüklenemedi");
      setRows([]);
    } finally {
      setIsLoading(false);
    }
  };

  useEffect(() => {
    loadProviderConfig();
    loadWatchlists();
  }, [source]);

  useEffect(() => {
    loadUniverse();
  }, [normalizedMode, source, exchange, marketType, quoteAssetFilter]);

  const toggleSymbol = (symbol) => {
    const nextSet = new Set(normalizedSelectedSymbols);
    if (nextSet.has(symbol)) {
      nextSet.delete(symbol);
    } else if (!multi) {
      nextSet.clear();
      nextSet.add(symbol);
    } else {
      nextSet.add(symbol);
    }
    const next = Array.from(nextSet);
    onSelectedSymbolsChange(next);
  };

  const saveWatchlist = async () => {
    const trimmed = watchlistName.trim();
    if (!trimmed) {
      toast.error("Watchlist adı zorunlu");
      return;
    }
    if (normalizedSelectedSymbols.length === 0) {
      toast.error("Watchlist için en az bir sembol seçin");
      return;
    }
    try {
      await apiClient.post("/symbol-selector/watchlists", {
        name: trimmed,
        source,
        exchange,
        market_type: marketType,
        symbols: normalizedSelectedSymbols,
      });
      setWatchlistName("");
      toast.success("Watchlist kaydedildi");
      await loadWatchlists();
    } catch (error) {
      toast.error(error?.response?.data?.detail || "Watchlist kaydedilemedi");
    }
  };

  const applyWatchlist = () => {
    const selected = watchlists.find((item) => item.id === selectedWatchlistId);
    if (!selected) {
      return;
    }
    const symbols = normalizeSymbols(selected.symbols || []);
    onSelectedSymbolsChange(multi ? symbols : symbols.slice(0, 1));
    toast.success(`${selected.name} uygulandı`);
  };

  return (
    <div className="space-y-3 rounded border border-slate-700 bg-slate-950 p-3" data-testid={`${testIdPrefix}-panel`}>
      <div className="grid gap-2 md:grid-cols-4" data-testid={`${testIdPrefix}-controls-grid`}>
        <label className="space-y-1" data-testid={`${testIdPrefix}-source-field`}>
          <span className="text-xs text-slate-400">Kaynak</span>
          <select value={source} onChange={(event) => onSourceChange(event.target.value)} className="h-9 w-full rounded border border-slate-700 bg-black px-2 text-sm" data-testid={`${testIdPrefix}-source-select`}>
            {SOURCE_OPTIONS.map((item) => (
              <option key={item.value} value={item.value} data-testid={`${testIdPrefix}-source-option-${item.value}`}>{item.label}</option>
            ))}
          </select>
        </label>

        <label className="space-y-1" data-testid={`${testIdPrefix}-mode-field`}>
          <span className="text-xs text-slate-400">Seçim Modu</span>
          <select value={normalizedMode} onChange={(event) => onModeChange(event.target.value)} className="h-9 w-full rounded border border-slate-700 bg-black px-2 text-sm" data-testid={`${testIdPrefix}-mode-select`}>
            {MODE_OPTIONS.map((item) => (
              <option key={item.value} value={item.value} data-testid={`${testIdPrefix}-mode-option-${item.value}`}>{item.label}</option>
            ))}
          </select>
        </label>

        <label className="space-y-1" data-testid={`${testIdPrefix}-search-field`}>
          <span className="text-xs text-slate-400">Sembol Ara</span>
          <Input value={search} onChange={(event) => setSearch(event.target.value.toUpperCase())} placeholder="BTC / AAPL" data-testid={`${testIdPrefix}-search-input`} />
        </label>

        <div className="flex items-end gap-2" data-testid={`${testIdPrefix}-actions-row`}>
          <Button onClick={() => loadUniverse()} disabled={isLoading} data-testid={`${testIdPrefix}-refresh-button`}>
            {isLoading ? "Yükleniyor..." : "Listele"}
          </Button>
        </div>
      </div>

      <div className="grid gap-2 md:grid-cols-3" data-testid={`${testIdPrefix}-watchlist-grid`}>
        <label className="space-y-1" data-testid={`${testIdPrefix}-watchlist-select-field`}>
          <span className="text-xs text-slate-400">Kayıtlı Liste</span>
          <select value={selectedWatchlistId} onChange={(event) => setSelectedWatchlistId(event.target.value)} className="h-9 w-full rounded border border-slate-700 bg-black px-2 text-sm" data-testid={`${testIdPrefix}-watchlist-select`}>
            <option value="" data-testid={`${testIdPrefix}-watchlist-option-empty`}>seçiniz</option>
            {watchlists.map((item) => (
              <option key={item.id} value={item.id} data-testid={`${testIdPrefix}-watchlist-option-${item.id}`}>{item.name}</option>
            ))}
          </select>
        </label>
        <div className="flex items-end" data-testid={`${testIdPrefix}-watchlist-apply-wrapper`}>
          <Button variant="outline" onClick={applyWatchlist} disabled={!selectedWatchlistId} data-testid={`${testIdPrefix}-watchlist-apply-button`}>Listeyi Uygula</Button>
        </div>
        <label className="space-y-1" data-testid={`${testIdPrefix}-watchlist-name-field`}>
          <span className="text-xs text-slate-400">Yeni Liste Adı</span>
          <div className="flex gap-2" data-testid={`${testIdPrefix}-watchlist-save-row`}>
            <Input value={watchlistName} onChange={(event) => setWatchlistName(event.target.value)} placeholder="örn: swing-izleme" data-testid={`${testIdPrefix}-watchlist-name-input`} />
            <Button variant="outline" onClick={saveWatchlist} data-testid={`${testIdPrefix}-watchlist-save-button`}>Kaydet</Button>
          </div>
        </label>
      </div>

      {source === "stock" && !providerConfig?.has_alpha_vantage_key && (
        <p className="text-xs text-amber-300" data-testid={`${testIdPrefix}-stock-key-warning`}>
          Senet evreni için Alpha Vantage API key gerekli. Admin &gt; Market Universe ekranından ekleyebilirsiniz.
        </p>
      )}

      <p className="text-xs text-slate-400" data-testid={`${testIdPrefix}-selected-count`}>Seçilen sembol: {normalizedSelectedSymbols.length}</p>

      <div className="max-h-52 overflow-auto rounded border border-slate-800" data-testid={`${testIdPrefix}-rows-wrapper`}>
        <table className="min-w-full text-xs" data-testid={`${testIdPrefix}-rows-table`}>
          <thead className="sticky top-0 bg-slate-900" data-testid={`${testIdPrefix}-rows-head`}>
            <tr>
              <th className="px-2 py-1 text-left">Seç</th>
              <th className="px-2 py-1 text-left">Symbol</th>
              <th className="px-2 py-1 text-left">Exchange</th>
              <th className="px-2 py-1 text-left">Vol 24h</th>
            </tr>
          </thead>
          <tbody data-testid={`${testIdPrefix}-rows-body`}>
            {rows.slice(0, 300).map((row, index) => {
              const checked = normalizedSelectedSymbols.includes(row.symbol);
              return (
                <tr key={`${row.symbol}-${index}`} className="border-t border-slate-800" data-testid={`${testIdPrefix}-row-${index}`}>
                  <td className="px-2 py-1" data-testid={`${testIdPrefix}-row-check-${index}`}>
                    <input type="checkbox" checked={checked} onChange={() => toggleSymbol(row.symbol)} data-testid={`${testIdPrefix}-row-checkbox-${index}`} />
                  </td>
                  <td className="px-2 py-1" data-testid={`${testIdPrefix}-row-symbol-${index}`}>{row.symbol}</td>
                  <td className="px-2 py-1" data-testid={`${testIdPrefix}-row-exchange-${index}`}>{row.exchange}</td>
                  <td className="px-2 py-1" data-testid={`${testIdPrefix}-row-volume-${index}`}>{row.volume_24h ?? "-"}</td>
                </tr>
              );
            })}
            {rows.length === 0 && (
              <tr data-testid={`${testIdPrefix}-rows-empty`}>
                <td colSpan={4} className="px-2 py-3 text-center text-slate-500" data-testid={`${testIdPrefix}-rows-empty-text`}>
                  Gösterilecek sembol yok.
                </td>
              </tr>
            )}
          </tbody>
        </table>
      </div>
    </div>
  );
};
