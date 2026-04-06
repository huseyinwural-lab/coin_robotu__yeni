import axios from "axios";

const CONFIGURED_BACKEND_URL = String(process.env.REACT_APP_BACKEND_URL || "").trim();
const LOOPBACK_URL_REGEX = /^https?:\/\/(localhost|127\.0\.0\.1)(:\d+)?$/i;
const isRemoteBrowser =
  typeof window !== "undefined" &&
  !/^(localhost|127\.0\.0\.1)$/i.test(String(window.location.hostname || ""));
const BACKEND_URL = CONFIGURED_BACKEND_URL;
const AUTH_TOKEN_KEY = "token";
const AUTH_USER_KEY = "auth_user";

if (!BACKEND_URL) {
  throw new Error(
    "Missing required frontend env: REACT_APP_BACKEND_URL. " +
      "API baseURL cannot be constructed.",
  );
}

if (!/^https?:\/\//i.test(BACKEND_URL)) {
  throw new Error(
    "Invalid REACT_APP_BACKEND_URL. Expected absolute http(s) URL.",
  );
}

if (isRemoteBrowser && LOOPBACK_URL_REGEX.test(BACKEND_URL)) {
  throw new Error(
    "Invalid REACT_APP_BACKEND_URL for remote browser. Loopback URL cannot be used in deployed environments.",
  );
}

export const FRONTEND_BACKEND_URL = BACKEND_URL.replace(/\/$/, "");

export const apiClient = axios.create({
  baseURL: `${FRONTEND_BACKEND_URL}/api`,
  timeout: 30000,
  withCredentials: true,
});

const isAuthPath = (url) => {
  const normalized = String(url || "");
  return normalized.includes("/auth/login") || normalized.includes("/auth/me") || normalized.includes("/mfa/") || normalized.includes("/auth/step-up");
};

const SESSION_STORAGE_KEY = "platform-session-id";
const DEVICE_STORAGE_KEY = "platform-device-id";

const decodeJwtPayload = (token) => {
  try {
    const [, payload = ""] = String(token || "").split(".");
    if (!payload) return null;
    const normalized = payload.replace(/-/g, "+").replace(/_/g, "/");
    const padded = normalized + "=".repeat((4 - (normalized.length % 4)) % 4);
    const decoded = atob(padded);
    return JSON.parse(decoded);
  } catch {
    return null;
  }
};

const setDeviceCookie = (deviceId) => {
  if (typeof document === "undefined") {
    return;
  }
  const secure = typeof window !== "undefined" && window.location.protocol === "https:" ? "; Secure" : "";
  document.cookie = `device_id=${encodeURIComponent(deviceId)}; Path=/; Max-Age=31536000; SameSite=Lax${secure}`;
};

const persistDeviceId = (deviceId) => {
  if (typeof window === "undefined") {
    return;
  }
  window.localStorage.setItem(DEVICE_STORAGE_KEY, deviceId);
  setDeviceCookie(deviceId);
};

const readStoredToken = () => {
  if (typeof window === "undefined") {
    return null;
  }
  return window.localStorage.getItem(AUTH_TOKEN_KEY);
};

const clearStoredAuth = () => {
  if (typeof window === "undefined") {
    return;
  }
  window.localStorage.removeItem(AUTH_TOKEN_KEY);
  window.localStorage.removeItem(AUTH_USER_KEY);
};

const ensureSessionId = () => {
  if (typeof window === "undefined") {
    return "server-session";
  }
  const current = window.localStorage.getItem(SESSION_STORAGE_KEY);
  if (current) {
    return current;
  }
  const created = typeof crypto !== "undefined" && crypto.randomUUID ? crypto.randomUUID() : `${Date.now()}-${Math.random().toString(16).slice(2)}`;
  window.localStorage.setItem(SESSION_STORAGE_KEY, created);
  return created;
};

const generateRequestId = () => {
  return typeof crypto !== "undefined" && crypto.randomUUID ? crypto.randomUUID() : `${Date.now()}-${Math.random().toString(16).slice(2)}`;
};

