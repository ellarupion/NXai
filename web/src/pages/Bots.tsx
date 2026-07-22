import { useState } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { api, ApiError } from "../api/client";
import { channelBotsQuery, themesQuery } from "../api/queries";
import {
  Button,
  Callout,
  Card,
  EmptyState,
  ErrorState,
  Input,
  LoadingState,
  Select,
  StatusBadge,
  Textarea,
} from "../components/ui";
import type { BotRole, Cadence, ChannelBot } from "../types";

const DEFAULT_CADENCE: Cadence = {
  posts_per_day_target: 8,
  min_interval_minutes: 30,
  max_interval_minutes: 180,
  jitter_minutes: 15,
  quiet_hours_start: 23,
  quiet_hours_end: 8,
};

const CADENCE_FIELDS: Array<{ key: keyof Cadence; label: string; hint: string }> = [
  { key: "posts_per_day_target", label: "Постов в день", hint: "Сколько постов бот старается выпустить за сутки" },
  { key: "min_interval_minutes", label: "Пауза между постами: от, мин", hint: "Раньше этого срока следующий пост не выйдет" },
  { key: "max_interval_minutes", label: "Пауза между постами: до, мин", hint: "Дольше этого срока бот ждать не будет" },
  { key: "jitter_minutes", label: "Разброс времени, ± мин", hint: "Случайный сдвиг каждого поста, чтобы расписание выглядело живым, а не роботским" },
  { key: "quiet_hours_start", label: "Не постить с, час", hint: "Начало ночной тишины — по часовому поясу из Настроек" },
  { key: "quiet_hours_end", label: "Не постить до, час", hint: "Конец ночной тишины — по часовому поясу из Настроек" },
];

function CreateBotForm() {
  const queryClient = useQueryClient();
  const themes = useQuery(themesQuery());
  const [role, setRole] = useState<BotRole>("theme");
  const [themeId, setThemeId] = useState("");
  const [botToken, setBotToken] = useState("");
  const [personaPrompt, setPersonaPrompt] = useState("");
  const [cadence, setCadence] = useState<Cadence>(DEFAULT_CADENCE);
  const [error, setError] = useState<string | null>(null);

  const create = useMutation({
    mutationFn: () =>
      api.post<ChannelBot>("/channel-bots", {
        role,
        theme_id: role === "theme" ? themeId || null : null,
        bot_token: botToken,
        persona_prompt: personaPrompt,
        cadence,
      }),
    onSuccess: () => {
      setBotToken("");
      setPersonaPrompt("");
      setThemeId("");
      setCadence(DEFAULT_CADENCE);
      queryClient.invalidateQueries({ queryKey: ["channel-bots"] });
    },
    onError: (err) => setError(err instanceof ApiError ? err.message : "Не удалось создать бота"),
  });

  return (
    <Card>
      <h2 className="mb-3 text-sm font-semibold text-ink">Новый бот</h2>
      <form
        className="flex flex-col gap-2"
        onSubmit={(e) => {
          e.preventDefault();
          setError(null);
          create.mutate();
        }}
      >
        <div className="flex gap-2">
          <Select value={role} onChange={(e) => setRole(e.target.value as BotRole)} className="flex-1">
            <option value="theme">Тематический бот</option>
            <option value="admin">Admin-бот (агрегирующий)</option>
          </Select>
          {role === "theme" && (
            <Select value={themeId} onChange={(e) => setThemeId(e.target.value)} required className="flex-1">
              <option value="">— выберите тему —</option>
              {themes.data?.map((theme) => (
                <option key={theme.id} value={theme.id}>
                  {theme.name}
                </option>
              ))}
            </Select>
          )}
        </div>
        <Input
          type="password"
          autoComplete="off"
          value={botToken}
          onChange={(e) => setBotToken(e.target.value)}
          placeholder="Токен от @BotFather"
          required
        />
        {role === "theme" && (
          <Textarea
            value={personaPrompt}
            onChange={(e) => setPersonaPrompt(e.target.value)}
            placeholder="Персона/стиль для рерайта (необязательно)"
            rows={2}
          />
        )}
        {role === "theme" && (
          <div className="grid grid-cols-2 gap-2 sm:grid-cols-3">
            {CADENCE_FIELDS.map(({ key, label, hint }) => (
              <label key={key} title={hint} className="flex flex-col gap-1 text-xs text-ink-muted">
                {label}
                <Input
                  type="number"
                  value={cadence[key]}
                  onChange={(e) => setCadence((c) => ({ ...c, [key]: Number(e.target.value) }))}
                />
              </label>
            ))}
          </div>
        )}
        <Button type="submit" disabled={create.isPending} className="self-start">
          Создать
        </Button>
        {error && <p className="text-sm text-bad">{error}</p>}
      </form>
    </Card>
  );
}

