import { Navigate } from "react-router-dom";

import { useAuth } from "@/context/AuthContext";

const adminRoles = new Set(["super_admin", "admin", "ops"]);

export const ProtectedRoute = ({ children, role = null }) => {
  const { user, loading } = useAuth();

  if (loading) {
    return (
      <div className="flex min-h-screen items-center justify-center bg-slate-950 text-slate-100" data-testid="auth-loading-state">
        Yükleniyor...
      </div>
    );
  }

  if (!user) {
    const loginPath = role === "admin" ? "/admin/login" : "/user/login";
    return <Navigate to={loginPath} replace />;
  }

  const roleMatched =
    !role
    || (role === "admin" && adminRoles.has(user.role))
    || (role !== "admin" && user.role === role);

  if (!roleMatched) {
    return <Navigate to={adminRoles.has(user.role) ? "/admin/dashboard" : "/user/dashboard"} replace />;
  }

  return children;
};
