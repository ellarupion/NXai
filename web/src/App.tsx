import { lazy, Suspense } from "react";
import { BrowserRouter, Navigate, Route, Routes } from "react-router-dom";
import { AuthProvider, useAuth } from "./auth/AuthContext";
import { Layout } from "./components/Layout";
import { LoadingState } from "./components/ui";

// lazy(): каждая страница — свой чанк (тот же приём, что в NX App.tsx).
const Login = lazy(() => import("./pages/Login").then((m) => ({ default: m.Login })));
const Dashboard = lazy(() => import("./pages/Dashboard").then((m) => ({ default: m.Dashboard })));
// Единый рабочий стол темы (конвейер, источники, бот, каналы, запас) — вкладки
// тем сверху, "+" создаёт новую. Заменил отдельные страницы Источники/Боты/
// Каналы/Запас/ThemeCard (аудит UX: "сто вкладок, чтобы поправить тему").
const Themes = lazy(() => import("./pages/Themes").then((m) => ({ default: m.Themes })));
const Settings = lazy(() => import("./pages/Settings").then((m) => ({ default: m.Settings })));
const TelethonSessions = lazy(() =>
  import("./pages/TelethonSessions").then((m) => ({ default: m.TelethonSessions })),
);
const Review = lazy(() => import("./pages/Review").then((m) => ({ default: m.Review })));
const Setup = lazy(() => import("./pages/Setup").then((m) => ({ default: m.Setup })));
const Queue = lazy(() => import("./pages/Queue").then((m) => ({ default: m.Queue })));

function ProtectedLayout() {
  const { isAuthenticated } = useAuth();
  if (!isAuthenticated) return <Navigate to="/login" replace />;
  return <Layout />;
}

function AppRoutes() {
  const { isAuthenticated } = useAuth();

  return (
    <Suspense
      fallback={
        <div className="flex min-h-screen items-center justify-center">
          <LoadingState />
        </div>
      }
    >
      <Routes>
        <Route path="/login" element={isAuthenticated ? <Navigate to="/" replace /> : <Login />} />
        <Route element={<ProtectedLayout />}>
          <Route path="/" element={<Dashboard />} />
          <Route path="/themes" element={<Themes />} />
          <Route path="/themes/:themeId" element={<Themes />} />
          <Route path="/telethon-sessions" element={<TelethonSessions />} />
          <Route path="/review" element={<Review />} />
          <Route path="/queue" element={<Queue />} />
          <Route path="/settings" element={<Settings />} />
          <Route path="/setup" element={<Setup />} />
        </Route>
        <Route path="*" element={<Navigate to="/" replace />} />
      </Routes>
    </Suspense>
  );
}

function App() {
  return (
    <AuthProvider>
      <BrowserRouter>
        <AppRoutes />
      </BrowserRouter>
    </AuthProvider>
  );
}

export default App;