function BotRow({ bot, themeName }: { bot: ChannelBot; themeName: string | null }) {
  const queryClient = useQueryClient();
  const [newToken, setNewToken] = useState("");
  const [editingPersona, setEditingPersona] = useState(false);
  const [persona, setPersona] = useState(bot.persona_prompt);
  const [error, setError] = useState<string | null>(null);

  const invalidate = () => queryClient.invalidateQueries({ queryKey: ["channel-bots"] });

  const update = useMutation({
    mutationFn: (payload: Partial<Pick<ChannelBot, "is_active" | "persona_prompt">> & { bot_token?: string }) =>
      api.put<ChannelBot>(`/channel-bots/${bot.id}`, payload),
    onSuccess: () => {
      setError(null);
      setNewToken("");
      setEditingPersona(false);
      invalidate();
    },
    onError: (err) => setError(err instanceof ApiError ? err.message : "Не удалось обновить бота"),
  });

  const remove = useMutation({
    mutationFn: () => api.delete(`/channel-bots/${bot.id}`),
    onSuccess: () => {
      setError(null);
      invalidate();
    },
    onError: (err) => setError(err instanceof ApiError ? err.message : "Не удалось удалить бота"),
  });

  const busy = update.isPending || remove.isPending;
  const label = bot.role === "admin" ? "Admin-бот" : (themeName ?? "— без темы —");

  return (
    <li className="flex flex-col gap-2 py-3 first:pt-0 last:pb-0">
      <div className="flex items-center justify-between gap-2">
        <div>
          <span className="font-medium text-ink">{label}</span>
          <span className="ml-2 text-xs text-ink-muted">{bot.token_set ? "токен задан" : "токен не задан"}</span>
          {bot.role === "admin" && (
            <span
              className={`ml-2 rounded-full px-2 py-0.5 text-xs font-medium whitespace-nowrap ${
                bot.notify_chat_set ? "bg-good-soft text-good" : "bg-bad-soft text-bad"
              }`}
            >
              {bot.notify_chat_set ? "получатель есть" : "напишите /start боту"}
            </span>
          )}
        </div>
        <div className="flex items-center gap-2">
          <StatusBadge active={bot.is_active} />
          <Button
            variant="secondary"
            disabled={busy}
            onClick={() => update.mutate({ is_active: !bot.is_active })}
          >
            {bot.is_active ? "Отключить" : "Включить"}
          </Button>
          <Button
            variant="danger"
            disabled={busy}
            onClick={() => {
              if (window.confirm(`Удалить бота «${label}»? Это необратимо.`)) remove.mutate();
            }}
          >
            Удалить
          </Button>
        </div>
      </div>

      {bot.role !== "admin" && (
        <>
          {editingPersona ? (
            <div className="flex flex-col gap-2">
              <Textarea
                value={persona}
                onChange={(e) => setPersona(e.target.value)}
                placeholder="Персона/стиль для рерайта"
                rows={4}
              />
              <div className="flex gap-2">
                <Button onClick={() => update.mutate({ persona_prompt: persona })} disabled={busy}>
                  Сохранить
                </Button>
                <Button
                  variant="secondary"
                  onClick={() => {
                    setPersona(bot.persona_prompt);
                    setEditingPersona(false);
                    setError(null);
                  }}
                  disabled={busy}
                >
                  Отмена
                </Button>
              </div>
            </div>
          ) : (
            <div className="flex items-start justify-between gap-3">
              <p className="text-sm text-ink-muted">
                {bot.persona_prompt || "Персона не задана."}
              </p>
              <button
                type="button"
                onClick={() => {
                  setPersona(bot.persona_prompt);
                  setEditingPersona(true);
                }}
                className="shrink-0 text-xs text-ink-muted underline decoration-dotted hover:text-ink"
              >
                Изменить персону
              </button>
            </div>
          )}
        </>
      )}

      {/* Свёрнуто: замена токена — редкая операция, постоянно открытое поле
          только шумит в списке. */}
      <details>
        <summary className="cursor-pointer select-none text-xs text-ink-muted hover:text-ink">
          Заменить токен
        </summary>
        <form
          className="mt-2 flex gap-2"
          onSubmit={(e) => {
            e.preventDefault();
            if (!newToken) return;
            setError(null);
            update.mutate({ bot_token: newToken });
          }}
        >
          <Input
            type="password"
            autoComplete="off"
            value={newToken}
            onChange={(e) => setNewToken(e.target.value)}
            placeholder="Новый токен от @BotFather"
            className="flex-1"
          />
          <Button type="submit" variant="secondary" disabled={busy || !newToken}>
            Заменить
          </Button>
        </form>
      </details>
      {error && <p className="text-xs text-bad">{error}</p>}
    </li>
  );
}

