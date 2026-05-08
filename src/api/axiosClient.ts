import axios from "axios";
import { clearSession, getActiveScope, getActiveToken } from "@/context/authSession";

/**
 * Définir `VITE_API_URL` dans `.env` (ex. backend AWS EC2).
 * Exemple : `http://13.xx.xx.xx:8010/api/v1` — sans slash final.
 */
function resolveBaseURL(): string {
  const fromEnv = import.meta.env.VITE_API_URL?.replace(/\/$/, "").trim();
  if (fromEnv) return fromEnv;
  if (import.meta.env.DEV) {
    console.warn(
      "[Sotipapier] VITE_API_URL manquant — fallback localhost. " +
        "Pour AWS, copiez `.env.example` vers `.env` et renseignez l’URL du cerveau."
    );
  }
  return "http://localhost:8010/api/v1";
}

export const axiosClient = axios.create({
  baseURL: resolveBaseURL(),
  headers: {
    "Content-Type": "application/json",
  },
  timeout: 600_000,
});

axiosClient.interceptors.request.use((config) => {
  const token = getActiveToken();
  if (token) {
    config.headers.Authorization = `Bearer ${token}`;
  }
  return config;
});

axiosClient.interceptors.response.use(
  (res) => res,
  (err) => {
    if (err.response?.status === 401) {
      clearSession(getActiveScope());
      window.dispatchEvent(new Event("sotipapier:auth-expired"));
    }
    return Promise.reject(err);
  }
);
