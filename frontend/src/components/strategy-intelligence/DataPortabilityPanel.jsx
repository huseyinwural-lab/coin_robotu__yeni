import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";

export const DataPortabilityPanel = ({
  role,
  exportDataset,
  onExportDatasetChange,
  onExport,
  onImportFileChange,
  onImportJson,
  isExporting,
  isImporting,
  importFileName,
}) => {
  const canImport = role === "super_admin";

  return (
    <section className="col-span-12 border border-slate-800 bg-slate-900 p-4" data-testid="strategy-intelligence-data-portability-panel">
      <p className="text-xs uppercase tracking-widest text-slate-500" data-testid="strategy-intelligence-data-portability-title">
        Import / Export (CSV + JSON)
      </p>

      <div className="mt-2 grid gap-2 md:grid-cols-3" data-testid="strategy-intelligence-export-controls">
        <select
          className="rounded border border-slate-700 bg-slate-950 px-2 py-2 text-sm"
          value={exportDataset}
          onChange={(event) => onExportDatasetChange(event.target.value)}
          data-testid="strategy-intelligence-export-dataset-select"
        >
          <option value="decision_requests">decision_requests</option>
          <option value="simulation_history">simulation_history</option>
        </select>
        <Button
          type="button"
          variant="outline"
          disabled={isExporting}
          onClick={() => onExport("json")}
          data-testid="strategy-intelligence-export-json-button"
        >
          {isExporting ? "Exporting..." : "Export JSON"}
        </Button>
        <Button
          type="button"
          variant="outline"
          disabled={isExporting}
          onClick={() => onExport("csv")}
          data-testid="strategy-intelligence-export-csv-button"
        >
          {isExporting ? "Exporting..." : "Export CSV"}
        </Button>
      </div>

      <div className="mt-2 grid gap-2 md:grid-cols-3" data-testid="strategy-intelligence-import-controls">
        <Input
          type="file"
          accept="application/json"
          onChange={onImportFileChange}
          data-testid="strategy-intelligence-import-json-file-input"
        />
        <p className="text-xs text-slate-400" data-testid="strategy-intelligence-import-json-file-name">
          file={importFileName || "-"}
        </p>
        <Button
          type="button"
          disabled={!canImport || isImporting}
          onClick={onImportJson}
          data-testid="strategy-intelligence-import-json-button"
        >
          {isImporting ? "Importing..." : "Import JSON"}
        </Button>
      </div>
    </section>
  );
};
