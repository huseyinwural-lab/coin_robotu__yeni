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

export const setAuthToken = (token) => {
  if (token) {
    apiClient.defaults.headers.common.Authorization = `Bearer ${token}`;
  } else {
    delete apiClient.defaults.headers.common.Authorization;
  }
};
