import { Suspense, lazy, type ReactNode } from "react";
import { Navigate, Route, Routes } from "react-router-dom";
import { AuthProvider } from "@/context/AuthContext";
import { AppShell } from "@/components/AppShell";
import { IndustrialLoader } from "@/components/IndustrialLoader";
import { ProtectedRoute } from "@/components/ProtectedRoute";

const LoginPage = lazy(() => import("@/pages/LoginPage").then((m) => ({ default: m.LoginPage })));
const RegisterPage = lazy(() => import("@/pages/RegisterPage").then((m) => ({ default: m.RegisterPage })));
const DashboardPage = lazy(() => import("@/pages/DashboardPage").then((m) => ({ default: m.DashboardPage })));
const AssistantPage = lazy(() => import("@/pages/AssistantPage").then((m) => ({ default: m.AssistantPage })));
const AdminConfigPage = lazy(() => import("@/pages/AdminConfigPage").then((m) => ({ default: m.AdminConfigPage })));
const AdminMonitoringPage = lazy(() =>
  import("@/pages/AdminMonitoringPage").then((m) => ({ default: m.AdminMonitoringPage }))
);
const AdminWindowPage = lazy(() => import("@/pages/AdminWindowPage").then((m) => ({ default: m.AdminWindowPage })));
const AdminRegisterPage = lazy(() => import("@/pages/AdminRegisterPage").then((m) => ({ default: m.AdminRegisterPage })));
const AdminForgotPasswordPage = lazy(() =>
  import("@/pages/AdminForgotPasswordPage").then((m) => ({ default: m.AdminForgotPasswordPage }))
);

function SuspenseLayout({ children }: { children: ReactNode }) {
  return (
    <div className="flex min-h-[50vh] flex-1 flex-col">
      <Suspense
        fallback={
          <div className="flex min-h-[55vh] flex-1 flex-col items-center justify-center py-16">
            <IndustrialLoader label="Chargement du module…" />
          </div>
        }
      >
        {children}
      </Suspense>
    </div>
  );
}

export default function App() {
  return (
    <AuthProvider>
      <Suspense
        fallback={
          <div className="flex min-h-screen flex-col items-center justify-center bg-navy-970">
            <IndustrialLoader label="Démarrage interface…" />
          </div>
        }
      >
        <Routes>
          <Route
            path="/login"
            element={
              <SuspenseLayout>
                <LoginPage />
              </SuspenseLayout>
            }
          />
          <Route
            path="/login/admin"
            element={
              <SuspenseLayout>
                <LoginPage scope="admin" />
              </SuspenseLayout>
            }
          />
          <Route
            path="/register"
            element={
              <SuspenseLayout>
                <RegisterPage />
              </SuspenseLayout>
            }
          />
          <Route
            path="/register/admin"
            element={
              <SuspenseLayout>
                <AdminRegisterPage />
              </SuspenseLayout>
            }
          />
          <Route
            path="/admin/forgot-password"
            element={
              <SuspenseLayout>
                <AdminForgotPasswordPage />
              </SuspenseLayout>
            }
          />
          <Route element={<ProtectedRoute />}>
            <Route element={<AppShell />}>
              <Route
                index
                element={
                  <SuspenseLayout>
                    <DashboardPage />
                  </SuspenseLayout>
                }
              />
              <Route
                path="assistant"
                element={
                  <SuspenseLayout>
                    <AssistantPage />
                  </SuspenseLayout>
                }
              />
            </Route>
          </Route>
          <Route element={<ProtectedRoute requireAdmin />}>
            <Route element={<AppShell />}>
              <Route
                path="admin"
                element={
                  <SuspenseLayout>
                    <AdminWindowPage />
                  </SuspenseLayout>
                }
              >
                <Route index element={<Navigate to="/admin/erp" replace />} />
                <Route
                  path="erp"
                  element={
                    <SuspenseLayout>
                      <AdminConfigPage />
                    </SuspenseLayout>
                  }
                />
                <Route
                  path="monitoring"
                  element={
                    <SuspenseLayout>
                      <AdminMonitoringPage />
                    </SuspenseLayout>
                  }
                />
              </Route>
            </Route>
          </Route>
          <Route path="*" element={<Navigate to="/" replace />} />
        </Routes>
      </Suspense>
    </AuthProvider>
  );
}
