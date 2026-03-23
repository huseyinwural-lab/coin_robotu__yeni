import { useCallback, useEffect, useState } from "react";
import { useNavigate, useParams } from "react-router-dom";
import { toast } from "sonner";

import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from "@/components/ui/table";
import { apiClient } from "@/lib/api";

const windowOptions = ["24h", "7d", "30d"];

export default function AdminStrategyTimelineChainPage() {
  const { chainId } = useParams();
  const navigate = useNavigate();

  const [windowRange, setWindowRange] = useState("30d");
  const [strategyId, setStrategyId] = useState("");
  const [loading, setLoading] = useState(false);
  const [nodes, setNodes] = useState([]);

  const loadChain = useCallback(async () => {
    if (!chainId) {
      setNodes([]);
      return;
    }
    setLoading(true);
    try {
      const { data } = await apiClient.get(`/admin/strategy/timeline/${encodeURIComponent(chainId)}`, {
        params: {
          window: windowRange,
          strategy_id: strategyId || null,
        },
      });
      setNodes(data?.nodes || []);
    } catch (error) {
      toast.error(error?.response?.data?.detail || "Chain detail yüklenemedi");
      setNodes([]);
    } finally {
      setLoading(false);
    }
  }, [chainId, strategyId, windowRange]);

  useEffect(() => {
    loadChain();
  }, [loadChain]);

  return (
    <section className="space-y-4" data-testid="strategy-timeline-chain-page">
      <header className="border border-black/40 bg-orange-300 p-4" data-testid="strategy-timeline-chain-header">
        <div className="flex flex-wrap items-center justify-between gap-2" data-testid="strategy-timeline-chain-header-row">
          <div>
            <h1 className="text-4xl font-black uppercase tracking-tight" data-testid="strategy-timeline-chain-title">Timeline Chain Detail</h1>
            <p className="text-sm" data-testid="strategy-timeline-chain-subtitle">chain_id: {chainId}</p>
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

      <div className="overflow-x-auto border border-black/25 bg-white" data-testid="strategy-timeline-chain-table-wrapper">
        <Table data-testid="strategy-timeline-chain-table">
          <TableHeader>
            <TableRow>
              <TableHead data-testid="strategy-timeline-chain-head-time">Time</TableHead>
              <TableHead data-testid="strategy-timeline-chain-head-type">Type</TableHead>
              <TableHead data-testid="strategy-timeline-chain-head-action">Action</TableHead>
              <TableHead data-testid="strategy-timeline-chain-head-parent">Parent</TableHead>
              <TableHead data-testid="strategy-timeline-chain-head-delta">Impact</TableHead>
            </TableRow>
          </TableHeader>
          <TableBody>
            {nodes.map((node, index) => (
              <TableRow key={`${node.event_id}-${index}`} data-testid={`strategy-timeline-chain-row-${index}`}>
                <TableCell className="text-xs" data-testid={`strategy-timeline-chain-time-${index}`}>{node.timestamp ? new Date(node.timestamp).toLocaleString() : "-"}</TableCell>
                <TableCell data-testid={`strategy-timeline-chain-type-${index}`}>{node.event_type || "-"}</TableCell>
                <TableCell data-testid={`strategy-timeline-chain-action-${index}`}>{node.action || "-"}</TableCell>
                <TableCell data-testid={`strategy-timeline-chain-parent-${index}`}>{node.parent_event_id || "root"}</TableCell>
                <TableCell data-testid={`strategy-timeline-chain-impact-${index}`}>{JSON.stringify(node.impact_payload || {})}</TableCell>
              </TableRow>
            ))}
            {!loading && nodes.length === 0 && (
              <TableRow data-testid="strategy-timeline-chain-empty-row">
                <TableCell colSpan={5} className="text-center text-sm text-black/70" data-testid="strategy-timeline-chain-empty-text">
                  Chain node bulunamadı.
                </TableCell>
              </TableRow>
            )}
          </TableBody>
        </Table>
      </div>
    </section>
  );
}
