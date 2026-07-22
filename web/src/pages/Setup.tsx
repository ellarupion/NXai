import { useState, type ComponentType } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { Link } from "react-router-dom";
import { api, ApiError } from "../api/client";
import {
  onboardingQuery,
  settingsQuery,
  telethonSessionsQuery,
  themesQuery,
} from "../api/queries";
import { Button, Card, ErrorState, Input, LoadingState, Select, Textarea } from "../components/ui";
import { LoginWizard } from "./TelethonSessions";
import type { ChannelBot, SourceChannel, TargetChannel, Theme } from "../types";

/* Онбординг-визард: те же 6 шагов, что в чеклисте дашборда
   (interfaces/api/routers/dashboard.py:get_onboarding), но с формами прямо в
   шаге — настроить всё, не бегая по страницам. Прогресс живёт на бэке: после
   каждого действия чеклист перечитывается, и визард сам двигается дальше. */

const STEP_ORDER = ["llm_key", "reader", "theme", "bot", "target", "source"] as const;
type StepKey = (typeof STEP_ORDER)[number];

const STEP_TITLES: Record<StepKey, string> = {
  llm_key: "Ключ ИИ",
  reader: "Аккаунт-читалка",
  theme: "Тема",
  bot: "Бот",
  target: "Канал",
  source: "Источники",
};

function invalidateOnboarding(queryClient: ReturnType<typeof useQueryClient>) {
  queryClient.invalidateQueries({ queryKey: ["onboarding"] });
}

function StepLlmKey() {
  const queryClient = useQueryClient();
  const [key, setKey] = useState("");
  const [error, setError] = useState<string | null>(null);
  const save = useMutation({
    mutationFn: () => api.put("/settings", { anthropic_api_key: key }),
    onSuccess: () => {
      setKey("");
      setError(null);
      invalidateOnboarding(queryClient);
      queryClient.invalidateQueries({ queryKey: ["settings"] });
    },
    onError: (err) => setError(err instanceof ApiError ? err.message : "Не удалось сохранить ключ"),
  });

  return (
    <div className="flex flex-col gap-3">
      <p className="text-sm text-ink-muted">
        Ключ Anthropic — «мозг» системы: им ИИ переписывает чужие посты в вашем
        стиле. Получить ключ можно в консоли Anthropic (console.anthropic.com →
        API Keys). Хранится в панели, сервер трогать не нужно.
      </p>
      <form
        className="flex gap-2"
        onSubmit={(e) => {
          e.preventDefault();
          if (key) save.mutate();
        }}
      >
        <Input
          type="password"
          autoComplete="off"
          value={key}
          onChange={(e) => setKey(e.target.value)}
          placeholder="sk-ant-…"
          className="flex-1"
          required
        />
        <Button type="submit" disabled={save.isPending || !key}>
          Сохранить
        </Button>
      </form>
      {error && <p className="text-sm text-bad">{error}</p>}
    </div>
  );
}

function StepReader() {
  const queryClient = useQueryClient();
  const settings = useQuery(settingsQuery());
  const [apiId, setApiId] = useState("");
  const [apiHash, setApiHash] = useState("");
  const [error, setError] = useState<string | null>(null);

  const saveApi = useMutation({
    mutationFn: () =>
      api.put("/settings", { telegram_api_id: Number(apiId), telegram_api_hash: apiHash }),
    onSuccess: () => {
      setError(null);
      queryClient.invalidateQueries({ queryKey: ["settings"] });
    },
    onError: (err) => setError(err instanceof ApiError ? err.message : "Не удалось сохранить"),
  });

  const apiConfigured =
    settings.data &&
    settings.data.telegram_api_id.source !== "unset" &&
    settings.data.telegram_api_hash.source !== "unset";

  return (
    <div className="flex flex-col gap-3">
      <p className="text-sm text-ink-muted">
        Читалка — обычный Telegram-аккаунт, которым система читает каналы
        конкурентов. Он ничего не публикует. Лучше отдельный номер, не ваш личный.
      </p>
      {settings.isLoading && <LoadingState />}
      {settings.data && !apiConfigured && (
        <div className="flex flex-col gap-2 rounded-lg bg-surface-2 p-3">
          <p className="text-sm text-ink">
            Сначала нужны api_id и api_hash из{" "}
            <a
              href="https://my.telegram.org"
              target="_blank"
              rel="noreferrer"
              className="text-accent underline underline-offset-2"
            >
              my.telegram.org
            </a>{" "}
            (раздел «API development tools», значения общие для всех читалок):
          </p>
          <form
            className="flex flex-col gap-2 sm:flex-row"
            onSubmit={(e) => {
              e.preventDefault();
              if (apiId && apiHash) saveApi.mutate();
            }}
          >
            <Input
              type="number"
              value={apiId}
              onChange={(e) => setApiId(e.target.value)}
              placeholder="api_id"
              className="sm:w-36"
              required
            />
            <Input
              value={apiHash}
              onChange={(e) => setApiHash(e.target.value)}
              placeholder="api_hash"
              className="flex-1"
              required
            />
            <Button type="submit" disabled={saveApi.isPending || !apiId || !apiHash}>
              Сохранить
            </Button>
          </form>
          {error && <p className="text-sm text-bad">{error}</p>}
        </div>
      )}
      {apiConfigured && <LoginWizard />}
    </div>
  );
}

