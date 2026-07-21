import { useState } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { api, ApiError } from "../api/client";
import { sourceChannelsQuery, themesQuery } from "../api/queries";
import { Button, Card, EmptyState, ErrorState, LoadingState, Select } from "../components/ui";
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
        Чужие каналы, которые читает Telethon-пул. Добавление новых каналов по
        @username (с резолвом в chat_id) — ROADMAP.md Phase 1, пока список
        только для уже существующих записей.
      </p>

      <Card>
        {isLoading && <LoadingState />}
        {error && <ErrorState message={error.message} />}
        {data && data.length === 0 && (
          <EmptyState
            message={
              unassignedOnly
                ? "Все источники уже распределены по темам."
                : "Источников пока нет."
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
                <AssignThemeCell channel={channel} />
              </li>
            ))}
          </ul>
        )}
      </Card>
    </div>
  );
}
