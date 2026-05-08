import {
  createContext,
  useCallback,
  useContext,
  useEffect,
  useMemo,
  useState,
  type ReactNode,
} from "react";
import { loginAuth, loginGoogleAuth, logoutAuth, meAuth, registerAuth } from "@/api/auth";
import {
  clearSession,
  getActiveScope,
  getToken,
  getUser,
  setActiveScope,
  setSession,
  type AuthScope,
} from "@/context/authSession";

export interface AuthUser {
  id?: string;
  email: string;
  name?: string;
  role?: string;
}

interface AuthContextValue {
  scope: AuthScope;
  user: AuthUser | null;
  token: string | null;
  isAuthenticated: boolean;
  isAdmin: boolean;
  setScope: (scope: AuthScope) => void;
  login: (email: string, password: string, scope?: AuthScope) => Promise<void>;
  loginWithGoogle: (idToken: string, scope?: AuthScope) => Promise<void>;
  register: (email: string, password: string, name?: string, scope?: AuthScope) => Promise<void>;
  logout: (scope?: AuthScope) => void;
}

const AuthContext = createContext<AuthContextValue | null>(null);

export function AuthProvider({ children }: { children: ReactNode }) {
  const [scope, setScopeState] = useState<AuthScope>(() => getActiveScope());
  const [user, setUser] = useState<AuthUser | null>(() => {
    const raw = getUser(getActiveScope());
    if (!raw) return null;
    try {
      return JSON.parse(raw) as AuthUser;
    } catch {
      return null;
    }
  });
  const [token, setToken] = useState<string | null>(() => getToken(getActiveScope()));

  const hydrateFromScope = useCallback((targetScope: AuthScope) => {
    setActiveScope(targetScope);
    setScopeState(targetScope);
    const t = getToken(targetScope);
    const rawUser = getUser(targetScope);
    setToken(t);
    if (!rawUser) {
      setUser(null);
      return;
    }
    try {
      setUser(JSON.parse(rawUser) as AuthUser);
    } catch {
      setUser(null);
    }
  }, []);

  useEffect(() => {
    const onExpired = () => {
      clearSession(getActiveScope());
      setUser(null);
      setToken(null);
    };
    window.addEventListener("sotipapier:auth-expired", onExpired);
    return () => window.removeEventListener("sotipapier:auth-expired", onExpired);
  }, []);

  const setScope = useCallback(
    (targetScope: AuthScope) => {
      hydrateFromScope(targetScope);
    },
    [hydrateFromScope]
  );

  const login = useCallback(async (email: string, password: string, targetScope?: AuthScope) => {
    const nextScope = targetScope || scope;
    setActiveScope(nextScope);
    const data = await loginAuth({ email, password });
    const role = (data.user.role || "operator").toLowerCase();
    if (nextScope === "admin" && role !== "admin") {
      throw new Error("Compte non admin");
    }
    const t = data.access_token;
    const u: AuthUser = {
      id: data.user.id,
      email: data.user.email,
      name: data.user.name,
      role,
    };
    setSession(nextScope, t, JSON.stringify(u));
    setScopeState(nextScope);
    setToken(t);
    setUser(u);
  }, [scope]);

  const loginWithGoogle = useCallback(async (idToken: string, targetScope?: AuthScope) => {
    const nextScope = targetScope || scope;
    setActiveScope(nextScope);
    const data = await loginGoogleAuth({ id_token: idToken });
    const role = (data.user.role || "operator").toLowerCase();
    if (nextScope === "admin" && role !== "admin") {
      throw new Error("Compte non admin");
    }
    const t = data.access_token;
    const u: AuthUser = {
      id: data.user.id,
      email: data.user.email,
      name: data.user.name,
      role,
    };
    setSession(nextScope, t, JSON.stringify(u));
    setScopeState(nextScope);
    setToken(t);
    setUser(u);
  }, [scope]);

  const register = useCallback(async (email: string, password: string, name?: string, targetScope?: AuthScope) => {
    const nextScope = targetScope || scope;
    setActiveScope(nextScope);
    const data = await registerAuth({ email, password, name });
    const role = (data.user.role || "operator").toLowerCase();
    if (nextScope === "admin" && role !== "admin") {
      throw new Error("Compte non admin");
    }
    const t = data.access_token;
    const u: AuthUser = {
      id: data.user.id,
      email: data.user.email,
      name: data.user.name,
      role,
    };
    setSession(nextScope, t, JSON.stringify(u));
    setScopeState(nextScope);
    setToken(t);
    setUser(u);
  }, [scope]);

  const logout = useCallback((targetScope?: AuthScope) => {
    const nextScope = targetScope || scope;
    setActiveScope(nextScope);
    void logoutAuth().catch(() => undefined);
    clearSession(nextScope);
    setToken(null);
    setUser(null);
  }, [scope]);

  useEffect(() => {
    if (!token) return;
    let active = true;
    void meAuth()
      .then((me) => {
        if (!active) return;
        const nextUser: AuthUser = {
          id: me.id,
          email: me.email,
          name: me.name,
          role: me.role || "operator",
        };
        setUser(nextUser);
        setSession(scope, token, JSON.stringify(nextUser));
      })
      .catch(() => {
        if (!active) return;
        clearSession(scope);
        setToken(null);
        setUser(null);
      });
    return () => {
      active = false;
    };
  }, [scope, token]);

  const value = useMemo<AuthContextValue>(
    () => ({
      user,
      token,
      scope,
      isAuthenticated: Boolean(token && user),
      isAdmin: String(user?.role || "").toLowerCase() === "admin",
      setScope,
      login,
      loginWithGoogle,
      register,
      logout,
    }),
    [user, token, scope, setScope, login, loginWithGoogle, register, logout]
  );

  return <AuthContext.Provider value={value}>{children}</AuthContext.Provider>;
}

export function useAuth(): AuthContextValue {
  const ctx = useContext(AuthContext);
  if (!ctx) throw new Error("useAuth must be used within AuthProvider");
  return ctx;
}
