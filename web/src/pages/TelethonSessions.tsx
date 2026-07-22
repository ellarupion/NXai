import { useState } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { api, ApiError } from "../api/client";
import { telethonSessionsQuery } from "../api/queries";
import { Button, Callout, Card, EmptyState, ErrorState, Input, LoadingState, StatusBadge } from "../components/ui";
import type { TelethonLoginStartResult, TelethonLoginStepResult, TelethonSession } from "../types";

type WizardStep = "phone" | "code" | "password";

// Экспортируется: онбординг-визард (/setup) встраивает эту же форму
// подключения аккаунта, чтобы не дублировать трёхшаговый флоу логина.
export function LoginWizard() {
  const queryClient = useQueryClient();
  const [step, setStep] = useState<WizardStep>("phone");
  const [attemptId, setAttemptId] = useState<string | null>(null);
  const [phoneNumber, setPhoneNumber] = useState("");
  const [label, setLabel] = useState("");
  const [code, setCode] = useState("");
  const [password, setPassword] = useState("");
  const [error, setError] = useState<string | null>(null);

  function reset() {
    setStep("phone");
    setAttemptId(null);
    setPhoneNumber("");
    setLabel("");
    setCode("");
    setPassword("");
    setError(null);
  }

  function finish() {
    reset();
    queryClient.invalidateQueries({ queryKey: ["telethon-sessions"] });
  }

  const startMutation = useMutation({
    mutationFn: () =>
      api.post<TelethonLoginStartResult>("/telethon-sessions/login/start", {
        phone_number: phoneNumber,
        label,
      }),
    onSuccess: (data) => {
      setAttemptId(data.attempt_id);
      setStep("code");
      setError(null);
    },
    onError: (err) => setError(err instanceof ApiError ? err.message : "Не удалось отправить код"),
  });

  const codeMutation = useMutation({
    mutationFn: () =>
      api.post<TelethonLoginStepResult>("/telethon-sessions/login/code", {
        attempt_id: attemptId,
        code,
      }),
    onSuccess: (data) => {
      setError(null);
      if (data.status === "password_required") {
        setStep("password");
        return;
      }
      finish();
    },
    onError: (err) => setError(err instanceof ApiError ? err.message : "Не удалось подтвердить код"),
  });

  const passwordMutation = useMutation({
    mutationFn: () =>
      api.post<TelethonLoginStepResult>("/telethon-sessions/login/password", {
        attempt_id: attemptId,
        password,
      }),
    onSuccess: () => finish(),
    onError: (err) => setError(err instanceof ApiError ? err.message : "Неверный пароль"),
  });

  return (
    <Card>
      <h2 className="mb-3 text-sm font-semibold text-ink">Новый аккаунт-читалка</h2>
      <p className="mb-3 text-sm text-ink-muted">
        Обычный Telegram-аккаунт, от имени которого система читает чужие каналы.
        Подключается в три шага: номер телефона → код из Telegram → пароль двухфакторной
        аутентификации (если включена). Аккаунт ничего не пишет и не публикует —
        только читает каналы-источники.
      </p>

      {step === "phone" && (
        <form
          className="flex flex-col gap-2"
          onSubmit={(e) => {
            e.preventDefault();
            setError(null);
            startMutation.mutate();
          }}
        >
          <Input
            value={label}
            onChange={(e) => setLabel(e.target.value)}
            placeholder="Название (например, reader-1 или сам номер)"
            required
          />
          <Input
            value={phoneNumber}
            onChange={(e) => setPhoneNumber(e.target.value)}
            placeholder="Номер телефона, с кодом страны (+79991234567)"
            required
          />
          <Button type="submit" disabled={startMutation.isPending} className="self-start">
            Отправить код
          </Button>
        </form>
      )}

      {step === "code" && (
        <form
          className="flex flex-col gap-2"
          onSubmit={(e) => {
            e.preventDefault();
            setError(null);
            codeMutation.mutate();
          }}
        >
          <p className="text-sm text-ink-muted">
            Код отправлен в Telegram на номер <span className="font-medium text-ink">{phoneNumber}</span>.
          </p>
          <Input
            value={code}
            onChange={(e) => setCode(e.target.value)}
            placeholder="Код из Telegram"
            autoFocus
            required
          />
          <div className="flex gap-2">
            <Button type="submit" disabled={codeMutation.isPending}>
              Подтвердить
            </Button>
            <Button type="button" variant="secondary" onClick={reset}>
              Начать заново
            </Button>
          </div>
        </form>
      )}

      {step === "password" && (
        <form
          className="flex flex-col gap-2"
          onSubmit={(e) => {
            e.preventDefault();
            setError(null);
            passwordMutation.mutate();
          }}
        >
          <p className="text-sm text-ink-muted">На аккаунте включена двухфакторная аутентификация.</p>
          <Input
            type="password"
            value={password}
            onChange={(e) => setPassword(e.target.value)}
            placeholder="Пароль 2FA"
            autoFocus
            required
          />
          <div className="flex gap-2">
            <Button type="submit" disabled={passwordMutation.isPending}>
              Войти
            </Button>
            <Button type="button" variant="secondary" onClick={reset}>
              Начать заново
            </Button>
          </div>
        </form>
      )}

      {error && <p className="mt-2 text-sm text-bad">{error}</p>}
    </Card>
  );
}