function StepTheme() {
  const queryClient = useQueryClient();
  const [name, setName] = useState("");
  const [error, setError] = useState<string | null>(null);
  const create = useMutation({
    mutationFn: () => api.post<Theme>("/themes", { name, default_style_prompt: "" }),
    onSuccess: () => {
      setName("");
      setError(null);
      invalidateOnboarding(queryClient);
      queryClient.invalidateQueries({ queryKey: ["themes"] });
    },
    onError: (err) => setError(err instanceof ApiError ? err.message : "Не удалось создать тему"),
  });

  return (
    <div className="flex flex-col gap-3">
      <p className="text-sm text-ink-muted">
        Тема — одно направление контента (например, «Мужской клуб» или «Финансы»).
        У каждой темы свои источники, свой бот со своим стилем и свои каналы.
      </p>
      <form
        className="flex gap-2"
        onSubmit={(e) => {
          e.preventDefault();
          if (name.trim()) create.mutate();
        }}
      >
        <Input
          value={name}
          onChange={(e) => setName(e.target.value)}
          placeholder="Название темы"
          className="flex-1"
          required
        />
        <Button type="submit" disabled={create.isPending || !name.trim()}>
          Создать
        </Button>
      </form>
      {error && <p className="text-sm text-bad">{error}</p>}
    </div>
  );
}

function StepBot() {
  const queryClient = useQueryClient();
  const themes = useQuery(themesQuery());
  const [themeId, setThemeId] = useState("");
  const [token, setToken] = useState("");
  const [persona, setPersona] = useState("");
  const [error, setError] = useState<string | null>(null);

  const create = useMutation({
    mutationFn: () =>
      api.post<ChannelBot>("/channel-bots", {
        role: "theme",
        theme_id: themeId,
        bot_token: token,
        persona_prompt: persona,
      }),
    onSuccess: () => {
      setToken("");
      setPersona("");
      setError(null);
      invalidateOnboarding(queryClient);
      queryClient.invalidateQueries({ queryKey: ["channel-bots"] });
    },
    onError: (err) => setError(err instanceof ApiError ? err.message : "Не удалось создать бота"),
  });

  return (
    <div className="flex flex-col gap-3">
      <p className="text-sm text-ink-muted">
        Бот будет публиковать посты в канал темы. Создайте бота у{" "}
        <a
          href="https://t.me/BotFather"
          target="_blank"
          rel="noreferrer"
          className="text-accent underline underline-offset-2"
        >
          @BotFather
        </a>{" "}
        (команда /newbot) и вставьте сюда его токен. Стиль можно описать сейчас или
        настроить позже на странице «Боты». Расписание публикаций получит разумные
        значения по умолчанию.
      </p>
      <form
        className="flex flex-col gap-2"
        onSubmit={(e) => {
          e.preventDefault();
          if (themeId && token) create.mutate();
        }}
      >
        <Select value={themeId} onChange={(e) => setThemeId(e.target.value)} required>
          <option value="">— выберите тему —</option>
          {themes.data?.map((t) => (
            <option key={t.id} value={t.id}>
              {t.name}
            </option>
          ))}
        </Select>
        <Input
          type="password"
          autoComplete="off"
          value={token}
          onChange={(e) => setToken(e.target.value)}
          placeholder="Токен от @BotFather"
          required
        />
        <Textarea
          value={persona}
          onChange={(e) => setPersona(e.target.value)}
          placeholder="Каким голосом писать посты (необязательно, настроите позже)"
          rows={2}
        />
        <Button type="submit" disabled={create.isPending || !themeId || !token} className="self-start">
          Создать бота
        </Button>
      </form>
      {error && <p className="text-sm text-bad">{error}</p>}
    </div>
  );
}

