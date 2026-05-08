import { NavLink, Outlet } from "react-router-dom";

const tabClass = ({ isActive }: { isActive: boolean }) =>
  [
    "rounded-sm border px-3 py-2 text-xs font-semibold transition",
    isActive
      ? "border-plant-accent/50 bg-plant-accent/15 text-plant-glow"
      : "border-navy-700 bg-navy-950/60 text-steel-500 hover:bg-navy-900",
  ].join(" ");

export function AdminWindowPage() {
  return (
    <div className="space-y-4">
      <div className="rounded-sm border border-navy-700 bg-navy-950/70 p-4">
        <h1 className="text-lg font-semibold text-steel-200">Admin Window</h1>
        <p className="mt-1 text-xs text-steel-500">
          Espace séparé pour connexion ERP SQL et monitoring background de l’application.
        </p>
        <div className="mt-3 flex flex-wrap gap-2">
          <NavLink to="/admin/erp" className={tabClass}>
            ERP Connexion
          </NavLink>
          <NavLink to="/admin/monitoring" className={tabClass}>
            Monitoring Background
          </NavLink>
        </div>
      </div>
      <Outlet />
    </div>
  );
}