function StyleExtractorCard() {
  const [refs, setRefs] = useState("");
  const [suggestion, setSuggestion] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);

  const extract = useMutation({
    mutationFn: () => {
      const posts = refs.split(/\n\s*\n/).map((p) => p.trim()).filter(Boolean);
      return api.post<{ suggested_persona: string }>("/channel-bots/extract-style", {
        reference_posts: posts,
      });
    },
    onSuccess: (data) => {
      setError(null);
      setSuggestion(data.suggested_persona);
    },
    onError: (err) => {
      setSuggestion(null);
      setError(err instanceof ApiError ? err.message : "Не удалось выучить стиль");
    },
  });

  return (
    <Card>
      <h2 className="mb-1 text-sm font-semibold text-ink">Выучить стиль по постам</h2>
      <p className="mb-3 text-sm text-ink-muted">
        Вставьте несколько реальных постов канала (по одному, разделяя пустой строкой) —
        ИИ опишет его голос и предложит готовую персону. Скопируйте её в поле «Персона»
        нужного бота выше.
      </p>
      <form
        className="flex flex-col gap-2"
        onSubmit={(e) => {
          e.preventDefault();
          setError(null);
          extract.mutate();
        }}
      >
        <Textarea
          value={refs}
          onChange={(e) => setRefs(e.target.value)}
          placeholder={"Пост 1…\n\nПост 2…\n\nПост 3…"}
          rows={6}
        />
        <Button type="submit" disabled={extract.isPending || !refs.trim()} className="self-start">
          {extract.isPending ? "Анализирую…" : "Выучить стиль"}
        </Button>
      </form>
      {error && <p className="mt-2 text-sm text-bad">{error}</p>}
      {suggestion && (
        <div className="mt-3 flex flex-col gap-2">
          <span className="text-xs font-medium text-ink">Предлагаемая персона:</span>
          <p className="whitespace-pre-wrap rounded-lg bg-surface-2 p-3 text-sm text-ink">{suggestion}</p>
          <Button
            type="button"
            variant="secondary"
            className="self-start"
            onClick={() => navigator.clipboard?.writeText(suggestion)}
          >
            Скопировать
          </Button>
        </div>
      )}
    </Card>
  );
}

export function Bots() {
  const bots = useQuery(channelBotsQuery());
  const themes = useQuery(themesQuery());
  const themeNameById = new Map(themes.data?.map((theme) => [theme.id, theme.name]) ?? []);

  return (
    <div className="flex flex-col gap-6">
      <h1 className="text-xl font-semibold text-ink">Боты</h1>
      <p className="text-sm text-ink-muted">
        Боты — это «руки» системы: тематический бот публикует посты в каналы своей
        темы и пишет их в её стиле (персоне), admin-бот шлёт вам уведомления и
        статистику. Токены хранятся в панели — доступ к серверу для смены не нужен.
        Admin-боту после создания один раз напишите /start в личку в Telegram, иначе
        Telegram не даст ему написать вам первым.
      </p>
      <Callout>
        Новый или изменённый бот подхватывается автоматически в течение ~30 секунд,
        без перезапуска сервера.
      </Callout>

      <CreateBotForm />

      <StyleExtractorCard />

      <Card>
        <h2 className="mb-3 text-sm font-semibold text-ink">Все боты</h2>
        {bots.isLoading && <LoadingState />}
        {bots.error && <ErrorState message={bots.error.message} />}
        {bots.data && bots.data.length === 0 && <EmptyState message="Ботов пока нет — создайте первого выше." />}
        {bots.data && bots.data.length > 0 && (
          <ul className="flex flex-col divide-y divide-border">
            {bots.data.map((bot) => (
              <BotRow key={bot.id} bot={bot} themeName={bot.theme_id ? (themeNameById.get(bot.theme_id) ?? null) : null} />
            ))}
          </ul>
        )}
      </Card>
    </div>
  );
}
