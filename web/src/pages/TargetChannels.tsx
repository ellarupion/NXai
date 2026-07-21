import { useState } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { api, ApiError } from "../api/client";
import { targetChannelsQuery, telethonSessionsQuery, themesQuery } from "../api/queries";
import {
  Button,
  Card,
  EmptyState,
  ErrorState,
  Input,
  LoadingState,
  Select,
  StatusBadge,
} from "../components/ui";
import type { CrosspostConfig, TargetChannel } from "../types";

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

function CreateTargetChannelForm() {
  const queryClient = useQueryClient();
  const themes = useQuery(themesQuery());
  const [themeId, setThemeId] = useState("");
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
    <Card>
      <h2 className="mb-3 text-sm font-semibold text-ink">Новый целевой канал</h2>
      <p className="mb-3 text-sm text-ink-muted">
        Тематический бот темы должен быть уже добавлен в канал админом — панель
        проверяет это через Bot API перед сохранением, а не просто верит вводу.
      </p>
      <form
        className="flex flex-col gap-2"
        onSubmit={(e) => {
          e.preventDefault();
          setError(null);
          create.mutate();
        }}
      >
        <Select value={themeId} onChange={(e) => setThemeId(e.target.value)} required>
          <option value="">— выберите тему —</option>
          {themes.data?.map((theme) => (
            <option key={theme.id} value={theme.id}>
              {theme.name}
            </option>
          ))}
        </Select>
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
    </Card>
  );
}

function TargetChannelRow({ targetChannel, themeName }: { targetChannel: TargetChannel; themeName: string }) {
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
      <div className="flex items-center justify-between gap-2">
        <div className="min-w-0">
          <p className="truncate font-medium text-ink">{targetChannel.title}</p>
          <p className="truncate text-xs text-ink-muted">
            {themeName} · {targetChannel.tg_chat_id}
          </p>
        </div>
        <div className="flex items-center gap-2">
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
      <label className="flex items-center gap-2 text-xs text-ink-muted">
        <span className="whitespace-nowrap">Метрики читает:</span>
        <Select
          value={targetChannel.metrics_session_id ?? ""}
          onChange={(e) => setMetricsSession.mutate(e.target.value || null)}
          disabled={setMetricsSession.isPending}
          className="flex-1"
        >
          <option value="">— не собирать —</option>
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

export function TargetChannels() {
  const { data, isLoading, error } = useQuery(targetChannelsQuery());
  const themes = useQuery(themesQuery());
  const themeNameById = new Map(themes.data?.map((theme) => [theme.id, theme.name]) ?? []);

  return (
    <div className="flex flex-col gap-6">
      <h1 className="text-xl font-semibold text-ink">Целевые каналы</h1>
      <p className="text-sm text-ink-muted">
        Каналы, куда тематические боты публикуют рерайты и заполняют расписание из
        пула. Один или несколько на тему.
      </p>

      <CreateTargetChannelForm />

      <Card>
        <h2 className="mb-3 text-sm font-semibold text-ink">Все каналы</h2>
        {isLoading && <LoadingState />}
        {error && <ErrorState message={error.message} />}
        {data && data.length === 0 && (
          <EmptyState message="Целевых каналов пока нет — добавьте первый выше." />
        )}
        {data && data.length > 0 && (
          <ul className="flex flex-col divide-y divide-border">
            {data.map((targetChannel) => (
              <TargetChannelRow
                key={targetChannel.id}
                targetChannel={targetChannel}
                themeName={themeNameById.get(targetChannel.theme_id) ?? "—"}
              />
            ))}
          </ul>
        )}
      </Card>
    </div>
  );
}
