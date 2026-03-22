import { useEffect, useState } from "react";
import { apiClient } from "@/lib/api";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "@/components/ui/select";
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from "@/components/ui/table";
import { toast } from "sonner";

export const StateRebuildLogsPage = () => {
  const [rows, setRows] = useState([]);
  const [scopeType, setScopeType] = useState("full");
  const [scopeValue, setScopeValue] = useState("");
  const [dateFrom, setDateFrom] = useState("");
  const [dateTo, setDateTo] = useState("");

  const load = async () => {
    try {
      const { data } = await apiClient.get("/admin-phase3/state-rebuild-logs");
      setRows(data || []);
    } catch (error) {
      toast.error(error?.response?.data?.detail || "State rebuild logs yüklenemedi");
    }
  };

  useEffect(() => {
    load();
    const id = setInterval(load, 15000);
    return () => clearInterval(id);
  }, []);

  const triggerRebuild = async () => {
    try {
      const params = new URLSearchParams();
      params.set("scope_type", scopeType);
      if (scopeValue.trim()) params.set("scope_value", scopeValue.trim());
      if (dateFrom) params.set("date_from", dateFrom);
      if (dateTo) params.set("date_to", dateTo);
      await apiClient.post(`/admin-phase3/state-rebuild/run?${params.toString()}`);
      toast.success("Rebuild tetiklendi");
      await load();
    } catch (error) {
      toast.error(error?.response?.data?.detail || "Rebuild trigger başarısız");
    }
  };

  return (
    <section className="space-y-4" data-testid="execution-control-rebuild-page">
      <div className="grid gap-2 md:grid-cols-5" data-testid="execution-control-rebuild-controls">
        <Select value={scopeType} onValueChange={setScopeType}>
          <SelectTrigger data-testid="execution-control-rebuild-scope-select"><SelectValue /></SelectTrigger>
          <SelectContent>
            <SelectItem value="full">full</SelectItem>
            <SelectItem value="partial">partial</SelectItem>
            <SelectItem value="entity_scoped">entity_scoped</SelectItem>
            <SelectItem value="symbol_scoped">symbol_scoped</SelectItem>
            <SelectItem value="date_range">date_range</SelectItem>
          </SelectContent>
        </Select>
        <Input placeholder="scope value" value={scopeValue} onChange={(e) => setScopeValue(e.target.value)} data-testid="execution-control-rebuild-scope-value-input" />
        <Input type="date" value={dateFrom} onChange={(e) => setDateFrom(e.target.value)} data-testid="execution-control-rebuild-date-from-input" />
        <Input type="date" value={dateTo} onChange={(e) => setDateTo(e.target.value)} data-testid="execution-control-rebuild-date-to-input" />
        <Button onClick={triggerRebuild} data-testid="execution-control-rebuild-trigger-button">Run Rebuild</Button>
      </div>

      <div className="overflow-x-auto border border-slate-800 bg-slate-900" data-testid="execution-control-rebuild-table-wrapper">
        <Table>
          <TableHeader>
            <TableRow>
              <TableHead>Type</TableHead>
              <TableHead>Status</TableHead>
              <TableHead>Source</TableHead>
              <TableHead>Started</TableHead>
              <TableHead>Details</TableHead>
            </TableRow>
          </TableHeader>
          <TableBody>
            {rows.map((row) => (
              <TableRow key={row.id} data-testid={`execution-control-rebuild-row-${row.id}`}>
                <TableCell>{row.rebuild_type}</TableCell>
                <TableCell>{row.status}</TableCell>
                <TableCell>{row.trigger_source}</TableCell>
                <TableCell>{new Date(row.started_at).toLocaleString()}</TableCell>
                <TableCell>
                  scanned={row.details?.scanned_count ?? row.details?.open_positions_count ?? "-"} · restored={row.details?.restored_count ?? "-"} · failed={row.details?.failed_count ?? "-"}
                </TableCell>
              </TableRow>
            ))}
          </TableBody>
        </Table>
      </div>
    </section>
  );
};
