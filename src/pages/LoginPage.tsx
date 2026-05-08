import { useEffect, useRef, useState } from "react";
import { Link, Navigate, useLocation } from "react-router-dom";
import { Lock, Mail } from "lucide-react";
import { useAuth } from "@/context/AuthContext";
import { type AuthScope } from "@/context/authSession";
import { HmiTag } from "@/components/IndustrialPanel";

export function LoginPage({ scope = "operator" }: { scope?: AuthScope }) {
  const { isAuthenticated, isAdmin, login, loginWithGoogle, setScope } = useAuth();
  const location = useLocation();
  const from =
    (location.state as { from?: { pathname: string } })?.from?.pathname ||
    (scope === "admin" ? "/admin/erp" : "/");
  const googleBtnRef = useRef<HTMLDivElement | null>(null);

  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [error, setError] = useState("");
  const [loading, setLoading] = useState(false);
  const [googleLoading, setGoogleLoading] = useState(false);

  useEffect(() => {
    setScope(scope);
  }, [scope, setScope]);

  useEffect(() => {
    const clientId = import.meta.env.VITE_GOOGLE_CLIENT_ID?.trim();
    if (!clientId || !googleBtnRef.current) return;

    const loadScript = async () => {
      if (!document.querySelector('script[src="https://accounts.google.com/gsi/client"]')) {
        await new Promise<void>((resolve, reject) => {
          const script = document.createElement("script");
          script.src = "https://accounts.google.com/gsi/client";
          script.async = true;
          script.defer = true;
          script.onload = () => resolve();
          script.onerror = () => reject(new Error("Impossible de charger Google Identity Services."));
          document.head.appendChild(script);
        });
      }

      const g = window.google;
      if (!g?.accounts?.id || !googleBtnRef.current) return;

      g.accounts.id.initialize({
        client_id: clientId,
        callback: async (resp: { credential?: string }) => {
          if (!resp?.credential) {
            setError("Token Google invalide.");
            return;
          }
          setGoogleLoading(true);
          setError("");
          try {
            await loginWithGoogle(resp.credential, scope);
          } catch {
            setError(
              scope === "admin"
                ? "Accès refusé: compte admin requis."
                : "Connexion Google impossible. Vérifiez la configuration OAuth."
            );
          } finally {
            setGoogleLoading(false);
          }
        },
      });

      googleBtnRef.current.innerHTML = "";
      g.accounts.id.renderButton(googleBtnRef.current, {
        type: "standard",
        shape: "rectangular",
        theme: "outline",
        text: "signin_with",
        size: "large",
        locale: "fr",
        width: 320,
      });
    };

    void loadScript().catch(() => {
      setError("Chargement Google Sign-In impossible.");
    });
  }, [loginWithGoogle, scope]);

  if (isAuthenticated && (scope !== "admin" || isAdmin)) {
    return <Navigate to={from} replace />;
  }

  async function handleSubmit(e: React.FormEvent) {
    e.preventDefault();
    setError("");
    if (!email.trim()) {
      setError("Indiquez un e-mail.");
      return;
    }
    setLoading(true);
    try {
      await login(email.trim(), password, scope);
    } catch {
      setError(scope === "admin" ? "Accès refusé: compte admin requis." : "Connexion impossible. Réessayez.");
    } finally {
      setLoading(false);
    }
  }

  return (
    <div className="relative flex min-h-screen flex-col items-center justify-center overflow-hidden hmi-app-bg px-4 py-12">
      <div className="pointer-events-none absolute inset-x-0 top-0 h-32 bg-gradient-to-b from-plant-accent/10 to-transparent" aria-hidden />

      <div className="relative w-full max-w-md">
        <div className="mb-6 flex justify-center gap-2">
          <HmiTag tone={scope === "admin" ? "orange" : "cyan"}>
            {scope === "admin" ? "Poste admin" : "Poste opérateur"}
          </HmiTag>
          <HmiTag tone="muted">Session locale</HmiTag>
        </div>

        <div className="relative overflow-hidden rounded-sm border border-navy-700/90 bg-gradient-to-b from-navy-900/95 to-navy-950 shadow-[0_0_60px_-12px_rgba(34,211,238,0.35)]">
          <span className="pointer-events-none absolute left-0 top-0 z-10 h-5 w-5 border-l-2 border-t-2 border-plant-accent" aria-hidden />
          <span className="pointer-events-none absolute right-0 top-0 z-10 h-5 w-5 border-r-2 border-t-2 border-plant-accent/50" aria-hidden />
          <span className="pointer-events-none absolute bottom-0 left-0 z-10 h-5 w-5 border-b-2 border-l-2 border-steel-700" aria-hidden />
          <span className="pointer-events-none absolute bottom-0 right-0 z-10 h-5 w-5 border-b-2 border-r-2 border-steel-700" aria-hidden />

          <div className="border-b border-navy-800 bg-navy-950/60 px-6 pb-5 pt-6 text-center">
            <div className="mx-auto mb-4 inline-flex max-w-full justify-center rounded-sm border border-plant-accent/30 bg-[#4a5238]/30 px-4 py-2.5 shadow-[0_0_24px_-8px_rgba(34,211,238,0.35)]">
              <img
                src="/image.png"
                alt="Sotipapier"
                className="h-11 w-auto max-w-full object-contain"
                width={280}
                height={44}
                decoding="async"
              />
            </div>
            <h1 className="text-xl font-semibold tracking-tight text-steel-100">
              {scope === "admin" ? "Connexion admin" : "Connexion opérateur"}
            </h1>
            <p className="mt-1 text-sm text-steel-600">Centre de contrôle — accès sécurisé</p>
          </div>

          <form onSubmit={handleSubmit} className="space-y-4 px-6 py-6">
            {error ? (
              <p className="rounded-sm border border-alert-red/45 bg-alert-red/10 px-3 py-2 font-mono text-xs text-alert-red">
                {error}
              </p>
            ) : null}
            <div>
              <label className="mb-1.5 block font-mono text-[10px] uppercase tracking-wider text-steel-600">
                Identifiant (e-mail)
              </label>
              <div className="relative">
                <Mail className="absolute left-3 top-1/2 h-4 w-4 -translate-y-1/2 text-steel-600" />
                <input
                  type="email"
                  autoComplete="username"
                  value={email}
                  onChange={(e) => setEmail(e.target.value)}
                  className="hmi-input w-full pl-10"
                  placeholder={scope === "admin" ? "admin@sotipapier.fr" : "operateur@sotipapier.fr"}
                />
              </div>
            </div>
            <div>
              <label className="mb-1.5 block font-mono text-[10px] uppercase tracking-wider text-steel-600">
                Mot de passe
              </label>
              <div className="relative">
                <Lock className="absolute left-3 top-1/2 h-4 w-4 -translate-y-1/2 text-steel-600" />
                <input
                  type="password"
                  autoComplete="current-password"
                  value={password}
                  onChange={(e) => setPassword(e.target.value)}
                  className="hmi-input w-full pl-10"
                  placeholder="••••••••"
                />
              </div>
            </div>
            <button
              type="submit"
              disabled={loading}
              className="w-full rounded-sm bg-gradient-to-r from-plant-accent to-cyan-600 py-3 text-sm font-semibold text-navy-950 shadow-[0_0_24px_-8px_rgba(34,211,238,0.7)] transition hover:brightness-110 disabled:opacity-50"
            >
              {loading ? "Connexion…" : "Valider l’accès"}
            </button>

            <div className="flex items-center gap-2 pt-1">
              <div className="h-px flex-1 bg-navy-800" />
              <span className="font-mono text-[10px] uppercase tracking-wider text-steel-700">ou</span>
              <div className="h-px flex-1 bg-navy-800" />
            </div>

            <div className="flex flex-col items-center gap-2">
              <div ref={googleBtnRef} />
              {googleLoading ? (
                <p className="font-mono text-[10px] text-steel-600">Connexion Google en cours…</p>
              ) : null}
              {!import.meta.env.VITE_GOOGLE_CLIENT_ID ? (
                <p className="text-[10px] text-steel-700">
                  Google Sign-In non configuré (VITE_GOOGLE_CLIENT_ID manquant).
                </p>
              ) : null}
            </div>
          </form>

          <div className="border-t border-navy-800 bg-navy-950/40 px-6 py-4 text-center">
            <p className="text-xs text-steel-600">
              {scope === "admin" ? "Espace opérateur ? " : "Pas encore de compte ? "}
              <Link to="/register" className="font-medium text-plant-glow hover:underline">
                {scope === "admin" ? "Créer/ouvrir un accès opérateur" : "Créer un accès"}
              </Link>
            </p>
            <p className="mt-2 text-xs text-steel-600">
              {scope === "admin" ? "Tu es opérateur ? " : "Tu es admin ? "}
              <Link to={scope === "admin" ? "/login" : "/login/admin"} className="font-medium text-plant-glow hover:underline">
                {scope === "admin" ? "Connexion opérateur" : "Connexion admin"}
              </Link>
            </p>
            {scope === "admin" ? (
              <p className="mt-2 text-xs text-steel-600">
                <Link to="/register/admin" className="font-medium text-plant-glow hover:underline">
                  Créer le premier admin (une seule fois)
                </Link>
                {" · "}
                <Link to="/admin/forgot-password" className="font-medium text-plant-glow hover:underline">
                  Mot de passe oublié
                </Link>
              </p>
            ) : null}
            <p className="mt-3 font-mono text-[10px] leading-relaxed text-steel-700">
              Authentification sécurisée via API backend.
            </p>
          </div>
        </div>
      </div>
    </div>
  );
}
