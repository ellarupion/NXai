import { useQuery } from "@tanstack/react-query";
import { Link } from "react-router-dom";
import { api } from "../api/client";
import { Card, EmptyState, ErrorState, LoadingState } from "../components/ui";
import { errorText } from "../lib/errors";
import { formatMoment, formatSlot, useProjectTz } from "../lib/datetime";
import { plural } from "../lib/plural";

/* Очередь публикаций: что и примерно когда выйдет по каждой теме. Точных
   времён у автопаблиша нет по замыслу (живой шафл с разбросом), поэтому
   слоты — ориентир по расписанию бота. Главный сигнал страницы — «на сколько
   дней хватит контента». */

interface RecentPublication {
  published_at: string;
  channel_title: string;
  preview: string;
}

interface ThemeQueue {
  theme_id: string;
  theme_name: string;
  has_active_bot: boolean;
  ready_posts: number;
  pool_ready: number;
  posts_per_day: number;
  days_left: number | null;
  next_slots: string[];
  recent: RecentPublication[];
}

const queueQuery = () => ({
  queryKey: ["queue-forecast"],
  queryFn: () => api.get<{ themes: ThemeQueue[] }>("/queue/forecast"),
});

function DaysLeftBadge({ theme }: { theme: ThemeQueue }) {
  if (!theme.has_active_bot) {
    return (
      <span className="rounded-full bg-bad-soft px-2 py-0.5 text-xs font-medium text-bad">
        нет активного бота — публиковать некому
      </span>
    );
  }
  if (theme.days_left === null) return null;
  const cls =
    theme.days_left < 1
      ? "bg-bad-soft text-bad"
      : theme.days_left < 2
        ? "bg-accent-soft text-accent"
        : "bg-good-soft text-good";
  return (
    <span className={`rounded-full px-2 py-0.5 text-xs font-medium ${cls}`}>
      контента на ~{theme.days_left} {plural(Math.max(1, Math.round(theme.days_left)), "день", "дня", "дней")}
    </span>
  );
}

function ThemeQueueCard({ theme, tz }: { theme: ThemeQueue; tz: string }) {
  const empty = theme.ready_posts + theme.pool_ready === 0;
  return (
    <Card className="flex flex-col gap-3">
      <div className="flex flex-wrap items-center justify-between gap-2">
        <Link
          to={`/themes/${theme.theme_id}`}
          className="font-medium text-ink underline decoration-dotted underline-offset-4 hover:text-accent"
        >
          {theme.theme_name}
        </Link>
        <DaysLeftBadge theme={theme} />
      </div>

      <p className="text-xs text-ink-muted">
        Готово к выходу: <span className="font-mono text-ink">{theme.ready_posts}</span>{" "}
        {plural(theme.ready_posts, "рерайт", "рерайта", "рерайтов")} +{" "}
        <span className="font-mono text-ink">{theme.pool_ready}</span> из запаса
        {theme.has_active_bot && <> · темп: {theme.posts_per_day}/день</>}
      </p>

      {empty && (
        <p className="text-sm text-ink-muted">
          Публиковать нечего.{" "}
          <Link to="/review" className="text-accent underline underline-offset-2">
            Сделайте посты
          </Link>{" "}
          или{" "}
          <Link to={`/themes/${theme.theme_id}`} className="text-accent underline underline-offset-2">
            пополните запас
          </Link>
          .
        </p>
      )}

      {theme.next_slots.length > 0 && (
        <div>
          <p className="mb-1.5 text-xs font-medium text-ink">Ближайшие выходы (ориентировочно):</p>
          <div className="flex flex-wrap gap-1.5">
            {theme.next_slots.slice(0, 8).map((slot, i) => (
              <span
                key={i}
                className="rounded-full bg-surface-2 px-2 py-0.5 font-mono text-xs tabular-nums text-ink-muted"
              >
                {formatSlot(slot, tz)}
              </span>
            ))}
          </div>
        </div>
      )}

      {theme.recent.length > 0 && (
        <details>
          <summary className="cursor-pointer select-none text-xs text-ink-muted hover:text-ink">
            Вышло недавно ({theme.recent.length})
          </summary>
          <ul className="mt-2 flex flex-col divide-y divide-border">
            {theme.recent.map((r, i) => (
              <li key={i} className="flex items-center justify-between gap-3 py-1.5">
                <span className="truncate text-xs text-ink-muted">{r.preview || r.channel_title}</span>
                <span className="shrink-0 font-mono text-xs tabular-nums text-ink-muted">
                  {formatMoment(r.published_at, tz)}
                </span>
              </li>
            ))}
          </ul>
        </details>
      )}
    </Card>
  );
}

export function Queue() {
  const { data, isLoading, error, refetch } = useQuery(queueQuery());
  const tz = useProjectTz();

  /* Наверх — у кого контент кончается раньше: это и есть вопрос, ради
     которого открывают страницу. days_left=null у темы с ботом означает
     «темп не задан» — такие после тех, у кого счёт идёт на дни. */
  const themes = [...(data?.themes ?? [])].sort(
    (a, b) => (a.days_left ?? Number.POSITIVE_INFINITY) - (b.days_left ?? Number.POSITIVE_INFINITY),
  );
  const live = themes.filter((t) => t.has_active_bot);
  const idle = themes.filter((t) => !t.has_active_bot);

  return (
    <div className="flex flex-col gap-6">
      <div>
        <h1 className="text-xl font-semibold text-ink">Очередь публикаций</h1>
        <p className="mt-1 text-sm text-ink-muted">
          Что и примерно когда выйдет по каждой теме. Времена ориентировочные —
          система нарочно публикует с живым разбросом, а не по секундам.
        </p>
        {/* Пояс подписан явно: тихие часы бот считает именно в нём, и без
            подписи слот «завтра ~05:30» читался как нарушение тишины 23–08,
            хотя это 08:30 по проекту (UX-аудит, №11). */}
        <p className="mt-1 text-xs text-ink-muted">
          Время указано по часовому поясу проекта:{" "}
          <span className="font-mono text-ink">{tz}</span> — в нём же считаются тихие часы.
        </p>
      </div>

      {isLoading && <LoadingState />}
      {error && <ErrorState message={errorText(error)} onRetry={() => refetch()} />}
      {data && data.themes.length === 0 && (
        <Card>
          <EmptyState message="Активных тем нет — создайте тему, и здесь появится её расписание." />
        </Card>
      )}

      {live.map((theme) => (
        <ThemeQueueCard key={theme.theme_id} theme={theme} tz={tz} />
      ))}

      {/* Темы без бота не публикуют ничего и не изменятся сами — держать их
          вперемешку с работающими значило прятать рабочую тему в конец списка
          (UX-аудит, №6). Сворачиваем, но не убираем: их видно и можно открыть. */}
      {idle.length > 0 && (
        <details>
          <summary className="cursor-pointer select-none text-sm text-ink-muted hover:text-ink">
            Ещё {idle.length} {plural(idle.length, "тема", "темы", "тем")} без активного бота —
            они ничего не публикуют
          </summary>
          <div className="mt-3 flex flex-col gap-6">
            {idle.map((theme) => (
              <ThemeQueueCard key={theme.theme_id} theme={theme} tz={tz} />
            ))}
          </div>
        </details>
      )}
    </div>
  );
}
