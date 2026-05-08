import axios from "axios";

/**
 * Backend industrial Harness (FastAPI) — chemins racine (/invoke, /resume, …).
 * Ex. prod : `http://13.39.163.86:8030` (sans slash final).
 */
export function resolveHarnessBaseURL(): string | null {
  const raw = import.meta.env.VITE_HARNESS_URL?.trim();
  if (!raw) return null;
  return raw.replace(/\/$/, "");
}

export const harnessModeEnabled = (): boolean => Boolean(resolveHarnessBaseURL());

export function createHarnessAxios() {
  const base = resolveHarnessBaseURL();
  if (!base) {
    throw new Error("harness_client_disabled");
  }
  return axios.create({
    baseURL: base,
    headers: { "Content-Type": "application/json" },
    timeout: 600_000,
  });
}
