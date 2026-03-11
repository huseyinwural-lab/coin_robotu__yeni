import { useCallback, useEffect, useState } from "react";
import { toast } from "sonner";

import { Button } from "@/components/ui/button";
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from "@/components/ui/table";
import { apiClient } from "@/lib/api";

export const AdminUserApprovalsPage = () => {
  const [requests, setRequests] = useState([]);
  const [loading, setLoading] = useState(false);

  const loadRequests = useCallback(async () => {
    setLoading(true);
    try {
      const { data } = await apiClient.get("/auth/admin/user-approval-requests?status=pending");
      setRequests(data);
    } catch (error) {
      toast.error(error?.response?.data?.detail || "Onay talepleri alınamadı");
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    loadRequests();
  }, [loadRequests]);

  const handleDecision = async (userId, action) => {
    try {
      await apiClient.post(`/auth/admin/user-approval-requests/${userId}/${action}`);
      toast.success(action === "approve" ? "Kullanıcı onaylandı" : "Kullanıcı reddedildi");
      loadRequests();
    } catch (error) {
      toast.error(error?.response?.data?.detail || "İşlem başarısız");
    }
  };

  return (
    <section className="space-y-4" data-testid="admin-user-approvals-page">
      <header className="border border-black/40 bg-orange-300 p-4" data-testid="admin-user-approvals-header">
        <h2 className="text-4xl font-black uppercase tracking-tight text-black" data-testid="admin-user-approvals-title">Kullanıcı Onay Merkezi</h2>
        <p className="mt-2 text-sm text-black/70" data-testid="admin-user-approvals-description">
          Yeni kayıt olan kullanıcılar burada bekler. Onay sonrası user panel girişine izin verilir.
        </p>
      </header>

      <div className="border border-black/30 bg-orange-100 p-4" data-testid="admin-user-approvals-toolbar">
        <Button
          className="border border-black bg-orange-500 text-black hover:bg-orange-600"
          onClick={loadRequests}
          data-testid="admin-user-approvals-refresh-button"
        >
          Yenile
        </Button>
        <p className="mt-2 text-sm text-black" data-testid="admin-user-approvals-count">Bekleyen Talep: {requests.length}</p>
      </div>

      <div className="border border-black/30 bg-orange-100" data-testid="admin-user-approvals-table-wrapper">
        <Table data-testid="admin-user-approvals-table">
          <TableHeader>
            <TableRow>
              <TableHead data-testid="admin-approvals-head-email">E-posta</TableHead>
              <TableHead data-testid="admin-approvals-head-status">Durum</TableHead>
              <TableHead data-testid="admin-approvals-head-requested">Talep Zamanı</TableHead>
              <TableHead data-testid="admin-approvals-head-actions">Aksiyon</TableHead>
            </TableRow>
          </TableHeader>
          <TableBody>
            {requests.map((item) => (
              <TableRow key={item.id} data-testid={`admin-approval-row-${item.id}`}>
                <TableCell data-testid={`admin-approval-email-${item.id}`}>{item.email}</TableCell>
                <TableCell data-testid={`admin-approval-status-${item.id}`}>{item.approval_status}</TableCell>
                <TableCell data-testid={`admin-approval-requested-at-${item.id}`}>{new Date(item.approval_requested_at).toLocaleString()}</TableCell>
                <TableCell className="flex flex-wrap gap-2" data-testid={`admin-approval-actions-${item.id}`}>
                  <Button
                    className="border border-black bg-black text-orange-400 hover:bg-zinc-800"
                    onClick={() => handleDecision(item.id, "approve")}
                    data-testid={`admin-approval-approve-button-${item.id}`}
                  >
                    Onayla
                  </Button>
                  <Button
                    className="border border-black bg-red-600 text-white hover:bg-red-700"
                    onClick={() => handleDecision(item.id, "reject")}
                    data-testid={`admin-approval-reject-button-${item.id}`}
                  >
                    Reddet
                  </Button>
                </TableCell>
              </TableRow>
            ))}
            {!loading && requests.length === 0 && (
              <TableRow data-testid="admin-approval-empty-row">
                <TableCell colSpan={4} className="text-center text-sm text-black/70" data-testid="admin-approval-empty-text">
                  Bekleyen kullanıcı talebi bulunmuyor.
                </TableCell>
              </TableRow>
            )}
          </TableBody>
        </Table>
      </div>
    </section>
  );
};