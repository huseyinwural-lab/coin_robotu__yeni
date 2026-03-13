import { useEffect, useState } from "react";
import { useNavigate } from "react-router-dom";
import { toast } from "sonner";

import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from "@/components/ui/table";
import { useAuth } from "@/context/AuthContext";
import { apiClient } from "@/lib/api";

const initialForm = {
  name: "",
  strategy_type: "trend_following",
  parameters: '{"ema_fast": 20, "ema_slow": 50}',
  is_active: true,
};

export const StrategyTemplatesPage = () => {
  const { user } = useAuth();
  const navigate = useNavigate();
  const [items, setItems] = useState([]);
  const [editingId, setEditingId] = useState(null);
  const [form, setForm] = useState(initialForm);

  const fetchItems = async () => {
    const { data } = await apiClient.get("/strategy-templates");
    setItems(data);
  };

  useEffect(() => {
    fetchItems();
  }, []);

  const submitTemplate = async (event) => {
    event.preventDefault();
    try {
      const payload = {
        ...form,
        parameters: JSON.parse(form.parameters),
      };
      if (editingId) {
        await apiClient.put(`/strategy-templates/${editingId}`, payload);
        toast.success("Template güncellendi");
      } else {
        await apiClient.post("/strategy-templates", payload);
        toast.success("Template oluşturuldu");
      }
      setEditingId(null);
      setForm(initialForm);
      fetchItems();
    } catch (error) {
      toast.error(error?.response?.data?.detail || "JSON formatını kontrol et");
    }
  };

  const editTemplate = (item) => {
    setEditingId(item.id);
    setForm({ ...item, parameters: JSON.stringify(item.parameters) });
  };

  return (
    <section className="space-y-4" data-testid="strategy-templates-page">
      <header className="border border-slate-800 bg-slate-900 p-4" data-testid="strategy-templates-header">
        <h2 className="text-4xl font-black uppercase tracking-tight" data-testid="strategy-templates-title">Strategy Template Yönetimi</h2>
        <p className="mt-2 text-sm text-slate-400" data-testid="strategy-templates-description">
          Trend Following, Mean Reversion, Breakout, Volatility Expansion modları için temel şablon alanı.
        </p>
      </header>

      {user?.role !== "admin" && (
        <section className="border border-emerald-500/40 bg-emerald-500/10 p-4" data-testid="strategy-templates-user-bridge-panel">
          <p className="text-xs uppercase tracking-widest text-emerald-300" data-testid="strategy-templates-user-bridge-title">User Bridge Guidance</p>
          <p className="mt-2 text-sm text-emerald-100" data-testid="strategy-templates-user-bridge-description">
            Bu ekran read-only. Şablonu aksiyona çevirmek için Scanner veya Execute ekranına geçin.
          </p>
          <div className="mt-3 flex flex-wrap gap-2" data-testid="strategy-templates-user-bridge-actions">
            <Button variant="outline" onClick={() => navigate("/user/scanner")} data-testid="strategy-templates-go-scanner-button">Scanner’a Git</Button>
            <Button variant="outline" onClick={() => navigate("/user/execute?source=strategy-template") } data-testid="strategy-templates-go-execute-button">Execute’a Git</Button>
          </div>
        </section>
      )}

      {user?.role === "admin" && (
        <form onSubmit={submitTemplate} className="grid gap-3 border border-blue-900 bg-slate-900 p-4 md:grid-cols-2" data-testid="strategy-template-form">
          <Input placeholder="Template adı" value={form.name} onChange={(event) => setForm((prev) => ({ ...prev, name: event.target.value }))} data-testid="strategy-form-name-input" required />
          <Input placeholder="Strategy type" value={form.strategy_type} onChange={(event) => setForm((prev) => ({ ...prev, strategy_type: event.target.value }))} data-testid="strategy-form-type-input" required />
          <Input placeholder='{"param": "value"}' value={form.parameters} onChange={(event) => setForm((prev) => ({ ...prev, parameters: event.target.value }))} data-testid="strategy-form-parameters-input" required className="md:col-span-2 font-mono" />

          <div className="flex gap-2 md:col-span-2">
            <Button type="submit" className="bg-blue-500 text-white hover:bg-blue-600" data-testid="strategy-form-submit-button">
              {editingId ? "Güncelle" : "Template Oluştur"}
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
                data-testid="strategy-form-cancel-edit-button"
              >
                İptal
              </Button>
            )}
          </div>
        </form>
      )}

      <div className="border border-slate-800 bg-slate-900" data-testid="strategy-templates-table-wrapper">
        <Table data-testid="strategy-templates-table">
          <TableHeader>
            <TableRow>
              <TableHead data-testid="strategy-table-head-name">Ad</TableHead>
              <TableHead data-testid="strategy-table-head-type">Tip</TableHead>
              <TableHead data-testid="strategy-table-head-params">Parametreler</TableHead>
              <TableHead data-testid="strategy-table-head-action">Aksiyon</TableHead>
            </TableRow>
          </TableHeader>
          <TableBody>
            {items.map((item) => (
              <TableRow key={item.id} data-testid={`strategy-table-row-${item.id}`}>
                <TableCell data-testid={`strategy-table-name-${item.id}`}>{item.name}</TableCell>
                <TableCell data-testid={`strategy-table-type-${item.id}`}>{item.strategy_type}</TableCell>
                <TableCell className="max-w-xs truncate font-mono text-xs" data-testid={`strategy-table-params-${item.id}`}>
                  {JSON.stringify(item.parameters)}
                </TableCell>
                <TableCell>
                  {user?.role === "admin" ? (
                    <Button size="sm" variant="outline" className="border-slate-600 bg-transparent" onClick={() => editTemplate(item)} data-testid={`strategy-table-edit-${item.id}`}>
                      Düzenle
                    </Button>
                  ) : (
                    <span className="text-xs text-slate-500" data-testid={`strategy-table-readonly-${item.id}`}>Readonly</span>
                  )}
                </TableCell>
              </TableRow>
            ))}
          </TableBody>
        </Table>
      </div>
    </section>
  );
};
