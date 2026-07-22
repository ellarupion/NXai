import { lazy, Suspense } from "react";
import { BrowserRouter, Navigate, Route, Routes } from "react-router-dom";
import { AuthProvider, useAuth } from "./auth/AuthContext";
import { Layout } from "./components/Layout";
import { LoadingState } from "./components/ui";

// lazy(): каждая страница — свой чанк (тот же приём, что в NX App.tsx).
const Login = lazy(() => import("./pages/Login").then((m) => ({ default: m.Login })));
const Dashboard = lazy(() => import("./pages/Dashboard").then((m) => ({ default: m.Dashboard })));
const Themes = lazy(() => import("./pages/Themes").then((m) => ({ default: m.Themes })));
const SourceChannels = lazy(() =>
  import("./pages/SourceChannels").then((m) => ({ default: m.SourceChannels })),
);
const Bots = lazy(() => import("./pages/Bots").then((m) => ({ default: m.Bots })));
const Settings = lazy(() => import("./pages/Settings").then((m) => ({ default: m.Settings })));
const TelethonSessions = lazy(() =>
  import("./pages/TelethonSessions").then((m) => ({ default: m.TelethonSessions })),
);
const TargetChannels = lazy(() =>
  import("./pages/TargetChannels").then((m) => ({ default: m.TargetChannels })),
);
const Review = lazy(() => import("./pages/Review").then((m) => ({ default: m.Review })));
const PoolPosts = lazy(() => import("./pages/PoolPosts").then((m) => ({ default: m.PoolPosts })));
const Setup = lazy(() => import("./pages/Setup").then((m) => ({ default: m.Setup })));
const ThemeCard = lazy(() => import("./pages/ThemeCard").then((m) => ({ default: m.ThemeCard })));

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
          <Route path="/themes/:themeId" element={<ThemeCard />} />
          <Route path="/source-channels" element={<SourceChannels />} />
          <Route path="/telethon-sessions" element={<TelethonSessions />} />
          <Route path="/target-channels" element={<TargetChannels />} />
          <Route path="/bots" element={<Bots />} />
          <Route path="/review" element={<Review />} />
          <Route path="/pool-posts" element={<PoolPosts />} />
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
