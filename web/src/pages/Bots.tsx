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
import { PersonaEditor, type PersonaValue } from "../components/PersonaEditor";
import type { BotRole, Cadence, ChannelBot, PersonaConfig } from "../types";

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
        <div className="flex flex-col gap-2 sm:flex-row">
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

const TONE_LABELS: Record<string, string> = {
  brash: "дерзкий блогер",
  expert: "спокойный эксперт",
  friendly: "дружеский",
  news: "новостной",
  custom: "свой тон",
};

function personaSummary(bot: ChannelBot): string {
  const c = bot.persona_config ?? {};
  const bits: string[] = [];
  if (c.tone) bits.push(TONE_LABELS[c.tone] ?? c.tone);
  if (c.length === "shorter") bits.push("короче исходника");
  if (c.length === "longer") bits.push("развёрнутее");
  if (c.emoji === "none") bits.push("без эмодзи");
  if (c.emoji === "many") bits.push("много эмодзи");
  if ((c.examples_good ?? []).length > 0) bits.push(`примеров: ${(c.examples_good ?? []).length}`);
  const head = bits.length > 0 ? `Стиль: ${bits.join(", ")}. ` : "";
  return (head + (bot.persona_prompt || "")).trim();
}

/* Автоправила дообучения: причина отклонения -> как компенсировать в персоне.
   apply возвращает патч конфига/особых указаний; null у wrong_tone — тону нет
   универсальной правки, зовём в конструктор. */
const REJECTION_FIXES: Record<
  string,
  { fix: ((c: PersonaConfig, custom: string) => { config: PersonaConfig; custom: string }) | null; hint: string }
> = {
  too_long: {
    hint: "выставит длину «короче исходника»",
    fix: (c, custom) => ({ config: { ...c, length: "shorter" }, custom }),
  },
  officialese: {
    hint: "добавит правило против канцелярита",
    fix: (c, custom) => ({
      config: c,
      custom: appendRule(custom, "Никакого канцелярита — пиши живым разговорным языком."),
    }),
  },
  watery: {
    hint: "добавит правило против воды",
    fix: (c, custom) => ({
      config: c,
      custom: appendRule(custom, "Без воды: каждое предложение несёт смысл, пустые фразы вырезай."),
    }),
  },
  lost_point: {
    hint: "снизит смелость рерайта — ближе к сути исходника",
    fix: (c, custom) => ({ config: { ...c, boldness: 2 }, custom }),
  },
  ad: {
    hint: "добавит правило против промо-оборотов",
    fix: (c, custom) => ({
      config: c,
      custom: appendRule(custom, "Не превращай пост в рекламу: промо-обороты и призывы «подписывайся/покупай» убирай."),
    }),
  },
  wrong_tone: { hint: "тон правится в конструкторе персоны", fix: null },
};

function appendRule(custom: string, rule: string): string {
  if (custom.includes(rule)) return custom;
  return custom ? `${custom}\n${rule}` : rule;
}

function RejectionSignals({ bot, onApply }: { bot: ChannelBot; onApply: (v: { config: PersonaConfig; custom: string }) => void }) {
  const stats = useQuery({
    queryKey: ["rejection-stats", bot.id],
    queryFn: () =>
      api.get<{ days: number; stats: Array<{ reason: string; label: string; count: number }> }>(
        `/channel-bots/${bot.id}/rejection-stats`,
      ),
  });
  if (!stats.data || stats.data.stats.length === 0) return null;
  return (
    <div className="rounded-lg bg-surface-2 p-3">
      <p className="mb-2 text-xs font-medium text-ink">
        Сигналы с Проверки за {stats.data.days} дней — почему отклоняли посты:
      </p>
      <ul className="flex flex-col gap-1.5">
        {stats.data.stats.map((st) => {
          const fixer = REJECTION_FIXES[st.reason];
          return (
            <li key={st.reason} className="flex items-center justify-between gap-2 text-xs text-ink-muted">
              <span>
                {st.label} — ×{st.count}
              </span>
              {fixer?.fix ? (
                <button
                  type="button"
                  title={fixer.hint}
                  onClick={() =>
                    onApply(fixer.fix!(bot.persona_config ?? {}, bot.persona_prompt))
                  }
                  className="shrink-0 rounded-full bg-accent-soft px-2 py-0.5 font-medium text-accent hover:opacity-80"
                >
                  Добавить правило
                </button>
              ) : (
                <span className="shrink-0 italic">{fixer?.hint}</span>
              )}
            </li>
          );
        })}
      </ul>
    </div>
  );
}

