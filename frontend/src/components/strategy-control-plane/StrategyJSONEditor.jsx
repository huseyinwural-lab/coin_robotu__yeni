import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";

export const StrategyJSONEditor = ({
  selectedStrategyId,
  versionForm,
  setVersionForm,
  isVersionConfigValid,
  versionEditorIssues,
  versionEditorSchema,
  showConfigDiffMode,
  setShowConfigDiffMode,
  versionConfigDiff,
  createVersionValidationTooltip,
  onSubmit,
}) => {
  return (
    <form className="space-y-2 border border-slate-800 bg-slate-900 p-4" onSubmit={onSubmit} data-testid="admin-strategy-version-create-form">
      <p className="text-xs uppercase tracking-widest text-slate-500" data-testid="admin-strategy-version-title">Create StrategyVersion</p>
      <Input
        placeholder="config schema version"
        value={versionForm.config_schema_version}
        onChange={(e) => setVersionForm((prev) => ({ ...prev, config_schema_version: e.target.value }))}
        data-testid="admin-strategy-version-schema-input"
      />

      <div className="grid gap-3 xl:grid-cols-2" data-testid="admin-strategy-version-editor-grid">
        <div className="space-y-2" data-testid="admin-strategy-version-editor-main">
          <div className={`rounded border p-2 text-xs ${isVersionConfigValid ? "border-emerald-600 text-emerald-300" : "border-red-600 text-red-300"}`} data-testid="admin-strategy-version-validation-summary-banner">
            {isVersionConfigValid
              ? "Validation summary: PASS"
              : `Validation summary: FAIL (${versionEditorIssues.length || 1} issue)`}
          </div>

          {!isVersionConfigValid && (
            <div className="rounded border border-red-700 bg-red-950/40 p-2 text-xs text-red-200" data-testid="admin-strategy-version-validation-upper-banner">
              Config geçersiz. Save devre dışı. Hataları düzeltmeden yeni version oluşturamazsınız.
            </div>
          )}

          <textarea
            className={`h-44 w-full border bg-slate-950 p-2 text-sm ${isVersionConfigValid ? "border-slate-700" : "border-red-500"}`}
            value={versionForm.config_json}
            onChange={(e) => setVersionForm((prev) => ({ ...prev, config_json: e.target.value }))}
            data-testid="admin-strategy-version-config-textarea"
          />

          {versionEditorIssues.length > 0 && (
            <div className="space-y-1 border border-red-700 p-2 text-xs" data-testid="admin-strategy-version-error-list-panel">
              {versionEditorIssues.map((issue, idx) => (
                <p key={`${issue.field}-${idx}`} className="text-red-300" data-testid={`admin-strategy-version-error-item-${idx}`}>
                  {issue.field}: {issue.message}
                </p>
              ))}
            </div>
          )}

          <div className="flex flex-wrap gap-2" data-testid="admin-strategy-version-editor-actions-row">
            <Button
              type="button"
              variant="outline"
              className="border-slate-500 text-slate-100"
              onClick={() => setShowConfigDiffMode((prev) => !prev)}
              data-testid="admin-strategy-version-diff-toggle-button"
            >
              Diff Mode: {String(showConfigDiffMode)}
            </Button>
          </div>

          {showConfigDiffMode && (
            <div className="space-y-1 border border-slate-700 p-2 text-xs" data-testid="admin-strategy-version-diff-panel">
              {versionConfigDiff.length === 0 && <p data-testid="admin-strategy-version-diff-empty">Fark bulunamadı.</p>}
              {versionConfigDiff.slice(0, 20).map((item, idx) => (
                <p key={`${item.field}-${idx}`} data-testid={`admin-strategy-version-diff-item-${idx}`}>
                  {item.field}: {JSON.stringify(item.current)} → {JSON.stringify(item.edited)}
                </p>
              ))}
            </div>
          )}
        </div>

        <div className="space-y-2 border border-slate-700 p-2 text-xs" data-testid="admin-strategy-version-schema-hint-panel">
          <p className="uppercase tracking-wider text-slate-400" data-testid="admin-strategy-version-schema-hint-title">Schema Hints</p>
          <p data-testid="admin-strategy-version-required-fields">required: {versionEditorSchema.required.join(", ")}</p>
          <div className="space-y-1" data-testid="admin-strategy-version-hints-list">
            {Object.entries(versionEditorSchema.hints).map(([field, hint]) => (
              <p key={field} data-testid={`admin-strategy-version-hint-${field}`}>{field}: {hint}</p>
            ))}
          </div>
          <div className="space-y-1" data-testid="admin-strategy-version-defaults-list">
            {Object.entries(versionEditorSchema.defaults).map(([field, value]) => (
              <p key={field} data-testid={`admin-strategy-version-default-${field}`}>{field} default: {JSON.stringify(value)}</p>
            ))}
          </div>
        </div>
      </div>

      <Button
        className="bg-orange-500 text-black hover:bg-orange-600"
        disabled={!selectedStrategyId || !isVersionConfigValid}
        title={createVersionValidationTooltip}
        data-testid="admin-strategy-version-submit-button"
      >
        Create Version
      </Button>
    </form>
  );
};
