import { useState } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { Navigate, useNavigate, useParams } from "react-router-dom";
import { api, ApiError } from "../api/client";
import {
  channelBotsQuery,
  poolPostsQuery,
  sourceChannelsQuery,
  targetChannelsQuery,
  telethonSessionsQuery,
  themeHealthQuery,
  themeQuery,
  themesQuery,
} from "../api/queries";
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
import { TrendsCard } from "./Dashboard";
import { plural } from "../lib/plural";
import type {
  Cadence,
  ChannelBot,
  CrosspostConfig,
  PersonaConfig,
  PoolPost,
  SourceChannel,
  TargetChannel,
  Theme,
  ThemeHealthStage,
  ThemeHealthStatus,
} from "../types";

/* Единый рабочий стол темы (вместо десятка отдельных страниц): сверху вкладки
   с названиями тем + «+ Новая тема», внутри — вообще всё про выбранную тему:
   конвейер, режим работы, источники (с назначением аккаунта-читалки),
   бот (персона/расписание/редактор/медиа/автопубликация), целевые каналы,
   запас постов. Реестр аккаунтов-читалок и глобальные ключи остаются на
   своих страницах («Аккаунты», «Настройки») — они не привязаны к одной теме. */

// ===== Вкладки тем =====

function ThemeTabBar({ themes, activeId }: { themes: Theme[]; activeId: string | null }) {
  const navigate = useNavigate();
  const queryClient = useQueryClient();
  const [creating, setCreating] = useState(false);
  const [name, setName] = useState("");
  const [error, setError] = useState<string | null>(null);

  const create = useMutation({
    mutationFn: () => api.post<Theme>("/themes", { name, default_style_prompt: "" }),
    onSuccess: (data) => {
      setName("");
      setCreating(false);
      setError(null);
      queryClient.invalidateQueries({ queryKey: ["themes"] });
      navigate(`/themes/${data.id}`);
    },
    onError: (err) => setError(err instanceof ApiError ? err.message : "Не удалось создать тему"),
  });

  return (
    <div className="flex flex-col gap-2">
      <div className="flex flex-nowrap items-center gap-2 overflow-x-auto pb-1">
        {themes.map((t) => (
          <button
            key={t.id}
            type="button"
            onClick={() => navigate(`/themes/${t.id}`)}
            className={[
              "flex shrink-0 items-center gap-1.5 rounded-full px-3 py-1.5 text-sm font-medium whitespace-nowrap transition-colors",
              t.id === activeId
                ? "bg-accent text-accent-ink"
                : "bg-surface-2 text-ink-muted hover:text-ink",
            ].join(" ")}
          >
            <span className={`h-1.5 w-1.5 shrink-0 rounded-full ${t.is_active ? "bg-good" : "bg-ink-muted"}`} />
            {t.name}
          </button>
        ))}
        <button
          type="button"
          onClick={() => setCreating((v) => !v)}
          className="shrink-0 rounded-full border border-dashed border-border px-3 py-1.5 text-sm text-ink-muted hover:border-accent hover:text-accent"
        >
          + Новая тема
        </button>
      </div>
      {creating && (
        <form
          className="flex flex-wrap gap-2"
          onSubmit={(e) => {
            e.preventDefault();
            if (name.trim()) create.mutate();
          }}
        >
          <Input
            value={name}
            onChange={(e) => setName(e.target.value)}
            placeholder="Название темы"
            autoFocus
            className="max-w-xs flex-1"
          />
          <Button type="submit" disabled={create.isPending || !name.trim()}>
            Создать
          </Button>
          <Button type="button" variant="secondary" onClick={() => setCreating(false)}>
            Отмена
          </Button>
        </form>
      )}
      {error && <p className="text-sm text-bad">{error}</p>}
    </div>
  );
}

// ===== Заголовок темы: имя, активность, запасной стиль =====

function ThemeHeader({ theme }: { theme: Theme }) {
  const queryClient = useQueryClient();
  const [editing, setEditing] = useState(false);
  const [name, setName] = useState(theme.name);
  const [stylePrompt, setStylePrompt] = useState(theme.default_style_prompt);
  const [error, setError] = useState<string | null>(null);

  const update = useMutation({
    mutationFn: (payload: Partial<Theme>) => api.put<Theme>(`/themes/${theme.id}`, payload),
    onSuccess: () => {
      setError(null);
      setEditing(false);
      queryClient.invalidateQueries({ queryKey: ["themes"] });
    },
    onError: (err) => setError(err instanceof ApiError ? err.message : "Не удалось сохранить"),
  });

  return (
    <div className="flex flex-col gap-2">
      <div className="flex flex-wrap items-center justify-between gap-3">
        <div className="flex items-center gap-3">
          <h1 className="text-xl font-semibold text-ink">{theme.name}</h1>
          <StatusBadge active={theme.is_active} />
        </div>
        <div className="flex flex-wrap items-center gap-3">
          <button
            type="button"
            onClick={() => setEditing((v) => !v)}
            className="text-xs text-ink-muted underline decoration-dotted hover:text-ink"
          >
            {editing ? "Скрыть" : "Переименовать / стиль"}
          </button>
          <button
            type="button"
            onClick={() => update.mutate({ is_active: !theme.is_active })}
            disabled={update.isPending}
            className="text-xs text-ink-muted underline decoration-dotted hover:text-ink"
          >
            {theme.is_active ? "Выключить тему" : "Включить тему"}
          </button>
        </div>
      </div>
      {editing && (
        <Card className="flex flex-col gap-2">
          <Input value={name} onChange={(e) => setName(e.target.value)} placeholder="Название" />
          <Textarea
            value={stylePrompt}
            onChange={(e) => setStylePrompt(e.target.value)}
            placeholder="Запасной стиль переписывания — используется, пока персона бота пуста"
            rows={3}
          />
          <div className="flex gap-2">
            <Button
              onClick={() => update.mutate({ name, default_style_prompt: stylePrompt })}
              disabled={update.isPending || !name.trim()}
            >
              Сохранить
            </Button>
            <Button variant="secondary" onClick={() => setEditing(false)} disabled={update.isPending}>
              Отмена
            </Button>
          </div>
          {error && <p className="text-sm text-bad">{error}</p>}
        </Card>
      )}
    </div>
  );
}

