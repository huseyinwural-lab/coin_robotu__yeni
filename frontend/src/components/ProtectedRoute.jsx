import { Navigate } from "react-router-dom";

import { useAuth } from "@/context/AuthContext";

const adminRoles = new Set(["super_admin", "admin", "ops"]);

export const ProtectedRoute = ({ children, role = null }) => {
  const { user, token, loading } = useAuth();

  if (loading) {
    return (
      <div className="flex min-h-screen items-center justify-center bg-slate-950 text-slate-100" data-testid="auth-loading-state">
        Yükleniyor...
      </div>
    );
  }

  if (!user && token) {
    return (
      <div className="flex min-h-screen items-center justify-center bg-slate-950 text-slate-100" data-testid="auth-session-restore-state">
        Oturum doğrulanıyor...
      </div>
    );
  }

  if (!user) {
    const loginPath = role === "admin" ? "/admin/login" : "/user/login";
    return <Navigate to={loginPath} replace />;
  }

  const normalizedRole = String(user?.role || "").toLowerCase();
  const roleMatched =
    !role
    || (role === "admin" && adminRoles.has(normalizedRole))
    || (role === "user" && (normalizedRole === "user" || adminRoles.has(normalizedRole)))
    || (role !== "admin" && role !== "user" && normalizedRole === String(role || "").toLowerCase());

  if (!roleMatched) {
    return <Navigate to={adminRoles.has(normalizedRole) ? "/admin/dashboard" : "/user/dashboard"} replace />;
  }

  return children;
};
