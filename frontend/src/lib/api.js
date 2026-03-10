import axios from "axios";

const BACKEND_URL = process.env.REACT_APP_BACKEND_URL;

export const apiClient = axios.create({
  baseURL: `${BACKEND_URL}/api`,
  timeout: 15000,
});

export const setAuthToken = (token) => {
  if (token) {
    apiClient.defaults.headers.common.Authorization = `Bearer ${token}`;
  } else {
    delete apiClient.defaults.headers.common.Authorization;
  }
};