// ===== Конвейер =====

const STAGE_DOT: Record<ThemeHealthStatus, string> = {
  ok: "bg-good",
  warn: "bg-[#e5b567]",
  crit: "bg-bad",
};

function PipelineStage({ stage }: { stage: ThemeHealthStage }) {
  return (
    <div className="flex min-w-0 flex-1 flex-col gap-1 rounded-lg bg-surface-2 p-3">
      <div className="flex items-center gap-2">
        <span className={`h-2.5 w-2.5 shrink-0 rounded-full ${STAGE_DOT[stage.status]}`} />
        <span className="truncate text-xs font-semibold text-ink">{stage.label}</span>
      </div>
      <span className="text-xs text-ink-muted">{stage.value}</span>
      {stage.hint && <span className="text-xs text-ink-muted italic">{stage.hint}</span>}
    </div>
  );
}

function Toggle({
  label,
  hint,
  checked,
  onChange,
  disabled,
}: {
  label: string;
  hint: string;
  checked: boolean;
  onChange: (value: boolean) => void;
  disabled: boolean;
}) {
  return (
    <label className="flex items-start gap-3">
      <input
        type="checkbox"
        checked={checked}
        onChange={(e) => onChange(e.target.checked)}
        disabled={disabled}
        className="mt-0.5"
      />
      <span>
        <span className="block text-sm font-medium text-ink">{label}</span>
        <span className="block text-xs text-ink-muted">{hint}</span>
      </span>
    </label>
  );
}

// ===== Источники =====

function formatScanned(iso: string | null): string {
  if (!iso) return "ждёт первого чтения (начнётся само в течение минуты)";
  const then = new Date(iso).getTime();
  const mins = Math.floor((Date.now() - then) / 60000);
  if (mins < 1) return "прочитан только что";
  if (mins < 60) return `прочитан ${mins} ${plural(mins, "минуту", "минуты", "минут")} назад`;
  const hours = Math.floor(mins / 60);
  if (hours < 24) return `прочитан ${hours} ${plural(hours, "час", "часа", "часов")} назад`;
  const days = Math.floor(hours / 24);
  return `прочитан ${days} ${plural(days, "день", "дня", "дней")} назад`;
}

function TrustScoreBadge({ value }: { value: number }) {
  const styles =
    value >= 1.0 ? "bg-good-soft text-good" : value >= 0.5 ? "bg-surface-2 text-ink-muted" : "bg-bad-soft text-bad";
  return (
    <span
      title="Надёжность источника: растёт сама, когда его посты доходят до публикации, и падает на повторах и отклонённых. Влияет на шанс попадания постов в отбор."
      className={`rounded-full px-2 py-0.5 text-xs font-medium whitespace-nowrap ${styles}`}
    >
      надёжность {value.toFixed(2)}
    </span>
  );
}

function AssignSessionCell({ channel }: { channel: SourceChannel }) {
  const queryClient = useQueryClient();
  const sessions = useQuery(telethonSessionsQuery());
  const [error, setError] = useState<string | null>(null);

  const assign = useMutation({
    mutationFn: (sessionId: string | null) =>
      api.put<SourceChannel>(`/source-channels/${channel.id}/ingest-session`, {
        ingest_session_id: sessionId,
      }),
    onSuccess: () => {
      setError(null);
      queryClient.invalidateQueries({ queryKey: ["source-channels"] });
    },
    onError: (err) => setError(err instanceof ApiError ? err.message : "Не удалось назначить читалку"),
  });

  return (
    <div className="flex flex-col items-stretch gap-1 sm:items-end">
      <Select
        value={channel.ingest_session_id ?? ""}
        disabled={assign.isPending || sessions.isLoading}
        onChange={(e) => assign.mutate(e.target.value === "" ? null : e.target.value)}
        className="w-full sm:w-auto sm:min-w-[10rem]"
      >
        <option value="">— читалка не назначена —</option>
        {sessions.data?.map((s) => (
          <option key={s.id} value={s.id}>
            {s.label}
          </option>
        ))}
      </Select>
      {error && <p className="text-xs text-bad">{error}</p>}
    </div>
  );
}

