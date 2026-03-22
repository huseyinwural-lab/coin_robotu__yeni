export const RoleVisibilityPanel = ({ role, canApplyOverride, canRequestDecision, canApproveExecute }) => {
  const roleMessage = canApplyOverride
    ? role === "admin"
      ? "admin: simulate + override request + decision request oluşturabilir"
      : "super_admin: simulate + approve/reject/execute + override apply/revoke"
    : "ops/viewer: read-only + simulation; kritik aksiyonlar kapalı";

  return (
    <section
      className="col-span-12 border border-slate-800 bg-slate-900 p-3"
      data-testid="strategy-intelligence-role-visibility-panel"
    >
      <p className="text-xs text-slate-300" data-testid="strategy-intelligence-role-visibility-text">
        {roleMessage}
      </p>
      <p className="mt-1 text-xs text-slate-500" data-testid="strategy-intelligence-role-capabilities-text">
        request_decision={String(canRequestDecision)} · approve_execute={String(canApproveExecute)} · override_write={String(canApplyOverride)}
      </p>
    </section>
  );
};
