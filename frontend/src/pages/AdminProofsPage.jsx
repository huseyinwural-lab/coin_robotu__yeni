import { useCallback, useEffect, useState } from "react";
import { toast } from "sonner";

import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { apiClient } from "@/lib/api";

export const AdminProofsPage = () => {
  const [loading, setLoading] = useState(true);
  const [proofs, setProofs] = useState([]);
  const [verifyResults, setVerifyResults] = useState({});
  const [batchFilters, setBatchFilters] = useState({
    artifact_type: "",
    status: "all",
    date_from: "",
    date_to: "",
  });
  const [batchResult, setBatchResult] = useState(null);
  const [batchRunning, setBatchRunning] = useState(false);

  const loadProofs = useCallback(async () => {
    setLoading(true);
    try {
      const { data } = await apiClient.get("/audit/admin/proofs");
      setProofs(data || []);
    } catch (error) {
      toast.error(error?.response?.data?.detail || "Proof listesi yüklenemedi");
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    loadProofs();
  }, [loadProofs]);

  const verifyArtifact = async (artifactId) => {
    try {
      const { data } = await apiClient.get(`/audit/artifacts/${artifactId}/verify`);
      setVerifyResults((prev) => ({ ...prev, [artifactId]: data }));
      if (data.verified) {
        toast.success("Artefact hash doğrulandı");
      } else {
        toast.error("Artefact hash mismatch tespit edildi");
      }
    } catch (error) {
      toast.error(error?.response?.data?.detail || "Doğrulama başarısız");
    }
  };

  const downloadArtifact = async (artifactId) => {
    try {
      const response = await apiClient.get(`/audit/artifacts/${artifactId}/download`, { responseType: "blob" });
      const disposition = response.headers["content-disposition"] || "";
      const filenameMatch = disposition.match(/filename="?([^\"]+)"?/i);
      const filename = filenameMatch?.[1] || `${artifactId}.json`;

      const url = window.URL.createObjectURL(new Blob([response.data], { type: "application/json" }));
      const link = document.createElement("a");
      link.href = url;
      link.setAttribute("download", filename);
      document.body.appendChild(link);
      link.click();
      link.remove();
      window.URL.revokeObjectURL(url);
      toast.success("Artefact indirildi");
    } catch (error) {
      toast.error(error?.response?.data?.detail || "Dosya indirilemedi");
    }
  };

  const runBatchVerify = async () => {
    setBatchRunning(true);
    try {
      const params = {
        artifact_type: batchFilters.artifact_type || undefined,
        status: batchFilters.status || "all",
        date_from: batchFilters.date_from || undefined,
        date_to: batchFilters.date_to || undefined,
      };
      const { data } = await apiClient.get("/audit/artifacts/verify-all", { params });
      setBatchResult(data);
      if (data.chain_broken || data.mismatch || data.missing) {
        toast.error("Batch verify: mismatch veya chain issue tespit edildi");
      } else {
        toast.success("Batch verify tamamlandı: tüm kayıtlar sağlam");
      }
    } catch (error) {
      toast.error(error?.response?.data?.detail || "Batch verify başarısız");
    } finally {
      setBatchRunning(false);
    }
  };

  return (
    <section className="space-y-4" data-testid="admin-proofs-page">
      <header className="border border-orange-700 bg-slate-900 p-4" data-testid="admin-proofs-header">
        <h2 className="text-4xl font-black uppercase tracking-tight text-orange-300" data-testid="admin-proofs-title">Proof Artefact Panel</h2>
        <p className="mt-2 text-sm text-slate-300" data-testid="admin-proofs-description">
          Lifecycle evidence, fallback replay evidence ve risk summary artefact bütünlüğü (SHA-256) doğrulama merkezi.
        </p>
      </header>

      <div className="border border-slate-800 bg-slate-900 p-4" data-testid="admin-proofs-batch-panel">
        <div className="flex flex-wrap items-center justify-between gap-3" data-testid="admin-proofs-batch-header">
          <p className="text-xs uppercase tracking-widest text-slate-500" data-testid="admin-proofs-batch-title">Batch Proof Verification</p>
          <Button
            className="bg-orange-500 text-black hover:bg-orange-600"
            onClick={runBatchVerify}
            disabled={batchRunning}
            data-testid="admin-proofs-batch-run-button"
          >
            {batchRunning ? "Doğrulanıyor..." : "Run Batch Verify"}
          </Button>
        </div>

        <div className="mt-3 grid gap-2 md:grid-cols-4" data-testid="admin-proofs-batch-filters">
          <Input
            placeholder="artifact_type"
            value={batchFilters.artifact_type}
            onChange={(event) => setBatchFilters((prev) => ({ ...prev, artifact_type: event.target.value }))}
            data-testid="admin-proofs-batch-artifact-type-input"
          />
          <Input
            placeholder="date_from (ISO)"
            value={batchFilters.date_from}
            onChange={(event) => setBatchFilters((prev) => ({ ...prev, date_from: event.target.value }))}
            data-testid="admin-proofs-batch-date-from-input"
          />
          <Input
            placeholder="date_to (ISO)"
            value={batchFilters.date_to}
            onChange={(event) => setBatchFilters((prev) => ({ ...prev, date_to: event.target.value }))}
            data-testid="admin-proofs-batch-date-to-input"
          />
          <select
            value={batchFilters.status}
            onChange={(event) => setBatchFilters((prev) => ({ ...prev, status: event.target.value }))}
            className="border border-slate-700 bg-slate-950 px-3 py-2 text-sm"
            data-testid="admin-proofs-batch-status-select"
          >
            <option value="all">all</option>
            <option value="verified">verified</option>
            <option value="mismatch">mismatch</option>
            <option value="missing">missing</option>
            <option value="chain_broken">chain_broken</option>
          </select>
        </div>

        {batchResult && (
          <div className="mt-3 grid gap-2 md:grid-cols-5 text-xs text-slate-200" data-testid="admin-proofs-batch-summary">
            <div data-testid="admin-proofs-batch-total">total: {batchResult.total}</div>
            <div data-testid="admin-proofs-batch-verified">verified: {batchResult.verified}</div>
            <div data-testid="admin-proofs-batch-mismatch">mismatch: {batchResult.mismatch}</div>
            <div data-testid="admin-proofs-batch-missing">missing: {batchResult.missing}</div>
            <div data-testid="admin-proofs-batch-chain-broken">chain_broken: {batchResult.chain_broken}</div>
            <div className="md:col-span-2" data-testid="admin-proofs-batch-chain-index">broken_index: {batchResult.chain_broken_index ?? "-"}</div>
            <div className="md:col-span-3 break-all" data-testid="admin-proofs-batch-chain-artifact">broken_artifact_id: {batchResult.chain_broken_artifact_id || "-"}</div>
          </div>
        )}
      </div>

      <div className="border border-slate-800 bg-slate-900 p-4" data-testid="admin-proofs-list-wrapper">
        {loading && <p className="text-sm text-slate-400" data-testid="admin-proofs-loading-text">Yükleniyor...</p>}
        {!loading && proofs.length === 0 && <p className="text-sm text-slate-400" data-testid="admin-proofs-empty-text">Henüz artefact yok</p>}

        <div className="space-y-3" data-testid="admin-proofs-list">
          {proofs.map((item) => {
            const verify = verifyResults[item.artifact_id];
            return (
              <div key={item.artifact_id} className="border border-slate-700 p-3" data-testid={`admin-proof-row-${item.artifact_id}`}>
                <div className="grid gap-2 md:grid-cols-2 xl:grid-cols-3" data-testid={`admin-proof-grid-${item.artifact_id}`}>
                  <p className="text-sm" data-testid={`admin-proof-id-${item.artifact_id}`}>proof_id: {item.proof_id}</p>
                  <p className="text-sm" data-testid={`admin-proof-evidence-type-${item.artifact_id}`}>evidence_type: {item.evidence_type}</p>
                  <p className="text-sm" data-testid={`admin-proof-status-${item.artifact_id}`}>status: {item.status}</p>
                  <p className="text-xs text-slate-400" data-testid={`admin-proof-chain-position-${item.artifact_id}`}>chain_pos: {item.chain_position ?? "-"}</p>
                  <p className="text-xs text-slate-400 break-all" data-testid={`admin-proof-prev-chain-${item.artifact_id}`}>prev_chain: {item.prev_chain_hash || "-"}</p>
                  <p className="text-xs text-slate-400 break-all" data-testid={`admin-proof-chain-hash-${item.artifact_id}`}>chain_hash: {item.chain_hash || "-"}</p>
                  <p className="text-xs text-slate-400 break-all" data-testid={`admin-proof-hash-${item.artifact_id}`}>sha256: {item.sha256}</p>
                  <p className="text-xs text-slate-400" data-testid={`admin-proof-created-at-${item.artifact_id}`}>created_at: {item.created_at}</p>
                  <p className="text-xs text-slate-400" data-testid={`admin-proof-filename-${item.artifact_id}`}>filename: {item.filename}</p>
                </div>

                {verify && (
                  <p className={`mt-2 text-xs ${verify.verified && verify.chain_valid ? "text-emerald-300" : "text-red-300"}`} data-testid={`admin-proof-verify-result-${item.artifact_id}`}>
                    verify={String(verify.verified)} · chain_valid={String(verify.chain_valid)} · expected={verify.sha256_expected} · actual={verify.sha256_actual}
                  </p>
                )}

                <div className="mt-3 flex flex-wrap gap-2" data-testid={`admin-proof-actions-${item.artifact_id}`}>
                  <Button className="bg-orange-500 text-black hover:bg-orange-600" onClick={() => verifyArtifact(item.artifact_id)} data-testid={`admin-proof-verify-button-${item.artifact_id}`}>
                    Verify
                  </Button>
                  <Button variant="outline" className="border-slate-500 text-slate-200" onClick={() => downloadArtifact(item.artifact_id)} data-testid={`admin-proof-download-button-${item.artifact_id}`}>
                    Download
                  </Button>
                </div>
              </div>
            );
          })}
        </div>
      </div>
    </section>
  );
};
