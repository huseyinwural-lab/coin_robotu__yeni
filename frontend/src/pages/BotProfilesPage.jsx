import { useEffect, useState } from "react";
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
  max_concurrent_trades: 3,
  timeframe: "15m",
  trend_timeframe: "1h",
  is_enabled: true,
};

export const BotProfilesPage = () => {
  const [items, setItems] = useState([]);
  const [strategyPerformance, setStrategyPerformance] = useState({ items: [] });
  const [editingId, setEditingId] = useState(null);
  const [deletingBotId, setDeletingBotId] = useState("");
  const [form, setForm] = useState(initialForm);
  const [formErrors, setFormErrors] = useState({});
  const [symbolSource, setSymbolSource] = useState("crypto");
  const [symbolMode, setSymbolMode] = useState("all_market_symbols");
  const [selectedSymbols, setSelectedSymbols] = useState(["BTCUSDT", "ETHUSDT"]);

  const fetchItems = async () => {
    const [profilesRes, strategyPerfRes] = await Promise.all([
      apiClient.get("/bot-profiles"),
      apiClient.get("/user/live/strategy-performance", { params: { window: "24h" } }),
    ]);
    setItems(profilesRes.data || []);
    setStrategyPerformance(strategyPerfRes.data || { items: [] });
  };

  const findStrategyParity = (strategyType) => (strategyPerformance?.items || []).find((item) => item.strategy_id === strategyType);

  useEffect(() => {
    fetchItems();
  }, []);

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
    if (!Number(form.max_concurrent_trades) || Number(form.max_concurrent_trades) < 1) {
      nextErrors.max_concurrent_trades = "Max Concurrent Trades en az 1 olmalı.";
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
      symbols: parsedSymbols,
      strategy_type: form.strategy_type,
      timeframe: form.timeframe,
      trend_timeframe: form.trend_timeframe,
      leverage: Number(form.max_concurrent_trades),
      is_enabled: Boolean(form.is_enabled),
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
      setSelectedSymbols(["BTCUSDT", "ETHUSDT"]);
      setSymbolMode("all_market_symbols");
      setFormErrors({});
      fetchItems();
    } catch (error) {
      toast.error(error?.response?.data?.detail || "Bot profili işlemi başarısız");
    }
  };

  const onEdit = (item) => {
    setEditingId(item.id);
    setForm({
      ...item,
      symbols: item.symbols.join(","),
      max_concurrent_trades: item.leverage,
    });
    setSymbolSource("crypto");
    setSymbolMode("manual_selection");
    setSelectedSymbols(item.symbols || []);
    setFormErrors({});
  };

  const toggleRunning = async (item) => {
    try {
      const endpoint = item.is_running ? "stop" : "start";
      await apiClient.post(`/pipeline/bots/${item.id}/${endpoint}`);
      toast.success(item.is_running ? "Bot durduruldu" : "Bot başlatıldı");
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
            <option value="trend_following">trend_following</option>
            <option value="mean_reversion">mean_reversion</option>
            <option value="volatility_breakout">volatility_breakout</option>
          </select>
          <p className="form-helper-text" id="bot-form-strategy-helper" data-testid="bot-form-strategy-helper">Botun sinyal üretim metodunu seçin.</p>
        </div>

        <div className="form-group" data-testid="bot-form-group-max-concurrent-trades">
          <label className="form-label" htmlFor="bot-form-max-concurrent-trades-input" data-testid="bot-form-max-concurrent-trades-label">Max Concurrent Trades</label>
          <Input
            id="bot-form-max-concurrent-trades-input"
            type="number"
            min={1}
            max={25}
            value={form.max_concurrent_trades}
            onChange={(event) => setForm((prev) => ({ ...prev, max_concurrent_trades: event.target.value }))}
            data-testid="bot-form-max-concurrent-trades-input"
            aria-label="Max Concurrent Trades"
            aria-describedby="bot-form-max-concurrent-trades-helper bot-form-max-concurrent-trades-error"
            required
          />
          <p className="form-helper-text" id="bot-form-max-concurrent-trades-helper" data-testid="bot-form-max-concurrent-trades-helper">Aynı anda açılabilecek maksimum işlem sayısını belirleyin.</p>
          {formErrors.max_concurrent_trades && <p className="form-error-text" id="bot-form-max-concurrent-trades-error" data-testid="bot-form-max-concurrent-trades-error">{formErrors.max_concurrent_trades}</p>}
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
                <TableCell data-testid={`bot-table-strategy-${item.id}`}>{item.strategy_type}</TableCell>
                <TableCell data-testid={`bot-table-parity-${item.id}`}>{parity ? `${parity.backtest?.win_rate ?? 0} / ${parity.live?.win_rate ?? 0} / ${parity.deviation_pct ?? 0}%` : "-"}</TableCell>
                <TableCell className="font-mono text-xs" data-testid={`bot-table-symbols-${item.id}`}>{item.symbols.join(", ")}</TableCell>
                <TableCell data-testid={`bot-table-runtime-${item.id}`}>{item.is_running ? "running" : "stopped"}</TableCell>
                <TableCell>
                  <div className="flex flex-wrap gap-2">
                    <Button size="sm" variant="outline" className="border-slate-600 bg-transparent" onClick={() => onEdit(item)} data-testid={`bot-table-edit-${item.id}`}>
                      Düzenle
                    </Button>
                    <Button
                      size="sm"
                      variant="outline"
                      className={`bg-transparent ${item.is_running ? "border-red-400 text-red-300" : "border-green-400 text-green-300"}`}
                      onClick={() => toggleRunning(item)}
                      data-testid={`bot-table-toggle-running-${item.id}`}
                    >
                      {item.is_running ? "Stop" : "Start"}
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
    </section>
  );
};
