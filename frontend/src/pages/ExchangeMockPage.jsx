import { useCallback, useEffect, useState } from "react";
import { toast } from "sonner";

import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from "@/components/ui/table";
import { apiClient } from "@/lib/api";

export const ExchangeMockPage = () => {
  const [botProfiles, setBotProfiles] = useState([]);
  const [events, setEvents] = useState([]);
  const [state, setState] = useState(null);
  const [isLoading, setIsLoading] = useState(true);
  const [isSubmitting, setIsSubmitting] = useState(false);
  const [form, setForm] = useState({ bot_profile_id: "", symbol: "BTCUSDT", side: "buy", quantity: 0.01 });

  const fetchAll = useCallback(async () => {
    setIsLoading(true);
    try {
      const [{ data: profiles }, { data: nextEvents }, { data: nextState }] = await Promise.all([
        apiClient.get("/bot-profiles"),
        apiClient.get("/exchange/mock/events"),
        apiClient.get("/exchange/mock/state"),
      ]);
      setBotProfiles(profiles);
      setEvents(nextEvents);
      setState(nextState);
      setForm((prev) => ({
        ...prev,
        bot_profile_id: prev.bot_profile_id || (profiles[0]?.id ?? ""),
      }));
    } catch (error) {
      toast.error(error?.response?.data?.detail || "Exchange mock verileri yüklenemedi");
    } finally {
      setIsLoading(false);
    }
  }, []);

  useEffect(() => {
    fetchAll();
  }, [fetchAll]);

  const submitMockOrder = async (event) => {
    event.preventDefault();
    setIsSubmitting(true);
    try {
      await apiClient.post("/exchange/mock/execute", { ...form, quantity: Number(form.quantity) });
      await fetchAll();
      toast.success("MOCK emir işlendi ve tablo yenilendi");
    } catch (error) {
      toast.error(error?.response?.data?.detail || "MOCK emir başarısız");
    } finally {
      setIsSubmitting(false);
    }
  };

  return (
    <section className="space-y-4" data-testid="exchange-mock-page">
      <header className="border border-orange-500/40 bg-slate-900 p-4" data-testid="exchange-mock-header">
        <h2 className="text-4xl font-black uppercase tracking-tight" data-testid="exchange-mock-title">Exchange Adapter Mock Akışı</h2>
        <p className="mt-2 text-sm text-slate-400" data-testid="exchange-mock-description">Binance adapter arayüzü aktif, gerçek emir gönderimi kapalı.</p>
      </header>

      <div className="grid gap-3 lg:grid-cols-2">
        <form onSubmit={submitMockOrder} className="space-y-3 border border-slate-800 bg-slate-900 p-4" data-testid="exchange-mock-form">
          <Input
            placeholder="Bot profile id"
            value={form.bot_profile_id}
            onChange={(event) => setForm((prev) => ({ ...prev, bot_profile_id: event.target.value }))}
            data-testid="exchange-form-bot-id-input"
            required
          />
          <Input placeholder="Symbol" value={form.symbol} onChange={(event) => setForm((prev) => ({ ...prev, symbol: event.target.value }))} data-testid="exchange-form-symbol-input" required />
          <Input placeholder="Side (buy/sell)" value={form.side} onChange={(event) => setForm((prev) => ({ ...prev, side: event.target.value }))} data-testid="exchange-form-side-input" required />
          <Input type="number" step="0.001" placeholder="Quantity" value={form.quantity} onChange={(event) => setForm((prev) => ({ ...prev, quantity: event.target.value }))} data-testid="exchange-form-quantity-input" required />

          <Button type="submit" className="w-full bg-orange-500 text-black hover:bg-orange-600" data-testid="exchange-form-submit-button">
            {isSubmitting ? "İşleniyor..." : "MOCK Execute"}
          </Button>

          <div className="border border-slate-700 p-3" data-testid="exchange-state-panel">
            <p className="text-xs uppercase tracking-widest text-slate-500" data-testid="exchange-state-label">Adapter State</p>
            <p className="mt-2 font-mono text-xs text-slate-200" data-testid="exchange-state-value">{state?.adapter?.connection || "-"}</p>
            <p className="font-mono text-xs text-slate-200" data-testid="exchange-state-last-order">{state?.last_order || "Last order yok"}</p>
          </div>
        </form>

        <div className="border border-slate-800 bg-slate-900" data-testid="exchange-events-table-wrapper">
          {isLoading && <p className="p-3 text-sm text-slate-400" data-testid="exchange-events-loading-state">Yükleniyor...</p>}
          {!isLoading && events.length === 0 && (
            <p className="p-3 text-sm text-slate-500" data-testid="exchange-events-empty-state">Henüz mock event oluşmadı.</p>
          )}
          <Table data-testid="exchange-events-table">
            <TableHeader>
              <TableRow>
                <TableHead data-testid="exchange-table-head-time">Zaman</TableHead>
                <TableHead data-testid="exchange-table-head-symbol">Symbol</TableHead>
                <TableHead data-testid="exchange-table-head-side">Side</TableHead>
                <TableHead data-testid="exchange-table-head-price">Price</TableHead>
              </TableRow>
            </TableHeader>
            <TableBody>
              {events.map((item) => (
                <TableRow key={item.id} data-testid={`exchange-table-row-${item.id}`}>
                  <TableCell className="font-mono text-xs" data-testid={`exchange-table-time-${item.id}`}>{new Date(item.created_at).toLocaleString()}</TableCell>
                  <TableCell data-testid={`exchange-table-symbol-${item.id}`}>{item.symbol}</TableCell>
                  <TableCell data-testid={`exchange-table-side-${item.id}`}>{item.side}</TableCell>
                  <TableCell className="font-mono" data-testid={`exchange-table-price-${item.id}`}>{item.mock_price}</TableCell>
                </TableRow>
              ))}
            </TableBody>
          </Table>
        </div>
      </div>

      <div className="border border-slate-800 bg-slate-900 p-4" data-testid="exchange-profile-hints-panel">
        <p className="text-xs uppercase tracking-widest text-slate-500" data-testid="exchange-profile-hints-label">Mevcut Bot Profilleri</p>
        <div className="mt-2 flex flex-wrap gap-2" data-testid="exchange-profile-hints-list">
          {botProfiles.map((profile) => (
            <button
              key={profile.id}
              type="button"
              onClick={() => setForm((prev) => ({ ...prev, bot_profile_id: profile.id, symbol: profile.symbols[0] || "BTCUSDT" }))}
              className="border border-slate-700 px-2 py-1 text-xs hover:border-orange-500"
              data-testid={`exchange-profile-chip-${profile.id}`}
            >
              {profile.name} ({profile.id.slice(0, 8)})
            </button>
          ))}
        </div>
      </div>
    </section>
  );
};
