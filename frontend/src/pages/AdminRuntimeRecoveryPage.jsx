import { useCallback, useEffect, useState } from "react";
import { toast } from "sonner";

import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { apiClient } from "@/lib/api";

export const AdminRuntimeRecoveryPage = () => {
  const [intents, setIntents] = useState([]);
  const [loading, setLoading] = useState(true);
  const [thresholds, setThresholds] = useState({
    pending_threshold: 60,
    submitted_threshold: 120,
    partial_threshold: 300,
  });

  const loadIntents = useCallback(async () => {
    setLoading(true);
    try {
      const { data } = await apiClient.get("/strategy-domain/admin/runtime/stuck-intents", { params: thresholds });
      setIntents(data || []);
    } catch (error) {
      toast.error(error?.response?.data?.detail || "Stuck intent listesi alınamadı");
    } finally {
      setLoading(false);
    }
  }, [thresholds]);

  useEffect(() => {
    loadIntents();
  }, [loadIntents]);

  const runAction = async (intentId, action) => {
    try {
      await apiClient.post(`/strategy-domain/admin/runtime/stuck-intents/${intentId}/${action}`);
      toast.success(`Recovery ${action} tamamlandı`);
      await loadIntents();
    } catch (error) {
      toast.error(error?.response?.data?.detail || "Recovery aksiyonu başarısız");
    }
  };

  return (
    <section className="space-y-4" data-testid="admin-runtime-recovery-page">
      <header className="border border-emerald-500/60 bg-slate-900 p-4" data-testid="admin-runtime-recovery-header">
        <h2 className="text-4xl font-black uppercase tracking-tight text-emerald-300" data-testid="admin-runtime-recovery-title">
          Stuck Intent Recovery
        </h2>
        <p className="mt-2 text-sm text-slate-400" data-testid="admin-runtime-recovery-description">
          Pending/submitted/partial intent’leri manuel kurtarma paneli.
        </p>
        <div className="mt-3 grid gap-2 md:grid-cols-3" data-testid="admin-runtime-recovery-thresholds">
          <Input
            type="number"
            value={thresholds.pending_threshold}
            onChange={(event) => setThresholds((prev) => ({ ...prev, pending_threshold: event.target.value }))}
            placeholder="pending threshold"
            data-testid="admin-runtime-recovery-pending-input"
          />
          <Input
            type="number"
            value={thresholds.submitted_threshold}
            onChange={(event) => setThresholds((prev) => ({ ...prev, submitted_threshold: event.target.value }))}
            placeholder="submitted threshold"
            data-testid="admin-runtime-recovery-submitted-input"
          />
          <Input
            type="number"
            value={thresholds.partial_threshold}
            onChange={(event) => setThresholds((prev) => ({ ...prev, partial_threshold: event.target.value }))}
            placeholder="partial threshold"
            data-testid="admin-runtime-recovery-partial-input"
          />
        </div>
        <Button className="mt-3 bg-emerald-500 text-black hover:bg-emerald-600" onClick={loadIntents} data-testid="admin-runtime-recovery-refresh">
          Refresh
        </Button>
      </header>

      {loading && <p className="text-sm text-slate-400" data-testid="admin-runtime-recovery-loading">Yükleniyor...</p>}
      {!loading && intents.length === 0 && (
        <p className="text-sm text-slate-400" data-testid="admin-runtime-recovery-empty">Stuck intent yok.</p>
      )}

      <div className="space-y-3" data-testid="admin-runtime-recovery-list">
        {intents.map((intent) => (
          <div key={intent.intent_id} className="border border-slate-700 bg-slate-900 p-3" data-testid={`runtime-recovery-row-${intent.intent_id}`}>
            <div className="grid gap-2 md:grid-cols-2 xl:grid-cols-3" data-testid={`runtime-recovery-grid-${intent.intent_id}`}>
              <p className="text-sm" data-testid={`runtime-recovery-intent-${intent.intent_id}`}>intent: {intent.intent_id}</p>
              <p className="text-sm" data-testid={`runtime-recovery-status-${intent.intent_id}`}>status: {intent.status}</p>
              <p className="text-sm" data-testid={`runtime-recovery-reason-${intent.intent_id}`}>reason: {intent.reason}</p>
              <p className="text-xs text-slate-400" data-testid={`runtime-recovery-age-${intent.intent_id}`}>age: {intent.age_seconds.toFixed(1)}s</p>
              <p className="text-xs text-slate-400" data-testid={`runtime-recovery-symbol-${intent.intent_id}`}>symbol: {intent.symbol}</p>
              <p className="text-xs text-slate-400" data-testid={`runtime-recovery-strategy-${intent.intent_id}`}>strategy: {intent.strategy_id}</p>
            </div>
            <div className="mt-3 flex flex-wrap gap-2" data-testid={`runtime-recovery-actions-${intent.intent_id}`}>
              <Button size="sm" className="bg-emerald-500 text-black hover:bg-emerald-600" onClick={() => runAction(intent.intent_id, "sync_exchange_state")} data-testid={`runtime-recovery-sync-${intent.intent_id}`}>
                Sync Exchange
              </Button>
              <Button size="sm" variant="outline" className="border-slate-500 text-slate-200" onClick={() => runAction(intent.intent_id, "replay_event_chain")} data-testid={`runtime-recovery-replay-${intent.intent_id}`}>
                Replay Chain
              </Button>
              <Button size="sm" variant="outline" className="border-orange-400 text-orange-300" onClick={() => runAction(intent.intent_id, "cancel_intent")} data-testid={`runtime-recovery-cancel-${intent.intent_id}`}>
                Cancel Intent
              </Button>
              <Button size="sm" variant="outline" className="border-red-400 text-red-300" onClick={() => runAction(intent.intent_id, "mark_failed")} data-testid={`runtime-recovery-mark-failed-${intent.intent_id}`}>
                Mark Failed
              </Button>
            </div>
          </div>
        ))}
      </div>
    </section>
  );
};
