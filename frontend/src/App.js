import "@/App.css";
import { BrowserRouter, Navigate, Route, Routes } from "react-router-dom";
import { Toaster } from "sonner";

import { AuthProvider, useAuth } from "@/context/AuthContext";
import { PanelLayout } from "@/components/PanelLayout";
import { ProtectedRoute } from "@/components/ProtectedRoute";
import { AdminLoginPage } from "@/pages/AdminLoginPage";
import { AdminDashboardPage } from "@/pages/AdminDashboardPage";
import { AdminExchangesPage } from "@/pages/AdminExchangesPage";
import { AdminFuturesRiskMonitorPage } from "@/pages/AdminFuturesRiskMonitorPage";
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
import { ExchangeMockPage } from "@/pages/ExchangeMockPage";
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

function App() {
  return (
    <AuthProvider>
      <BrowserRouter>
        <Routes>
          <Route path="/" element={<HomeRedirect />} />
          <Route path="/login" element={<Navigate to="/user/login" replace />} />
          <Route path="/user/login" element={<UserLoginPage />} />
          <Route path="/admin/login" element={<AdminLoginPage />} />

          <Route
            path="/admin"
            element={
              <ProtectedRoute role="admin">
                <PanelLayout />
              </ProtectedRoute>
            }
          >
            <Route path="dashboard" element={<AdminDashboardPage />} />
            <Route path="users" element={<AdminUsersPage />} />
            <Route path="user-approvals" element={<AdminUserApprovalsPage />} />
            <Route path="system-alerts" element={<AdminSystemAlertsPage />} />
            <Route path="strategy-observability" element={<AdminStrategyObservabilityPage />} />
            <Route path="futures/risk-monitor" element={<AdminFuturesRiskMonitorPage />} />
            <Route path="futures/liquidation-protection" element={<AdminFuturesRiskMonitorPage />} />
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
            <Route path="exposure-groups" element={<ExposureGroupsPage />} />
            <Route path="correlation-matrix" element={<CorrelationMatrixPage />} />
            <Route path="execution-states" element={<ExecutionStatesPage />} />
            <Route path="hardening-checklist" element={<HardeningChecklistPage />} />
            <Route path="failed-events" element={<FailedEventsPage />} />
            <Route path="state-rebuild" element={<StateRebuildLogsPage />} />
            <Route path="backtest-cards" element={<BacktestCardsPage />} />
            <Route path="monitoring" element={<MonitoringPage />} />
            <Route path="phase4-live" element={<Phase4LiveControlPage />} />
            <Route path="audit-logs" element={<AuditLogsPage />} />
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
            <Route path="bots" element={<BotProfilesPage />} />
            <Route path="risk-policies" element={<RiskPoliciesPage />} />
            <Route path="strategies" element={<StrategyTemplatesPage />} />
            <Route path="backtest-insights" element={<BacktestInsightsPage />} />
            <Route path="exchange-settings" element={<UserExchangeSettingsPage />} />
            <Route path="positions" element={<PaperPositionsPage />} />
            <Route path="exchange-mock" element={<ExchangeMockPage />} />
          </Route>

          <Route path="/app/*" element={<Navigate to="/" replace />} />
        </Routes>
      </BrowserRouter>
      <Toaster position="top-right" richColors closeButton />
    </AuthProvider>
  );
}

export default App;
