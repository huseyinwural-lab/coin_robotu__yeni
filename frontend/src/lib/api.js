import axios from "axios";

const BACKEND_URL = String(process.env.REACT_APP_BACKEND_URL || "").trim();

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

export const apiClient = axios.create({
  baseURL: `${BACKEND_URL.replace(/\/$/, "")}/api`,
  timeout: 15000,
});

const SESSION_STORAGE_KEY = "platform-session-id";

const ensureSessionId = () => {
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

apiClient.interceptors.request.use((config) => {
  const nextConfig = config;
  nextConfig.headers = nextConfig.headers || {};
  nextConfig.headers["X-Session-ID"] = ensureSessionId();
  nextConfig.headers["X-Request-ID"] = generateRequestId();
  return nextConfig;
});

export const setAuthToken = (token) => {
  if (token) {
    apiClient.defaults.headers.common.Authorization = `Bearer ${token}`;
  } else {
    delete apiClient.defaults.headers.common.Authorization;
  }
};
