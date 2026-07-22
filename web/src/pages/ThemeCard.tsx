import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { Link, useParams } from "react-router-dom";
import { api, ApiError } from "../api/client";
import {
  channelBotsQuery,
  poolPostsQuery,
  sourceChannelsQuery,
  targetChannelsQuery,
  themeHealthQuery,
  themeQuery,
} from "../api/queries";
import { Card, ErrorState, LoadingState, StatusBadge } from "../components/ui";
import { TrendsCard } from "./Dashboard";
import { plural } from "../lib/plural";
import type { Theme, ThemeHealthStage, ThemeHealthStatus } from "../types";
import { useState } from "react";

/* Карточка темы — всё про одну тему в одном месте: диагностика конвейера
   («почему молчит»), источники, бот, каналы, запас, тумблеры премодерации и
   дайджеста. Списочные страницы остаются реестрами, здесь — центр управления. */

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

export function ThemeCard() {
  const { themeId = "" } = useParams();
  const queryClient = useQueryClient();
  const theme = useQuery(themeQuery(themeId));
  const health = useQuery(themeHealthQuery(themeId));
  const sources = useQuery(sourceChannelsQuery(false));
  const bots = useQuery(channelBotsQuery());
  const channels = useQuery(targetChannelsQuery());
  const pool = useQuery(poolPostsQuery(themeId));
  const [error, setError] = useState<string | null>(null);

  const update = useMutation({
    mutationFn: (payload: Partial<Theme>) => api.put<Theme>(`/themes/${themeId}`, payload),
    onSuccess: () => {
      setError(null);
      queryClient.invalidateQueries({ queryKey: ["themes"] });
      queryClient.invalidateQueries({ queryKey: ["themes", themeId] });
      queryClient.invalidateQueries({ queryKey: ["theme-health", themeId] });
    },
    onError: (err) => setError(err instanceof ApiError ? err.message : "Не удалось сохранить"),
  });

  if (theme.isLoading) return <LoadingState />;
  if (theme.error) return <ErrorState message={theme.error.message} />;
  if (!theme.data) return null;

  const themeSources = (sources.data ?? []).filter((s) => s.theme_id === themeId);
  const themeBot = (bots.data ?? []).find((b) => b.theme_id === themeId);
  const themeChannels = (channels.data ?? []).filter((c) => c.theme_id === themeId);
  const poolReady = (pool.data ?? []).filter((p) => p.status === "ready").length;

  return (
    <div className="flex flex-col gap-6">
      <div className="flex flex-wrap items-center justify-between gap-3">
        <div className="flex items-center gap-3">
          <Link to="/themes" className="text-sm text-ink-muted hover:text-ink">
            ← Темы
          </Link>
          <h1 className="text-xl font-semibold text-ink">{theme.data.name}</h1>
          <StatusBadge active={theme.data.is_active} />
        </div>
      </div>

      <Card>
        <h2 className="mb-1 text-sm font-semibold text-ink">Конвейер</h2>
        <p className="mb-3 text-xs text-ink-muted">
          Путь поста слева направо. Если тема молчит — ищите первый жёлтый или
          красный шаг: там и застряло.
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
          onChange={(v) => update.mutate({ premoderation: v })}
          disabled={update.isPending}
        />
        <Toggle
          label={`Дайджест дня (в ${String(theme.data.digest_hour).padStart(2, "0")}:00)`}
          hint="Раз в сутки ИИ собирает лучшие посты дня в один пост-дайджест и кладёт его в «Проверку»."
          checked={theme.data.digest_enabled}
          onChange={(v) => update.mutate({ digest_enabled: v })}
          disabled={update.isPending}
        />
        {error && <p className="text-sm text-bad">{error}</p>}
      </Card>

      <div className="grid gap-4 md:grid-cols-2">
        <Card>
          <div className="mb-2 flex items-center justify-between">
            <h2 className="text-sm font-semibold text-ink">Источники ({themeSources.length})</h2>
            <Link to="/source-channels" className="text-xs text-accent underline underline-offset-2">
              Управлять
            </Link>
          </div>
          {themeSources.length === 0 && (
            <p className="text-sm text-ink-muted">
              Нет ни одного — добавьте на странице «Источники», иначе теме неоткуда
              брать контент.
            </p>
          )}
          <ul className="flex flex-col divide-y divide-border">
            {themeSources.map((s) => (
              <li key={s.id} className="flex items-center justify-between gap-2 py-1.5">
                <span className="truncate text-sm text-ink">{s.title}</span>
                <span className="shrink-0 text-xs text-ink-muted">
                  {s.candidate_count} {plural(s.candidate_count, "пост", "поста", "постов")}
                </span>
              </li>
            ))}
          </ul>
        </Card>

        <Card>
          <div className="mb-2 flex items-center justify-between">
            <h2 className="text-sm font-semibold text-ink">Бот и стиль</h2>
            <Link to="/bots" className="text-xs text-accent underline underline-offset-2">
              Управлять
            </Link>
          </div>
          {!themeBot && (
            <p className="text-sm text-ink-muted">
              У темы нет бота — создайте его на странице «Боты», без него публиковать
              некому.
            </p>
          )}
          {themeBot && (
            <div className="flex flex-col gap-2">
              <div className="flex items-center gap-2">
                <StatusBadge active={themeBot.is_active} />
                <span className="text-xs text-ink-muted">
                  {themeBot.token_set ? "токен задан" : "токен не задан"}
                </span>
              </div>
              <p className="line-clamp-4 text-sm text-ink-muted">
                {themeBot.persona_prompt || "Персона не задана — посты пишутся запасным стилем темы."}
              </p>
            </div>
          )}
        </Card>

        <Card>
          <div className="mb-2 flex items-center justify-between">
            <h2 className="text-sm font-semibold text-ink">Каналы ({themeChannels.length})</h2>
            <Link to="/target-channels" className="text-xs text-accent underline underline-offset-2">
              Управлять
            </Link>
          </div>
          {themeChannels.length === 0 && (
            <p className="text-sm text-ink-muted">
              Нет ни одного — добавьте на странице «Каналы», иначе публиковать некуда.
            </p>
          )}
          <ul className="flex flex-col divide-y divide-border">
            {themeChannels.map((c) => (
              <li key={c.id} className="flex items-center justify-between gap-2 py-1.5">
                <span className="truncate text-sm text-ink">{c.title}</span>
                <StatusBadge active={c.is_active} />
              </li>
            ))}
          </ul>
        </Card>

        <Card>
          <div className="mb-2 flex items-center justify-between">
            <h2 className="text-sm font-semibold text-ink">Запас постов</h2>
            <Link to="/pool-posts" className="text-xs text-accent underline underline-offset-2">
              Управлять
            </Link>
          </div>
          <p className="text-sm text-ink-muted">
            Готово к выходу: <span className="font-medium text-ink">{poolReady}</span>.
            {poolReady < 3 &&
              " Маловато — держите 3–5 «вечных» постов, чтобы антиреклама и расписание не оставались без материала."}
          </p>
        </Card>
      </div>
    </div>
  );
}
