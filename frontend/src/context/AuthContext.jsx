import { createContext, useContext, useEffect, useMemo, useState } from "react";

import { apiClient, setAuthToken } from "@/lib/api";

const AuthContext = createContext(null);
const AUTH_TOKEN_KEY = "token";
const AUTH_USER_KEY = "auth_user";

const readStoredUser = () => {
  try {
    const raw = localStorage.getItem(AUTH_USER_KEY);
    if (!raw) {
      return null;
    }
    return JSON.parse(raw);
  } catch {
    return null;
  }
};

const persistAuthSession = ({ token, user }) => {
  if (token) {
    localStorage.setItem(AUTH_TOKEN_KEY, token);
  }
  if (user) {
    localStorage.setItem(AUTH_USER_KEY, JSON.stringify(user));
  }
};

const clearAuthSession = () => {
  localStorage.removeItem(AUTH_TOKEN_KEY);
  localStorage.removeItem(AUTH_USER_KEY);
};

export const AuthProvider = ({ children }) => {
  const [user, setUser] = useState(readStoredUser);
  const [token, setToken] = useState(localStorage.getItem(AUTH_TOKEN_KEY));
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    let cancelled = false;

    const hydrate = async () => {
      if (!token) {
        setAuthToken(null);
        if (!cancelled) {
          setUser(null);
          setLoading(false);
        }
        return;
      }

      if (!cancelled) {
        setLoading(true);
      }

      try {
        setAuthToken(token);
        const { data } = await apiClient.get("/auth/me");
        if (!cancelled) {
          setUser(data);
          localStorage.setItem(AUTH_USER_KEY, JSON.stringify(data));
        }
      } catch (error) {
        const errorCode = String(error?.code || "").toUpperCase();
        const errorMessage = String(error?.message || "").toLowerCase();
        const isCanceledRequest = errorCode === "ERR_CANCELED" || errorMessage.includes("canceled");
        if (isCanceledRequest) {
          return;
        }
        const status = Number(error?.response?.status || 0);
        if (status === 401) {
          clearAuthSession();
          setAuthToken(null);
          if (!cancelled) {
            setToken(null);
            setUser(null);
          }
        } else if (!cancelled) {
          setAuthToken(token);
          setUser((prev) => prev || readStoredUser());
        }
      } finally {
        if (!cancelled) {
          setLoading(false);
        }
      }
    };

    hydrate();

    return () => {
      cancelled = true;
    };
  }, [token]);

  useEffect(() => {
    const onAuthExpired = () => {
      clearAuthSession();
      setAuthToken(null);
      setToken(null);
      setUser(null);
    };

    const onStorageChanged = (event) => {
      if (event.key === AUTH_TOKEN_KEY) {
        const nextToken = localStorage.getItem(AUTH_TOKEN_KEY);
        setToken(nextToken);
      }
      if (event.key === AUTH_USER_KEY) {
        setUser(readStoredUser());
      }
    };

    window.addEventListener("platform-auth-expired", onAuthExpired);
    window.addEventListener("storage", onStorageChanged);
    return () => {
      window.removeEventListener("platform-auth-expired", onAuthExpired);
      window.removeEventListener("storage", onStorageChanged);
    };
  }, []);

  const login = async ({ email, password, panel = "user" }) => {
    const { data } = await apiClient.post("/auth/login", { email, password, panel });
    if (data?.mfa_required) {
      return {
        mfaRequired: true,
        challengeToken: data.mfa_challenge_token,
        methods: data.mfa_methods || [],
        expiresAt: data.mfa_expires_at,
        emailDeliveryStatus: data.email_delivery_status,
        emailCodePreview: data.email_code_preview,
        user: data.user || null,
      };
    }

    persistAuthSession({ token: data.access_token, user: data.user || null });
    setAuthToken(data.access_token);
    setToken(data.access_token);
    setUser(data.user);
    return { mfaRequired: false, user: data.user };
  };

  const verifyMfaChallenge = async ({ challengeToken, method, code }) => {
    const { data } = await apiClient.post("/auth/mfa/challenge/verify", {
      challenge_token: challengeToken,
      method,
      code,
    });
    persistAuthSession({ token: data.access_token, user: data.user || null });
    setAuthToken(data.access_token);
    setToken(data.access_token);
    setUser(data.user);
    return data.user;
  };

  const register = async ({ email, password, first_name, last_name, full_name, phone }) => {
    const { data } = await apiClient.post("/auth/register", {
      email,
      password,
      first_name,
      last_name,
      full_name,
      phone,
    });
    return data;
  };

  const logout = () => {
    clearAuthSession();
    setAuthToken(null);
    setToken(null);
    setUser(null);
  };

  const value = useMemo(
    () => ({ user, token, loading, login, verifyMfaChallenge, register, logout }),
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