const ensureDeviceId = () => {
  if (typeof window === "undefined") {
    return "server-device-id";
  }
  const current = String(window.localStorage.getItem(DEVICE_STORAGE_KEY) || "").trim();
  if (current.length >= 24) {
    setDeviceCookie(current);
    return current;
  }
  const randomPart = typeof crypto !== "undefined" && crypto.randomUUID
    ? crypto.randomUUID().replace(/-/g, "")
    : `${Date.now()}${Math.random().toString(16).slice(2)}`;
  const deviceId = `dev${randomPart}`.slice(0, 64);
  persistDeviceId(deviceId);
  return deviceId;
};

const syncDeviceIdFromToken = (token) => {
  if (typeof window === "undefined") {
    return;
  }
  const payload = decodeJwtPayload(token);
  const tokenDeviceId = String(payload?.device_id || "").trim();
  if (tokenDeviceId.length < 24) {
    return;
  }
  const current = String(window.localStorage.getItem(DEVICE_STORAGE_KEY) || "").trim();
  if (current !== tokenDeviceId) {
    persistDeviceId(tokenDeviceId);
  } else {
    setDeviceCookie(tokenDeviceId);
  }
};

export const getSessionDeviceId = () => ensureDeviceId();
export const getSessionId = () => ensureSessionId();
export const buildSessionHeaders = () => ({
  "Content-Type": "application/json",
  "X-Session-ID": ensureSessionId(),
  "X-Session-Device": ensureDeviceId(),
  "X-Request-ID": generateRequestId(),
});

const AUTH_EXPIRED_EVENT_COOLDOWN_MS = 4000;
let lastAuthExpiredEventAt = 0;

const dispatchAuthExpiredOnce = () => {
  if (typeof window === "undefined") {
    return;
  }
  const now = Date.now();
  if (now - lastAuthExpiredEventAt < AUTH_EXPIRED_EVENT_COOLDOWN_MS) {
    return;
  }
  lastAuthExpiredEventAt = now;
  window.dispatchEvent(new Event("platform-auth-expired"));
};

export const classifyApiError = (error) => {
  const status = Number(error?.response?.status || 0);
  const code = String(error?.response?.data?.code || "").toUpperCase();
  const reasonDetail = String(error?.response?.data?.detail || "").toLowerCase();
  const transportCode = String(error?.code || "").toUpperCase();
  const message = String(error?.message || "").toLowerCase();

  if (status === 401 || code.includes("AUTH") || reasonDetail.includes("auth") || reasonDetail.includes("token")) {
    return "auth_error";
  }

  if (
    status >= 500 ||
    [502, 503, 504].includes(status) ||
    code === "DB_POOL_TIMEOUT" ||
    code === "SERVICE_UNAVAILABLE" ||
    transportCode === "ERR_NETWORK" ||
    transportCode === "ECONNABORTED" ||
    transportCode === "ERR_BAD_RESPONSE" ||
    message.includes("timeout") ||
    message.includes("network") ||
    message.includes("pool")
  ) {
    return "infra_error";
  }

  return "trade_blocker";
};

apiClient.interceptors.request.use((config) => {
  const nextConfig = config;
  nextConfig.headers = nextConfig.headers || {};
  nextConfig.__authTokenSnapshot = readStoredToken();
  if (isAuthPath(nextConfig.url)) {
    nextConfig.timeout = 30000;
  }

  if (!nextConfig.headers.Authorization) {
    const token = readStoredToken();
    if (token) {
      nextConfig.headers.Authorization = `Bearer ${token}`;
      syncDeviceIdFromToken(token);
    }
  } else {
    const bearer = String(nextConfig.headers.Authorization || "");
    const token = bearer.startsWith("Bearer ") ? bearer.slice(7).trim() : "";
    if (token) {
      syncDeviceIdFromToken(token);
    }
  }

  nextConfig.headers["X-Session-ID"] = ensureSessionId();
  nextConfig.headers["X-Session-Device"] = ensureDeviceId();
  nextConfig.headers["X-Request-ID"] = generateRequestId();
  return nextConfig;
});

