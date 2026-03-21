import "@/App.css";
import { BrowserRouter, Navigate, Route, Routes, useLocation } from "react-router-dom";
import { Toaster } from "sonner";

import { AuthProvider, useAuth } from "@/context/AuthContext";
import { PanelLayout } from "@/components/PanelLayout";
import { ProtectedRoute } from "@/components/ProtectedRoute";
import { AdminLoginPage } from "@/pages/AdminLoginPage";
import { AdminDashboardPage } from "@/pages/AdminDashboardPage";
import { AdminExchangesPage } from "@/pages/AdminExchangesPage";
import { AdminFuturesRiskMonitorPage } from "@/pages/AdminFuturesRiskMonitorPage";
import { AdminFuturesStrategyAnalyticsPage } from "@/pages/AdminFuturesStrategyAnalyticsPage";
import { AdminFuturesStrategyGovernancePage } from "@/pages/AdminFuturesStrategyGovernancePage";
import { AdminFuturesClusterRiskPage } from "@/pages/AdminFuturesClusterRiskPage";
import { AdminFuturesCapitalGovernancePage } from "@/pages/AdminFuturesCapitalGovernancePage";
import { AdminFuturesTailRiskPage } from "@/pages/AdminFuturesTailRiskPage";
import { AdminFuturesLiveReadinessPage } from "@/pages/AdminFuturesLiveReadinessPage";
import { AdminFuturesScalingValidationPage } from "@/pages/AdminFuturesScalingValidationPage";
import { AdminFuturesMicrostructureGuardPage } from "@/pages/AdminFuturesMicrostructureGuardPage";
import { AdminFuturesTestnetControlPage } from "@/pages/AdminFuturesTestnetControlPage";
import { AdminProofsPage } from "@/pages/AdminProofsPage";
import { AdminReportsArchivePage } from "@/pages/AdminReportsArchivePage";
import { AdminRiskOrchestratorPage } from "@/pages/AdminRiskOrchestratorPage";
import { AdminRiskOrchestratorAnalyticsPage } from "@/pages/AdminRiskOrchestratorAnalyticsPage";
import { AdminRuntimeQuarantinePage } from "@/pages/AdminRuntimeQuarantinePage";
import { AdminRuntimeRecoveryPage } from "@/pages/AdminRuntimeRecoveryPage";
import { AdminStrategiesPage } from "@/pages/AdminStrategiesPage";
import { AdminStrategyObservabilityPage } from "@/pages/AdminStrategyObservabilityPage";
import { AdminSystemAlertsPage } from "@/pages/AdminSystemAlertsPage";
import { AdminUserApprovalsPage } from "@/pages/AdminUserApprovalsPage";
import { AdminUsersPage } from "@/pages/AdminUsersPage";
import { AuditLogsPage } from "@/pages/AuditLogsPage";
import { BacktestCardsPage } from "@/pages/BacktestCardsPage";
import { BacktestInsightsPage } from "@/pages/BacktestInsightsPage";
import { BotProfilesPage } from "@/pages/BotProfilesPage";
import { CorrelationMatrixPage } from "@/pages/CorrelationMatrixPage";
import { ExecutionPoliciesPage } from "@/pages/ExecutionPoliciesPage";
import { ExecutionStatesPage } from "@/pages/ExecutionStatesPage";
import { ExposureGroupsPage } from "@/pages/ExposureGroupsPage";
import { FailedEventsPage } from "@/pages/FailedEventsPage";
import { HardeningChecklistPage } from "@/pages/HardeningChecklistPage";
import { LandingPage } from "@/pages/LandingPage";
import { MarketUniversePage } from "@/pages/MarketUniversePage";
import { MonitoringPage } from "@/pages/MonitoringPage";
import { PaperPositionsPage } from "@/pages/PaperPositionsPage";
import { Phase4LiveControlPage } from "@/pages/Phase4LiveControlPage";
import { RiskPoliciesPage } from "@/pages/RiskPoliciesPage";
import { StateRebuildLogsPage } from "@/pages/StateRebuildLogsPage";
import { StrategyTemplatesPage } from "@/pages/StrategyTemplatesPage";
import { UserLoginPage } from "@/pages/UserLoginPage";
import { UserExchangeSettingsPage } from "@/pages/UserExchangeSettingsPage";
import { UserDashboardPage } from "@/pages/UserDashboardPage";
import { UserPortfolioPage } from "@/pages/UserPortfolioPage";
import { UserTradesPage } from "@/pages/UserTradesPage";
import { UserScannerPage } from "@/pages/UserScannerPage";
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
import { AdminExecutionQueuePage } from "@/pages/AdminExecutionQueuePage";
import { AdminStrategyAllocationPage } from "@/pages/AdminStrategyAllocationPage";
import { AdminPortfolioRiskPage } from "@/pages/AdminPortfolioRiskPage";
import { AdminPositionsMonitorPage } from "@/pages/AdminPositionsMonitorPage";
import { AdminStrategyIntelligencePage } from "@/pages/AdminStrategyIntelligencePage";
import { AdminCrossDashboardConsistencyPage } from "@/pages/AdminCrossDashboardConsistencyPage";
import { AdminCanonicalStrategyRegistryPage } from "@/pages/AdminCanonicalStrategyRegistryPage";
import { AdminLearningPanelPage } from "@/pages/AdminLearningPanelPage";
import { AdminLearningImpactSimulatorPage } from "@/pages/AdminLearningImpactSimulatorPage";
import { AdminLiveTradingDashboardPage } from "@/pages/AdminLiveTradingDashboardPage";
import { AdminUniverseMonitorPage } from "@/pages/AdminUniverseMonitorPage";
import { AdminFreshnessHeatmapPage } from "@/pages/AdminFreshnessHeatmapPage";
import { AdminCommercialOpsPage } from "@/pages/AdminCommercialOpsPage";
import { AdminExecutionReadinessPage } from "@/pages/AdminExecutionReadinessPage";
import { AdminBrandSettingsPage } from "@/pages/AdminBrandSettingsPage";
import { AdminAnomalyTimelinePage } from "@/pages/AdminAnomalyTimelinePage";
import { MfaSettingsPage } from "@/pages/MfaSettingsPage";