function SessionRow({ telethonSession }: { telethonSession: TelethonSession }) {
  const queryClient = useQueryClient();
  const [label, setLabel] = useState(telethonSession.label);
  const [error, setError] = useState<string | null>(null);

  const update = useMutation({
    mutationFn: (payload: Partial<Pick<TelethonSession, "label" | "is_active">>) =>
      api.put<TelethonSession>(`/telethon-sessions/${telethonSession.id}`, payload),
    onSuccess: () => {
      setError(null);
      queryClient.invalidateQueries({ queryKey: ["telethon-sessions"] });
    },
    onError: (err) => setError(err instanceof ApiError ? err.message : "Не удалось обновить"),
  });

  const remove = useMutation({
    mutationFn: () => api.delete(`/telethon-sessions/${telethonSession.id}`),
    onSuccess: () => {
      setError(null);
      queryClient.invalidateQueries({ queryKey: ["telethon-sessions"] });
    },
    onError: (err) => setError(err instanceof ApiError ? err.message : "Не удалось удалить"),
  });

  return (
    <li className="flex flex-col gap-2 py-3 first:pt-0 last:pb-0">
      <div className="flex flex-wrap items-center justify-between gap-2">
        <form
          className="flex min-w-0 flex-1 gap-2"
          onSubmit={(e) => {
            e.preventDefault();
            if (label === telethonSession.label) return;
            setError(null);
            update.mutate({ label });
          }}
        >
          <Input value={label} onChange={(e) => setLabel(e.target.value)} className="flex-1" />
          {label !== telethonSession.label && (
            <Button type="submit" variant="secondary" disabled={update.isPending}>
              Сохранить
            </Button>
          )}
        </form>
        <div className="flex flex-wrap items-center gap-2">
          <StatusBadge active={telethonSession.is_active} />
          <Button
            variant="secondary"
            disabled={update.isPending}
            onClick={() => update.mutate({ is_active: !telethonSession.is_active })}
          >
            {telethonSession.is_active ? "Отключить" : "Включить"}
          </Button>
          <Button
            variant="danger"
            disabled={remove.isPending}
            onClick={() => {
              if (window.confirm(`Удалить аккаунт «${telethonSession.label}»? Источники, читаемые им, останутся без назначенной сессии.`)) {
                remove.mutate();
              }
            }}
          >
            Удалить
          </Button>
        </div>
      </div>
      {error && <p className="text-xs text-bad">{error}</p>}
    </li>
  );
}

export function TelethonSessions() {
  const { data, isLoading, error } = useQuery(telethonSessionsQuery());

  return (
    <div className="flex flex-col gap-6">
      <h1 className="text-xl font-semibold text-ink">Аккаунты-читалки</h1>
      <p className="text-sm text-ink-muted">
        Аккаунты, от имени которых система читает каналы-источники. Один аккаунт
        тянет ограниченное число каналов — заводите несколько по мере роста списка
        источников, а не один на всё.
      </p>
      <Callout>
        Новый аккаунт начинает читать назначенные каналы автоматически в течение
        ~30 секунд, без перезапуска сервера.
      </Callout>

      <LoginWizard />

      <Card>
        <h2 className="mb-3 text-sm font-semibold text-ink">Все аккаунты</h2>
        {isLoading && <LoadingState />}
        {error && <ErrorState message={error.message} />}
        {data && data.length === 0 && (
          <EmptyState message="Аккаунтов пока нет — заведите первый выше." />
        )}
        {data && data.length > 0 && (
          <ul className="flex flex-col divide-y divide-border">
            {data.map((telethonSession) => (
              <SessionRow key={telethonSession.id} telethonSession={telethonSession} />
            ))}
          </ul>
        )}
      </Card>
    </div>
  );
}
