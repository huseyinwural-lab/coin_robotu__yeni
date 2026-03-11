import { useCallback, useEffect, useState } from "react";
import { toast } from "sonner";

import { Button } from "@/components/ui/button";
import { apiClient } from "@/lib/api";

export const AdminProofsPage = () => {
  const [loading, setLoading] = useState(true);
  const [proofs, setProofs] = useState([]);
  const [verifyResults, setVerifyResults] = useState({});

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

  return (
    <section className="space-y-4" data-testid="admin-proofs-page">
      <header className="border border-orange-700 bg-slate-900 p-4" data-testid="admin-proofs-header">
        <h2 className="text-4xl font-black uppercase tracking-tight text-orange-300" data-testid="admin-proofs-title">Proof Artefact Panel</h2>
        <p className="mt-2 text-sm text-slate-300" data-testid="admin-proofs-description">
          Lifecycle evidence, fallback replay evidence ve risk summary artefact bütünlüğü (SHA-256) doğrulama merkezi.
        </p>
      </header>

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
                  <p className="text-xs text-slate-400 break-all" data-testid={`admin-proof-hash-${item.artifact_id}`}>sha256: {item.sha256}</p>
                  <p className="text-xs text-slate-400" data-testid={`admin-proof-created-at-${item.artifact_id}`}>created_at: {item.created_at}</p>
                  <p className="text-xs text-slate-400" data-testid={`admin-proof-filename-${item.artifact_id}`}>filename: {item.filename}</p>
                </div>

                {verify && (
                  <p className={`mt-2 text-xs ${verify.verified ? "text-emerald-300" : "text-red-300"}`} data-testid={`admin-proof-verify-result-${item.artifact_id}`}>
                    verify={String(verify.verified)} · expected={verify.sha256_expected} · actual={verify.sha256_actual}
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
