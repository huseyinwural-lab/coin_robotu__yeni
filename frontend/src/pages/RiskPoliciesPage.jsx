import { useEffect, useMemo, useState } from "react";
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
  const [formErrors, setFormErrors] = useState({});
  const [reasonById, setReasonById] = useState({});
  const [previewImpact, setPreviewImpact] = useState(null);
  const [selectedPolicy, setSelectedPolicy] = useState(null);
  const [history, setHistory] = useState([]);

  const activePolicy = useMemo(() => (items || []).find((item) => item.is_active) || null, [items]);

  const fetchItems = async () => {
    const { data } = await apiClient.get("/risk-policies");
    setItems(data);
  };

  useEffect(() => {
    fetchItems();
  }, []);

  const handleSubmit = async (event) => {
    event.preventDefault();

    const nextErrors = {};
    if (!form.name.trim()) {
      nextErrors.name = "Policy Name zorunludur.";
    }
    if (!Number(form.position_size_pct) || Number(form.position_size_pct) <= 0) {
      nextErrors.position_size_pct = "Position Size (%) 0'dan büyük olmalı.";
    }
    if (!Number(form.atr_stop_multiplier) || Number(form.atr_stop_multiplier) <= 0) {
      nextErrors.atr_stop_multiplier = "ATR Multiplier 0'dan büyük olmalı.";
    }
    if (!Number(form.risk_reward_ratio) || Number(form.risk_reward_ratio) <= 0) {
      nextErrors.risk_reward_ratio = "Risk Reward Ratio (RR) 0'dan büyük olmalı.";
    }
    if (!Number(form.max_open_positions) || Number(form.max_open_positions) < 1) {
      nextErrors.max_open_positions = "Max Concurrent Trades en az 1 olmalı.";
    }
    if (!Number(form.daily_loss_cutoff_pct) || Number(form.daily_loss_cutoff_pct) <= 0) {
      nextErrors.daily_loss_cutoff_pct = "Max Daily Loss (%) 0'dan büyük olmalı.";
    }

    setFormErrors(nextErrors);
    if (Object.keys(nextErrors).length > 0) {
      toast.error("Form alanlarını kontrol edin");
      return;
    }

    const payload = {
      name: form.name.trim(),
      position_size_pct: Number(form.position_size_pct),
      atr_stop_multiplier: Number(form.atr_stop_multiplier),
      risk_reward_ratio: Number(form.risk_reward_ratio),
      daily_loss_cutoff_pct: Number(form.daily_loss_cutoff_pct),
      max_open_positions: Number(form.max_open_positions),
      max_leverage: Number(form.max_leverage),
      spread_limit_bps: Number(form.spread_limit_bps),
      slippage_limit_bps: Number(form.slippage_limit_bps),
      min_liquidity_usdt: Number(form.min_liquidity_usdt),
      reason_note: reasonById[editingId || 'draft'] || 'manual_update',
    };

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
      setFormErrors({});
      fetchItems();
    } catch (error) {
      toast.error(error?.response?.data?.detail || "Risk policy işlemi başarısız");
    }
  };

  const editPolicy = (item) => {
    setEditingId(item.id);
    setForm(item);
    setFormErrors({});
    setSelectedPolicy(item);
  };

  const requireReason = (id) => {
    const value = String(reasonById[id] || '').trim();
    if (!value) {
      toast.error('Reason zorunlu');
      return null;
    }
    return value;
  };

  const previewPolicyImpact = async (item) => {
    try {
      const { data } = await apiClient.post(`/risk-policies/${item.id}/preview-impact`, {
        current_daily_pnl_pct: 1.5,
        current_open_positions: 1,
        current_leverage: 2,
        current_spread_bps: 12,
        current_slippage_bps: 10,
      });
      setPreviewImpact(data);
      setSelectedPolicy(item);
      toast.success('Risk impact preview hazır');
    } catch (error) {
      toast.error(error?.response?.data?.detail || 'Impact preview başarısız');
    }
  };

  const activatePolicy = async (item) => {
    const reason = requireReason(item.id);
    if (!reason) return;
    try {
      await apiClient.post(`/risk-policies/${item.id}/activate`, { reason });
      await fetchItems();
      toast.success('Policy active oldu');
    } catch (error) {
      toast.error(error?.response?.data?.detail || 'Policy activate başarısız');
    }
  };

  const loadHistory = async (item) => {
    try {
      const { data } = await apiClient.get(`/risk-policies/${item.id}/history`);
      setHistory(data?.items || []);
      setSelectedPolicy(item);
    } catch (error) {
      toast.error(error?.response?.data?.detail || 'Policy history yüklenemedi');
    }
  };

  const rollbackPolicy = async (item) => {
    const reason = requireReason(item.id);
    if (!reason) return;
    try {
      await apiClient.post(`/risk-policies/${item.id}/rollback`, { reason });
      await fetchItems();
      toast.success('Policy rollback tamamlandı');
    } catch (error) {
      toast.error(error?.response?.data?.detail || 'Policy rollback başarısız');
    }
  };

  return (
    <section className="space-y-4" data-testid="risk-policies-page">
      <header className="border border-slate-800 bg-slate-900 p-4" data-testid="risk-policies-header">
        <h2 className="text-4xl font-black uppercase tracking-tight" data-testid="risk-policies-title">Risk Policy Yönetimi</h2>
        <p className="mt-2 text-sm text-slate-400" data-testid="risk-policies-description">Position sizing, ATR, RR ve günlük risk limitleri tek formda yönetilir.</p>
        <div className="mt-3 grid gap-2 rounded border border-cyan-800/40 bg-cyan-950/20 p-3 md:grid-cols-3" data-testid="risk-policies-active-indicator-panel">
          <p className="text-xs" data-testid="risk-policies-active-indicator-status">
            Policy Status: {activePolicy ? activePolicy.lifecycle_state?.toUpperCase() : "INACTIVE"}
          </p>
          <p className="text-xs" data-testid="risk-policies-active-indicator-name">
            Active Policy: {activePolicy?.name || "-"}
          </p>
          <p className="text-xs" data-testid="risk-policies-active-indicator-note">
            {activePolicy ? `${activePolicy.version_group_id} v${activePolicy.version_num} · activated_by=${activePolicy.activated_by || '-'} · enforce=${activePolicy.metadata_json?.enforce ? 'on' : 'pending'}` : 'no active policy selected'}
          </p>
        </div>
      </header>

      <form onSubmit={handleSubmit} className="grid gap-3 border border-slate-800 bg-slate-900 p-4 md:grid-cols-2" data-testid="risk-policy-form">
        <div className="form-group" data-testid="risk-form-group-name">
          <label className="form-label" htmlFor="risk-form-name-input" data-testid="risk-form-name-label">Policy Name</label>
          <Input
            id="risk-form-name-input"
            value={form.name}
            onChange={(event) => setForm((prev) => ({ ...prev, name: event.target.value }))}
            data-testid="risk-form-name-input"
            aria-label="Policy Name"
            aria-describedby="risk-form-name-helper risk-form-name-error"
            required
          />
          <p className="form-helper-text" id="risk-form-name-helper" data-testid="risk-form-name-helper">Risk politikasını ayırt etmek için açık bir ad girin.</p>
          {formErrors.name && <p className="form-error-text" id="risk-form-name-error" data-testid="risk-form-name-error">{formErrors.name}</p>}
        </div>

        <div className="form-group" data-testid="risk-form-group-position-size">
          <label className="form-label" htmlFor="risk-form-position-size-input" data-testid="risk-form-position-size-label">Position Size (%)</label>
          <Input
            id="risk-form-position-size-input"
            type="number"
            step="0.1"
            value={form.position_size_pct}
            onChange={(event) => setForm((prev) => ({ ...prev, position_size_pct: event.target.value }))}
            data-testid="risk-form-position-size-input"
            aria-label="Position Size (%)"
            aria-describedby="risk-form-position-size-helper risk-form-position-size-error"
            required
          />
          <p className="form-helper-text" id="risk-form-position-size-helper" data-testid="risk-form-position-size-helper">Her işlemde kullanılacak pozisyon yüzdesi.</p>
          {formErrors.position_size_pct && <p className="form-error-text" id="risk-form-position-size-error" data-testid="risk-form-position-size-error">{formErrors.position_size_pct}</p>}
        </div>

        <div className="form-group" data-testid="risk-form-group-atr">
          <label className="form-label" htmlFor="risk-form-atr-input" data-testid="risk-form-atr-label">ATR Multiplier</label>
          <Input
            id="risk-form-atr-input"
            type="number"
            step="0.1"
            value={form.atr_stop_multiplier}
            onChange={(event) => setForm((prev) => ({ ...prev, atr_stop_multiplier: event.target.value }))}
            data-testid="risk-form-atr-input"
            aria-label="ATR Multiplier"
            aria-describedby="risk-form-atr-helper risk-form-atr-error"
            required
          />
          <p className="form-helper-text" id="risk-form-atr-helper" data-testid="risk-form-atr-helper">Stop-loss mesafesini ATR bazlı ayarlar.</p>
          {formErrors.atr_stop_multiplier && <p className="form-error-text" id="risk-form-atr-error" data-testid="risk-form-atr-error">{formErrors.atr_stop_multiplier}</p>}
        </div>

        <div className="form-group" data-testid="risk-form-group-rr">
          <label className="form-label" htmlFor="risk-form-rr-input" data-testid="risk-form-rr-label">Risk Reward Ratio (RR)</label>
          <Input
            id="risk-form-rr-input"
            type="number"
            step="0.1"
            value={form.risk_reward_ratio}
            onChange={(event) => setForm((prev) => ({ ...prev, risk_reward_ratio: event.target.value }))}
            data-testid="risk-form-rr-input"
            aria-label="Risk Reward Ratio (RR)"
            aria-describedby="risk-form-rr-helper risk-form-rr-error"
            required
          />
          <p className="form-helper-text" id="risk-form-rr-helper" data-testid="risk-form-rr-helper">Hedef kazanç / risk oranını belirler.</p>
          {formErrors.risk_reward_ratio && <p className="form-error-text" id="risk-form-rr-error" data-testid="risk-form-rr-error">{formErrors.risk_reward_ratio}</p>}
        </div>

        <div className="form-group" data-testid="risk-form-group-max-open">
          <label className="form-label" htmlFor="risk-form-max-open-input" data-testid="risk-form-max-open-label">Max Concurrent Trades</label>
          <Input
            id="risk-form-max-open-input"
            type="number"
            value={form.max_open_positions}
            onChange={(event) => setForm((prev) => ({ ...prev, max_open_positions: event.target.value }))}
            data-testid="risk-form-max-open-input"
            aria-label="Max Concurrent Trades"
            aria-describedby="risk-form-max-open-helper risk-form-max-open-error"
            required
          />
          <p className="form-helper-text" id="risk-form-max-open-helper" data-testid="risk-form-max-open-helper">Aynı anda açık kalabilecek işlem sayısı üst limiti.</p>
          {formErrors.max_open_positions && <p className="form-error-text" id="risk-form-max-open-error" data-testid="risk-form-max-open-error">{formErrors.max_open_positions}</p>}
        </div>

        <div className="form-group" data-testid="risk-form-group-daily-loss">
          <label className="form-label" htmlFor="risk-form-cutoff-input" data-testid="risk-form-cutoff-label">Max Daily Loss (%)</label>
          <Input
            id="risk-form-cutoff-input"
            type="number"
            step="0.1"
            value={form.daily_loss_cutoff_pct}
            onChange={(event) => setForm((prev) => ({ ...prev, daily_loss_cutoff_pct: event.target.value }))}
            data-testid="risk-form-cutoff-input"
            aria-label="Max Daily Loss (%)"
            aria-describedby="risk-form-cutoff-helper risk-form-cutoff-error"
            required
          />
          <p className="form-helper-text" id="risk-form-cutoff-helper" data-testid="risk-form-cutoff-helper">Günlük kayıp yüzdesi bu değeri aşarsa yeni işlem engellenir.</p>
          {formErrors.daily_loss_cutoff_pct && <p className="form-error-text" id="risk-form-cutoff-error" data-testid="risk-form-cutoff-error">{formErrors.daily_loss_cutoff_pct}</p>}
        </div>

        <div className="flex gap-2 md:col-span-2">
          <Input value={reasonById[editingId || 'draft'] || ''} onChange={(event) => setReasonById((prev) => ({ ...prev, [editingId || 'draft']: event.target.value }))} placeholder="reason note" data-testid="risk-form-reason-input" />
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
                setFormErrors({});
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
              <TableHead data-testid="risk-table-head-status">Status</TableHead>
              <TableHead data-testid="risk-table-head-version">Version</TableHead>
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
                <TableCell data-testid={`risk-table-status-${item.id}`}>
                  <span className={`rounded px-2 py-1 text-xs font-semibold ${activePolicy?.id === item.id ? "bg-emerald-200 text-emerald-900" : "bg-slate-300 text-slate-800"}`} data-testid={`risk-table-status-badge-${item.id}`}>
                    {item.is_active ? "ACTIVE" : item.lifecycle_state?.toUpperCase() || 'INACTIVE'}
                  </span>
                </TableCell>
                <TableCell data-testid={`risk-table-version-${item.id}`}>v{item.version_num}</TableCell>
                <TableCell>
                  <div className="flex flex-wrap gap-2">
                    <Button size="sm" variant="outline" className="border-slate-600 bg-transparent" onClick={() => editPolicy(item)} data-testid={`risk-table-edit-${item.id}`}>Düzenle</Button>
                    <Button size="sm" variant="outline" className="border-cyan-600 bg-transparent" onClick={() => previewPolicyImpact(item)} data-testid={`risk-table-preview-${item.id}`}>Preview</Button>
                    <Button size="sm" variant="outline" className="border-emerald-600 bg-transparent" onClick={() => activatePolicy(item)} data-testid={`risk-table-activate-${item.id}`}>Set Active</Button>
                    <Button size="sm" variant="outline" className="border-amber-600 bg-transparent" onClick={() => loadHistory(item)} data-testid={`risk-table-history-${item.id}`}>History</Button>
                    <Button size="sm" variant="outline" className="border-rose-600 bg-transparent" onClick={() => rollbackPolicy(item)} data-testid={`risk-table-rollback-${item.id}`}>Rollback</Button>
                  </div>
                  <Input className="mt-2" value={reasonById[item.id] || ''} onChange={(event) => setReasonById((prev) => ({ ...prev, [item.id]: event.target.value }))} placeholder="reason" data-testid={`risk-table-reason-${item.id}`} />
                </TableCell>
              </TableRow>
            ))}
          </TableBody>
        </Table>
      </div>

      <div className="grid gap-4 lg:grid-cols-2" data-testid="risk-policy-observability-grid">
        <article className="border border-slate-800 bg-slate-900 p-4" data-testid="risk-policy-impact-preview-panel">
          <h3 className="text-base font-semibold" data-testid="risk-policy-impact-preview-title">Real-time Risk Impact Preview</h3>
          <pre className="mt-3 overflow-x-auto bg-slate-950 p-3 text-xs text-slate-200" data-testid="risk-policy-impact-preview-json">{JSON.stringify(previewImpact || {}, null, 2)}</pre>
        </article>
        <article className="border border-slate-800 bg-slate-900 p-4" data-testid="risk-policy-history-panel">
          <h3 className="text-base font-semibold" data-testid="risk-policy-history-title">Version / History / Rollback</h3>
          <pre className="mt-3 overflow-x-auto bg-slate-950 p-3 text-xs text-slate-200" data-testid="risk-policy-history-json">{JSON.stringify(history || [], null, 2)}</pre>
        </article>
        <article className="border border-slate-800 bg-slate-900 p-4" data-testid="risk-policy-enforce-panel">
          <h3 className="text-base font-semibold" data-testid="risk-policy-enforce-title">Execution Enforce Kanıtı</h3>
          <pre className="mt-3 overflow-x-auto bg-slate-950 p-3 text-xs text-slate-200" data-testid="risk-policy-enforce-json">{JSON.stringify(activePolicy?.metadata_json?.enforce || {}, null, 2)}</pre>
        </article>
        <article className="border border-slate-800 bg-slate-900 p-4" data-testid="risk-policy-kill-switch-panel">
          <h3 className="text-base font-semibold" data-testid="risk-policy-kill-switch-title">Kill Switch Görünürlüğü</h3>
          <pre className="mt-3 overflow-x-auto bg-slate-950 p-3 text-xs text-slate-200" data-testid="risk-policy-kill-switch-json">{JSON.stringify({ state: activePolicy?.metadata_json?.kill_switch || 'unknown', source: 'global', reason: activePolicy?.status_reason || null }, null, 2)}</pre>
        </article>
      </div>
    </section>
  );
};
