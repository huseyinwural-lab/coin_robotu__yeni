import { Input } from "@/components/ui/input";
import { Button } from "@/components/ui/button";

export const OverrideForm = ({
  form,
  setForm,
  canApply,
  simulationReady,
  onRequestApply,
  isSubmitting,
}) => {
  const reasonOk = String(form.override_reason || "").trim().length >= 12;
  const hasExpiry = Boolean(form.override_expires_at || Number(form.override_ttl_minutes || 0) > 0);
  const canSubmit = canApply && simulationReady && reasonOk && hasExpiry && String(form.override_action_type || "").trim().length > 0;

  return (
    <section className="border border-slate-800 bg-slate-900 p-4" data-testid="strategy-intelligence-override-form-panel">
      <p className="text-xs uppercase tracking-widest text-slate-500" data-testid="strategy-intelligence-override-form-title">Override Form (simulate → confirm → apply)</p>

      {!simulationReady && (
        <p className="mt-2 text-xs text-amber-300" data-testid="strategy-intelligence-simulation-required-guard">
          Simulation required: önce Run Simulation çalıştırın.
        </p>
      )}

      <div className="mt-2 grid gap-2 md:grid-cols-2" data-testid="strategy-intelligence-override-form-grid">
        <Input
          placeholder="override_action_type"
          value={form.override_action_type}
          onChange={(event) => setForm((prev) => ({ ...prev, override_action_type: event.target.value }))}
          data-testid="strategy-intelligence-override-action-type-input"
        />
        <Input
          placeholder="target_id (örn user_id)"
          value={form.override_target_id}
          onChange={(event) => setForm((prev) => ({ ...prev, override_target_id: event.target.value }))}
          data-testid="strategy-intelligence-override-target-id-input"
        />
        <Input
          placeholder="reason (min 12 karakter)"
          value={form.override_reason}
          onChange={(event) => setForm((prev) => ({ ...prev, override_reason: event.target.value }))}
          data-testid="strategy-intelligence-override-reason-input"
        />
        <Input
          type="datetime-local"
          placeholder="expires_at"
          value={form.override_expires_at}
          onChange={(event) => setForm((prev) => ({ ...prev, override_expires_at: event.target.value }))}
          data-testid="strategy-intelligence-override-expires-at-input"
        />
        <Input
          type="number"
          min="1"
          placeholder="ttl_minutes"
          value={form.override_ttl_minutes}
          onChange={(event) => setForm((prev) => ({ ...prev, override_ttl_minutes: event.target.value }))}
          data-testid="strategy-intelligence-override-ttl-input"
        />
      </div>

      <div className="mt-3" data-testid="strategy-intelligence-override-form-actions">
        <Button
          onClick={onRequestApply}
          disabled={!canSubmit || isSubmitting}
          className="border border-rose-500 bg-rose-700 text-white"
          data-testid="strategy-intelligence-override-apply-request-button"
        >
          {isSubmitting ? "Uygulanıyor..." : "Apply Override"}
        </Button>
      </div>
    </section>
  );
};