function BotRow({ bot, themeName }: { bot: ChannelBot; themeName: string | null }) {
  const queryClient = useQueryClient();
  const [newToken, setNewToken] = useState("");
  const [editingPersona, setEditingPersona] = useState(false);
  const [persona, setPersona] = useState<PersonaValue>({
    config: bot.persona_config ?? {},
    custom: bot.persona_prompt,
  });
  const [error, setError] = useState<string | null>(null);
  const [checkResult, setCheckResult] = useState<{ ok: boolean; detail: string } | null>(null);

  const check = useMutation({
    mutationFn: () => api.post<{ ok: boolean; detail: string }>(`/channel-bots/${bot.id}/check`),
    onSuccess: (data) => setCheckResult(data),
    onError: (err) =>
      setCheckResult({
        ok: false,
        detail: err instanceof ApiError ? err.message : "Не удалось выполнить проверку",
      }),
  });

  const invalidate = () => queryClient.invalidateQueries({ queryKey: ["channel-bots"] });

  const update = useMutation({
    mutationFn: (
      payload: Partial<Pick<ChannelBot, "is_active" | "persona_prompt" | "persona_config">> & {
        bot_token?: string;
      },
    ) => api.put<ChannelBot>(`/channel-bots/${bot.id}`, payload),
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
      <div className="flex flex-wrap items-center justify-between gap-2">
        <div className="min-w-0">
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
        <div className="flex flex-wrap items-center gap-2">
          <StatusBadge active={bot.is_active} />
          <Button
            variant="secondary"
            disabled={check.isPending}
            onClick={() => check.mutate()}
            title="Живая проверка токена через Telegram (getMe)"
          >
            {check.isPending ? "Проверяю…" : "Проверить связь"}
          </Button>
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

      {checkResult && (
        <p className={`text-xs ${checkResult.ok ? "text-good" : "text-bad"}`}>
          {checkResult.detail}
        </p>
      )}

      {bot.role !== "admin" && (
        <>
          <RejectionSignals
            bot={bot}
            onApply={(v) => update.mutate({ persona_prompt: v.custom, persona_config: v.config })}
          />
          {editingPersona ? (
            <div className="flex flex-col gap-2 rounded-lg border border-border p-3">
              <h3 className="text-xs font-semibold text-ink">Конструктор персоны</h3>
              <PersonaEditor value={persona} onChange={setPersona} botId={bot.id} />
              <div className="flex gap-2">
                <Button
                  onClick={() =>
                    update.mutate({ persona_prompt: persona.custom, persona_config: persona.config })
                  }
                  disabled={busy}
                >
                  Сохранить персону
                </Button>
                <Button
                  variant="secondary"
                  onClick={() => {
                    setPersona({ config: bot.persona_config ?? {}, custom: bot.persona_prompt });
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
                {personaSummary(bot) || "Персона не задана — настройте стиль, чтобы посты писались вашим голосом."}
              </p>
              <button
                type="button"
                onClick={() => {
                  setPersona({ config: bot.persona_config ?? {}, custom: bot.persona_prompt });
                  setEditingPersona(true);
                }}
                className="shrink-0 text-xs text-ink-muted underline decoration-dotted hover:text-ink"
              >
                Настроить персону
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
