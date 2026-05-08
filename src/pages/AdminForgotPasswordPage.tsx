import { useEffect, useState } from "react";
import { Link, useNavigate } from "react-router-dom";
import { KeyRound, Lock, Mail } from "lucide-react";
import { forgotAdminPasswordAuth } from "@/api/auth";
import { useAuth } from "@/context/AuthContext";
import { HmiTag } from "@/components/IndustrialPanel";

export function AdminForgotPasswordPage() {
  const { setScope } = useAuth();
  const navigate = useNavigate();
  const [email, setEmail] = useState("");
  const [newPassword, setNewPassword] = useState("");
  const [bootstrapKey, setBootstrapKey] = useState("");
  const [error, setError] = useState("");
  const [ok, setOk] = useState("");
  const [loading, setLoading] = useState(false);

  useEffect(() => {
    setScope("admin");
  }, [setScope]);

  async function handleSubmit(e: React.FormEvent) {
    e.preventDefault();
    setError("");
    setOk("");
    if (!email.trim() || newPassword.length < 8 || !bootstrapKey.trim()) {
      setError("Email, nouveau mot de passe (8+) et bootstrap key sont requis.");
      return;
    }
    setLoading(true);
    try {
      const out = await forgotAdminPasswordAuth({
        email: email.trim(),
        new_password: newPassword,
        bootstrap_key: bootstrapKey.trim(),
      });
      setOk(out.message || "Mot de passe admin réinitialisé.");
      setTimeout(() => navigate("/login/admin"), 900);
    } catch (err: any) {
      const detail = err?.response?.data?.detail;
      setError(typeof detail === "string" ? detail : "Réinitialisation impossible.");
    } finally {
      setLoading(false);
    }
  }

  return (
    <div className="relative flex min-h-screen flex-col items-center justify-center overflow-hidden hmi-app-bg px-4 py-12">
      <div className="relative w-full max-w-md">
        <div className="mb-6 flex justify-center gap-2">
          <HmiTag tone="orange">Admin</HmiTag>
          <HmiTag tone="muted">Mot de passe oublié</HmiTag>
        </div>
        <div className="rounded-sm border border-navy-700/90 bg-navy-950/90">
          <form onSubmit={handleSubmit} className="space-y-4 px-6 py-6">
            {error ? <p className="rounded-sm border border-alert-red/45 bg-alert-red/10 px-3 py-2 text-xs text-alert-red">{error}</p> : null}
            {ok ? <p className="rounded-sm border border-emerald-600/35 bg-emerald-500/10 px-3 py-2 text-xs text-emerald-300">{ok}</p> : null}
            <div className="relative">
              <Mail className="absolute left-3 top-1/2 h-4 w-4 -translate-y-1/2 text-steel-600" />
              <input type="email" value={email} onChange={(e) => setEmail(e.target.value)} className="hmi-input w-full pl-10" placeholder="Email admin" />
            </div>
            <div className="relative">
              <Lock className="absolute left-3 top-1/2 h-4 w-4 -translate-y-1/2 text-steel-600" />
              <input type="password" value={newPassword} onChange={(e) => setNewPassword(e.target.value)} className="hmi-input w-full pl-10" placeholder="Nouveau mot de passe" />
            </div>
            <div className="relative">
              <KeyRound className="absolute left-3 top-1/2 h-4 w-4 -translate-y-1/2 text-steel-600" />
              <input value={bootstrapKey} onChange={(e) => setBootstrapKey(e.target.value)} className="hmi-input w-full pl-10" placeholder="Bootstrap key admin" />
            </div>
            <button type="submit" disabled={loading} className="w-full rounded-sm bg-gradient-to-r from-alert-orange to-amber-600 py-3 text-sm font-semibold text-white disabled:opacity-50">
              {loading ? "Réinitialisation…" : "Réinitialiser le mot de passe"}
            </button>
            <p className="text-center text-xs text-steel-600">
              <Link to="/login/admin" className="text-plant-glow hover:underline">Retour connexion admin</Link>
            </p>
          </form>
        </div>
      </div>
    </div>
  );
}