function StepTarget() {
  const queryClient = useQueryClient();
  const themes = useQuery(themesQuery());
  const [themeId, setThemeId] = useState("");
  const [chatId, setChatId] = useState("");
  const [error, setError] = useState<string | null>(null);

  const create = useMutation({
    mutationFn: () =>
      api.post<TargetChannel>("/target-channels", {
        theme_id: themeId,
        chat_id_or_username: chatId,
        signature: "",
      }),
    onSuccess: () => {
      setChatId("");
      setError(null);
      invalidateOnboarding(queryClient);
      queryClient.invalidateQueries({ queryKey: ["target-channels"] });
    },
    onError: (err) => setError(err instanceof ApiError ? err.message : "Не удалось добавить канал"),
  });

  return (
    <div className="flex flex-col gap-3">
      <p className="text-sm text-ink-muted">
        Ваш канал, куда пойдут публикации. Перед добавлением сделайте бота из
        прошлого шага администратором канала — панель это проверит по-настоящему,
        через Telegram, и не примет канал без прав.
      </p>
      <form
        className="flex flex-col gap-2"
        onSubmit={(e) => {
          e.preventDefault();
          if (themeId && chatId) create.mutate();
        }}
      >
        <Select value={themeId} onChange={(e) => setThemeId(e.target.value)} required>
          <option value="">— выберите тему —</option>
          {themes.data?.map((t) => (
            <option key={t.id} value={t.id}>
              {t.name}
            </option>
          ))}
        </Select>
        <Input
          value={chatId}
          onChange={(e) => setChatId(e.target.value)}
          placeholder="@username канала или chat_id (-100…)"
          required
        />
        <Button type="submit" disabled={create.isPending || !themeId || !chatId} className="self-start">
          Проверить и добавить
        </Button>
      </form>
      {error && <p className="text-sm text-bad">{error}</p>}
    </div>
  );
}

function StepSource() {
  const queryClient = useQueryClient();
  const themes = useQuery(themesQuery());
  const sessions = useQuery(telethonSessionsQuery());
  const [themeId, setThemeId] = useState("");
  const [sessionId, setSessionId] = useState("");
  const [username, setUsername] = useState("");
  const [added, setAdded] = useState<string[]>([]);
  const [error, setError] = useState<string | null>(null);

  const create = useMutation({
    mutationFn: () =>
      api.post<SourceChannel>("/source-channels", {
        username_or_link: username,
        ingest_session_id: sessionId,
        theme_id: themeId || null,
      }),
    onSuccess: (data) => {
      setAdded((list) => [...list, data.title]);
      setUsername("");
      setError(null);
      invalidateOnboarding(queryClient);
      queryClient.invalidateQueries({ queryKey: ["source-channels"] });
    },
    onError: (err) => setError(err instanceof ApiError ? err.message : "Не удалось добавить источник"),
  });

  return (
    <div className="flex flex-col gap-3">
      <p className="text-sm text-ink-muted">
        Источники — чужие каналы, откуда брать контент. Добавьте 3–5 живых каналов
        вашей тематики: чем больше выбор, тем лучше отбор. Панель найдёт каждый
        канал через читалку и сразу подпишется на него.
      </p>
      <form
        className="flex flex-col gap-2"
        onSubmit={(e) => {
          e.preventDefault();
          if (username && sessionId) create.mutate();
        }}
      >
        <div className="flex flex-col gap-2 sm:flex-row">
          <Select
            value={sessionId}
            onChange={(e) => setSessionId(e.target.value)}
            required
            className="flex-1"
          >
            <option value="">— какой читалкой читать —</option>
            {sessions.data?.map((s) => (
              <option key={s.id} value={s.id}>
                {s.label}
              </option>
            ))}
          </Select>
          <Select value={themeId} onChange={(e) => setThemeId(e.target.value)} className="flex-1">
            <option value="">— в какую тему —</option>
            {themes.data?.map((t) => (
              <option key={t.id} value={t.id}>
                {t.name}
              </option>
            ))}
          </Select>
        </div>
        <div className="flex gap-2">
          <Input
            value={username}
            onChange={(e) => setUsername(e.target.value)}
            placeholder="@username чужого канала"
            className="flex-1"
            required
          />
          <Button type="submit" disabled={create.isPending || !username || !sessionId}>
            Добавить
          </Button>
        </div>
      </form>
      {added.length > 0 && (
        <p className="text-sm text-good">Добавлено: {added.join(", ")} — можно добавить ещё.</p>
      )}
      {error && <p className="text-sm text-bad">{error}</p>}
    </div>
  );
}

