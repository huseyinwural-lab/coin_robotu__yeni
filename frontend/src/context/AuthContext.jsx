import { createContext, useContext, useEffect, useMemo, useRef, useState } from "react";

import { apiClient, buildSessionHeaders, FRONTEND_BACKEND_URL, setAuthToken } from "@/lib/api";

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

const authFetchJson = async (path, { method = "GET", body = null, token = null, timeoutMs = 45000 } = {}) => {
  const controller = new AbortController();
  const timer = window.setTimeout(() => controller.abort(), timeoutMs);
  try {
    const response = await fetch(`${FRONTEND_BACKEND_URL}/api${path}`, {
      method,
      headers: {
        ...buildSessionHeaders(),
        ...(token ? { Authorization: `Bearer ${token}` } : {}),
      },
      credentials: "include",
      cache: "no-store",
      signal: controller.signal,
      body: body ? JSON.stringify(body) : undefined,
    });
    let payload = null;
    try {
      payload = await response.json();
    } catch {
      payload = null;
    }
    if (!response.ok) {
      const error = new Error((payload && (payload.detail || payload.reason_code)) || `request_failed_${response.status}`);
      error.response = { status: response.status, data: payload };
      throw error;
    }
    return payload;
  } finally {
    window.clearTimeout(timer);
  }
};

export const AuthProvider = ({ children }) => {
  const [user, setUser] = useState(readStoredUser);
  const [token, setToken] = useState(localStorage.getItem(AUTH_TOKEN_KEY));
  const [loading, setLoading] = useState(true);
  const lastHydratedTokenRef = useRef(null);

  useEffect(() => {
    let cancelled = false;

    const hydrate = async () => {
      const hydrateToken = token;
      lastHydratedTokenRef.current = hydrateToken;
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
        const { data } = await apiClient.get("/auth/me", { timeout: 30000 });
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
        const detail = String(error?.response?.data?.detail || "").toLowerCase();
        if (status === 401 && detail.includes("session_device_mismatch")) {
          try {
            await new Promise((resolve) => window.setTimeout(resolve, 350));
            const retry = await apiClient.get("/auth/me", { timeout: 30000 });
            if (!cancelled) {
              setUser(retry.data);
              localStorage.setItem(AUTH_USER_KEY, JSON.stringify(retry.data));
              setLoading(false);
            }
            return;
          } catch {
            // fall through to normal 401 cleanup
          }
        }
        if (status === 0 || String(error?.name || "").toLowerCase() === "aborterror" || String(error?.code || "").toUpperCase() === "ERR_NETWORK") {
          try {
            const retryPayload = await authFetchJson("/auth/me", { method: "GET", token, timeoutMs: 30000 });
            if (!cancelled) {
              setUser(retryPayload);
              localStorage.setItem(AUTH_USER_KEY, JSON.stringify(retryPayload));
              setLoading(false);
            }
            return;
          } catch {
            // continue into normal fallback path
          }
        }
        if (status === 401) {
          const latestStoredToken = localStorage.getItem(AUTH_TOKEN_KEY);
          if (latestStoredToken && latestStoredToken !== hydrateToken) {
            if (!cancelled) {
              setLoading(false);
            }
            return;
          }
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
    clearAuthSession();
    setAuthToken(null);
    const panelPath = panel === "admin" ? "/auth/login/admin" : panel === "user" ? "/auth/login/user" : "/auth/login";
    let data;
    let lastError = null;
    const isNetworkLikeError = (error) => {
      const code = String(error?.code || "").toUpperCase();
      const message = String(error?.message || "").toLowerCase();
      return (
        code === "ERR_NETWORK" ||
        code === "ERR_ABORTED" ||
        code === "ERR_CANCELED" ||
        String(error?.name || "").toLowerCase() === "aborterror" ||
        message.includes("network") ||
        message.includes("canceled") ||
        message.includes("aborted")
      );
    };

    for (let attempt = 0; attempt < 3; attempt += 1) {
      try {
        const response = await apiClient.post(panelPath, { email, password }, { timeout: 45000 });
        data = response.data;
        break;
      } catch (error) {
        if (!isNetworkLikeError(error)) {
          throw error;
        }
        lastError = error;
        try {
          data = await authFetchJson(panelPath, { method: "POST", body: { email, password }, timeoutMs: 45000 });
          break;
        } catch (fallbackError) {
          lastError = fallbackError;
        }
        if (attempt < 2) {
          await new Promise((resolve) => window.setTimeout(resolve, 400 + attempt * 300));
        }
      }
    }

    if (!data) {
      throw lastError || new Error("login_request_failed");
    }
    if (data?.mfa_required) {
      return {
        mfaRequired: true,
        challengeToken: data.mfa_challenge_token,
        methods: data.mfa_methods || [],
        expiresAt: data.mfa_expires_at,
        graceActive: Boolean(data.mfa_grace_active),
        graceExpiresAt: data.mfa_grace_expires_at || null,
        mfaSetupRequired: Boolean(data.mfa_setup_required),
        riskLevel: data.risk_level || "low",
        riskReasons: data.risk_reasons || [],
        challengeReason: data.challenge_reason || null,
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
    let data;
    try {
      const response = await apiClient.post("/mfa/verify", {
        challenge_token: challengeToken,
        method,
        code: code || "",
      }, { timeout: 30000 });
      data = response.data;
    } catch (error) {
      const code = String(error?.code || "").toUpperCase();
      const message = String(error?.message || "").toLowerCase();
      const isNetworkLike = code === "ERR_NETWORK" || code === "ERR_ABORTED" || String(error?.name || "").toLowerCase() === "aborterror" || message.includes("network") || message.includes("canceled") || message.includes("aborted");
      if (!isNetworkLike) {
        throw error;
      }
      data = await authFetchJson("/mfa/verify", { method: "POST", body: { challenge_token: challengeToken, method, code: code || "" }, timeoutMs: 30000 });
    }
    persistAuthSession({ token: data.access_token, user: data.user || null });
    setAuthToken(data.access_token);
    setToken(data.access_token);
    setUser(data.user);
    return data.user;
  };

  const stepUpAuth = async ({ method, code, scope = [] }) => {
    const { data } = await apiClient.post("/auth/step-up", { method, code, scope });
    persistAuthSession({ token: data.access_token, user: data.user || null });
    setAuthToken(data.access_token);
    setToken(data.access_token);
    setUser(data.user);
    return data;
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
    () => ({ user, token, loading, login, verifyMfaChallenge, stepUpAuth, register, logout }),
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
