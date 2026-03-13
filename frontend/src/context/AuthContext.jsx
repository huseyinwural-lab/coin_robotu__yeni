import { createContext, useContext, useEffect, useMemo, useState } from "react";

import { apiClient, setAuthToken } from "@/lib/api";

const AuthContext = createContext(null);

export const AuthProvider = ({ children }) => {
  const [user, setUser] = useState(null);
  const [token, setToken] = useState(localStorage.getItem("token"));
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    const hydrate = async () => {
      if (!token) {
        setLoading(false);
        return;
      }
      try {
        setAuthToken(token);
        const { data } = await apiClient.get("/auth/me");
        setUser(data);
      } catch (error) {
        localStorage.removeItem("token");
        setAuthToken(null);
        setToken(null);
        setUser(null);
      } finally {
        setLoading(false);
      }
    };
    hydrate();
  }, [token]);

  const login = async ({ email, password, panel = "user" }) => {
    const loginEndpoint = panel === "admin" ? "/auth/login/admin" : "/auth/login/user";
    const { data } = await apiClient.post(loginEndpoint, { email, password });
    localStorage.setItem("token", data.access_token);
    setAuthToken(data.access_token);
    setToken(data.access_token);
    setUser(data.user);
    return data.user;
  };

  const register = async ({ email, password, full_name, phone }) => {
    const { data } = await apiClient.post("/auth/register", { email, password, full_name, phone });
    return data;
  };

  const logout = () => {
    localStorage.removeItem("token");
    setAuthToken(null);
    setToken(null);
    setUser(null);
  };

  const value = useMemo(
    () => ({ user, token, loading, login, register, logout }),
    [user, token, loading],
  );

  return <AuthContext.Provider value={value}>{children}</AuthContext.Provider>;
};

export const useAuth = () => {
  const context = useContext(AuthContext);
  if (!context) {
    throw new Error("useAuth must be used within AuthProvider");
  }
  return context;
};