function SourceRow({ channel }: { channel: SourceChannel }) {
  const queryClient = useQueryClient();
  const [error, setError] = useState<string | null>(null);
  const invalidate = () => queryClient.invalidateQueries({ queryKey: ["source-channels"] });

  const setActive = useMutation({
    mutationFn: (isActive: boolean) =>
      api.put<SourceChannel>(`/source-channels/${channel.id}/active`, { is_active: isActive }),
    onSuccess: () => {
      setError(null);
      invalidate();
    },
    onError: (err) => setError(err instanceof ApiError ? err.message : "Не удалось изменить"),
  });

  const detach = useMutation({
    mutationFn: () => api.put<SourceChannel>(`/source-channels/${channel.id}/theme`, { theme_id: null }),
    onSuccess: () => {
      setError(null);
      invalidate();
    },
    onError: (err) => setError(err instanceof ApiError ? err.message : "Не удалось открепить"),
  });

  const remove = useMutation({
    mutationFn: () => api.delete(`/source-channels/${channel.id}`),
    onSuccess: () => {
      setError(null);
      invalidate();
    },
    onError: (err) => setError(err instanceof ApiError ? err.message : "Не удалось удалить"),
  });

  const busy = setActive.isPending || detach.isPending || remove.isPending;

  return (
    <li className="flex flex-col gap-2 py-3 first:pt-0 last:pb-0">
      <div className="flex flex-col gap-2 sm:flex-row sm:items-center sm:justify-between sm:gap-3">
        <div className="min-w-0">
          <div className="flex items-center gap-2">
            <p className="truncate font-medium text-ink">{channel.title}</p>
            <TrustScoreBadge value={channel.trust_score} />
            {!channel.is_active && (
              <span className="rounded-full bg-surface-2 px-2 py-0.5 text-xs text-ink-muted">выключен</span>
            )}
          </div>
          <p className="truncate text-xs text-ink-muted">
            {channel.tg_username ? `@${channel.tg_username}` : (channel.tg_chat_id ?? "—")} ·{" "}
            {channel.candidate_count} {plural(channel.candidate_count, "пост", "поста", "постов")} ·{" "}
            {formatScanned(channel.last_scanned_at)}
          </p>
        </div>
        <AssignSessionCell channel={channel} />
      </div>
      <div className="flex flex-wrap gap-3">
        <button
          type="button"
          onClick={() => setActive.mutate(!channel.is_active)}
          disabled={busy}
          className="text-xs text-ink-muted underline decoration-dotted hover:text-ink"
        >
          {channel.is_active ? "Выключить" : "Включить"}
        </button>
        <button
          type="button"
          onClick={() => detach.mutate()}
          disabled={busy}
          className="text-xs text-ink-muted underline decoration-dotted hover:text-ink"
          title="Источник останется в системе, но перестанет относиться к этой теме"
        >
          Открепить от темы
        </button>
        <button
          type="button"
          onClick={() => {
            if (
              window.confirm(
                `Удалить источник «${channel.title}» вместе со всеми его постами? Это необратимо. Чтобы просто убрать из ротации, используйте «Выключить».`,
              )
            ) {
              remove.mutate();
            }
          }}
          disabled={busy}
          className="text-xs text-bad underline decoration-dotted hover:opacity-80"
        >
          Удалить
        </button>
      </div>
      {error && <p className="text-xs text-bad">{error}</p>}
    </li>
  );
}

function AddSourceForm({ themeId }: { themeId: string }) {
  const queryClient = useQueryClient();
  const sessions = useQuery(telethonSessionsQuery());
  const [usernameOrLink, setUsernameOrLink] = useState("");
  const [ingestSessionId, setIngestSessionId] = useState("");
  const [error, setError] = useState<string | null>(null);

  const create = useMutation({
    mutationFn: () =>
      api.post<SourceChannel>("/source-channels", {
        username_or_link: usernameOrLink,
        ingest_session_id: ingestSessionId,
        theme_id: themeId,
      }),
    onSuccess: () => {
      setUsernameOrLink("");
      setError(null);
      queryClient.invalidateQueries({ queryKey: ["source-channels"] });
    },
    onError: (err) => setError(err instanceof ApiError ? err.message : "Не удалось добавить источник"),
  });

  const noSessions = sessions.data && sessions.data.length === 0;

  return (
    <div className="flex flex-col gap-2">
      {noSessions && (
        <p className="text-sm text-bad">
          Сначала заведите хотя бы один аккаунт-читалку во вкладке «Аккаунты» — им и будет
          прочитан этот канал.
        </p>
      )}
      <form
        className="flex flex-col gap-2 sm:flex-row"
        onSubmit={(e) => {
          e.preventDefault();
          setError(null);
          create.mutate();
        }}
      >
        <Input
          value={usernameOrLink}
          onChange={(e) => setUsernameOrLink(e.target.value)}
          placeholder="@username или t.me/ссылка чужого канала"
          required
          className="flex-1"
        />
        <Select
          value={ingestSessionId}
          onChange={(e) => setIngestSessionId(e.target.value)}
          required
          className="sm:w-56"
        >
          <option value="">— аккаунт-читалка —</option>
          {sessions.data?.map((s) => (
            <option key={s.id} value={s.id}>
              {s.label}
            </option>
          ))}
        </Select>
        <Button type="submit" disabled={create.isPending || Boolean(noSessions)}>
          Добавить
        </Button>
      </form>
      {error && <p className="text-sm text-bad">{error}</p>}
    </div>
  );
}

function AttachExistingSourceForm({ themeId }: { themeId: string }) {
  const queryClient = useQueryClient();
  const unassigned = useQuery(sourceChannelsQuery(true));
  const [selected, setSelected] = useState("");
  const [error, setError] = useState<string | null>(null);

  const attach = useMutation({
    mutationFn: () => api.put<SourceChannel>(`/source-channels/${selected}/theme`, { theme_id: themeId }),
    onSuccess: () => {
      setSelected("");
      setError(null);
      queryClient.invalidateQueries({ queryKey: ["source-channels"] });
    },
    onError: (err) => setError(err instanceof ApiError ? err.message : "Не удалось прикрепить"),
  });

  if (!unassigned.data || unassigned.data.length === 0) return null;

  return (
    <form
      className="flex flex-wrap gap-2"
      onSubmit={(e) => {
        e.preventDefault();
        if (selected) attach.mutate();
      }}
    >
      <Select value={selected} onChange={(e) => setSelected(e.target.value)} className="flex-1">
        <option value="">— прикрепить существующий источник без темы —</option>
        {unassigned.data.map((s) => (
          <option key={s.id} value={s.id}>
            {s.title}
          </option>
        ))}
      </Select>
      <Button type="submit" variant="secondary" disabled={attach.isPending || !selected}>
        Прикрепить
      </Button>
      {error && <p className="text-sm text-bad">{error}</p>}
    </form>
  );
}

