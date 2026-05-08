import { useEffect, useState } from "react";
import { Link, Navigate } from "react-router-dom";
import { Lock, Mail, User } from "lucide-react";
import { useAuth } from "@/context/AuthContext";
import { HmiTag } from "@/components/IndustrialPanel";

export function RegisterPage() {
  const { isAuthenticated, register, setScope } = useAuth();
  useEffect(() => {
    setScope("operator");
  }, [setScope]);

  const [name, setName] = useState("");
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [error, setError] = useState("");
  const [loading, setLoading] = useState(false);

  if (isAuthenticated) {
    return <Navigate to="/" replace />;
  }

  async function handleSubmit(e: React.FormEvent) {
    e.preventDefault();
    setError("");
    if (!email.trim() || password.length < 8) {
      setError("E-mail requis et mot de passe d’au moins 8 caractères.");
      return;
    }
    setLoading(true);
    try {
      await register(email.trim(), password, name.trim() || undefined, "operator");
    } catch {
      setError("Inscription impossible. Réessayez.");
    } finally {
      setLoading(false);
    }
  }

  return (
    <div className="relative flex min-h-screen flex-col items-center justify-center overflow-hidden hmi-app-bg px-4 py-12">
      <div className="pointer-events-none absolute inset-x-0 top-0 h-32 bg-gradient-to-b from-alert-orange/12 to-transparent" aria-hidden />

      <div className="relative w-full max-w-md">
        <div className="mb-6 flex justify-center gap-2">
          <HmiTag tone="orange">Nouvel opérateur</HmiTag>
          <HmiTag tone="muted">Registre local</HmiTag>
        </div>

        <div className="relative overflow-hidden rounded-sm border border-navy-700/90 bg-gradient-to-b from-navy-900/95 to-navy-950 shadow-[0_0_50px_-14px_rgba(234,88,12,0.35)]">
          <span className="pointer-events-none absolute left-0 top-0 z-10 h-5 w-5 border-l-2 border-t-2 border-alert-orange/80" aria-hidden />
          <span className="pointer-events-none absolute right-0 top-0 z-10 h-5 w-5 border-r-2 border-t-2 border-alert-orange/40" aria-hidden />
          <span className="pointer-events-none absolute bottom-0 left-0 z-10 h-5 w-5 border-b-2 border-l-2 border-steel-700" aria-hidden />
          <span className="pointer-events-none absolute bottom-0 right-0 z-10 h-5 w-5 border-b-2 border-r-2 border-steel-700" aria-hidden />

          <div className="border-b border-navy-800 bg-navy-950/60 px-6 pb-5 pt-6 text-center">
            <div className="mx-auto mb-4 inline-flex max-w-full justify-center rounded-sm border border-alert-orange/35 bg-[#4a5238]/30 px-4 py-2.5 shadow-[0_0_22px_-8px_rgba(234,88,12,0.35)]">
              <img
                src="/image.png"
                alt="Sotipapier"
                className="h-11 w-auto max-w-full object-contain"
                width={280}
                height={44}
                decoding="async"
              />
            </div>
            <p className="font-mono text-[10px] uppercase tracking-[0.28em] text-alert-orange/90">Enregistrement</p>
            <h1 className="mt-1 text-xl font-semibold tracking-tight text-steel-100">Créer un accès</h1>
            <p className="mt-1 text-sm text-steel-600">Profil opérateur (création en base)</p>
          </div>

          <form onSubmit={handleSubmit} className="space-y-4 px-6 py-6">
            {error ? (
              <p className="rounded-sm border border-alert-red/45 bg-alert-red/10 px-3 py-2 font-mono text-xs text-alert-red">
                {error}
              </p>
            ) : null}
            <div>
              <label className="mb-1.5 block font-mono text-[10px] uppercase tracking-wider text-steel-600">
                Nom affiché
              </label>
              <div className="relative">
                <User className="absolute left-3 top-1/2 h-4 w-4 -translate-y-1/2 text-steel-600" />
                <input
                  type="text"
                  value={name}
                  onChange={(e) => setName(e.target.value)}
                  className="hmi-input w-full pl-10"
                  placeholder="J. Dupont"
                />
              </div>
            </div>
            <div>
              <label className="mb-1.5 block font-mono text-[10px] uppercase tracking-wider text-steel-600">
                E-mail
              </label>
              <div className="relative">
                <Mail className="absolute left-3 top-1/2 h-4 w-4 -translate-y-1/2 text-steel-600" />
                <input
                  type="email"
                  autoComplete="email"
                  value={email}
                  onChange={(e) => setEmail(e.target.value)}
                  className="hmi-input w-full pl-10"
                  placeholder="operateur@sotipapier.fr"
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
                  autoComplete="new-password"
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
              className="w-full rounded-sm bg-gradient-to-r from-alert-orange to-amber-600 py-3 text-sm font-semibold text-white shadow-[0_0_28px_-8px_rgba(234,88,12,0.65)] transition hover:brightness-110 disabled:opacity-50"
            >
              {loading ? "Création…" : "Enregistrer le profil"}
            </button>
          </form>

          <div className="border-t border-navy-800 px-6 py-4 text-center">
            <p className="text-xs text-steel-600">
              Déjà inscrit ?{" "}
              <Link to="/login" className="font-medium text-plant-glow hover:underline">
                Se connecter
              </Link>
            </p>
          </div>
        </div>
      </div>
    </div>
  );
}
