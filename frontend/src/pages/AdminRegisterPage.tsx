import { useEffect, useState } from "react";
import { Link, Navigate } from "react-router-dom";
import { KeyRound, Lock, Mail, User } from "lucide-react";
import { useAuth } from "@/context/AuthContext";
import { getAdminRegistrationStatusAuth, registerAdminAuth } from "@/api/auth";
import { HmiTag } from "@/components/IndustrialPanel";

export function AdminRegisterPage() {
  const { isAuthenticated, isAdmin, setScope, login } = useAuth();
  const [name, setName] = useState("");
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [bootstrapKey, setBootstrapKey] = useState("");
  const [adminExists, setAdminExists] = useState<boolean | null>(null);
  const [error, setError] = useState("");
  const [loading, setLoading] = useState(false);

  useEffect(() => {
    setScope("admin");
    void getAdminRegistrationStatusAuth()
      .then((d) => setAdminExists(Boolean(d.admin_exists)))
      .catch(() => setAdminExists(true));
  }, [setScope]);

  if (isAuthenticated && isAdmin) return <Navigate to="/admin/erp" replace />;
  if (adminExists) return <Navigate to="/login/admin" replace />;

  async function handleSubmit(e: React.FormEvent) {
    e.preventDefault();
    setError("");
    if (!email.trim() || password.length < 8) {
      setError("E-mail requis et mot de passe d’au moins 8 caractères.");
      return;
    }
    setLoading(true);
    try {
      await registerAdminAuth({
        email: email.trim(),
        password,
        name: name.trim() || undefined,
        bootstrap_key: bootstrapKey.trim(),
      });
      await login(email.trim(), password, "admin");
    } catch (err: any) {
      const detail = err?.response?.data?.detail;
      setError(typeof detail === "string" ? detail : "Inscription admin impossible.");
    } finally {
      setLoading(false);
    }
  }

  return (
    <div className="relative flex min-h-screen flex-col items-center justify-center overflow-hidden hmi-app-bg px-4 py-12">
      <div className="relative w-full max-w-md">
        <div className="mb-6 flex justify-center gap-2">
          <HmiTag tone="orange">Initialisation admin</HmiTag>
          <HmiTag tone="muted">Autorisé une seule fois</HmiTag>
        </div>
        <div className="rounded-sm border border-navy-700/90 bg-navy-950/90">
          <div className="border-b border-navy-800 px-6 py-5 text-center">
            <h1 className="text-xl font-semibold text-steel-100">Créer le premier admin</h1>
          </div>
          <form onSubmit={handleSubmit} className="space-y-4 px-6 py-6">
            {error ? <p className="rounded-sm border border-alert-red/45 bg-alert-red/10 px-3 py-2 text-xs text-alert-red">{error}</p> : null}
            <div className="relative">
              <User className="absolute left-3 top-1/2 h-4 w-4 -translate-y-1/2 text-steel-600" />
              <input value={name} onChange={(e) => setName(e.target.value)} className="hmi-input w-full pl-10" placeholder="Nom admin" />
            </div>
            <div className="relative">
              <Mail className="absolute left-3 top-1/2 h-4 w-4 -translate-y-1/2 text-steel-600" />
              <input type="email" value={email} onChange={(e) => setEmail(e.target.value)} className="hmi-input w-full pl-10" placeholder="admin@sotipapier.fr" />
            </div>
            <div className="relative">
              <Lock className="absolute left-3 top-1/2 h-4 w-4 -translate-y-1/2 text-steel-600" />
              <input type="password" value={password} onChange={(e) => setPassword(e.target.value)} className="hmi-input w-full pl-10" placeholder="Mot de passe" />
            </div>
            <div className="relative">
              <KeyRound className="absolute left-3 top-1/2 h-4 w-4 -translate-y-1/2 text-steel-600" />
              <input value={bootstrapKey} onChange={(e) => setBootstrapKey(e.target.value)} className="hmi-input w-full pl-10" placeholder="Bootstrap key admin" />
            </div>
            <button type="submit" disabled={loading} className="w-full rounded-sm bg-gradient-to-r from-alert-orange to-amber-600 py-3 text-sm font-semibold text-white disabled:opacity-50">
              {loading ? "Création…" : "Créer admin"}
            </button>
          </form>
          <div className="border-t border-navy-800 px-6 py-4 text-center">
            <Link to="/login/admin" className="text-xs text-plant-glow hover:underline">Retour connexion admin</Link>
          </div>
        </div>
      </div>
    </div>
  );
}

