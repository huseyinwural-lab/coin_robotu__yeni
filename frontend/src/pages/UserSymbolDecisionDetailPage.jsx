import { useEffect, useState } from "react";
import { useNavigate, useParams } from "react-router-dom";
import { toast } from "sonner";

import { Button } from "@/components/ui/button";
import { apiClient } from "@/lib/api";
import { DecisionCard } from "@/pages/user/components/DecisionCard";
import { ExplainabilityDrawer } from "@/pages/user/components/ExplainabilityDrawer";
import { UserLearningImpactWidget } from "@/pages/user/components/UserLearningImpactWidget";

export const UserSymbolDecisionDetailPage = () => {
  const navigate = useNavigate();
  const { symbol } = useParams();
  const normalizedSymbol = String(symbol || "").toUpperCase();

  const [decisionCard, setDecisionCard] = useState(null);
  const [explainability, setExplainability] = useState(null);
  const [loading, setLoading] = useState(true);
  const [drawerOpen, setDrawerOpen] = useState(false);
  const [drawerLoading, setDrawerLoading] = useState(false);
  const [impactStrategyId, setImpactStrategyId] = useState("");
  const [impactFamily, setImpactFamily] = useState("");

  const formatDateLabel = (value) => {
    if (!value) {
      return "-";
    }
    const parsed = new Date(value);
    if (Number.isNaN(parsed.getTime())) {
      return "-";
    }
    return parsed.toLocaleString("tr-TR");
  };

  const loadExplainability = async () => {
    if (!normalizedSymbol) {
      setExplainability(null);
      return;
    }
    setDrawerLoading(true);
    try {
      const { data } = await apiClient.get(`/user/explainability/${encodeURIComponent(normalizedSymbol)}`);
      setExplainability(data || null);
    } catch (error) {
      setExplainability(null);
      toast.error(error?.response?.data?.detail || "Explainability yüklenemedi");
    } finally {
      setDrawerLoading(false);
    }
  };

  const loadDecisionDetail = async ({ silent = false } = {}) => {
    if (!normalizedSymbol) {
      return;
    }
    if (!silent) {
      setLoading(true);
    }
    try {
      const { data } = await apiClient.get(`/user/decision-cards/${encodeURIComponent(normalizedSymbol)}`);
      setDecisionCard(data || null);
      setImpactStrategyId(data?.top_contributors?.[0]?.strategy_id || "");
      setImpactFamily(data?.dominant_family || "");
      await loadExplainability();
    } catch (error) {
      toast.error(error?.response?.data?.detail || "Symbol detail yüklenemedi");
      setDecisionCard(null);
    } finally {
      if (!silent) {
        setLoading(false);
      }
    }
  };

  useEffect(() => {
    loadDecisionDetail();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [normalizedSymbol]);

  const openImpactFromCard = (card) => {
    setImpactStrategyId(card?.top_contributors?.[0]?.strategy_id || "");
    setImpactFamily(card?.dominant_family || "");
  };

  useEffect(() => {
    const timer = setInterval(() => {
      loadDecisionDetail({ silent: true });
    }, 10000);
    return () => clearInterval(timer);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [normalizedSymbol]);

  return (
    <section className="space-y-4" data-testid="user-symbol-decision-detail-page">
      <header className="border border-slate-800 bg-slate-900 p-4" data-testid="user-symbol-decision-detail-header">
        <h2 className="text-4xl font-black uppercase tracking-tight" data-testid="user-symbol-decision-detail-title">Symbol Detail</h2>
        <p className="mt-2 text-sm text-slate-400" data-testid="user-symbol-decision-detail-description">
          {normalizedSymbol || "-"} için decision card + explainability detay görünümü.
        </p>
      </header>

      <div className="flex flex-wrap items-center gap-2" data-testid="user-symbol-decision-detail-toolbar">
        <Button type="button" variant="outline" onClick={() => navigate("/user/scanner")} data-testid="user-symbol-decision-detail-back-button">
          Scanner'a Dön
        </Button>
        <Button type="button" variant="outline" onClick={() => loadDecisionDetail()} data-testid="user-symbol-decision-detail-refresh-button">
          Yenile
        </Button>
        <p className="text-xs text-slate-400" data-testid="user-symbol-decision-detail-auto-refresh">Auto Refresh: 10s</p>
      </div>

      {loading && <div className="rounded border border-slate-700 bg-slate-900 p-3 text-sm" data-testid="user-symbol-decision-detail-loading">Yükleniyor...</div>}
      {!loading && !decisionCard && (
        <div className="rounded border border-slate-700 bg-slate-900 p-3 text-sm" data-testid="user-symbol-decision-detail-empty">
          Symbol için decision card bulunamadı.
        </div>
      )}

      {!loading && decisionCard && (
        <div className="grid gap-3 md:grid-cols-3" data-testid="user-symbol-decision-detail-card-grid">
          <DecisionCard card={decisionCard} onOpenExplainability={() => setDrawerOpen(true)} onOpenImpactSimulator={openImpactFromCard} />
          <div className="rounded border border-fuchsia-700/50 bg-fuchsia-950/20 p-3" data-testid="user-symbol-decision-detail-summary-panel">
            <p className="text-sm font-semibold" data-testid="user-symbol-decision-detail-summary-title">Explainability Özeti</p>
            <p className="mt-2 text-xs" data-testid="user-symbol-decision-detail-summary-symbol">Symbol: {normalizedSymbol}</p>
            <p className="text-xs" data-testid="user-symbol-decision-detail-summary-updated">Updated: {formatDateLabel(decisionCard.updated_at || decisionCard.generated_at)}</p>
            <Button type="button" className="mt-3" variant="outline" onClick={() => setDrawerOpen(true)} data-testid="user-symbol-decision-detail-open-drawer-button">
              Explainability Drawer Aç
            </Button>
          </div>
          <div data-testid="user-symbol-decision-detail-learning-impact-corner">
            <UserLearningImpactWidget
              symbol={normalizedSymbol}
              defaultStrategyId={impactStrategyId}
              defaultFamily={impactFamily}
              testIdPrefix="user-symbol-detail-learning-impact"
            />
          </div>
        </div>
      )}

      <ExplainabilityDrawer
        isOpen={drawerOpen}
        onOpenChange={setDrawerOpen}
        selectedSymbol={normalizedSymbol}
        isLoading={drawerLoading}
        explainability={explainability}
        formatDateLabel={formatDateLabel}
      />
    </section>
  );
};
