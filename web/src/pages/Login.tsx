import { useState } from "react";
import { useNavigate } from "react-router-dom";
import { useAuth } from "../auth/AuthContext";
import { ApiError } from "../api/client";
import { Button, Input } from "../components/ui";

export function Login() {
  const { loginWithPassword, isLoading } = useAuth();
  const navigate = useNavigate();
  const [username, setUsername] = useState("");
  const [password, setPassword] = useState("");
  const [error, setError] = useState<string | null>(null);

  return (
    <div className="flex min-h-screen flex-col bg-bg">
      <div className="flex flex-1 items-center justify-center px-4">
        <div className="shadow-token w-full max-w-sm rounded-xl border border-border bg-surface p-8 text-center">
          <div className="mb-2 text-2xl font-semibold tracking-tight text-ink">NXai</div>
          <p className="mb-6 text-sm text-ink-muted">Войдите в панель.</p>

          <form
            className="flex flex-col gap-2 text-left"
            onSubmit={(e) => {
              e.preventDefault();
              setError(null);
              loginWithPassword(username, password)
                .then(() => navigate("/"))
                .catch((err) => setError(err instanceof ApiError ? err.message : "Не удалось войти"));
            }}
          >
            <label className="flex flex-col gap-1 text-xs text-ink-muted">
              Логин
              <Input
                value={username}
                onChange={(e) => setUsername(e.target.value)}
                autoComplete="username"
                required
              />
            </label>
            <label className="flex flex-col gap-1 text-xs text-ink-muted">
              Пароль
              <Input
                type="password"
                value={password}
                onChange={(e) => setPassword(e.target.value)}
                autoComplete="current-password"
                required
              />
            </label>
            <Button type="submit" disabled={isLoading} className="mt-1">
              Войти
            </Button>
            {error && <p className="text-sm text-bad">{error}</p>}
          </form>
        </div>
      </div>
    </div>
  );
}
