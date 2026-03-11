import "@/App.css";
import { BrowserRouter, Navigate, Route, Routes } from "react-router-dom";
import { Toaster } from "sonner";

import { AuthProvider, useAuth } from "@/context/AuthContext";
import { PanelLayout } from "@/components/PanelLayout";
import { ProtectedRoute } from "@/components/ProtectedRoute";
import { AdminDashboardPage } from "@/pages/AdminDashboardPage";
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
import { LoginPage } from "@/pages/LoginPage";
import { MarketUniversePage } from "@/pages/MarketUniversePage";
import { MonitoringPage } from "@/pages/MonitoringPage";
import { PaperPositionsPage } from "@/pages/PaperPositionsPage";
import { Phase4LiveControlPage } from "@/pages/Phase4LiveControlPage";
import { RiskPoliciesPage } from "@/pages/RiskPoliciesPage";
import { StateRebuildLogsPage } from "@/pages/StateRebuildLogsPage";
import { StrategyTemplatesPage } from "@/pages/StrategyTemplatesPage";
import { UserDashboardPage } from "@/pages/UserDashboardPage";

const HomeRedirect = () => {
  const { user } = useAuth();

  if (!user) {
    return <LandingPage />;
  }
  if (user.role === "admin") {
    return <Navigate to="/app/admin" replace />;
  }
  return <Navigate to="/app/user" replace />;
};

function App() {
  return (
    <AuthProvider>
      <BrowserRouter>
        <Routes>
          <Route path="/" element={<HomeRedirect />} />
          <Route path="/login" element={<LoginPage />} />

          <Route
            path="/app"
            element={
              <ProtectedRoute>
                <PanelLayout />
              </ProtectedRoute>
            }
          >
            <Route path="user" element={<UserDashboardPage />} />
            <Route path="admin" element={<ProtectedRoute role="admin"><AdminDashboardPage /></ProtectedRoute>} />
            <Route path="market-universe" element={<ProtectedRoute role="admin"><MarketUniversePage /></ProtectedRoute>} />
            <Route path="execution-policies" element={<ProtectedRoute role="admin"><ExecutionPoliciesPage /></ProtectedRoute>} />
            <Route path="exposure-groups" element={<ProtectedRoute role="admin"><ExposureGroupsPage /></ProtectedRoute>} />
            <Route path="correlation-matrix" element={<ProtectedRoute role="admin"><CorrelationMatrixPage /></ProtectedRoute>} />
            <Route path="execution-states" element={<ProtectedRoute role="admin"><ExecutionStatesPage /></ProtectedRoute>} />
            <Route path="hardening-checklist" element={<ProtectedRoute role="admin"><HardeningChecklistPage /></ProtectedRoute>} />
            <Route path="failed-events" element={<ProtectedRoute role="admin"><FailedEventsPage /></ProtectedRoute>} />
            <Route path="state-rebuild" element={<ProtectedRoute role="admin"><StateRebuildLogsPage /></ProtectedRoute>} />
            <Route path="backtest-cards" element={<ProtectedRoute role="admin"><BacktestCardsPage /></ProtectedRoute>} />
            <Route path="monitoring" element={<ProtectedRoute role="admin"><MonitoringPage /></ProtectedRoute>} />
            <Route path="phase4-live" element={<ProtectedRoute role="admin"><Phase4LiveControlPage /></ProtectedRoute>} />
            <Route path="bots" element={<BotProfilesPage />} />
            <Route path="risk-policies" element={<RiskPoliciesPage />} />
            <Route path="strategies" element={<StrategyTemplatesPage />} />
            <Route path="backtest-insights" element={<BacktestInsightsPage />} />
            <Route path="positions" element={<PaperPositionsPage />} />
            <Route path="audit-logs" element={<ProtectedRoute role="admin"><AuditLogsPage /></ProtectedRoute>} />
            <Route path="exchange-mock" element={<ExchangeMockPage />} />
          </Route>
        </Routes>
      </BrowserRouter>
      <Toaster position="top-right" richColors closeButton />
    </AuthProvider>
  );
}

export default App;
