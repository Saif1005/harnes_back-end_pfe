import { Navigate, Outlet, useLocation } from "react-router-dom";
import { useAuth } from "@/context/AuthContext";

export function ProtectedRoute({ requireAdmin = false }: { requireAdmin?: boolean }) {
  const { isAuthenticated, isAdmin } = useAuth();
  const location = useLocation();
  const loginPath = requireAdmin ? "/login/admin" : "/login";

  if (!isAuthenticated) {
    return <Navigate to={loginPath} replace state={{ from: location }} />;
  }
  if (requireAdmin && !isAdmin) {
    return <Navigate to="/login/admin" replace state={{ from: location }} />;
  }

  return <Outlet />;
}
