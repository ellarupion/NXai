import { useState } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { api, ApiError } from "../api/client";
import { channelBotsQuery, themesQuery } from "../api/queries";
import {
  Button,
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

const CADENCE_FIELDS: Array<{ key: keyof Cadence; label: string }> = [
  { key: "posts_per_day_target", label: "Постов/день" },
  { key: "min_interval_minutes", label: "Мин. интервал, мин" },
  { key: "max_interval_minutes", label: "Макс. интервал, мин" },
  { key: "jitter_minutes", label: "Джиттер, мин" },
  { key: "quiet_hours_start", label: "Тихие часы с (по таймзоне проекта)" },
  { key: "quiet_hours_end", label: "Тихие часы до (по таймзоне проекта)" },
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
            {CADENCE_FIELDS.map(({ key, label }) => (
              <label key={key} className="flex flex-col gap-1 text-xs text-ink-muted">
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
  const [error, setError] = useState<string | null>(null);

  const update = useMutation({
    mutationFn: (payload: Partial<Pick<ChannelBot, "is_active">> & { bot_token?: string }) =>
      api.put<ChannelBot>(`/channel-bots/${bot.id}`, payload),
    onSuccess: () => {
      setError(null);
      setNewToken("");
      queryClient.invalidateQueries({ queryKey: ["channel-bots"] });
    },
    onError: (err) => setError(err instanceof ApiError ? err.message : "Не удалось обновить бота"),
  });

  return (
    <li className="flex flex-col gap-2 py-3 first:pt-0 last:pb-0">
      <div className="flex items-center justify-between gap-2">
        <div>
          <span className="font-medium text-ink">
            {bot.role === "admin" ? "Admin-бот" : (themeName ?? "— без темы —")}
          </span>
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
            disabled={update.isPending}
            onClick={() => update.mutate({ is_active: !bot.is_active })}
          >
            {bot.is_active ? "Отключить" : "Включить"}
          </Button>
        </div>
      </div>
      {bot.persona_prompt && <p className="text-sm text-ink-muted">{bot.persona_prompt}</p>}
      <form
        className="flex gap-2"
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
          placeholder="Заменить токен"
          className="flex-1"
        />
        <Button type="submit" variant="secondary" disabled={update.isPending || !newToken}>
          Заменить
        </Button>
      </form>
      {error && <p className="text-xs text-bad">{error}</p>}
    </li>
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
        Токен каждого бота хранится в базе, не в .env сервера — ротация и добавление
        новых тематических ботов не требует доступа к серверу. Admin-боту после
        создания нужно один раз написать /start в личку в Telegram — иначе Bot API
        не даст боту написать первым, и уведомления будет некуда слать.
      </p>

      <CreateBotForm />

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
