import { useEffect, useState } from "react";
import { toast } from "sonner";

import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from "@/components/ui/table";
import { apiClient } from "@/lib/api";

const initialForm = {
  name: "",
  exchange: "binance",
  market_type: "spot",
  symbols: "BTCUSDT,ETHUSDT",
  strategy_type: "trend_following",
  timeframe: "15m",
  trend_timeframe: "1h",
  leverage: 3,
  is_enabled: true,
};

export const BotProfilesPage = () => {
  const [items, setItems] = useState([]);
  const [editingId, setEditingId] = useState(null);
  const [form, setForm] = useState(initialForm);

  const fetchItems = async () => {
    const { data } = await apiClient.get("/bot-profiles");
    setItems(data);
  };

  useEffect(() => {
    fetchItems();
  }, []);

  const handleSubmit = async (event) => {
    event.preventDefault();
    const payload = {
      ...form,
      symbols: form.symbols.split(",").map((value) => value.trim()).filter(Boolean),
      leverage: Number(form.leverage),
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
      fetchItems();
    } catch (error) {
      toast.error(error?.response?.data?.detail || "Bot profili işlemi başarısız");
    }
  };

  const onEdit = (item) => {
    setEditingId(item.id);
    setForm({ ...item, symbols: item.symbols.join(",") });
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

  return (
    <section className="space-y-4" data-testid="bot-profiles-page">
      <header className="border border-slate-800 bg-slate-900 p-4" data-testid="bot-profiles-header">
        <h2 className="text-4xl font-black uppercase tracking-tight" data-testid="bot-profiles-title">Bot Profile Yönetimi</h2>
        <p className="mt-2 text-sm text-slate-400" data-testid="bot-profiles-description">Create / Update iskeleti hazır. Gerçek trade açılmaz.</p>
      </header>

      <form onSubmit={handleSubmit} className="grid gap-3 border border-slate-800 bg-slate-900 p-4 md:grid-cols-2" data-testid="bot-profile-form">
        <Input placeholder="Bot adı" value={form.name} onChange={(event) => setForm((prev) => ({ ...prev, name: event.target.value }))} data-testid="bot-form-name-input" required />
        <Input placeholder="Exchange" value={form.exchange} onChange={(event) => setForm((prev) => ({ ...prev, exchange: event.target.value }))} data-testid="bot-form-exchange-input" required />
        <Input placeholder="Market type" value={form.market_type} onChange={(event) => setForm((prev) => ({ ...prev, market_type: event.target.value }))} data-testid="bot-form-market-type-input" required />
        <Input placeholder="Symbols (CSV)" value={form.symbols} onChange={(event) => setForm((prev) => ({ ...prev, symbols: event.target.value }))} data-testid="bot-form-symbols-input" required />
        <Input placeholder="Strategy type" value={form.strategy_type} onChange={(event) => setForm((prev) => ({ ...prev, strategy_type: event.target.value }))} data-testid="bot-form-strategy-type-input" required />
        <Input placeholder="Leverage" type="number" min={1} max={25} value={form.leverage} onChange={(event) => setForm((prev) => ({ ...prev, leverage: event.target.value }))} data-testid="bot-form-leverage-input" required />

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
              <TableHead data-testid="bot-table-head-symbols">Semboller</TableHead>
              <TableHead data-testid="bot-table-head-runtime">Runtime</TableHead>
              <TableHead data-testid="bot-table-head-action">Aksiyon</TableHead>
            </TableRow>
          </TableHeader>
          <TableBody>
            {items.map((item) => (
              <TableRow key={item.id} data-testid={`bot-table-row-${item.id}`}>
                <TableCell data-testid={`bot-table-name-${item.id}`}>{item.name}</TableCell>
                <TableCell data-testid={`bot-table-market-${item.id}`}>{item.market_type}</TableCell>
                <TableCell data-testid={`bot-table-strategy-${item.id}`}>{item.strategy_type}</TableCell>
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
                  </div>
                </TableCell>
              </TableRow>
            ))}
          </TableBody>
        </Table>
      </div>
    </section>
  );
};