const STEP_FORMS: Record<StepKey, ComponentType> = {
  llm_key: StepLlmKey,
  reader: StepReader,
  theme: StepTheme,
  bot: StepBot,
  target: StepTarget,
  source: StepSource,
};

export function Setup() {
  const { data, isLoading, error } = useQuery(onboardingQuery());
  // null — «следовать за прогрессом» (первый несделанный шаг); клик по чипу
  // переключает на конкретный шаг, например вернуться и добавить ещё источник.
  const [manualStep, setManualStep] = useState<StepKey | null>(null);

  if (isLoading) return <LoadingState />;
  if (error) return <ErrorState message={error.message} />;
  if (!data) return null;

  const doneByKey = new Map(data.steps.map((s) => [s.key, s.done]));
  const firstUndone = STEP_ORDER.find((k) => !doneByKey.get(k)) ?? null;
  const activeStep = manualStep ?? firstUndone;
  const doneCount = STEP_ORDER.filter((k) => doneByKey.get(k)).length;
  const ActiveForm = activeStep ? STEP_FORMS[activeStep] : null;

  return (
    <div className="mx-auto flex max-w-2xl flex-col gap-6">
      <div>
        <h1 className="text-xl font-semibold text-ink">Настройка системы</h1>
        <p className="mt-1 text-sm text-ink-muted">
          Шесть шагов — и система начнёт собирать, переписывать и предлагать вам
          посты. Каждый шаг проверяется по-настоящему; можно уйти и вернуться —
          прогресс не потеряется.
        </p>
      </div>

      <div className="flex flex-wrap gap-2">
        {STEP_ORDER.map((key, i) => {
          const done = Boolean(doneByKey.get(key));
          const active = key === activeStep;
          return (
            <button
              key={key}
              type="button"
              onClick={() => setManualStep(key)}
              className={[
                "flex items-center gap-1.5 rounded-full px-3 py-1.5 text-xs font-medium transition-colors",
                active
                  ? "bg-accent text-accent-ink"
                  : done
                    ? "bg-good-soft text-good hover:opacity-80"
                    : "bg-surface-2 text-ink-muted hover:text-ink",
              ].join(" ")}
            >
              <span>{done ? "✓" : i + 1}</span>
              {STEP_TITLES[key]}
            </button>
          );
        })}
      </div>

      {data.all_done && manualStep === null ? (
        <Card className="border-accent/40">
          <h2 className="mb-2 text-sm font-semibold text-ink">Система запущена 🎉</h2>
          <p className="text-sm text-ink-muted">
            Всё подключено. Читалки уже собирают посты из источников — первые
            кандидаты появятся в течение ~30 минут. Дальше система работает сама:
            отбирает виральное, переписывает вашим стилем и публикует по расписанию.
          </p>
          <p className="mt-2 text-sm text-ink-muted">
            Не хотите ждать —{" "}
            <Link to="/review" className="text-accent underline underline-offset-2">
              сделайте первые посты прямо сейчас
            </Link>{" "}
            на странице «Проверка».
          </p>
        </Card>
      ) : (
        ActiveForm && (
          <Card>
            <h2 className="mb-3 text-sm font-semibold text-ink">
              Шаг {STEP_ORDER.indexOf(activeStep as StepKey) + 1} из 6 —{" "}
              {STEP_TITLES[activeStep as StepKey]}
              {doneByKey.get(activeStep as StepKey) && (
                <span className="ml-2 rounded-full bg-good-soft px-2 py-0.5 text-xs text-good">
                  уже сделано — можно добавить ещё
                </span>
              )}
            </h2>
            <ActiveForm />
          </Card>
        )
      )}

      <p className="text-xs text-ink-muted">
        Настроено {doneCount} из 6. Продвинутые настройки (расписание бота, подписи,
        кросспост) живут на своих страницах — визард задаёт только необходимое.
      </p>
    </div>
  );
}
