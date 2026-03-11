import { Navigate } from "react-router-dom";

import { useAuth } from "@/context/AuthContext";

export const ProtectedRoute = ({ children, role = null }) => {
  const { user, loading } = useAuth();

  if (loading) {
    return (
      <div className="warm-theme flex min-h-screen items-center justify-center bg-slate-950 text-slate-100" data-testid="auth-loading-state">
        Yükleniyor...
      </div>
    );
  }

  if (!user) {
    return <Navigate to="/login" replace />;
  }

  if (role && user.role !== role) {
    return <Navigate to="/app/user" replace />;
  }

  return children;
};
