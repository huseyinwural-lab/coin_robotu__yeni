import { useEffect, useState } from "react";
import { toast } from "sonner";

import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from "@/components/ui/table";
import { apiClient } from "@/lib/api";

const initialForm = {
  name: "",
  position_size_pct: 2,
  atr_stop_multiplier: 1.5,
  risk_reward_ratio: 2,
  daily_loss_cutoff_pct: 5,
  max_open_positions: 3,
  max_leverage: 3,
  spread_limit_bps: 30,
  slippage_limit_bps: 40,
  min_liquidity_usdt: 100000,
};

export const RiskPoliciesPage = () => {
  const [items, setItems] = useState([]);
  const [editingId, setEditingId] = useState(null);
  const [form, setForm] = useState(initialForm);

  const fetchItems = async () => {
    const { data } = await apiClient.get("/risk-policies");
    setItems(data);
  };

  useEffect(() => {
    fetchItems();
  }, []);

  const handleSubmit = async (event) => {
    event.preventDefault();
    const payload = Object.fromEntries(
      Object.entries(form).map(([key, value]) => [key, key === "name" ? value : Number(value)]),
    );
    try {
      if (editingId) {
        await apiClient.put(`/risk-policies/${editingId}`, payload);
        toast.success("Risk policy güncellendi");
      } else {
        await apiClient.post("/risk-policies", payload);
        toast.success("Risk policy oluşturuldu");
      }
      setEditingId(null);
      setForm(initialForm);
      fetchItems();
    } catch (error) {
      toast.error(error?.response?.data?.detail || "Risk policy işlemi başarısız");
    }
  };

  const editPolicy = (item) => {
    setEditingId(item.id);
    setForm(item);
  };

  return (
    <section className="space-y-4" data-testid="risk-policies-page">
      <header className="border border-slate-800 bg-slate-900 p-4" data-testid="risk-policies-header">
        <h2 className="text-4xl font-black uppercase tracking-tight" data-testid="risk-policies-title">Risk Policy Yönetimi</h2>
        <p className="mt-2 text-sm text-slate-400" data-testid="risk-policies-description">Position sizing, ATR SL, RR ve cutoff alanları yönetilir.</p>
      </header>

      <form onSubmit={handleSubmit} className="grid gap-3 border border-slate-800 bg-slate-900 p-4 md:grid-cols-2" data-testid="risk-policy-form">
        <Input placeholder="Policy adı" value={form.name} onChange={(event) => setForm((prev) => ({ ...prev, name: event.target.value }))} data-testid="risk-form-name-input" required />
        <Input type="number" step="0.1" placeholder="Position size %" value={form.position_size_pct} onChange={(event) => setForm((prev) => ({ ...prev, position_size_pct: event.target.value }))} data-testid="risk-form-position-size-input" required />
        <Input type="number" step="0.1" placeholder="ATR stop" value={form.atr_stop_multiplier} onChange={(event) => setForm((prev) => ({ ...prev, atr_stop_multiplier: event.target.value }))} data-testid="risk-form-atr-input" required />
        <Input type="number" step="0.1" placeholder="Risk/Reward" value={form.risk_reward_ratio} onChange={(event) => setForm((prev) => ({ ...prev, risk_reward_ratio: event.target.value }))} data-testid="risk-form-rr-input" required />
        <Input type="number" step="0.1" placeholder="Daily cutoff %" value={form.daily_loss_cutoff_pct} onChange={(event) => setForm((prev) => ({ ...prev, daily_loss_cutoff_pct: event.target.value }))} data-testid="risk-form-cutoff-input" required />
        <Input type="number" placeholder="Max open positions" value={form.max_open_positions} onChange={(event) => setForm((prev) => ({ ...prev, max_open_positions: event.target.value }))} data-testid="risk-form-max-open-input" required />

        <div className="flex gap-2 md:col-span-2">
          <Button type="submit" className="bg-orange-500 text-black hover:bg-orange-600" data-testid="risk-form-submit-button">
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
              data-testid="risk-form-cancel-edit-button"
            >
              İptal
            </Button>
          )}
        </div>
      </form>

      <div className="border border-slate-800 bg-slate-900" data-testid="risk-policies-table-wrapper">
        <Table data-testid="risk-policies-table">
          <TableHeader>
            <TableRow>
              <TableHead data-testid="risk-table-head-name">Ad</TableHead>
              <TableHead data-testid="risk-table-head-position">Position %</TableHead>
              <TableHead data-testid="risk-table-head-atr">ATR</TableHead>
              <TableHead data-testid="risk-table-head-rr">RR</TableHead>
              <TableHead data-testid="risk-table-head-action">Aksiyon</TableHead>
            </TableRow>
          </TableHeader>
          <TableBody>
            {items.map((item) => (
              <TableRow key={item.id} data-testid={`risk-table-row-${item.id}`}>
                <TableCell data-testid={`risk-table-name-${item.id}`}>{item.name}</TableCell>
                <TableCell className="font-mono" data-testid={`risk-table-position-${item.id}`}>{item.position_size_pct}</TableCell>
                <TableCell className="font-mono" data-testid={`risk-table-atr-${item.id}`}>{item.atr_stop_multiplier}</TableCell>
                <TableCell className="font-mono" data-testid={`risk-table-rr-${item.id}`}>{item.risk_reward_ratio}</TableCell>
                <TableCell>
                  <Button size="sm" variant="outline" className="border-slate-600 bg-transparent" onClick={() => editPolicy(item)} data-testid={`risk-table-edit-${item.id}`}>
                    Düzenle
                  </Button>
                </TableCell>
              </TableRow>
            ))}
          </TableBody>
        </Table>
      </div>
    </section>
  );
};
