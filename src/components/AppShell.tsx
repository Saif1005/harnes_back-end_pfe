import { Link, NavLink, Outlet } from "react-router-dom";
import {
  Gauge,
  LayoutDashboard,
  LogOut,
  MessageSquareText,
  Settings2,
} from "lucide-react";
import { useAuth } from "@/context/AuthContext";
import { OperatorStatusBar } from "@/components/OperatorStatusBar";

const navClass = ({ isActive }: { isActive: boolean }) =>
  [
    "group relative flex items-center gap-3 rounded-sm px-3 py-2.5 text-sm font-medium transition-all duration-150",
    isActive
      ? "bg-gradient-to-r from-plant-accent/25 to-transparent text-steel-100 shadow-[inset_3px_0_0_0_rgba(34,211,238,0.9)]"
      : "text-steel-500 hover:bg-navy-800/80 hover:text-steel-300",
  ].join(" ");

export function AppShell() {
  const { user, logout, isAdmin } = useAuth();

  return (
    <div className="flex min-h-screen hmi-app-bg">
      {/* Rail latéral accent + motif oblique léger */}
      <aside className="rail-accent relative flex w-[248px] shrink-0 flex-col border-r border-navy-800/90 bg-[linear-gradient(165deg,rgba(15,39,68,0.97)_0%,rgba(5,11,20,0.98)_50%,rgba(10,22,40,0.95)_100%)] shadow-[inset_-1px_0_0_rgba(34,211,238,0.06)]">
        <div
          className="pointer-events-none absolute inset-0 opacity-[0.04]"
          style={{
            backgroundImage: "repeating-linear-gradient(-45deg, transparent, transparent 8px, rgba(255,255,255,0.03) 8px, rgba(255,255,255,0.03) 9px)",
          }}
          aria-hidden
        />

        <div className="relative border-b border-navy-800/80 px-4 py-6">
          <div className="flex items-start gap-3">
            <div className="relative shrink-0 overflow-hidden rounded-sm border border-navy-700/90 bg-[#4a5238]/35 px-2 py-1.5 shadow-[inset_0_1px_0_rgba(255,255,255,0.06)]">
              <img
                src="/image.png"
                alt="Sotipapier"
                className="h-9 w-auto max-w-[200px] object-contain object-left"
                width={200}
                height={36}
                decoding="async"
              />
              <span
                className="absolute -right-0.5 -top-0.5 h-2 w-2 rounded-full bg-emerald-500 shadow-[0_0_8px_#22c55e]"
                title="Session"
              />
            </div>
            <div className="min-w-0 pt-1">
              <p className="truncate text-base font-semibold tracking-tight text-steel-100">Centre HMI</p>
              <p className="mt-0.5 font-mono text-[10px] text-steel-600">Papier — Contrôle prod.</p>
            </div>
          </div>
        </div>

        <nav className="relative flex flex-1 flex-col gap-0.5 p-3">
          <p className="mb-2 px-2 font-mono text-[10px] uppercase tracking-[0.2em] text-steel-600">Navigation</p>
          <NavLink to="/" end className={navClass}>
            <LayoutDashboard className="h-4 w-4 shrink-0 opacity-80 group-hover:opacity-100" />
            Tableau de bord
          </NavLink>
          <NavLink to="/assistant" className={navClass}>
            <MessageSquareText className="h-4 w-4 shrink-0 opacity-80 group-hover:opacity-100" />
            Assistant IA
          </NavLink>
          {isAdmin ? (
            <NavLink to="/admin/erp" className={navClass}>
              <Settings2 className="h-4 w-4 shrink-0 opacity-80 group-hover:opacity-100" />
              Admin Window
            </NavLink>
          ) : null}
        </nav>

        <div className="relative mt-auto border-t border-navy-800/80 p-3">
          <div className="mb-3 flex items-center gap-2 rounded-sm border border-navy-800 bg-navy-950/80 px-2 py-2">
            <Gauge className="h-4 w-4 shrink-0 text-steel-600" />
            <div className="min-w-0 flex-1">
              <p className="truncate font-mono text-[11px] text-steel-300">{user?.email}</p>
              <p className="font-mono text-[10px] uppercase tracking-wider text-steel-600">
                {isAdmin ? "Admin" : "Opérateur"}
              </p>
            </div>
          </div>
          <button
            type="button"
            onClick={() => logout()}
            className="flex w-full items-center justify-center gap-2 rounded-sm border border-alert-orange/30 bg-alert-orange/5 py-2.5 text-sm font-medium text-alert-orange transition-colors hover:bg-alert-orange/15"
          >
            <LogOut className="h-4 w-4" />
            Déconnexion
          </button>
        </div>
      </aside>

      <div className="flex min-h-screen min-w-0 flex-1 flex-col">
        <OperatorStatusBar />
        <header className="flex h-12 shrink-0 items-center justify-between border-b border-navy-800/90 bg-navy-950/40 px-5 backdrop-blur-md">
          <div className="flex items-center gap-3">
            <span className="hidden font-mono text-[11px] uppercase tracking-[0.18em] text-steel-600 sm:inline">
              Écran principal
            </span>
            <span className="h-4 w-px bg-navy-700" aria-hidden />
            <span className="text-xs text-steel-500">Supervision &amp; agents IA</span>
          </div>
          <Link
            to="/assistant"
            className="group flex items-center gap-2 rounded-sm border border-plant-accent/25 bg-plant-accent/10 px-3 py-1.5 font-mono text-[11px] uppercase tracking-wider text-plant-glow transition-colors hover:border-plant-accent/50 hover:bg-plant-accent/20"
          >
            Console assistant
            <span className="transition-transform group-hover:translate-x-0.5">→</span>
          </Link>
        </header>
        <main className="hmi-scrollbar flex-1 overflow-auto p-6 md:p-8">
          <Outlet />
        </main>
      </div>
    </div>
  );
}
