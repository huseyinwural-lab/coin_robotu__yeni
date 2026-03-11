import { useEffect, useState } from "react";
import { toast } from "sonner";

import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from "@/components/ui/table";
import { apiClient } from "@/lib/api";

const initialForm = {
  name: "all_symbols",
  label: "All Symbols Unified Exposure Group",
  symbols: "",
  max_group_open_positions: 12,
  max_group_directional_positions: 8,
  max_group_risk_pct: 35,
};

export const ExposureGroupsPage = () => {
  const [groups, setGroups] = useState([]);
  const [editingId, setEditingId] = useState(null);
  const [form, setForm] = useState(initialForm);

  const loadGroups = async () => {
    try {
      const { data } = await apiClient.get("/admin-phase3/exposure-groups");
      setGroups(data);
    } catch (error) {
      toast.error(error?.response?.data?.detail || "Exposure group verisi alınamadı");
    }
  };

  useEffect(() => {
    loadGroups();
  }, []);

  const submitGroup = async (event) => {
    event.preventDefault();
    const payload = {
      ...form,
      symbols: form.symbols.split(",").map((item) => item.trim().toUpperCase()).filter(Boolean),
      max_group_open_positions: Number(form.max_group_open_positions),
      max_group_directional_positions: Number(form.max_group_directional_positions),
      max_group_risk_pct: Number(form.max_group_risk_pct),
    };
    try {
      if (editingId) {
        await apiClient.put(`/admin-phase3/exposure-groups/${editingId}`, payload);
        toast.success("Exposure group güncellendi");
      } else {
        await apiClient.post("/admin-phase3/exposure-groups", payload);
        toast.success("Exposure group eklendi");
      }
      setForm(initialForm);
      setEditingId(null);
      loadGroups();
    } catch (error) {
      toast.error(error?.response?.data?.detail || "Exposure group işlemi başarısız");
    }
  };

  return (
    <section className="space-y-4" data-testid="exposure-groups-page">
      <header className="border border-blue-900 bg-slate-900 p-4" data-testid="exposure-groups-header">
        <h2 className="text-4xl font-black uppercase tracking-tight text-blue-300" data-testid="exposure-groups-title">Exposure Group Yönetimi</h2>
        <p className="mt-2 text-sm text-slate-400" data-testid="exposure-groups-description">İlk iterasyon sade mod: tek havuz exposure kontrolü.</p>
      </header>

      <form onSubmit={submitGroup} className="grid gap-3 border border-slate-800 bg-slate-900 p-4 md:grid-cols-2" data-testid="exposure-group-form">
        <Input placeholder="name" value={form.name} onChange={(event) => setForm((prev) => ({ ...prev, name: event.target.value }))} data-testid="exposure-form-name-input" required />
        <Input placeholder="label" value={form.label} onChange={(event) => setForm((prev) => ({ ...prev, label: event.target.value }))} data-testid="exposure-form-label-input" required />
        <Input placeholder="symbols CSV (boş=all)" value={form.symbols} onChange={(event) => setForm((prev) => ({ ...prev, symbols: event.target.value }))} data-testid="exposure-form-symbols-input" />
        <Input type="number" placeholder="max group open positions" value={form.max_group_open_positions} onChange={(event) => setForm((prev) => ({ ...prev, max_group_open_positions: event.target.value }))} data-testid="exposure-form-open-limit-input" required />
        <Input type="number" placeholder="max directional positions" value={form.max_group_directional_positions} onChange={(event) => setForm((prev) => ({ ...prev, max_group_directional_positions: event.target.value }))} data-testid="exposure-form-direction-limit-input" required />
        <Input type="number" step="0.1" placeholder="max group risk %" value={form.max_group_risk_pct} onChange={(event) => setForm((prev) => ({ ...prev, max_group_risk_pct: event.target.value }))} data-testid="exposure-form-risk-limit-input" required />

        <div className="md:col-span-2">
          <Button className="bg-blue-600 text-white hover:bg-blue-700" data-testid="exposure-form-submit-button">
            {editingId ? "Güncelle" : "Group Ekle"}
          </Button>
        </div>
      </form>

      <div className="border border-slate-800 bg-slate-900" data-testid="exposure-groups-table-wrapper">
        <Table data-testid="exposure-groups-table">
          <TableHeader>
            <TableRow>
              <TableHead data-testid="exposure-table-head-name">Name</TableHead>
              <TableHead data-testid="exposure-table-head-label">Label</TableHead>
              <TableHead data-testid="exposure-table-head-symbols">Symbols</TableHead>
              <TableHead data-testid="exposure-table-head-risk">Risk %</TableHead>
              <TableHead data-testid="exposure-table-head-action">Aksiyon</TableHead>
            </TableRow>
          </TableHeader>
          <TableBody>
            {groups.map((group) => (
              <TableRow key={group.id} data-testid={`exposure-row-${group.id}`}>
                <TableCell data-testid={`exposure-name-${group.id}`}>{group.name}</TableCell>
                <TableCell data-testid={`exposure-label-${group.id}`}>{group.label}</TableCell>
                <TableCell className="font-mono text-xs" data-testid={`exposure-symbols-${group.id}`}>{group.symbols.length ? group.symbols.join(",") : "ALL"}</TableCell>
                <TableCell className="font-mono" data-testid={`exposure-risk-${group.id}`}>{group.max_group_risk_pct}</TableCell>
                <TableCell>
                  <Button
                    size="sm"
                    variant="outline"
                    className="border-slate-700 bg-transparent"
                    onClick={() => {
                      setEditingId(group.id);
                      setForm({
                        name: group.name,
                        label: group.label,
                        symbols: group.symbols.join(","),
                        max_group_open_positions: group.max_group_open_positions,
                        max_group_directional_positions: group.max_group_directional_positions,
                        max_group_risk_pct: group.max_group_risk_pct,
                      });
                    }}
                    data-testid={`exposure-edit-${group.id}`}
                  >
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
