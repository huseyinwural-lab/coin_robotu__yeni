import { useMemo, useState } from "react";
import { toast } from "sonner";

import { Button } from "@/components/ui/button";
import { Tooltip, TooltipContent, TooltipProvider, TooltipTrigger } from "@/components/ui/tooltip";
import { apiClient } from "@/lib/api";

const metricHelp = {
  projected_risk_score: "0-1 arası tahmini toplam risk seviyesi.",
  projected_gate_decision: "Risk eşiğine göre beklenen gate sonucu.",
  expected_hit_rate_delta: "Uygulanırsa başarı oranında beklenen değişim.",
  expected_avg_return_delta: "Uygulanırsa ortalama getiride beklenen değişim.",
  allocation_drift_delta: "Sermaye dağılımında tahmini kayma etkisi.",
  hedge_effect_score: "Hedge etkisinin beklenen kuvvet skoru (0-1).",
};

export const UserLearningImpactWidget = ({
  symbol,
  defaultStrategyId,
  defaultFamily,
  compact = false,
  testIdPrefix = "user-learning-impact",
}) => {
  const [form, setForm] = useState({
    strategy_id: defaultStrategyId || "",
    family: defaultFamily || "",
    recommendation_type: "decrease_weight_recommendation",
    suggested_weight_multiplier: "0.8",
  });
  const [result, setResult] = useState(null);
  const [note, setNote] = useState("");
  const [isSimulating, setIsSimulating] = useState(false);
  const [isSending, setIsSending] = useState(false);

  const title = useMemo(() => (compact ? "Impact Sim" : "Learning Recommendation Impact Simulator"), [compact]);

  const runSimulation = async () => {
    setIsSimulating(true);
    try {
      const payload = {
        symbol: symbol || null,
        strategy_id: String(form.strategy_id || "").trim() || null,
        family: String(form.family || "").trim() || null,
        recommendation_type: form.recommendation_type,
        suggested_weight_multiplier: form.suggested_weight_multiplier ? Number(form.suggested_weight_multiplier) : null,
      };
      const { data } = await apiClient.post("/user/learning-simulator/simulate", payload);
      setResult(data || null);
      toast.success("User impact simülasyonu hazır");
    } catch (error) {
      toast.error(error?.response?.data?.detail || "Simülasyon başarısız");
    } finally {
      setIsSimulating(false);
    }
  };

  const submitSuggestion = async () => {
    if (!result) {
      toast.error("Önce simülasyon çalıştırın");
      return;
    }
    setIsSending(true);
    try {
      await apiClient.post("/user/learning-simulator/suggestions", {
        symbol: symbol || null,
        strategy_id: form.strategy_id || null,
        family: form.family || null,
        recommendation_type: form.recommendation_type,
        simulation_payload: result,
        note,
      });
      toast.success("Öneri admin ekibine gönderildi");
      setNote("");
    } catch (error) {
      toast.error(error?.response?.data?.detail || "Öneri gönderilemedi");
    } finally {
      setIsSending(false);
    }
  };

  return (
    <TooltipProvider>
      <section className="rounded border border-blue-700/60 bg-blue-950/20 p-3" data-testid={`${testIdPrefix}-panel`}>
        <p className="text-xs uppercase tracking-widest text-blue-300" data-testid={`${testIdPrefix}-title`}>{title}</p>
        <p className="mt-1 text-xs text-blue-100" data-testid={`${testIdPrefix}-subtitle`}>Read-only · admin apply ayrı süreç</p>

        <div className="mt-2 grid gap-2 md:grid-cols-2" data-testid={`${testIdPrefix}-form-grid`}>
          <input
            value={form.strategy_id}
            onChange={(event) => setForm((prev) => ({ ...prev, strategy_id: event.target.value }))}
            placeholder="strategy_id"
            className="h-9 rounded border border-blue-700 bg-black px-2 text-xs"
            data-testid={`${testIdPrefix}-strategy-id-input`}
          />
          <input
            value={form.family}
            onChange={(event) => setForm((prev) => ({ ...prev, family: event.target.value }))}
            placeholder="family"
            className="h-9 rounded border border-blue-700 bg-black px-2 text-xs"
            data-testid={`${testIdPrefix}-family-input`}
          />
          <select
            value={form.recommendation_type}
            onChange={(event) => setForm((prev) => ({ ...prev, recommendation_type: event.target.value }))}
            className="h-9 rounded border border-blue-700 bg-black px-2 text-xs"
            data-testid={`${testIdPrefix}-recommendation-type-select`}
          >
            <option value="disable_recommendation">disable_recommendation</option>
            <option value="decrease_weight_recommendation">decrease_weight_recommendation</option>
            <option value="increase_weight_recommendation">increase_weight_recommendation</option>
          </select>
          <input
            type="number"
            min="0.1"
            max="3"
            step="0.05"
            value={form.suggested_weight_multiplier}
            onChange={(event) => setForm((prev) => ({ ...prev, suggested_weight_multiplier: event.target.value }))}
            className="h-9 rounded border border-blue-700 bg-black px-2 text-xs"
            data-testid={`${testIdPrefix}-weight-multiplier-input`}
          />
        </div>

        <div className="mt-2 flex flex-wrap gap-2" data-testid={`${testIdPrefix}-actions`}>
          <Button type="button" variant="outline" size="sm" disabled={isSimulating} onClick={runSimulation} data-testid={`${testIdPrefix}-simulate-button`}>
            {isSimulating ? "Simulating..." : "Impact Simulate"}
          </Button>
          <Button type="button" variant="outline" size="sm" disabled={isSending || !result} onClick={submitSuggestion} data-testid={`${testIdPrefix}-send-admin-suggestion-button`}>
            {isSending ? "Gönderiliyor..." : "Admin’e Öneri Gönder"}
          </Button>
        </div>

        <input
          value={note}
          onChange={(event) => setNote(event.target.value)}
          placeholder="Admin notu (opsiyonel)"
          className="mt-2 h-9 w-full rounded border border-blue-700 bg-black px-2 text-xs"
          data-testid={`${testIdPrefix}-note-input`}
        />

        {result && (
          <div className="mt-3 grid gap-1 md:grid-cols-2" data-testid={`${testIdPrefix}-metrics-grid`}>
            {Object.entries(metricHelp).map(([key, help]) => (
              <div key={key} className="rounded border border-blue-800/50 px-2 py-1" data-testid={`${testIdPrefix}-metric-${key}`}>
                <Tooltip>
                  <TooltipTrigger asChild>
                    <p className="cursor-help text-[11px] text-blue-100" data-testid={`${testIdPrefix}-metric-label-${key}`}>
                      {key}
                    </p>
                  </TooltipTrigger>
                  <TooltipContent data-testid={`${testIdPrefix}-metric-tooltip-${key}`}>{help}</TooltipContent>
                </Tooltip>
                <p className="text-xs" data-testid={`${testIdPrefix}-metric-value-${key}`}>{String(result[key])}</p>
              </div>
            ))}
          </div>
        )}
      </section>
    </TooltipProvider>
  );
};
