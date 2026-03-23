import { useCallback, useEffect, useMemo, useState } from "react";
import { useNavigate, useParams } from "react-router-dom";
import { toast } from "sonner";

import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { apiClient } from "@/lib/api";

const windowOptions = ["24h", "7d", "30d"];
const INITIAL_VISIBLE_NODE_COUNT = 80;
const LOAD_MORE_NODE_COUNT = 80;

export default function AdminStrategyTimelineChainPage() {
  const { chainId } = useParams();
  const navigate = useNavigate();

  const [windowRange, setWindowRange] = useState("30d");
  const [strategyId, setStrategyId] = useState("");
  const [loading, setLoading] = useState(false);
  const [nodes, setNodes] = useState([]);
  const [summary, setSummary] = useState(null);
  const [showNodes, setShowNodes] = useState(false);
  const [visibleCount, setVisibleCount] = useState(INITIAL_VISIBLE_NODE_COUNT);
  const [onlyBrokenLinks, setOnlyBrokenLinks] = useState(false);
  const [includeSeed, setIncludeSeed] = useState(false);
  const [expandedMap, setExpandedMap] = useState({});
  const [meta, setMeta] = useState(null);

  const loadChain = useCallback(async () => {
    if (!chainId) {
      setNodes([]);
      setSummary(null);
      return;
    }
    setLoading(true);
    try {
      const { data } = await apiClient.get(`/admin/strategy/timeline/${encodeURIComponent(chainId)}`, {
        params: {
          window: windowRange,
          strategy_id: strategyId || null,
          include_seed: includeSeed,
        },
      });
      setNodes(data?.nodes || []);
      setSummary(data?.summary || null);
      setMeta(data?.meta || null);
      setVisibleCount(INITIAL_VISIBLE_NODE_COUNT);
      setExpandedMap({});
    } catch (error) {
      toast.error(error?.response?.data?.detail || "Chain detail yüklenemedi");
      setNodes([]);
      setSummary(null);
      setMeta(null);
    } finally {
      setLoading(false);
    }
  }, [chainId, includeSeed, strategyId, windowRange]);

  useEffect(() => {
    loadChain();
  }, [loadChain]);

  const filteredNodes = useMemo(() => {
    if (!onlyBrokenLinks) {
      return nodes;
    }
    return nodes.filter((item) => Boolean(item?.is_broken_link));
  }, [nodes, onlyBrokenLinks]);

  const visibleNodes = useMemo(() => {
    if (!showNodes) {
      return [];
    }
    return filteredNodes.slice(0, visibleCount);
  }, [filteredNodes, showNodes, visibleCount]);

  const narrativeText = useMemo(() => {
    if (summary?.invalid_reasons?.includes("seed_chain_hidden")) {
      return "Bu zincir test/seed namespace içinde. Gerçek operasyon görünümünde varsayılan olarak gizlenir.";
    }
    if (!summary || !nodes.length) {
      return "Zincir verisi yok: işlem nedeni veya sistem tepkisi bulunamadı.";
    }
    const broken = Number(summary?.broken_links_count || 0);
    if (broken > 0) {
      return `Chain kırık: ${broken} kopuk ilişki bulundu. Önce broken link'leri inceleyin.`;
    }
    const manual = Number(summary?.manual_action_count || 0);
    const system = Number(summary?.system_reaction_count || 0);
    return `Akış net: ${manual} manual aksiyon sonrası ${system} sistem tepkisi oluştu.`;
  }, [nodes.length, summary]);

  const toggleNodeExpand = (eventId) => {
    const key = String(eventId || "");
    if (!key) return;
    setExpandedMap((prev) => ({
      ...prev,
      [key]: !prev[key],
    }));
  };

  const collapseAllNodes = () => {
    setExpandedMap({});
  };

  const hasMoreNodes = showNodes && filteredNodes.length > visibleCount;

  return (
    <section className="space-y-4" data-testid="strategy-timeline-chain-page">
      <header className="border border-black/40 bg-orange-300 p-4" data-testid="strategy-timeline-chain-header">
        <div className="flex flex-wrap items-center justify-between gap-2" data-testid="strategy-timeline-chain-header-row">
          <div>
            <h1 className="text-4xl font-black uppercase tracking-tight" data-testid="strategy-timeline-chain-title">Timeline Chain Detail</h1>
            <p className="text-sm" data-testid="strategy-timeline-chain-subtitle">chain_id: {chainId}</p>
            {!!meta?.seed_chain && (
              <p className="mt-1 inline-flex rounded border border-amber-700 bg-amber-100 px-2 py-0.5 text-xs font-semibold text-amber-900" data-testid="strategy-timeline-chain-seed-badge">
                TEST/SEED CHAIN
              </p>
            )}
          </div>
          <Button
            variant="outline"
            className="border-black bg-white text-black"
            onClick={() => navigate("/admin/strategy/observability")}
            data-testid="strategy-timeline-chain-back-button"
          >
            Geri Dön
          </Button>
        </div>
      </header>

      <div className="grid gap-2 border border-black/30 bg-orange-100 p-4 md:grid-cols-4" data-testid="strategy-timeline-chain-filters">
        <select
          value={windowRange}
          onChange={(event) => setWindowRange(event.target.value)}
          className="border border-black/40 bg-white px-3 py-2 text-sm"
          data-testid="strategy-timeline-chain-window-select"
        >
          {windowOptions.map((value) => (
            <option key={value} value={value} data-testid={`strategy-timeline-chain-window-option-${value}`}>
              {value}
            </option>
          ))}
        </select>

        <Input
          value={strategyId}
          onChange={(event) => setStrategyId(event.target.value)}
          placeholder="strategy_id (opsiyonel)"
          data-testid="strategy-timeline-chain-strategy-input"
        />

        <Button onClick={loadChain} className="border border-black bg-black text-orange-300 hover:bg-zinc-800" data-testid="strategy-timeline-chain-refresh-button">
          Yenile
        </Button>

        <p className="self-center text-sm" data-testid="strategy-timeline-chain-loading-text">loading: {String(loading)}</p>
      </div>

      <div className="border border-black/30 bg-orange-50 p-4" data-testid="strategy-timeline-chain-summary-panel">
        <div className="flex flex-wrap items-center justify-between gap-2" data-testid="strategy-timeline-chain-summary-header-row">
          <h2 className="text-base font-semibold" data-testid="strategy-timeline-chain-summary-title">5 Saniye Zincir Özeti</h2>
          <div className="flex flex-wrap items-center gap-2" data-testid="strategy-timeline-chain-summary-actions-row">
            <Button
              size="sm"
              variant="outline"
              className="border-black bg-white text-black"
              onClick={() => setShowNodes((prev) => !prev)}
              data-testid="strategy-timeline-chain-toggle-nodes-button"
            >
              {showNodes ? "Detayı Gizle" : "Zinciri Aç"}
            </Button>
            <Button
              size="sm"
              variant="outline"
              className="border-black bg-white text-black"
              onClick={() => setOnlyBrokenLinks((prev) => !prev)}
              data-testid="strategy-timeline-chain-broken-filter-button"
            >
              {onlyBrokenLinks ? "Tüm Node'lar" : "Sadece Broken"}
            </Button>
            <Button
              size="sm"
              variant="outline"
              className="border-black bg-white text-black"
              onClick={collapseAllNodes}
              data-testid="strategy-timeline-chain-collapse-all-button"
            >
              Hepsini Daralt
            </Button>
            <Button
              size="sm"
              variant="outline"
              className="border-black bg-white text-black"
              onClick={() => setIncludeSeed((prev) => !prev)}
              data-testid="strategy-timeline-chain-seed-toggle-button"
            >
              {includeSeed ? "Seed Gizle" : "Seed Göster"}
            </Button>
          </div>
        </div>

        <p className="mt-2 text-sm" data-testid="strategy-timeline-chain-summary-narrative">{narrativeText}</p>

        <div className="mt-3 grid gap-2 sm:grid-cols-2 lg:grid-cols-4" data-testid="strategy-timeline-chain-kpi-grid">
          <div className="border border-black/20 bg-white p-2" data-testid="strategy-timeline-chain-kpi-total">
            <p className="text-xs">Total Nodes</p>
            <p className="text-lg font-semibold">{summary?.total_nodes ?? 0}</p>
          </div>
          <div className="border border-black/20 bg-white p-2" data-testid="strategy-timeline-chain-kpi-manual-system">
            <p className="text-xs">Manual / System</p>
            <p className="text-lg font-semibold">{summary?.manual_action_count ?? 0} / {summary?.system_reaction_count ?? 0}</p>
          </div>
          <div className={`border p-2 ${summary?.broken_links_count ? "border-red-600 bg-red-100" : "border-emerald-600 bg-emerald-100"}`} data-testid="strategy-timeline-chain-kpi-broken-links">
            <p className="text-xs">Broken Links</p>
            <p className="text-lg font-semibold">{summary?.broken_links_count ?? 0}</p>
          </div>
          <div className="border border-black/20 bg-white p-2" data-testid="strategy-timeline-chain-kpi-depth">
            <p className="text-xs">Root / Max Depth</p>
            <p className="text-lg font-semibold">{summary?.root_nodes_count ?? 0} / {summary?.max_depth ?? 0}</p>
          </div>
        </div>

        {!!summary && !summary?.is_chain_valid && (
          <div className="mt-3 border border-red-700 bg-red-100 p-2 text-sm text-red-900" data-testid="strategy-timeline-chain-invalid-banner">
            <p className="font-semibold" data-testid="strategy-timeline-chain-invalid-title">⚠️ Chain INVALID</p>
            <p data-testid="strategy-timeline-chain-invalid-reasons">nedenler: {(summary?.invalid_reasons || []).join(", ") || "unknown"}</p>
          </div>
        )}

        {!!summary?.root_cause_hint && (
          <div className="mt-3 border border-black/40 bg-white p-2 text-sm" data-testid="strategy-timeline-chain-root-cause-hint-panel">
            <p className="font-semibold" data-testid="strategy-timeline-chain-root-cause-hint-title">
              Deterministik Operasyon Önerisi (kesin neden değil)
            </p>
            <p data-testid="strategy-timeline-chain-root-cause-hint-text">{summary?.root_cause_hint?.hint || "-"}</p>
            <p className="text-xs text-black/70" data-testid="strategy-timeline-chain-root-cause-hint-meta">
              rule_key: {summary?.root_cause_hint?.rule_key || "-"} | signature: {summary?.root_cause_hint?.reason_signature || "-"}
            </p>
          </div>
        )}

        {!!summary?.virtualization_recommended && (
          <p className="mt-2 text-xs text-black/70" data-testid="strategy-timeline-chain-virtualization-note">
            Bu chain yüksek hacimli (500+). Performans için özet + parça parça yükleme modunda gösteriliyor.
          </p>
        )}
      </div>

      <div className="space-y-2 border border-black/25 bg-white p-3" data-testid="strategy-timeline-chain-node-list-wrapper">
        {!showNodes && (
          <p className="text-sm text-black/70" data-testid="strategy-timeline-chain-collapsed-note">
            Zincir varsayılan olarak özet modunda. “Zinciri Aç” ile detayları görüntüleyin.
          </p>
        )}

        {showNodes && visibleNodes.map((node, index) => {
          const eventId = String(node?.event_id || `row-${index}`);
          const isExpanded = Boolean(expandedMap[eventId]);
          const isBroken = Boolean(node?.is_broken_link);
          return (
            <article
              key={`${eventId}-${index}`}
              className={`rounded border p-3 ${isBroken ? "border-red-700 bg-red-50" : "border-black/20 bg-zinc-50"}`}
              data-testid={`strategy-timeline-chain-node-card-${index}`}
            >
              <div className="flex flex-wrap items-center justify-between gap-2" data-testid={`strategy-timeline-chain-node-header-${index}`}>
                <div className="flex flex-wrap items-center gap-2">
                  <span className="rounded border border-black/20 bg-white px-2 py-0.5 text-xs" data-testid={`strategy-timeline-chain-node-index-${index}`}>
                    #{node?.causal_index ?? index + 1}
                  </span>
                  <span className="rounded border border-black/20 bg-white px-2 py-0.5 text-xs" data-testid={`strategy-timeline-chain-node-stage-${index}`}>
                    {node?.flow_stage || node?.event_type || "unknown"}
                  </span>
                  {isBroken && (
                    <span className="rounded border border-red-700 bg-red-200 px-2 py-0.5 text-xs font-semibold text-red-900" data-testid={`strategy-timeline-chain-node-broken-badge-${index}`}>
                      BROKEN LINK
                    </span>
                  )}
                </div>
                <Button
                  size="sm"
                  variant="outline"
                  className="h-7 border-black bg-white text-black"
                  onClick={() => toggleNodeExpand(eventId)}
                  data-testid={`strategy-timeline-chain-node-expand-button-${index}`}
                >
                  {isExpanded ? "Daralt" : "Genişlet"}
                </Button>
              </div>

              <p className="mt-2 text-sm font-semibold" data-testid={`strategy-timeline-chain-node-action-${index}`}>{node?.action || "-"}</p>
              <p className="text-xs text-black/70" data-testid={`strategy-timeline-chain-node-time-${index}`}>
                {node?.timestamp ? new Date(node.timestamp).toLocaleString() : "-"}
              </p>
              <p className="text-xs text-black/70" data-testid={`strategy-timeline-chain-node-parent-${index}`}>
                parent_event_id: {node?.parent_event_id || "root"}
              </p>

              <div className="mt-2 flex flex-wrap gap-2" data-testid={`strategy-timeline-chain-node-impact-labels-${index}`}>
                {(node?.impact_labels || ["Impact etiketi yok"]).map((label, chipIndex) => (
                  <span
                    key={`${eventId}-impact-${chipIndex}`}
                    className="rounded border border-black/20 bg-white px-2 py-0.5 text-xs"
                    data-testid={`strategy-timeline-chain-node-impact-chip-${index}-${chipIndex}`}
                  >
                    {label}
                  </span>
                ))}
              </div>

              {isExpanded && (
                <div className="mt-3 grid gap-2 border border-black/15 bg-white p-2 text-xs" data-testid={`strategy-timeline-chain-node-details-${index}`}>
                  <p data-testid={`strategy-timeline-chain-node-reason-${index}`}>reason: {node?.reason || "-"}</p>
                  <p data-testid={`strategy-timeline-chain-node-strategy-${index}`}>strategy_id: {node?.strategy_id || "-"}</p>
                  <p data-testid={`strategy-timeline-chain-node-actor-${index}`}>actor_role: {node?.actor_role || "-"}</p>
                  <p data-testid={`strategy-timeline-chain-node-relation-status-${index}`}>relation_status: {node?.relation_status || "-"}</p>
                  <p data-testid={`strategy-timeline-chain-node-broken-reason-${index}`}>broken_reason: {node?.broken_reason || "-"}</p>
                  <p data-testid={`strategy-timeline-chain-node-depth-${index}`}>causal_depth: {node?.causal_depth ?? 0}</p>
                  <p data-testid={`strategy-timeline-chain-node-severity-status-${index}`}>
                    severity/status: {node?.severity || "-"} / {node?.status || "-"}
                  </p>
                </div>
              )}
            </article>
          );
        })}

        {showNodes && hasMoreNodes && (
          <div className="flex justify-center" data-testid="strategy-timeline-chain-load-more-row">
            <Button
              variant="outline"
              className="border-black bg-white text-black"
              onClick={() => setVisibleCount((prev) => prev + LOAD_MORE_NODE_COUNT)}
              data-testid="strategy-timeline-chain-load-more-button"
            >
              Daha Fazla Yükle ({Math.min(LOAD_MORE_NODE_COUNT, filteredNodes.length - visibleCount)} daha)
            </Button>
          </div>
        )}

        {showNodes && !loading && filteredNodes.length === 0 && (
          <div className="rounded border border-black/20 bg-zinc-50 p-3 text-center text-sm text-black/70" data-testid="strategy-timeline-chain-empty-state">
            {summary?.invalid_reasons?.includes("seed_chain_hidden")
              ? "Bu zincir seed namespace içinde olduğu için gizlendi. Görmek için 'Seed Göster' açın."
              : onlyBrokenLinks
                ? "Broken chain bulunamadı."
                : "Chain node bulunamadı."}
          </div>
        )}
      </div>
    </section>
  );
}
