export type AuthScope = "operator" | "admin";

const ACTIVE_SCOPE_KEY = "sotipapier_auth_scope";

function tokenKey(scope: AuthScope): string {
  return scope === "admin" ? "sotipapier_token_admin" : "sotipapier_token_operator";
}

function userKey(scope: AuthScope): string {
  return scope === "admin" ? "sotipapier_user_admin" : "sotipapier_user_operator";
}

export function getActiveScope(): AuthScope {
  const raw = localStorage.getItem(ACTIVE_SCOPE_KEY);
  return raw === "admin" ? "admin" : "operator";
}

export function setActiveScope(scope: AuthScope): void {
  localStorage.setItem(ACTIVE_SCOPE_KEY, scope);
}

export function getToken(scope: AuthScope): string | null {
  return localStorage.getItem(tokenKey(scope));
}

export function getUser(scope: AuthScope): string | null {
  return localStorage.getItem(userKey(scope));
}

export function setSession(scope: AuthScope, token: string, user: string): void {
  localStorage.setItem(tokenKey(scope), token);
  localStorage.setItem(userKey(scope), user);
}

export function clearSession(scope: AuthScope): void {
  localStorage.removeItem(tokenKey(scope));
  localStorage.removeItem(userKey(scope));
}

export function getActiveToken(): string | null {
  return getToken(getActiveScope());
}