const wait = (ms) => new Promise((resolve) => setTimeout(resolve, ms));

const shouldRetryRequest = (error) => {
  const config = error?.config || {};
  const method = String(config.method || "get").toLowerCase();
  const url = String(config.url || "");
  const retryableMethods = new Set(["get", "head", "options"]);
  const retryableStatus = new Set([502, 503, 504]);
  const retryableCodes = new Set(["ECONNABORTED", "ERR_NETWORK", "ERR_BAD_RESPONSE"]);
  const retryBudget = isAuthPath(url) ? 2 : 1;

  if ((config.__retryCount || 0) >= retryBudget) {
    return false;
  }

  if (String(error?.code || "").toUpperCase() === "ERR_CANCELED") {
    return false;
  }

  const retryableAuthPath = url.includes("/auth/login") || url.includes("/auth/me");
  if (!retryableMethods.has(method) && !retryableAuthPath) {
    return false;
  }

  if (retryableStatus.has(Number(error?.response?.status))) {
    return true;
  }

  if (retryableCodes.has(String(error?.code || "").toUpperCase())) {
    return true;
  }

  const message = String(error?.message || "").toLowerCase();
  return message.includes("timeout") || message.includes("network error");
};

apiClient.interceptors.response.use(
  (response) => response,
  async (error) => {
    const config = error?.config || {};

    if (shouldRetryRequest(error)) {
      config.__retryCount = (config.__retryCount || 0) + 1;
      await wait(350);
      return apiClient.request(config);
    }

    const status = Number(error?.response?.status || 0);
    const url = String(config.url || "");
    const latestStoredToken = readStoredToken();
    const authSnapshot = String(config.__authTokenSnapshot || "");
    const isLoginLike =
      url.includes("/auth/login") ||
      url.includes("/auth/me") ||
      url.includes("/auth/mfa/challenge/verify") ||
      url.includes("/auth/mfa/verify") ||
      url.includes("/mfa/verify") ||
      url.includes("/auth/step-up");
    const detail401 = String(error?.response?.data?.detail || "").toLowerCase();

    if (
      status === 401 &&
      !isLoginLike &&
      detail401.includes("session_device_mismatch") &&
      !config.__sessionRebindRetried
    ) {
      config.__sessionRebindRetried = true;
      const latestToken = readStoredToken();
      if (latestToken) {
        config.headers = config.headers || {};
        config.headers.Authorization = `Bearer ${latestToken}`;
        config.headers["X-Session-ID"] = ensureSessionId();
        config.headers["X-Session-Device"] = ensureDeviceId();
        config.headers["X-Request-ID"] = generateRequestId();
        await wait(240);
        return apiClient.request(config);
      }
    }

    const shouldForceLogout =
      detail401.includes("token_expired") ||
      detail401.includes("session_revoked") ||
      detail401.includes("token_revoked") ||
      detail401.includes("invalid_token") ||
      detail401.includes("not_authenticated");

    if (status === 401 && !isLoginLike && shouldForceLogout && (!latestStoredToken || latestStoredToken === authSnapshot)) {
      clearStoredAuth();
      setAuthToken(null);
      dispatchAuthExpiredOnce();
    }

    if (status === 403) {
      const detailRaw = error?.response?.data?.detail;
      const detail = typeof detailRaw === "string" ? detailRaw.toLowerCase() : String(detailRaw?.reason_code || "").toLowerCase();
      if (detail.includes("step_up_required") && typeof window !== "undefined") {
        window.dispatchEvent(new Event("platform-step-up-required"));
      }
    }

    error.apiErrorClass = classifyApiError(error);
    error.apiErrorCode = String(error?.response?.data?.code || "").toUpperCase();

    return Promise.reject(error);
  },
);

export const setAuthToken = (token) => {
  if (token) {
    apiClient.defaults.headers.common.Authorization = `Bearer ${token}`;
  } else {
    delete apiClient.defaults.headers.common.Authorization;
  }
};