const HomeRedirect = () => {
  const { user } = useAuth();
  const adminRoles = new Set(["super_admin", "admin", "ops"]);

  if (!user) {
    return <LandingPage />;
  }
  if (adminRoles.has(user.role)) {
    return <Navigate to="/admin/dashboard" replace />;
  }
  return <Navigate to="/user/dashboard" replace />;
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

          <Route path="/dashboard" element={<Navigate to="/user/dashboard" replace />} />
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
            <Route path="live-trading-dashboard" element={<AdminLiveTradingDashboardPage />} />
            <Route path="cross-dashboard-consistency" element={<AdminCrossDashboardConsistencyPage />} />
            <Route path="users" element={<Navigate to="/admin/users/customers" replace />} />
            <Route path="commercial-ops" element={<AdminCommercialOpsPage />} />
            <Route path="users/admins" element={<AdminUsersPage scope="admin" />} />
            <Route path="users/customers" element={<AdminUsersPage scope="user" />} />
            <Route path="user-approvals" element={<AdminUserApprovalsPage />} />
            <Route path="system-alerts" element={<AdminSystemAlertsPage />} />
            <Route path="strategy/observability" element={<AdminStrategyObservabilityPage />} />
            <Route path="futures/risk-monitor" element={<AdminFuturesRiskMonitorPage />} />
            <Route path="futures/liquidation-protection" element={<AdminFuturesRiskMonitorPage />} />
            <Route path="futures/strategy-analytics" element={<AdminFuturesStrategyAnalyticsPage />} />
            <Route path="futures/strategy-governance" element={<AdminFuturesStrategyGovernancePage />} />
            <Route path="futures/cluster-risk" element={<AdminFuturesClusterRiskPage />} />
            <Route path="futures/capital-governance" element={<AdminFuturesCapitalGovernancePage />} />
            <Route path="futures/tail-risk" element={<AdminFuturesTailRiskPage />} />
            <Route path="futures/live-readiness" element={<AdminFuturesLiveReadinessPage />} />
            <Route path="system-readiness" element={<AdminFuturesLiveReadinessPage />} />
            <Route path="futures/scaling-validation" element={<AdminFuturesScalingValidationPage />} />
            <Route path="futures/microstructure-guard" element={<AdminFuturesMicrostructureGuardPage />} />
            <Route path="futures/testnet-control" element={<AdminFuturesTestnetControlPage />} />
            <Route path="exchanges" element={<AdminExchangesPage />} />
            <Route path="proofs" element={<AdminProofsPage />} />
            <Route path="reports/archive" element={<AdminReportsArchivePage />} />
            <Route path="strategies" element={<AdminStrategiesPage />} />
            <Route path="risk-orchestrator" element={<AdminRiskOrchestratorPage />} />
            <Route path="risk-orchestrator/analytics" element={<AdminRiskOrchestratorAnalyticsPage />} />
            <Route path="runtime/quarantine" element={<AdminRuntimeQuarantinePage />} />
            <Route path="runtime/recovery" element={<AdminRuntimeRecoveryPage />} />
            <Route path="market-universe" element={<MarketUniversePage />} />
            <Route path="execution-policies" element={<ExecutionPoliciesPage />} />
            <Route path="execution-queue" element={<AdminExecutionQueuePage />} />
            <Route path="execution-readiness" element={<AdminExecutionReadinessPage />} />
            <Route path="mfa-settings" element={<MfaSettingsPage />} />
            <Route path="brand-settings" element={<AdminBrandSettingsPage />} />
            <Route path="anomaly-timeline" element={<AdminAnomalyTimelinePage />} />
            <Route path="strategy/allocation" element={<AdminStrategyAllocationPage />} />
            <Route path="portfolio-risk" element={<AdminPortfolioRiskPage />} />
            <Route path="positions-monitor" element={<AdminPositionsMonitorPage />} />
            <Route path="strategy/intelligence" element={<AdminStrategyIntelligencePage />} />
            <Route path="strategy/canonical-registry" element={<AdminCanonicalStrategyRegistryPage />} />
            <Route path="learning-panel" element={<AdminLearningPanelPage />} />
            <Route path="learning-impact-simulator" element={<AdminLearningImpactSimulatorPage />} />
            <Route path="universe-monitor" element={<AdminUniverseMonitorPage />} />
            <Route path="freshness-heatmap" element={<AdminFreshnessHeatmapPage />} />
            <Route path="exposure-groups" element={<ExposureGroupsPage />} />
            <Route path="correlation-matrix" element={<CorrelationMatrixPage />} />
            <Route path="strategy/execution-state-machine" element={<ExecutionStatesPage />} />
            <Route path="hardening-checklist" element={<HardeningChecklistPage />} />
            <Route path="failed-events" element={<FailedEventsPage />} />
            <Route path="state-rebuild" element={<StateRebuildLogsPage />} />
            <Route path="backtest-cards" element={<BacktestCardsPage />} />
            <Route path="monitoring" element={<MonitoringPage />} />
            <Route path="system-status" element={<MonitoringPage />} />
            <Route path="phase4-live" element={<Phase4LiveControlPage />} />
            <Route path="audit-logs" element={<AuditLogsPage />} />

            <Route path="strategy-allocation" element={<Navigate to="/admin/strategy/allocation" replace />} />
            <Route path="strategy-intelligence" element={<Navigate to="/admin/strategy/intelligence" replace />} />
            <Route path="canonical-strategy-registry" element={<Navigate to="/admin/strategy/canonical-registry" replace />} />
            <Route path="execution-states" element={<Navigate to="/admin/strategy/execution-state-machine" replace />} />
            <Route path="strategy-observability" element={<Navigate to="/admin/strategy/observability" replace />} />
          </Route>

          <Route
            path="/user"
            element={
              <ProtectedRoute role="user">
                <PanelLayout />
              </ProtectedRoute>
            }
          >
            <Route path="dashboard" element={<UserDashboardPage />} />
            <Route path="portfolio" element={<UserPortfolioPage />} />
            <Route path="trades" element={<UserTradesPage />} />
            <Route path="scanner" element={<UserScannerPage />} />
            <Route path="indicator-screener" element={<UserIndicatorScreenerPage />} />
            <Route path="signals" element={<UserSignalsPage />} />
            <Route path="symbol/:symbol" element={<UserSymbolDecisionDetailPage />} />
            <Route path="reports" element={<UserReportsPage />} />
            <Route path="execute" element={<ExecuteToTradeRedirect />} />
            <Route path="trade" element={<UserTradePage />} />
            <Route path="chart" element={<UserChartPage />} />
            <Route path="bot-profiles" element={<BotProfilesPage />} />
            <Route path="bots" element={<Navigate to="/user/bot-profiles" replace />} />
            <Route path="risk-policy" element={<RiskPoliciesPage />} />
            <Route path="risk-policies" element={<Navigate to="/user/risk-policy" replace />} />
            <Route path="strategies" element={<StrategyTemplatesPage />} />
            <Route path="backtest-insights" element={<BacktestInsightsPage />} />
            <Route path="exchange-settings" element={<UserExchangeSettingsPage />} />
            <Route path="mfa-settings" element={<MfaSettingsPage />} />
            <Route path="positions" element={<UserPositionsPage />} />
            <Route path="live-trading-dashboard" element={<UserLiveTradingDashboardPage />} />
            <Route path="paper-positions" element={<PaperPositionsPage />} />
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
