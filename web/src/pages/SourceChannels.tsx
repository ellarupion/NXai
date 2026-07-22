import { useState } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { api, ApiError } from "../api/client";
import { sourceChannelsQuery, telethonSessionsQuery, themesQuery } from "../api/queries";
import { Button, Callout, Card, EmptyState, ErrorState, Input, LoadingState, Select } from "../components/ui";
import { plural } from "../lib/plural";
import type { SourceChannel } from "../types";

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

  const remove = useMutation({
    mutationFn: () => api.delete(`/source-channels/${channel.id}`),
    onSuccess: () => {
      setError(null);
      invalidate();
    },
    onError: (err) => setError(err instanceof ApiError ? err.message : "Не удалось удалить"),
  });

  const busy = setActive.isPending || remove.isPending;

  return (
    <li className="flex flex-col gap-2 py-3 first:pt-0 last:pb-0">
      <div className="flex flex-col gap-2 sm:flex-row sm:items-center sm:justify-between sm:gap-3">
        <div className="min-w-0">
          <div className="flex items-center gap-2">
            <p className="truncate font-medium text-ink">{channel.title}</p>
            <TrustScoreBadge value={channel.trust_score} />
            {!channel.is_active && (
              <span className="rounded-full bg-surface-2 px-2 py-0.5 text-xs text-ink-muted">
                выключен
              </span>
            )}
          </div>
          <p className="truncate text-xs text-ink-muted">
            {channel.tg_username ? `@${channel.tg_username}` : channel.tg_chat_id ?? "—"} ·{" "}
            {channel.candidate_count} {plural(channel.candidate_count, "пост", "поста", "постов")} ·{" "}
            {formatScanned(channel.last_scanned_at)}
          </p>
        </div>
        <div className="flex flex-col gap-2 sm:flex-row sm:items-center sm:gap-3">
          <AssignSessionCell channel={channel} />
          <AssignThemeCell channel={channel} />
        </div>
      </div>
      <div className="flex gap-3">
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

function AssignThemeCell({ channel }: { channel: SourceChannel }) {
  const queryClient = useQueryClient();
  const themes = useQuery(themesQuery());
  const [error, setError] = useState<string | null>(null);

  const assign = useMutation({
    mutationFn: (themeId: string | null) =>
      api.put<SourceChannel>(`/source-channels/${channel.id}/theme`, { theme_id: themeId }),
    onSuccess: () => {
      setError(null);
      queryClient.invalidateQueries({ queryKey: ["source-channels"] });
    },
    onError: (err) => setError(err instanceof ApiError ? err.message : "Не удалось назначить тему"),
  });

  return (
    <div className="flex flex-col items-stretch gap-1 sm:items-end">
      <Select
        value={channel.theme_id ?? ""}
        disabled={assign.isPending || themes.isLoading}
        onChange={(e) => assign.mutate(e.target.value === "" ? null : e.target.value)}
        className="w-full sm:w-auto sm:min-w-[10rem]"
      >
        <option value="">— без темы —</option>
        {themes.data?.map((theme) => (
          <option key={theme.id} value={theme.id}>
            {theme.name}
          </option>
        ))}
      </Select>
      {error && <p className="text-xs text-bad">{error}</p>}
    </div>
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

function AddSourceChannelForm() {
  const queryClient = useQueryClient();
  const themes = useQuery(themesQuery());
  const sessions = useQuery(telethonSessionsQuery());
  const [usernameOrLink, setUsernameOrLink] = useState("");
  const [ingestSessionId, setIngestSessionId] = useState("");
  const [themeId, setThemeId] = useState("");
  const [error, setError] = useState<string | null>(null);

  const create = useMutation({
    mutationFn: () =>
      api.post<SourceChannel>("/source-channels", {
        username_or_link: usernameOrLink,
        ingest_session_id: ingestSessionId,
        theme_id: themeId || null,
      }),
    onSuccess: () => {
      setUsernameOrLink("");
      setError(null);
      queryClient.invalidateQueries({ queryKey: ["source-channels"] });
    },
    onError: (err) => setError(err instanceof ApiError ? err.message : "Не удалось добавить канал"),
  });

  const noSessions = sessions.data && sessions.data.length === 0;

  return (
    <Card>
      <h2 className="mb-3 text-sm font-semibold text-ink">Добавить источник</h2>
      {noSessions && (
        <p className="mb-3 text-sm text-bad">
          Сначала заведите хотя бы один аккаунт-читалку во вкладке «Аккаунты» — им и
          будет прочитан этот канал.
        </p>
      )}
      <form
        className="flex flex-col gap-2"
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
        />
        <div className="flex flex-col gap-2 sm:flex-row">
          <Select
            value={ingestSessionId}
            onChange={(e) => setIngestSessionId(e.target.value)}
            required
            className="flex-1"
          >
            <option value="">— выберите аккаунт-читалку —</option>
            {sessions.data?.map((s) => (
              <option key={s.id} value={s.id}>
                {s.label}
              </option>
            ))}
          </Select>
          <Select value={themeId} onChange={(e) => setThemeId(e.target.value)} className="flex-1">
            <option value="">— без темы —</option>
            {themes.data?.map((theme) => (
              <option key={theme.id} value={theme.id}>
                {theme.name}
              </option>
            ))}
          </Select>
        </div>
        <Button type="submit" disabled={create.isPending || Boolean(noSessions)} className="self-start">
          Добавить
        </Button>
        {error && <p className="text-sm text-bad">{error}</p>}
      </form>
    </Card>
  );
}

export function SourceChannels() {
  const [unassignedOnly, setUnassignedOnly] = useState(false);
  const { data, isLoading, error } = useQuery(sourceChannelsQuery(unassignedOnly));

  return (
    <div className="flex flex-col gap-6">
      <div className="flex items-center justify-between gap-2">
        <h1 className="text-xl font-semibold text-ink">Источники</h1>
        <span title="Источники без темы не участвуют в работе — их посты никуда не идут">
          <Button variant="secondary" onClick={() => setUnassignedOnly((v) => !v)}>
            {unassignedOnly ? "Показать все" : "Только без темы"}
          </Button>
        </span>
      </div>

      <p className="text-sm text-ink-muted">
        Чужие каналы, из которых берётся контент. При добавлении система находит канал
        по @username и подписывает на него выбранный аккаунт-читалку — иначе новые посты
        оттуда не приходят.
      </p>
      <Callout>
        Новый источник начинает читаться в реальном времени автоматически в течение
        ~30 секунд (докачка истории подхватит его в ближайшем цикле).
      </Callout>

      <AddSourceChannelForm />

      <Card>
        {isLoading && <LoadingState />}
        {error && <ErrorState message={error.message} />}
        {data && data.length === 0 && (
          <EmptyState
            message={
              unassignedOnly
                ? "Все источники уже распределены по темам."
                : "Источников пока нет — добавьте первый выше."
            }
          />
        )}
        {data && data.length > 0 && (
          <ul className="flex flex-col divide-y divide-border">
            {data.map((channel) => (
              <SourceRow key={channel.id} channel={channel} />
            ))}
          </ul>
        )}
      </Card>
    </div>
  );
}
