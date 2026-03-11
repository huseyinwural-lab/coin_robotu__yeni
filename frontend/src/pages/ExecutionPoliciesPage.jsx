import { useEffect, useState } from "react";
import { toast } from "sonner";

import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from "@/components/ui/table";
import { apiClient } from "@/lib/api";

const initialForm = {
  strategy_type: "trend_following",
  execution_style: "balanced",
  order_preference: "limit_first",
  timeout_seconds: 8,
  fallback_behavior: "market_fallback",
  partial_fill_tolerance_pct: 60,
  execution_urgency: "medium",
  retry_limit: 2,
  is_active: true,
};

export const ExecutionPoliciesPage = () => {
  const [policies, setPolicies] = useState([]);
  const [editingId, setEditingId] = useState(null);
  const [form, setForm] = useState(initialForm);

  const loadPolicies = async () => {
    try {
      const { data } = await apiClient.get("/admin-phase3/execution-policies");
      setPolicies(data);
    } catch (error) {
      toast.error(error?.response?.data?.detail || "Execution policy verisi alınamadı");
    }
  };

  useEffect(() => {
    loadPolicies();
  }, []);

  const submitPolicy = async (event) => {
    event.preventDefault();
    const payload = {
      ...form,
      timeout_seconds: Number(form.timeout_seconds),
      partial_fill_tolerance_pct: Number(form.partial_fill_tolerance_pct),
      retry_limit: Number(form.retry_limit),
    };
    try {
      if (editingId) {
        await apiClient.put(`/admin-phase3/execution-policies/${editingId}`, payload);
        toast.success("Execution policy güncellendi");
      } else {
        await apiClient.post("/admin-phase3/execution-policies", payload);
        toast.success("Execution policy oluşturuldu");
      }
      setForm(initialForm);
      setEditingId(null);
      loadPolicies();
    } catch (error) {
      toast.error(error?.response?.data?.detail || "Execution policy işlemi başarısız");
    }
  };

  return (
    <section className="space-y-4" data-testid="execution-policies-page">
      <header className="border border-blue-900 bg-slate-900 p-4" data-testid="execution-policies-header">
        <h2 className="text-4xl font-black uppercase tracking-tight text-blue-300" data-testid="execution-policies-title">
          Execution Policy Yönetimi
        </h2>
        <p className="mt-2 text-sm text-slate-400" data-testid="execution-policies-description">
          Breakout=aggressive, MeanReversion=passive, TrendFollowing=balanced, VolatilityExpansion=balanced
        </p>
      </header>

      <form onSubmit={submitPolicy} className="grid gap-3 border border-slate-800 bg-slate-900 p-4 md:grid-cols-2" data-testid="execution-policy-form">
        <Input placeholder="strategy_type" value={form.strategy_type} onChange={(event) => setForm((prev) => ({ ...prev, strategy_type: event.target.value }))} data-testid="policy-form-strategy-input" required />
        <Input placeholder="execution_style" value={form.execution_style} onChange={(event) => setForm((prev) => ({ ...prev, execution_style: event.target.value }))} data-testid="policy-form-style-input" required />
        <Input placeholder="order_preference" value={form.order_preference} onChange={(event) => setForm((prev) => ({ ...prev, order_preference: event.target.value }))} data-testid="policy-form-order-input" required />
        <Input type="number" placeholder="timeout_seconds" value={form.timeout_seconds} onChange={(event) => setForm((prev) => ({ ...prev, timeout_seconds: event.target.value }))} data-testid="policy-form-timeout-input" required />
        <Input placeholder="fallback_behavior" value={form.fallback_behavior} onChange={(event) => setForm((prev) => ({ ...prev, fallback_behavior: event.target.value }))} data-testid="policy-form-fallback-input" required />
        <Input type="number" placeholder="partial_fill_tolerance_pct" value={form.partial_fill_tolerance_pct} onChange={(event) => setForm((prev) => ({ ...prev, partial_fill_tolerance_pct: event.target.value }))} data-testid="policy-form-partial-fill-input" required />
        <Input placeholder="execution_urgency" value={form.execution_urgency} onChange={(event) => setForm((prev) => ({ ...prev, execution_urgency: event.target.value }))} data-testid="policy-form-urgency-input" required />
        <Input type="number" placeholder="retry_limit" value={form.retry_limit} onChange={(event) => setForm((prev) => ({ ...prev, retry_limit: event.target.value }))} data-testid="policy-form-retry-input" required />
        <div className="md:col-span-2">
          <Button className="bg-blue-600 text-white hover:bg-blue-700" data-testid="policy-form-submit-button">
            {editingId ? "Güncelle" : "Policy Ekle"}
          </Button>
        </div>
      </form>

      <div className="border border-slate-800 bg-slate-900" data-testid="execution-policies-table-wrapper">
        <Table data-testid="execution-policies-table">
          <TableHeader>
            <TableRow>
              <TableHead data-testid="policy-table-head-strategy">Strategy</TableHead>
              <TableHead data-testid="policy-table-head-style">Style</TableHead>
              <TableHead data-testid="policy-table-head-order">Order</TableHead>
              <TableHead data-testid="policy-table-head-timeout">Timeout</TableHead>
              <TableHead data-testid="policy-table-head-action">Aksiyon</TableHead>
            </TableRow>
          </TableHeader>
          <TableBody>
            {policies.map((policy) => (
              <TableRow key={policy.id} data-testid={`policy-table-row-${policy.id}`}>
                <TableCell data-testid={`policy-strategy-${policy.id}`}>{policy.strategy_type}</TableCell>
                <TableCell data-testid={`policy-style-${policy.id}`}>{policy.execution_style}</TableCell>
                <TableCell data-testid={`policy-order-${policy.id}`}>{policy.order_preference}</TableCell>
                <TableCell className="font-mono" data-testid={`policy-timeout-${policy.id}`}>{policy.timeout_seconds}s</TableCell>
                <TableCell>
                  <Button
                    size="sm"
                    variant="outline"
                    className="border-slate-700 bg-transparent"
                    onClick={() => {
                      setEditingId(policy.id);
                      setForm({
                        strategy_type: policy.strategy_type,
                        execution_style: policy.execution_style,
                        order_preference: policy.order_preference,
                        timeout_seconds: policy.timeout_seconds,
                        fallback_behavior: policy.fallback_behavior,
                        partial_fill_tolerance_pct: policy.partial_fill_tolerance_pct,
                        execution_urgency: policy.execution_urgency,
                        retry_limit: policy.retry_limit,
                        is_active: policy.is_active,
                      });
                    }}
                    data-testid={`policy-edit-${policy.id}`}
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