// ===== Бот темы =====

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

function CreateThemeBotForm({ themeId }: { themeId: string }) {
  const queryClient = useQueryClient();
  const [botToken, setBotToken] = useState("");
  const [personaPrompt, setPersonaPrompt] = useState("");
  const [cadence, setCadence] = useState<Cadence>(DEFAULT_CADENCE);
  const [error, setError] = useState<string | null>(null);

  const create = useMutation({
    mutationFn: () =>
      api.post<ChannelBot>("/channel-bots", {
        role: "theme",
        theme_id: themeId,
        bot_token: botToken,
        persona_prompt: personaPrompt,
        cadence,
      }),
    onSuccess: () => {
      setBotToken("");
      setPersonaPrompt("");
      setCadence(DEFAULT_CADENCE);
      setError(null);
      queryClient.invalidateQueries({ queryKey: ["channel-bots"] });
    },
    onError: (err) => setError(err instanceof ApiError ? err.message : "Не удалось создать бота"),
  });

  return (
    <form
      className="flex flex-col gap-2"
      onSubmit={(e) => {
        e.preventDefault();
        setError(null);
        create.mutate();
      }}
    >
      <p className="text-sm text-ink-muted">
        У темы нет бота — без него некому публиковать в канал и переписывать посты.
        Создайте бота у @BotFather и вставьте его токен.
      </p>
      <Input
        type="password"
        autoComplete="off"
        value={botToken}
        onChange={(e) => setBotToken(e.target.value)}
        placeholder="Токен от @BotFather"
        required
      />
      <Textarea
        value={personaPrompt}
        onChange={(e) => setPersonaPrompt(e.target.value)}
        placeholder="Персона/стиль (можно детально настроить конструктором после создания)"
        rows={2}
      />
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
      <Button type="submit" disabled={create.isPending} className="self-start">
        Создать бота
      </Button>
      {error && <p className="text-sm text-bad">{error}</p>}
    </form>
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
   fix возвращает патч конфига/особых указаний; null у wrong_tone — тону нет
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

function RejectionSignals({
  bot,
  onApply,
}: {
  bot: ChannelBot;
  onApply: (v: { config: PersonaConfig; custom: string }) => void;
}) {
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
                  onClick={() => onApply(fixer.fix!(bot.persona_config ?? {}, bot.persona_prompt))}
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

function CadenceEditor({
  bot,
  busy,
  onSave,
}: {
  bot: ChannelBot;
  busy: boolean;
  onSave: (cadence: Cadence) => void;
}) {
  const [cadence, setCadence] = useState<Cadence>(bot.cadence);
  const dirty = JSON.stringify(cadence) !== JSON.stringify(bot.cadence);

  return (
    <details className="rounded-lg bg-surface-2 p-3">
      <summary className="cursor-pointer select-none text-xs font-medium text-ink">Расписание публикаций</summary>
      <div className="mt-2 flex flex-col gap-2">
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
        {dirty && (
          <Button variant="secondary" className="self-start" disabled={busy} onClick={() => onSave(cadence)}>
            Сохранить расписание
          </Button>
        )}
      </div>
    </details>
  );
}

function ThemeBotPanel({ bot }: { bot: ChannelBot }) {
  const queryClient = useQueryClient();
  const [newToken, setNewToken] = useState("");
  const [editingPersona, setEditingPersona] = useState(false);
  const [persona, setPersona] = useState<PersonaValue>({
    config: bot.persona_config ?? {},
    custom: bot.persona_prompt,
  });
  const [editorId, setEditorId] = useState(bot.editor_chat_id ? String(bot.editor_chat_id) : "");
  const [error, setError] = useState<string | null>(null);
  const [checkResult, setCheckResult] = useState<{ ok: boolean; detail: string } | null>(null);

  const invalidate = () => queryClient.invalidateQueries({ queryKey: ["channel-bots"] });

  const check = useMutation({
    mutationFn: () => api.post<{ ok: boolean; detail: string }>(`/channel-bots/${bot.id}/check`),
    onSuccess: (data) => setCheckResult(data),
    onError: (err) =>
      setCheckResult({
        ok: false,
        detail: err instanceof ApiError ? err.message : "Не удалось выполнить проверку",
      }),
  });

  const update = useMutation({
    mutationFn: (
      payload: Partial<
        Pick<
          ChannelBot,
          "is_active" | "persona_prompt" | "persona_config" | "use_media" | "autopublish_enabled" | "cadence"
        >
      > & { bot_token?: string; editor_chat_id?: number },
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

  return (
    <div className="flex flex-col gap-3">
      <div className="flex flex-wrap items-center justify-between gap-2">
        <div className="flex items-center gap-2">
          <StatusBadge active={bot.is_active} />
          <span className="text-xs text-ink-muted">{bot.token_set ? "токен задан" : "токен не задан"}</span>
        </div>
        <div className="flex flex-wrap items-center gap-2">
          <Button
            variant="secondary"
            disabled={check.isPending}
            onClick={() => check.mutate()}
            title="Живая проверка токена через Telegram (getMe)"
          >
            {check.isPending ? "Проверяю…" : "Проверить связь"}
          </Button>
          <Button variant="secondary" disabled={busy} onClick={() => update.mutate({ is_active: !bot.is_active })}>
            {bot.is_active ? "Отключить" : "Включить"}
          </Button>
          <Button
            variant="danger"
            disabled={busy}
            onClick={() => {
              if (window.confirm("Удалить бота темы? Это необратимо.")) remove.mutate();
            }}
          >
            Удалить
          </Button>
        </div>
      </div>

      {checkResult && <p className={`text-xs ${checkResult.ok ? "text-good" : "text-bad"}`}>{checkResult.detail}</p>}

      <div className="flex flex-col gap-2 rounded-lg bg-surface-2 p-3">
        <label
          className="flex flex-col gap-1 text-xs text-ink-muted"
          title="Бот будет присылать сюда готовые посты с кнопками Одобрить / Поправить / Отклонить. Чтобы узнать ID, редактор должен написать боту /start — бот ответит числом."
        >
          ID редактора (проверка постов в Telegram)
          <div className="flex flex-wrap gap-2">
            <Input
              type="number"
              value={editorId}
              onChange={(e) => setEditorId(e.target.value)}
              placeholder="Редактор пишет боту /start и получает свой ID"
              className="flex-1"
            />
            {editorId !== (bot.editor_chat_id ? String(bot.editor_chat_id) : "") && (
              <Button
                variant="secondary"
                disabled={busy}
                onClick={() => update.mutate({ editor_chat_id: Number(editorId) || 0 })}
              >
                Сохранить
              </Button>
            )}
          </div>
          <span>
            {bot.editor_chat_id
              ? "Готовые посты уходят редактору в Telegram; правки редактора бот запоминает в личности."
              : "Не задан — посты ждут одобрения только в веб-«Проверке»."}
          </span>
        </label>
        <label
          className="flex items-center gap-2 text-xs text-ink-muted"
          title="Бот прикладывает фото исходного поста. Рерайт при этом ужимается под лимит подписи Telegram к фото (1024 символа)."
        >
          <input
            type="checkbox"
            checked={bot.use_media}
            disabled={busy}
            onChange={(e) => update.mutate({ use_media: e.target.checked })}
          />
          Брать медиа из исходного поста
        </label>
        <label
          className="flex items-center gap-2 text-xs text-ink-muted"
          title="Выключено — бот только готовит посты и шлёт их редактору, сам в канал ничего не ставит (и антиреклама не перекрывает). Включайте, когда рерайт устроит."
        >
          <input
            type="checkbox"
            checked={bot.autopublish_enabled}
            disabled={busy}
            onChange={(e) => update.mutate({ autopublish_enabled: e.target.checked })}
          />
          Автопубликация в канал{!bot.autopublish_enabled && " (выключена — бот сам ничего не постит)"}
        </label>
      </div>

      <CadenceEditor bot={bot} busy={busy} onSave={(cadence) => update.mutate({ cadence })} />

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
              onClick={() => update.mutate({ persona_prompt: persona.custom, persona_config: persona.config })}
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
    </div>
  );
}

// ===== Целевые каналы =====

function CrosspostEditor({ targetChannel }: { targetChannel: TargetChannel }) {
  const queryClient = useQueryClient();
  const [config, setConfig] = useState<CrosspostConfig>(targetChannel.crosspost ?? {});
  const [error, setError] = useState<string | null>(null);

  const save = useMutation({
    mutationFn: (crosspost: CrosspostConfig) =>
      api.put<TargetChannel>(`/target-channels/${targetChannel.id}/crosspost`, { crosspost }),
    onSuccess: () => {
      setError(null);
      queryClient.invalidateQueries({ queryKey: ["target-channels"] });
    },
    onError: (err) => setError(err instanceof ApiError ? err.message : "Не удалось сохранить"),
  });

  const vk = config.vk ?? {};
  const max = config.max ?? {};

  return (
    <details className="text-xs text-ink-muted">
      <summary className="cursor-pointer select-none">Кросспост в VK / MAX</summary>
      <div className="mt-2 flex flex-col gap-3">
        <div className="flex flex-col gap-1">
          <label className="flex items-center gap-2 text-ink">
            <input
              type="checkbox"
              checked={Boolean(vk.enabled)}
              onChange={(e) => setConfig({ ...config, vk: { ...vk, enabled: e.target.checked } })}
            />
            <span>VK</span>
          </label>
          <Input
            value={vk.access_token ?? ""}
            onChange={(e) => setConfig({ ...config, vk: { ...vk, access_token: e.target.value } })}
            placeholder="VK access_token сообщества"
          />
          <Input
            value={vk.owner_id ?? ""}
            onChange={(e) => setConfig({ ...config, vk: { ...vk, owner_id: e.target.value } })}
            placeholder="owner_id (со знаком минус для сообщества, напр. -12345)"
          />
        </div>
        <div className="flex flex-col gap-1">
          <label className="flex items-center gap-2 text-ink">
            <input
              type="checkbox"
              checked={Boolean(max.enabled)}
              onChange={(e) => setConfig({ ...config, max: { ...max, enabled: e.target.checked } })}
            />
            <span>MAX</span>
          </label>
          <Input
            value={max.access_token ?? ""}
            onChange={(e) => setConfig({ ...config, max: { ...max, access_token: e.target.value } })}
            placeholder="MAX bot access_token"
          />
          <Input
            value={max.chat_id ?? ""}
            onChange={(e) => setConfig({ ...config, max: { ...max, chat_id: e.target.value } })}
            placeholder="MAX chat_id канала"
          />
        </div>
        <Button
          type="button"
          variant="secondary"
          className="self-start"
          disabled={save.isPending}
          onClick={() => save.mutate(config)}
        >
          Сохранить кросспост
        </Button>
        {error && <p className="text-bad">{error}</p>}
      </div>
    </details>
  );
}

function CreateTargetChannelForm({ themeId }: { themeId: string }) {
  const queryClient = useQueryClient();
  const [chatIdOrUsername, setChatIdOrUsername] = useState("");
  const [signature, setSignature] = useState("");
  const [error, setError] = useState<string | null>(null);

  const create = useMutation({
    mutationFn: () =>
      api.post<TargetChannel>("/target-channels", {
        theme_id: themeId,
        chat_id_or_username: chatIdOrUsername,
        signature,
      }),
    onSuccess: () => {
      setChatIdOrUsername("");
      setSignature("");
      setError(null);
      queryClient.invalidateQueries({ queryKey: ["target-channels"] });
    },
    onError: (err) => setError(err instanceof ApiError ? err.message : "Не удалось добавить канал"),
  });

  return (
    <form
      className="flex flex-col gap-2"
      onSubmit={(e) => {
        e.preventDefault();
        setError(null);
        create.mutate();
      }}
    >
      <p className="text-sm text-ink-muted">
        Бот темы должен быть уже добавлен в канал админом — панель проверяет это через Bot API
        перед сохранением, а не просто верит вводу.
      </p>
      <Input
        value={chatIdOrUsername}
        onChange={(e) => setChatIdOrUsername(e.target.value)}
        placeholder="@username канала или числовой chat_id (например, -1001234567890)"
        required
      />
      <Input
        value={signature}
        onChange={(e) => setSignature(e.target.value)}
        placeholder="Подпись к публикациям (необязательно)"
      />
      <Button type="submit" disabled={create.isPending} className="self-start">
        Добавить
      </Button>
      {error && <p className="text-sm text-bad">{error}</p>}
    </form>
  );
}

function TargetChannelRow({ targetChannel }: { targetChannel: TargetChannel }) {
  const queryClient = useQueryClient();
  const sessions = useQuery(telethonSessionsQuery());
  const [signature, setSignature] = useState(targetChannel.signature);
  const [error, setError] = useState<string | null>(null);

  const update = useMutation({
    mutationFn: (payload: Partial<Pick<TargetChannel, "signature" | "is_active">>) =>
      api.put<TargetChannel>(`/target-channels/${targetChannel.id}`, payload),
    onSuccess: () => {
      setError(null);
      queryClient.invalidateQueries({ queryKey: ["target-channels"] });
    },
    onError: (err) => setError(err instanceof ApiError ? err.message : "Не удалось обновить"),
  });

  const setMetricsSession = useMutation({
    mutationFn: (metricsSessionId: string | null) =>
      api.put<TargetChannel>(`/target-channels/${targetChannel.id}/metrics-session`, {
        metrics_session_id: metricsSessionId,
      }),
    onSuccess: () => {
      setError(null);
      queryClient.invalidateQueries({ queryKey: ["target-channels"] });
      queryClient.invalidateQueries({ queryKey: ["engagement"] });
    },
    onError: (err) => setError(err instanceof ApiError ? err.message : "Не удалось назначить"),
  });

  return (
    <li className="flex flex-col gap-2 py-3 first:pt-0 last:pb-0">
      <div className="flex flex-wrap items-center justify-between gap-2">
        <div className="min-w-0">
          <p className="truncate font-medium text-ink">{targetChannel.title}</p>
          <p className="truncate text-xs text-ink-muted">{targetChannel.tg_chat_id}</p>
        </div>
        <div className="flex flex-wrap items-center gap-2">
          <StatusBadge active={targetChannel.is_active} />
          <Button
            variant="secondary"
            disabled={update.isPending}
            onClick={() => update.mutate({ is_active: !targetChannel.is_active })}
          >
            {targetChannel.is_active ? "Отключить" : "Включить"}
          </Button>
        </div>
      </div>
      <form
        className="flex gap-2"
        onSubmit={(e) => {
          e.preventDefault();
          if (signature === targetChannel.signature) return;
          setError(null);
          update.mutate({ signature });
        }}
      >
        <Input
          value={signature}
          onChange={(e) => setSignature(e.target.value)}
          placeholder="Подпись к публикациям"
          className="flex-1"
        />
        {signature !== targetChannel.signature && (
          <Button type="submit" variant="secondary" disabled={update.isPending}>
            Сохранить
          </Button>
        )}
      </form>
      <label
        className="flex flex-col items-stretch gap-1 text-xs text-ink-muted sm:flex-row sm:items-center sm:gap-2"
        title="Выбранный аккаунт-читалка раз в полчаса снимает просмотры и пересылки ваших публикаций. Аккаунт должен состоять в этом канале."
      >
        <span className="whitespace-nowrap">Просмотры собирает:</span>
        <Select
          value={targetChannel.metrics_session_id ?? ""}
          onChange={(e) => setMetricsSession.mutate(e.target.value || null)}
          disabled={setMetricsSession.isPending}
          className="flex-1"
        >
          <option value="">— никто (просмотры не собираются) —</option>
          {sessions.data?.map((s) => (
            <option key={s.id} value={s.id}>
              {s.label}
            </option>
          ))}
        </Select>
      </label>
      <CrosspostEditor targetChannel={targetChannel} />
      {error && <p className="text-xs text-bad">{error}</p>}
    </li>
  );
}

// ===== Запас постов =====

function CreatePoolPostForm({ themeId }: { themeId: string }) {
  const queryClient = useQueryClient();
  const [text, setText] = useState("");
  const [error, setError] = useState<string | null>(null);

  const create = useMutation({
    mutationFn: () => api.post<PoolPost>("/pool-posts", { theme_id: themeId, text }),
    onSuccess: () => {
      setText("");
      setError(null);
      queryClient.invalidateQueries({ queryKey: ["pool-posts"] });
    },
    onError: (err) => setError(err instanceof ApiError ? err.message : "Не удалось добавить пост"),
  });

  return (
    <form
      className="flex flex-col gap-2"
      onSubmit={(e) => {
        e.preventDefault();
        setError(null);
        create.mutate();
      }}
    >
      <p className="text-sm text-ink-muted">
        «Вечные» посты темы: выручают, когда рерайтов не хватает, и перекрывают чужую рекламу в
        течение часа после детекта. Держите 3–5 штук.
      </p>
      <Textarea
        value={text}
        onChange={(e) => setText(e.target.value)}
        placeholder="Текст поста"
        rows={4}
        required
      />
      <Button type="submit" disabled={create.isPending} className="self-start">
        Добавить
      </Button>
      {error && <p className="text-sm text-bad">{error}</p>}
    </form>
  );
}

function PoolPostRow({ post }: { post: PoolPost }) {
  const queryClient = useQueryClient();
  const [text, setText] = useState(post.text);
  const [error, setError] = useState<string | null>(null);

  const update = useMutation({
    mutationFn: (payload: Partial<Pick<PoolPost, "text">>) => api.put<PoolPost>(`/pool-posts/${post.id}`, payload),
    onSuccess: () => {
      setError(null);
      queryClient.invalidateQueries({ queryKey: ["pool-posts"] });
    },
    onError: (err) => setError(err instanceof ApiError ? err.message : "Не удалось обновить"),
  });

  const remove = useMutation({
    mutationFn: () => api.delete(`/pool-posts/${post.id}`),
    onSuccess: () => {
      setError(null);
      queryClient.invalidateQueries({ queryKey: ["pool-posts"] });
    },
    onError: (err) => setError(err instanceof ApiError ? err.message : "Не удалось удалить"),
  });

  const statusLabel = post.status === "ready" ? "Готов к выходу" : "Недавно выходил (отдыхает)";

  return (
    <li className="flex flex-col gap-2 py-3 first:pt-0 last:pb-0">
      <div className="flex items-center justify-between gap-2">
        <span
          className={`rounded-full px-2 py-0.5 text-xs font-medium whitespace-nowrap ${
            post.status === "ready" ? "bg-good-soft text-good" : "bg-surface-2 text-ink-muted"
          }`}
        >
          {statusLabel}
        </span>
        <span className="text-xs text-ink-muted">
          использован раз: {post.times_used} · источник:{" "}
          {post.source === "manual" ? "вручную" : post.source === "generated" ? "сгенерирован" : "переиспользован кандидат"}
        </span>
      </div>
      <Textarea value={text} onChange={(e) => setText(e.target.value)} rows={3} />
      <div className="flex gap-2">
        {text !== post.text && (
          <Button variant="secondary" disabled={update.isPending} onClick={() => update.mutate({ text })}>
            Сохранить текст
          </Button>
        )}
        <Button
          variant="danger"
          disabled={remove.isPending}
          onClick={() => {
            if (window.confirm("Удалить пост из запаса?")) remove.mutate();
          }}
        >
          Удалить
        </Button>
      </div>
      {error && <p className="text-xs text-bad">{error}</p>}
    </li>
  );
}

// ===== Рабочий стол темы =====

function ThemeDetail({ themeId }: { themeId: string }) {
  const theme = useQuery(themeQuery(themeId));
  const health = useQuery(themeHealthQuery(themeId));
  const sources = useQuery(sourceChannelsQuery(false));
  const bots = useQuery(channelBotsQuery());
  const channels = useQuery(targetChannelsQuery());
  const pool = useQuery(poolPostsQuery(themeId));
  const queryClient = useQueryClient();
  const [modeError, setModeError] = useState<string | null>(null);

  const updateMode = useMutation({
    mutationFn: (payload: Partial<Theme>) => api.put<Theme>(`/themes/${themeId}`, payload),
    onSuccess: () => {
      setModeError(null);
      queryClient.invalidateQueries({ queryKey: ["themes", themeId] });
      queryClient.invalidateQueries({ queryKey: ["theme-health", themeId] });
    },
    onError: (err) => setModeError(err instanceof ApiError ? err.message : "Не удалось сохранить"),
  });

  if (theme.isLoading) return <LoadingState />;
  if (theme.error) return <ErrorState message={theme.error.message} />;
  if (!theme.data) return null;

  const themeSources = (sources.data ?? []).filter((s) => s.theme_id === themeId);
  const themeBot = (bots.data ?? []).find((b) => b.theme_id === themeId);
  const themeChannels = (channels.data ?? []).filter((c) => c.theme_id === themeId);
  const poolPosts = pool.data ?? [];

  return (
    <div className="flex flex-col gap-4">
      <ThemeHeader theme={theme.data} />

      <Card>
        <h2 className="mb-1 text-sm font-semibold text-ink">Конвейер</h2>
        <p className="mb-3 text-xs text-ink-muted">
          Путь поста слева направо. Если тема молчит — ищите первый жёлтый или красный шаг: там
          и застряло.
        </p>
        {health.isLoading && <LoadingState />}
        {health.error && <ErrorState message={health.error.message} />}
        {health.data && (
          <div className="flex flex-col gap-2 lg:flex-row">
            {health.data.stages.map((stage) => (
              <PipelineStage key={stage.key} stage={stage} />
            ))}
          </div>
        )}
      </Card>

      <TrendsCard themeId={themeId} />

      <Card className="flex flex-col gap-4">
        <h2 className="text-sm font-semibold text-ink">Режим работы</h2>
        <Toggle
          label="Премодерация"
          hint="Каждый пост темы попадает в «Проверку» и выходит только после вашего одобрения. Выключите, когда стилю можно доверять — посты пойдут в канал сами."
          checked={theme.data.premoderation}
          onChange={(v) => updateMode.mutate({ premoderation: v })}
          disabled={updateMode.isPending}
        />
        <div className="flex items-start gap-3">
          <input
            type="checkbox"
            checked={theme.data.digest_enabled}
            onChange={(e) => updateMode.mutate({ digest_enabled: e.target.checked })}
            disabled={updateMode.isPending}
            className="mt-1"
          />
          <div className="flex flex-col gap-1">
            <div className="flex flex-wrap items-center gap-2">
              <span className="text-sm font-medium text-ink">Дайджест дня в</span>
              <select
                value={theme.data.digest_hour}
                onChange={(e) => updateMode.mutate({ digest_hour: Number(e.target.value) })}
                disabled={updateMode.isPending || !theme.data.digest_enabled}
                className="rounded border border-border bg-surface px-1 py-0.5 text-sm text-ink"
              >
                {Array.from({ length: 24 }, (_, h) => (
                  <option key={h} value={h}>
                    {String(h).padStart(2, "0")}:00
                  </option>
                ))}
              </select>
            </div>
            <span className="text-xs text-ink-muted">
              Раз в сутки ИИ собирает лучшие посты дня в один пост-дайджест и кладёт его в
              «Проверку».
            </span>
          </div>
        </div>
        {modeError && <p className="text-sm text-bad">{modeError}</p>}
      </Card>

      <Card className="flex flex-col gap-3">
        <h2 className="text-sm font-semibold text-ink">Источники ({themeSources.length})</h2>
        <p className="text-xs text-ink-muted">
          Чужие каналы, из которых берётся контент. При добавлении система находит канал по
          @username и подписывает на него выбранный аккаунт-читалку.
        </p>
        <Callout>
          Новый источник начинает читаться автоматически в течение ~30 секунд.
        </Callout>
        <AddSourceForm themeId={themeId} />
        <AttachExistingSourceForm themeId={themeId} />
        {themeSources.length === 0 ? (
          <EmptyState message="Нет ни одного источника — добавьте выше, иначе теме неоткуда брать контент." />
        ) : (
          <ul className="flex flex-col divide-y divide-border">
            {themeSources.map((s) => (
              <SourceRow key={s.id} channel={s} />
            ))}
          </ul>
        )}
      </Card>

      <Card className="flex flex-col gap-3">
        <h2 className="text-sm font-semibold text-ink">Бот и стиль</h2>
        {!themeBot ? <CreateThemeBotForm themeId={themeId} /> : <ThemeBotPanel bot={themeBot} />}
      </Card>

      <Card className="flex flex-col gap-3">
        <h2 className="text-sm font-semibold text-ink">Каналы ({themeChannels.length})</h2>
        <CreateTargetChannelForm themeId={themeId} />
        {themeChannels.length === 0 ? (
          <EmptyState message="Нет ни одного целевого канала — добавьте выше, иначе публиковать некуда." />
        ) : (
          <ul className="flex flex-col divide-y divide-border">
            {themeChannels.map((c) => (
              <TargetChannelRow key={c.id} targetChannel={c} />
            ))}
          </ul>
        )}
      </Card>

      <Card className="flex flex-col gap-3">
        <h2 className="text-sm font-semibold text-ink">Запас постов</h2>
        <CreatePoolPostForm themeId={themeId} />
        {poolPosts.length === 0 ? (
          <EmptyState message="Запас пуст — без него антиреклама не сможет перекрывать чужие посты." />
        ) : (
          <ul className="flex flex-col divide-y divide-border">
            {poolPosts.map((p) => (
              <PoolPostRow key={p.id} post={p} />
            ))}
          </ul>
        )}
      </Card>
    </div>
  );
}

// ===== Точка входа =====

export function Themes() {
  const { themeId } = useParams();
  const themes = useQuery(themesQuery());

  if (themes.isLoading) return <LoadingState />;
  if (themes.error) return <ErrorState message={themes.error.message} />;

  const list = themes.data ?? [];

  if (!themeId && list.length > 0) {
    return <Navigate to={`/themes/${list[0].id}`} replace />;
  }

  const activeId = themeId && list.some((t) => t.id === themeId) ? themeId : null;

  return (
    <div className="flex flex-col gap-6">
      <div>
        <h1 className="text-xl font-semibold text-ink">Темы</h1>
        <p className="mt-1 text-sm text-ink-muted">
          Всё об одной теме в одном месте — переключайтесь вкладками сверху.
        </p>
      </div>

      <ThemeTabBar themes={list} activeId={activeId} />

      {list.length === 0 && (
        <Card>
          <EmptyState message="Тем пока нет — создайте первую кнопкой «+ Новая тема» выше." />
        </Card>
      )}

      {activeId && <ThemeDetail themeId={activeId} />}
    </div>
  );
}
