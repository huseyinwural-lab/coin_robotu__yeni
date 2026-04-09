import "@/App.css";
import { BrowserRouter, Navigate, Route, Routes, useLocation } from "react-router-dom";
import { Toaster } from "sonner";

import { AuthProvider, useAuth } from "@/context/AuthContext";
import { PanelLayout } from "@/components/PanelLayout";
import { ProtectedRoute } from "@/components/ProtectedRoute";
import { AdminLoginPage } from "@/pages/AdminLoginPage";
import { AdminDashboardPage } from "@/pages/AdminDashboardPage";
import AdminOnboardingObservabilityPage from "@/pages/AdminOnboardingObservabilityPage";
import { AdminExchangesPage } from "@/pages/AdminExchangesPage";
import { AdminFuturesRiskMonitorPage } from "@/pages/AdminFuturesRiskMonitorPage";
import { AdminFuturesStrategyControlGovernancePage } from "@/pages/AdminFuturesStrategyControlGovernancePage";
import { AdminFuturesClusterRiskPage } from "@/pages/AdminFuturesClusterRiskPage";
import { AdminFuturesTailRiskPage } from "@/pages/AdminFuturesTailRiskPage";
import { AdminFuturesLiveReadinessPage } from "@/pages/AdminFuturesLiveReadinessPage";
import { AdminFuturesScalingValidationPage } from "@/pages/AdminFuturesScalingValidationPage";
import { AdminFuturesMicrostructureGuardPage } from "@/pages/AdminFuturesMicrostructureGuardPage";
import { AdminFuturesLiveControlPage } from "@/pages/AdminFuturesLiveControlPage";
import { AdminProofsPage } from "@/pages/AdminProofsPage";
import { AdminReportsArchivePage } from "@/pages/AdminReportsArchivePage";
import { AdminRiskOrchestratorPage } from "@/pages/AdminRiskOrchestratorPage";
import { AdminRiskOrchestratorAnalyticsPage } from "@/pages/AdminRiskOrchestratorAnalyticsPage";
import { AdminRuntimeQuarantinePage } from "@/pages/AdminRuntimeQuarantinePage";
import { AdminRuntimeRecoveryPage } from "@/pages/AdminRuntimeRecoveryPage";
import { AdminStrategiesPage } from "@/pages/AdminStrategiesPage";
import { AdminSystemAlertsPage } from "@/pages/AdminSystemAlertsPage";
import { AdminUserApprovalsPage } from "@/pages/AdminUserApprovalsPage";
import { AdminUsersPage } from "@/pages/AdminUsersPage";
import { AdminUserUsersPage } from "@/pages/AdminUserUsersPage";
import { AuditLogsPage } from "@/pages/AuditLogsPage";
import { BacktestCardsPage } from "@/pages/BacktestCardsPage";
import { BacktestInsightsPage } from "@/pages/BacktestInsightsPage";
import { BotProfilesPage } from "@/pages/BotProfilesPage";
import { CorrelationMatrixPage } from "@/pages/CorrelationMatrixPage";
import { ExecutionPoliciesPage } from "@/pages/ExecutionPoliciesPage";
import { ExecutionIdempotencyPage } from "@/pages/ExecutionIdempotencyPage";
import { ExecutionTracePage } from "@/pages/ExecutionTracePage";
import { AdminExecutionAlertsPage } from "@/pages/AdminExecutionAlertsPage";
import { ExposureGroupsPage } from "@/pages/ExposureGroupsPage";
import { FailedEventsPage } from "@/pages/FailedEventsPage";
import { HardeningChecklistPage } from "@/pages/HardeningChecklistPage";
import { LandingPage } from "@/pages/LandingPage";
import { MarketUniversePage } from "@/pages/MarketUniversePage";
import { MonitoringPage } from "@/pages/MonitoringPage";
import { RiskPoliciesPage } from "@/pages/RiskPoliciesPage";
import { StateRebuildLogsPage } from "@/pages/StateRebuildLogsPage";
import { StrategyTemplatesPage } from "@/pages/StrategyTemplatesPage";
import { StrategyTemplateDetailPage } from "@/pages/StrategyTemplateDetailPage";
import { UserLoginPage } from "@/pages/UserLoginPage";
import { UserExchangeSettingsPage } from "@/pages/UserExchangeSettingsPage";
import { UserExchangeDiagnosticsPage } from "@/pages/UserExchangeDiagnosticsPage";
import { UserDashboardPage } from "@/pages/UserDashboardPage";
import { UserPortfolioPage } from "@/pages/UserPortfolioPage";
import { UserTradesPage } from "@/pages/UserTradesPage";
import { UserTradeDetailPage } from "@/pages/UserTradeDetailPage";
import { UserExecutionPage } from "@/pages/UserExecutionPage";
import { UserAlertCenterPage } from "@/pages/UserAlertCenterPage";
import { UserSettingsPage } from "@/pages/UserSettingsPage";
import { UserActivityLogPage } from "@/pages/UserActivityLogPage";
import { UserScannerPage } from "@/pages/UserScannerPage";
import { UserSimpleScannerPage } from "@/pages/UserSimpleScannerPage";
import { UserIndicatorScreenerPage } from "@/pages/UserIndicatorScreenerPage";
import { UserSignalsPage } from "@/pages/UserSignalsPage";
import { UserSymbolDecisionDetailPage } from "@/pages/UserSymbolDecisionDetailPage";
import { UserReportsPage } from "@/pages/UserReportsPage";
import { UserTradePage } from "@/pages/UserTradePage";
import { UserChartPage } from "@/pages/UserChartPage";
import { UserPositionsPage } from "@/pages/UserPositionsPage";
import { ForgotPasswordPage } from "@/pages/ForgotPasswordPage";
import { ResetPasswordPage } from "@/pages/ResetPasswordPage";
import UserLiveTradingDashboardPage from "@/pages/user/UserLiveTradingDashboardPage";
import { AdminStrategyAllocationPage } from "@/pages/AdminStrategyAllocationPage";
import { AdminPortfolioRiskPage } from "@/pages/AdminPortfolioRiskPage";
import { AdminPositionsMonitorPage } from "@/pages/AdminPositionsMonitorPage";
import { AdminStrategyIntelligencePage } from "@/pages/AdminStrategyIntelligencePage";
import { AdminCrossDashboardConsistencyPage } from "@/pages/AdminCrossDashboardConsistencyPage";
import { AdminCanonicalStrategyRegistryPage } from "@/pages/AdminCanonicalStrategyRegistryPage";
import { AdminLearningPanelPage } from "@/pages/AdminLearningPanelPage";
import { AdminLiveTradingDashboardPage } from "@/pages/AdminLiveTradingDashboardPage";
import { AdminUniverseMonitorPage } from "@/pages/AdminUniverseMonitorPage";
import { AdminFreshnessHeatmapPage } from "@/pages/AdminFreshnessHeatmapPage";
import { AdminCommercialOpsPage } from "@/pages/AdminCommercialOpsPage";
import { AdminRevenuePage } from "@/pages/AdminRevenuePage";
import { AdminUserEconomicsPage } from "@/pages/AdminUserEconomicsPage";
import { AdminSnapshotsPage } from "@/pages/AdminSnapshotsPage";
import { AdminCredentialOrchestrationPage } from "@/pages/AdminCredentialOrchestrationPage";
import { AdminExecutionReadinessPage } from "@/pages/AdminExecutionReadinessPage";
import { AdminExecutionOperatorCenterPage } from "@/pages/AdminExecutionOperatorCenterPage";
import { AdminBrandSettingsPage } from "@/pages/AdminBrandSettingsPage";
import { AdminAnomalyTimelinePage } from "@/pages/AdminAnomalyTimelinePage";
import AdminIncidentIntelligencePage from "@/pages/AdminIncidentIntelligencePage";
import AdminIncidentDetailPage from "@/pages/AdminIncidentDetailPage";
import AdminUnifiedControlRoomPage from "@/pages/AdminUnifiedControlRoomPage";
import { AdminActionAuditPage } from "@/pages/AdminActionAuditPage";
import { PipelineOperationsPage } from "@/pages/PipelineOperationsPage";
import { MfaSettingsPage } from "@/pages/MfaSettingsPage";
import { AdminLiveGatePage } from "@/pages/AdminLiveGatePage";

