import { useCallback, useEffect, useMemo, useState } from "react";
import { toast } from "sonner";

import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { apiClient } from "@/lib/api";

const ALLOWED_QUOTE_ASSETS = new Set(["USDT", "USDC"]);

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

const areSameSymbolSet = (left, right) => {
  const leftNormalized = normalizeSymbols(left).sort();
  const rightNormalized = normalizeSymbols(right).sort();
  if (leftNormalized.length !== rightNormalized.length) {
    return false;
  }
  return leftNormalized.every((value, index) => value === rightNormalized[index]);
};

const detectQuoteAsset = (symbol) => {
  const normalized = String(symbol || "").trim().toUpperCase();
  if (normalized.endsWith("USDT")) return "USDT";
  if (normalized.endsWith("USDC")) return "USDC";
  return "UNKNOWN";
};

const liquidityBandFromVolume = (volume) => {
  const numeric = Number(volume || 0);
  if (numeric >= 50_000_000) return "high";
  if (numeric >= 10_000_000) return "medium";
  return "low";
};

const riskBandFromVolume = (volume) => {
  const liquidityBand = liquidityBandFromVolume(volume);
  if (liquidityBand === "high") return "low";
  if (liquidityBand === "medium") return "medium";
  return "high";
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
  onWatchlistApplied,
}) => {
  const [search, setSearch] = useState("");
  const [rows, setRows] = useState([]);
  const [isLoading, setIsLoading] = useState(false);
  const [watchlists, setWatchlists] = useState([]);
  const [selectedWatchlistId, setSelectedWatchlistId] = useState("");
  const [watchlistName, setWatchlistName] = useState("");
  const [isDeletingWatchlist, setIsDeletingWatchlist] = useState(false);
  const [providerConfig, setProviderConfig] = useState(null);
  const [liquidityBandFilter, setLiquidityBandFilter] = useState("all");
  const [riskBandFilter, setRiskBandFilter] = useState("all");
  const [exchangeFilter, setExchangeFilter] = useState("all");

  const normalizedSelectedSymbols = useMemo(() => normalizeSymbols(selectedSymbols), [selectedSymbols]);
  const normalizedMode = useMemo(() => normalizeModeValue(mode), [mode]);
  const normalizedRows = useMemo(
    () => rows.slice(0, 300).map((row) => {
      const symbol = String(row?.symbol || "").trim().toUpperCase();
      const quoteAsset = String(row?.quote_asset || detectQuoteAsset(symbol)).trim().toUpperCase() || "UNKNOWN";
      const unsupported = String(source || "crypto").toLowerCase() !== "crypto" || !ALLOWED_QUOTE_ASSETS.has(quoteAsset);
      return {
        ...row,
        symbol,
        quote_asset: quoteAsset,
        unsupported,
      };
    }).filter((row) => Boolean(row.symbol)),
    [rows, source],
  );

  const depthFilteredRows = useMemo(() => {
    return normalizedRows.filter((row) => {
      const liquidityBand = liquidityBandFromVolume(row.volume_24h);
      const riskBand = riskBandFromVolume(row.volume_24h);
      const rowExchange = String(row.exchange || "").toLowerCase();

      if (exchangeFilter !== "all" && rowExchange !== exchangeFilter) return false;
      if (liquidityBandFilter !== "all" && liquidityBand !== liquidityBandFilter) return false;
      if (riskBandFilter !== "all" && riskBand !== riskBandFilter) return false;
      return true;
    });
  }, [normalizedRows, exchangeFilter, liquidityBandFilter, riskBandFilter]);

  const exchangeOptions = useMemo(() => {
    const values = Array.from(new Set(normalizedRows.map((row) => String(row.exchange || "").toLowerCase()).filter(Boolean)));
    return ["all", ...values];
  }, [normalizedRows]);

  const loadProviderConfig = useCallback(async () => {
    try {
      const { data } = await apiClient.get("/symbol-selector/provider-config");
      setProviderConfig(data || null);
    } catch {
      setProviderConfig(null);
    }
  }, []);

  const loadWatchlists = useCallback(async () => {
    try {
      const { data } = await apiClient.get("/symbol-selector/watchlists", { params: { source } });
      setWatchlists(data || []);
    } catch {
      setWatchlists([]);
    }
  }, [source]);

  const loadUniverse = useCallback(async ({ forceMode } = {}) => {
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
        const selectable = new Set(
          (data?.rows || [])
            .map((row) => ({
              symbol: String(row?.symbol || "").trim().toUpperCase(),
              quote_asset: String(row?.quote_asset || detectQuoteAsset(row?.symbol)).trim().toUpperCase(),
            }))
            .filter((row) => row.symbol && ALLOWED_QUOTE_ASSETS.has(row.quote_asset))
            .map((row) => row.symbol),
        );
        const next = normalizeSymbols(data?.selected_symbols || []).filter((symbol) => selectable.has(symbol));
        const current = multi ? normalizeSymbols(normalizedSelectedSymbols) : normalizeSymbols(normalizedSelectedSymbols).slice(0, 1);
        const target = multi ? next : next.slice(0, 1);
        if (areSameSymbolSet(current, target)) {
          return;
        }
        if (multi) {
          onSelectedSymbolsChange(target);
        } else {
          onSelectedSymbolsChange(target);
        }
      }
    } catch (error) {
      toast.error(error?.response?.data?.detail || "Sembol evreni yüklenemedi");
      setRows([]);
    } finally {
      setIsLoading(false);
    }
  }, [
    exchange,
    marketType,
    multi,
    normalizedMode,
    normalizedSelectedSymbols,
    onSelectedSymbolsChange,
    quoteAssetFilter,
    search,
    source,
  ]);

  useEffect(() => {
    loadProviderConfig();
    loadWatchlists();
  }, [loadProviderConfig, loadWatchlists]);

  useEffect(() => {
    loadUniverse();
  }, [loadUniverse]);

  const toggleSymbol = (row) => {
    const symbol = String(row?.symbol || "").trim().toUpperCase();
    if (!symbol || row?.unsupported) {
      return;
    }
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

  const visibleSymbols = useMemo(
    () => depthFilteredRows.filter((row) => !row.unsupported).map((row) => row.symbol),
    [depthFilteredRows],
  );

  const allVisibleSelected = useMemo(
    () => visibleSymbols.length > 0 && visibleSymbols.every((symbol) => normalizedSelectedSymbols.includes(symbol)),
    [visibleSymbols, normalizedSelectedSymbols],
  );

  const selectAllVisible = () => {
    if (!multi) {
      onSelectedSymbolsChange(visibleSymbols.slice(0, 1));
      return;
    }
    const merged = Array.from(new Set([...(normalizedSelectedSymbols || []), ...visibleSymbols]));
    onSelectedSymbolsChange(merged);
  };

  const clearAllSelected = () => {
    onSelectedSymbolsChange([]);
  };

  const toggleAllVisible = () => {
    if (allVisibleSelected) {
      const next = normalizedSelectedSymbols.filter((symbol) => !visibleSymbols.includes(symbol));
      onSelectedSymbolsChange(next);
      return;
    }
    selectAllVisible();
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
    const symbols = normalizeSymbols(selected.symbols || []).filter(
      (symbol) => symbol.endsWith("USDT") || symbol.endsWith("USDC"),
    );
    if (symbols.length === 0) {
      toast.error("Seçili listede geçerli USDT/USDC market bulunamadı");
      return;
    }
    onSelectedSymbolsChange(multi ? symbols : symbols.slice(0, 1));
    if (typeof onWatchlistApplied === "function") {
      onWatchlistApplied(symbols);
    }
    toast.success(`${selected.name} uygulandı`);
  };

  const deleteWatchlist = async () => {
    if (!selectedWatchlistId) {
      return;
    }

    const selected = watchlists.find((item) => item.id === selectedWatchlistId);
    const name = selected?.name || "watchlist";
    const approved = typeof window === "undefined" ? true : window.confirm(`${name} listesini silmek istiyor musunuz?`);
    if (!approved) {
      return;
    }

    setIsDeletingWatchlist(true);
    try {
      await apiClient.delete(`/symbol-selector/watchlists/${selectedWatchlistId}`);
      toast.success("Watchlist silindi");
      setSelectedWatchlistId("");
      await loadWatchlists();
    } catch (error) {
      toast.error(error?.response?.data?.detail || "Watchlist silinemedi");
    } finally {
      setIsDeletingWatchlist(false);
    }
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
          <Input
            value={search}
            onChange={(event) => setSearch(event.target.value.toUpperCase())}
            placeholder="ETHUSDT / SOLUSDC"
            data-testid={`${testIdPrefix}-search-input`}
          />
        </label>

        <div className="flex items-end gap-2" data-testid={`${testIdPrefix}-actions-row`}>
          <Button onClick={() => loadUniverse()} disabled={isLoading} data-testid={`${testIdPrefix}-refresh-button`}>
            {isLoading ? "Yükleniyor..." : "Listele"}
          </Button>
        </div>
      </div>

      <div className="grid gap-2 md:grid-cols-3" data-testid={`${testIdPrefix}-depth-filters-grid`}>
        <label className="space-y-1" data-testid={`${testIdPrefix}-depth-liquidity-field`}>
          <span className="text-xs text-slate-400">Liquidity Band</span>
          <select
            value={liquidityBandFilter}
            onChange={(event) => setLiquidityBandFilter(event.target.value)}
            className="h-9 w-full rounded border border-slate-700 bg-black px-2 text-sm"
            data-testid={`${testIdPrefix}-depth-liquidity-select`}
          >
            <option value="all">all</option>
            <option value="high">high</option>
            <option value="medium">medium</option>
            <option value="low">low</option>
          </select>
        </label>

        <label className="space-y-1" data-testid={`${testIdPrefix}-depth-risk-field`}>
          <span className="text-xs text-slate-400">Risk Band</span>
          <select
            value={riskBandFilter}
            onChange={(event) => setRiskBandFilter(event.target.value)}
            className="h-9 w-full rounded border border-slate-700 bg-black px-2 text-sm"
            data-testid={`${testIdPrefix}-depth-risk-select`}
          >
            <option value="all">all</option>
            <option value="high">high</option>
            <option value="medium">medium</option>
            <option value="low">low</option>
          </select>
        </label>

        <label className="space-y-1" data-testid={`${testIdPrefix}-depth-exchange-field`}>
          <span className="text-xs text-slate-400">Exchange</span>
          <select
            value={exchangeFilter}
            onChange={(event) => setExchangeFilter(event.target.value)}
            className="h-9 w-full rounded border border-slate-700 bg-black px-2 text-sm"
            data-testid={`${testIdPrefix}-depth-exchange-select`}
          >
            {exchangeOptions.map((item) => (
              <option key={item} value={item}>{item}</option>
            ))}
          </select>
        </label>
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
        <div className="flex items-end gap-2" data-testid={`${testIdPrefix}-watchlist-apply-wrapper`}>
          <Button variant="outline" onClick={applyWatchlist} disabled={!selectedWatchlistId} data-testid={`${testIdPrefix}-watchlist-apply-button`}>Listeyi Uygula</Button>
          <Button
            variant="outline"
            onClick={deleteWatchlist}
            disabled={!selectedWatchlistId || isDeletingWatchlist}
            data-testid={`${testIdPrefix}-watchlist-delete-button`}
          >
            {isDeletingWatchlist ? "Siliniyor..." : "Sil"}
          </Button>
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

      <div className="flex flex-wrap items-center justify-between gap-2" data-testid={`${testIdPrefix}-bulk-actions-row`}>
        <p className="text-xs text-slate-400" data-testid={`${testIdPrefix}-selected-count`}>Selected Symbols: {normalizedSelectedSymbols.length}</p>
        <div className="flex flex-wrap gap-2" data-testid={`${testIdPrefix}-bulk-actions-buttons`}>
          <Button type="button" variant="outline" onClick={selectAllVisible} data-testid={`${testIdPrefix}-select-all-button`}>
            Select All
          </Button>
          <Button type="button" variant="outline" onClick={clearAllSelected} data-testid={`${testIdPrefix}-clear-all-button`}>
            Clear All
          </Button>
        </div>
      </div>

      <div className="max-h-52 overflow-auto rounded border border-slate-800" data-testid={`${testIdPrefix}-rows-wrapper`}>
        <table className="min-w-full text-xs" data-testid={`${testIdPrefix}-rows-table`}>
          <thead className="sticky top-0 bg-slate-900" data-testid={`${testIdPrefix}-rows-head`}>
            <tr>
              <th className="px-2 py-1 text-left" data-testid={`${testIdPrefix}-header-select-all`}>
                <input
                  type="checkbox"
                  checked={allVisibleSelected}
                  onChange={toggleAllVisible}
                  data-testid={`${testIdPrefix}-header-select-all-checkbox`}
                />
              </th>
              <th className="px-2 py-1 text-left">Symbol</th>
              <th className="px-2 py-1 text-left" data-testid={`${testIdPrefix}-header-quote-asset`}>Quote Asset</th>
              <th className="px-2 py-1 text-left">Exchange</th>
              <th className="px-2 py-1 text-left">Vol 24h</th>
              <th className="px-2 py-1 text-left" data-testid={`${testIdPrefix}-header-policy`}>Strategy Policy</th>
            </tr>
          </thead>
          <tbody data-testid={`${testIdPrefix}-rows-body`}>
            {depthFilteredRows.map((row, index) => {
              const checked = normalizedSelectedSymbols.includes(row.symbol);
              return (
                <tr
                  key={`${row.symbol}-${index}`}
                  className={`border-t border-slate-800 ${row.unsupported ? "cursor-not-allowed opacity-50" : ""}`}
                  data-testid={`${testIdPrefix}-row-${index}`}
                >
                  <td className="px-2 py-1" data-testid={`${testIdPrefix}-row-check-${index}`}>
                    <input
                      type="checkbox"
                      checked={checked}
                      disabled={row.unsupported}
                      onChange={() => toggleSymbol(row)}
                      data-testid={`${testIdPrefix}-row-checkbox-${index}`}
                    />
                  </td>
                  <td className="px-2 py-1" data-testid={`${testIdPrefix}-row-symbol-${index}`}>{row.symbol}</td>
                  <td className="px-2 py-1" data-testid={`${testIdPrefix}-row-quote-asset-${index}`}>{row.quote_asset}</td>
                  <td className="px-2 py-1" data-testid={`${testIdPrefix}-row-exchange-${index}`}>{row.exchange}</td>
                  <td className="px-2 py-1" data-testid={`${testIdPrefix}-row-volume-${index}`}>{row.volume_24h ?? "-"}</td>
                  <td className="px-2 py-1" data-testid={`${testIdPrefix}-row-policy-${index}`}>
                    {row.unsupported ? "UNSUPPORTED_PAIR" : "SUPPORTED"}
                  </td>
                </tr>
              );
            })}
            {normalizedRows.length === 0 && (
              <tr data-testid={`${testIdPrefix}-rows-empty`}>
                <td colSpan={6} className="px-2 py-3 text-center text-slate-500" data-testid={`${testIdPrefix}-rows-empty-text`}>
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
