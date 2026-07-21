import { useState } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { api, ApiError } from "../api/client";
import { sourceChannelsQuery, telethonSessionsQuery, themesQuery } from "../api/queries";
import { Button, Card, EmptyState, ErrorState, Input, LoadingState, Select } from "../components/ui";
import type { SourceChannel } from "../types";

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
    <div className="flex flex-col items-end gap-1">
      <Select
        value={channel.theme_id ?? ""}
        disabled={assign.isPending || themes.isLoading}
        onChange={(e) => assign.mutate(e.target.value === "" ? null : e.target.value)}
        className="min-w-[10rem]"
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
    onError: (err) => setError(err instanceof ApiError ? err.message : "Не удалось назначить сессию"),
  });

  return (
    <div className="flex flex-col items-end gap-1">
      <Select
        value={channel.ingest_session_id ?? ""}
        disabled={assign.isPending || sessions.isLoading}
        onChange={(e) => assign.mutate(e.target.value === "" ? null : e.target.value)}
        className="min-w-[10rem]"
      >
        <option value="">— без сессии —</option>
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
        <div className="flex gap-2">
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
        <Button variant="secondary" onClick={() => setUnassignedOnly((v) => !v)}>
          {unassignedOnly ? "Показать все" : "Только без темы"}
        </Button>
      </div>

      <p className="text-sm text-ink-muted">
        Чужие каналы, которые читает Telethon-пул. Добавление резолвит @username через
        выбранный аккаунт-читалку и подписывает его на канал — иначе живые апдейты по
        нему не приходят (ARCHITECTURE.md §7).
      </p>

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
              <li key={channel.id} className="flex items-center justify-between gap-3 py-3 first:pt-0 last:pb-0">
                <div className="min-w-0">
                  <p className="truncate font-medium text-ink">{channel.title}</p>
                  <p className="truncate text-xs text-ink-muted">
                    {channel.tg_username ? `@${channel.tg_username}` : channel.tg_chat_id ?? "—"}
                  </p>
                </div>
                <div className="flex items-center gap-3">
                  <AssignSessionCell channel={channel} />
                  <AssignThemeCell channel={channel} />
                </div>
              </li>
            ))}
          </ul>
        )}
      </Card>
    </div>
  );
}