const HomeRedirect = () => {
  const { user } = useAuth();
  const adminRoles = new Set(["super_admin", "admin", "ops"]);

  if (!user) {
    return <LandingPage />;
  }
  if (adminRoles.has(String(user.role || "").toLowerCase())) {
    return <Navigate to="/admin/dashboard" replace />;
  }
  return <Navigate to="/user/bot-profiles" replace />;
};

const ExecuteToTradeRedirect = () => {
  const location = useLocation();
  const search = String(location?.search || "");
  return <Navigate to={`/user/trade${search}`} replace />;
};

function App() {
  return (
    <AuthProvider>
      <BrowserRouter>
        <Routes>
          <Route path="/" element={<HomeRedirect />} />
          <Route path="/login" element={<Navigate to="/user/login" replace />} />
          <Route path="/user/login" element={<UserLoginPage />} />
          <Route path="/admin/login" element={<AdminLoginPage />} />
          <Route path="/forgot-password" element={<ForgotPasswordPage />} />
          <Route path="/reset-password" element={<ResetPasswordPage />} />

          <Route path="/dashboard" element={<Navigate to="/user/bot-profiles" replace />} />
          <Route path="/portfolio" element={<Navigate to="/user/portfolio" replace />} />
          <Route path="/trades" element={<Navigate to="/user/trades" replace />} />
          <Route path="/scanner" element={<Navigate to="/user/scanner" replace />} />
          <Route path="/signals" element={<Navigate to="/user/signals" replace />} />
          <Route path="/reports" element={<Navigate to="/user/reports" replace />} />
          <Route path="/execute" element={<ExecuteToTradeRedirect />} />

          <Route
            path="/admin"
            element={
              <ProtectedRoute role="admin">
                <PanelLayout />
              </ProtectedRoute>
            }
          >
            <Route path="dashboard" element={<AdminDashboardPage />} />
            <Route path="live-gate" element={<AdminLiveGatePage />} />
            <Route path="live-trading-dashboard" element={<AdminLiveTradingDashboardPage />} />
            <Route path="cross-dashboard-consistency" element={<AdminCrossDashboardConsistencyPage />} />
            <Route path="users" element={<Navigate to="/admin/kullanicilar/user-kullanicilar" replace />} />
            <Route path="commercial-ops" element={<AdminCommercialOpsPage />} />
            <Route path="revenue" element={<AdminRevenuePage />} />
            <Route path="users/economics" element={<Navigate to="/admin/kullanicilar/kullanici-ekonomisi" replace />} />
            <Route path="snapshots" element={<AdminSnapshotsPage />} />
            <Route path="credential-orchestration" element={<AdminCredentialOrchestrationPage />} />
            <Route path="users/admins" element={<Navigate to="/admin/kullanicilar/admin-kullanicilar" replace />} />
            <Route path="users/customers" element={<Navigate to="/admin/kullanicilar/user-kullanicilar" replace />} />
            <Route path="user-approvals" element={<Navigate to="/admin/kullanicilar/kullanici-onaylar" replace />} />
            <Route path="kullanicilar" element={<Navigate to="/admin/kullanicilar/kullanici-onaylar" replace />} />
            <Route path="kullanıcılar" element={<Navigate to="/admin/kullanicilar/kullanici-onaylar" replace />} />
            <Route path="kullanicilar/admin-kullanicilar" element={<AdminUsersPage scope="admin" />} />
            <Route path="kullanicilar/user-kullanicilar" element={<AdminUserUsersPage />} />
            <Route path="kullanicilar/kullanici-onaylar" element={<AdminUserApprovalsPage />} />
            <Route path="kullanicilar/kullanici-ekonomisi" element={<AdminUserEconomicsPage />} />
            <Route path="core/kullanicilar" element={<Navigate to="/admin/kullanicilar/kullanici-onaylar" replace />} />
            <Route path="core/kullanicilar/admin-kullanicilar" element={<Navigate to="/admin/kullanicilar/admin-kullanicilar" replace />} />
            <Route path="core/kullanicilar/user-kullanicilar" element={<Navigate to="/admin/kullanicilar/user-kullanicilar" replace />} />
            <Route path="core/kullanicilar/kullanici-onaylar" element={<Navigate to="/admin/kullanicilar/kullanici-onaylar" replace />} />
            <Route path="core/kullanicilar/kullanici-ekonomisi" element={<Navigate to="/admin/kullanicilar/kullanici-ekonomisi" replace />} />
            <Route path="onboarding-observability" element={<AdminOnboardingObservabilityPage />} />
            <Route path="system-alerts" element={<AdminSystemAlertsPage />} />
            <Route path="strategy/observability" element={<Navigate to="/admin/dashboard" replace />} />
            <Route path="strategy/observability/:strategyId" element={<Navigate to="/admin/dashboard" replace />} />
            <Route path="strategy/timeline/:chainId" element={<Navigate to="/admin/dashboard" replace />} />
            <Route path="futures/risk-monitor" element={<AdminFuturesRiskMonitorPage />} />
            <Route path="futures/liquidation-protection" element={<AdminFuturesRiskMonitorPage />} />
            <Route path="futures/strategy-control" element={<AdminFuturesStrategyControlGovernancePage />} />
            <Route path="futures/strategy-analytics" element={<Navigate to="/admin/futures/strategy-control" replace />} />
            <Route path="futures/strategy-governance" element={<Navigate to="/admin/futures/strategy-control" replace />} />
            <Route path="futures/cluster-risk" element={<AdminFuturesClusterRiskPage />} />
            <Route path="futures/capital-governance" element={<Navigate to="/admin/futures/strategy-control" replace />} />
            <Route path="futures/tail-risk" element={<AdminFuturesTailRiskPage />} />
            <Route path="futures/live-readiness" element={<AdminFuturesLiveReadinessPage />} />
            <Route path="system-readiness" element={<AdminFuturesLiveReadinessPage />} />
            <Route path="futures/scaling-validation" element={<AdminFuturesScalingValidationPage />} />
            <Route path="futures/microstructure-guard" element={<AdminFuturesMicrostructureGuardPage />} />
            <Route path="futures/live-control" element={<AdminFuturesLiveControlPage />} />
            <Route path="exchanges" element={<AdminExchangesPage />} />
            <Route path="proofs" element={<AdminProofsPage />} />
            <Route path="reports/archive" element={<AdminReportsArchivePage />} />
            <Route path="strategies" element={<AdminStrategiesPage />} />
            <Route path="risk-orchestrator" element={<AdminRiskOrchestratorPage />} />
            <Route path="risk-orchestrator/analytics" element={<AdminRiskOrchestratorAnalyticsPage />} />
            <Route path="runtime/quarantine" element={<AdminRuntimeQuarantinePage />} />
            <Route path="runtime/recovery" element={<AdminRuntimeRecoveryPage />} />
            <Route path="market-universe" element={<MarketUniversePage />} />
            <Route path="execution-policies" element={<Navigate to="/admin/dashboard" replace />} />
            <Route path="execution-queue" element={<Navigate to="/admin/dashboard" replace />} />
            <Route path="execution-readiness" element={<AdminExecutionReadinessPage />} />
            <Route path="execution/operator-center" element={<AdminExecutionOperatorCenterPage />} />
            <Route path="action-audit" element={<AdminActionAuditPage />} />
            <Route path="pipeline-control" element={<Navigate to="/admin/pipeline-operations" replace />} />
            <Route path="pipeline-monitoring" element={<Navigate to="/admin/pipeline-operations" replace />} />
            <Route path="pipeline-operations" element={<PipelineOperationsPage />} />
            <Route path="mfa-settings" element={<MfaSettingsPage />} />
            <Route path="brand-settings" element={<AdminBrandSettingsPage />} />
            <Route path="anomaly-timeline" element={<AdminAnomalyTimelinePage />} />
            <Route path="incident-intelligence" element={<AdminIncidentIntelligencePage />} />
            <Route path="incident-intelligence/:incidentId" element={<AdminIncidentDetailPage />} />
            <Route path="unified-control-room" element={<AdminUnifiedControlRoomPage />} />
            <Route path="strategy/allocation" element={<AdminStrategyAllocationPage />} />
            <Route path="portfolio-risk" element={<AdminPortfolioRiskPage />} />
            <Route path="positions-monitor" element={<AdminPositionsMonitorPage />} />
            <Route path="strategy/intelligence" element={<AdminStrategyIntelligencePage />} />
            <Route path="strategy/canonical-registry" element={<AdminCanonicalStrategyRegistryPage />} />
            <Route path="learning-panel" element={<AdminLearningPanelPage />} />
            <Route path="learning-impact-simulator" element={<Navigate to="/admin/dashboard" replace />} />
            <Route path="universe-monitor" element={<AdminUniverseMonitorPage />} />
            <Route path="freshness-heatmap" element={<AdminFreshnessHeatmapPage />} />
            <Route path="exposure-groups" element={<ExposureGroupsPage />} />
            <Route path="correlation-matrix" element={<CorrelationMatrixPage />} />
            <Route path="strategy/execution-state-machine" element={<Navigate to="/admin/dashboard" replace />} />
            <Route path="hardening-checklist" element={<HardeningChecklistPage />} />
            <Route path="failed-events" element={<FailedEventsPage />} />
            <Route path="state-rebuild" element={<StateRebuildLogsPage />} />
            <Route path="execution/states" element={<Navigate to="/admin/dashboard" replace />} />
            <Route path="execution/analytics" element={<Navigate to="/admin/dashboard" replace />} />
            <Route path="execution/failures" element={<FailedEventsPage />} />
            <Route path="execution/idempotency" element={<ExecutionIdempotencyPage />} />
            <Route path="execution/trace" element={<ExecutionTracePage />} />
            <Route path="execution/alerts" element={<AdminExecutionAlertsPage />} />
            <Route path="execution/rebuild" element={<StateRebuildLogsPage />} />
            <Route path="backtest-cards" element={<BacktestCardsPage />} />
            <Route path="monitoring" element={<Navigate to="/admin/dashboard" replace />} />
            <Route path="system-status" element={<Navigate to="/admin/dashboard" replace />} />
            <Route path="phase4-live" element={<Navigate to="/admin/dashboard" replace />} />
            <Route path="audit-logs" element={<AuditLogsPage />} />
            <Route path="log" element={<Navigate to="/admin/audit-logs" replace />} />
            <Route path="logs" element={<Navigate to="/admin/audit-logs" replace />} />
            <Route path="core/logs" element={<AuditLogsPage />} />

            <Route path="strategy-allocation" element={<Navigate to="/admin/strategy/allocation" replace />} />
            <Route path="strategy-intelligence" element={<Navigate to="/admin/strategy/intelligence" replace />} />
            <Route path="canonical-strategy-registry" element={<Navigate to="/admin/strategy/canonical-registry" replace />} />
            <Route path="execution-states" element={<Navigate to="/admin/execution/states" replace />} />
            <Route path="execution-failures" element={<Navigate to="/admin/execution/failures" replace />} />
            <Route path="strategy-observability" element={<Navigate to="/admin/dashboard" replace />} />
          </Route>

          <Route
            path="/user"
            element={
              <ProtectedRoute role="user">
                <PanelLayout />
              </ProtectedRoute>
            }
          >
            <Route path="dashboard" element={<UserLiveTradingDashboardPage />} />
            <Route path="overview" element={<UserDashboardPage />} />
            <Route path="portfolio" element={<UserPortfolioPage />} />
            <Route path="trades" element={<UserTradesPage />} />
            <Route path="trades/:tradeId" element={<UserTradeDetailPage />} />
            <Route path="execution" element={<UserExecutionPage />} />
            <Route path="alerts" element={<UserAlertCenterPage />} />
            <Route path="activity-log" element={<UserActivityLogPage />} />
            <Route path="scanner" element={<UserScannerPage />} />
            <Route path="pro-scanner" element={<UserScannerPage />} />
            <Route path="indicator-screener" element={<UserSimpleScannerPage />} />
            <Route path="signals" element={<UserSignalsPage />} />
            <Route path="signal" element={<Navigate to="/user/signals" replace />} />
            <Route path="symbol/:symbol" element={<UserSymbolDecisionDetailPage />} />
            <Route path="reports" element={<Navigate to="/user/portfolio?tab=reports" replace />} />
            <Route path="execute" element={<ExecuteToTradeRedirect />} />
            <Route path="trade" element={<UserTradePage />} />
            <Route path="trade-entry" element={<Navigate to="/user/trade" replace />} />
            <Route path="chart" element={<UserChartPage />} />
            <Route path="bot-profiles" element={<BotProfilesPage />} />
            <Route path="pro-bot-profiles" element={<BotProfilesPage />} />
            <Route path="bots" element={<Navigate to="/user/bot-profiles" replace />} />
            <Route path="risk-policy" element={<RiskPoliciesPage />} />
            <Route path="risk-policies" element={<RiskPoliciesPage />} />
            <Route path="strategies" element={<Navigate to="/user/bot-profiles" replace />} />
            <Route path="pro-strategies" element={<StrategyTemplatesPage />} />
            <Route path="strategies/:templateId" element={<StrategyTemplateDetailPage />} />
            <Route path="backtest-insights" element={<BacktestInsightsPage />} />
            <Route path="exchange-settings" element={<UserExchangeSettingsPage />} />
            <Route path="exchange-diagnostics" element={<UserExchangeDiagnosticsPage />} />
            <Route path="settings" element={<UserSettingsPage />} />
            <Route path="mfa-settings" element={<MfaSettingsPage />} />
            <Route path="positions" element={<UserPositionsPage />} />
            <Route path="live-trading-dashboard" element={<UserLiveTradingDashboardPage />} />
            <Route path="exchange-mock" element={<Navigate to="/user/dashboard" replace />} />
          </Route>

          <Route path="/app/*" element={<Navigate to="/" replace />} />
        </Routes>
      </BrowserRouter>
      <Toaster position="top-right" richColors closeButton />
    </AuthProvider>
  );
}

export default App;
