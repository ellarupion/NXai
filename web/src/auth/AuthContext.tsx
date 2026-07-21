import { createContext, useCallback, useContext, useEffect, useState, type ReactNode } from "react";
import { api, clearToken, getToken, setToken } from "../api/client";

interface AuthContextValue {
  isAuthenticated: boolean;
  isLoading: boolean;
  loginWithPassword: (username: string, password: string) => Promise<void>;
  logout: () => void;
}

const AuthContext = createContext<AuthContextValue | null>(null);

export function AuthProvider({ children }: { children: ReactNode }) {
  const [isAuthenticated, setIsAuthenticated] = useState(() => Boolean(getToken()));
  const [isLoading, setIsLoading] = useState(false);

  useEffect(() => {
    // Любой 401 из любого запроса (см. api/client.ts) сбрасывает сессию тут —
    // без этого пользователь остался бы на защищённой странице с мёртвым токеном.
    const onUnauthorized = () => setIsAuthenticated(false);
    window.addEventListener("nxai-unauthorized", onUnauthorized);
    return () => window.removeEventListener("nxai-unauthorized", onUnauthorized);
  }, []);

  const loginWithPassword = useCallback(async (username: string, password: string) => {
    setIsLoading(true);
    try {
      const { access_token } = await api.post<{ access_token: string }>("/auth/login", {
        username,
        password,
      });
      setToken(access_token);
      setIsAuthenticated(true);
    } finally {
      setIsLoading(false);
    }
  }, []);

  const logout = useCallback(() => {
    clearToken();
    setIsAuthenticated(false);
  }, []);

  return (
    <AuthContext.Provider value={{ isAuthenticated, isLoading, loginWithPassword, logout }}>
      {children}
    </AuthContext.Provider>
  );
}

export function useAuth(): AuthContextValue {
  const ctx = useContext(AuthContext);
  if (!ctx) throw new Error("useAuth must be used within AuthProvider");
  return ctx;
}
