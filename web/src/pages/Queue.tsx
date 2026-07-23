import { useQuery } from "@tanstack/react-query";
import { Link } from "react-router-dom";
import { api } from "../api/client";
import { Card, EmptyState, ErrorState, LoadingState } from "../components/ui";
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

function formatSlot(iso: string): string {
  const d = new Date(iso);
  const today = new Date();
  const tomorrow = new Date(today);
  tomorrow.setDate(today.getDate() + 1);
  const hhmm = d.toLocaleTimeString("ru-RU", { hour: "2-digit", minute: "2-digit" });
  if (d.toDateString() === today.toDateString()) return `сегодня ~${hhmm}`;
  if (d.toDateString() === tomorrow.toDateString()) return `завтра ~${hhmm}`;
  return `${d.toLocaleDateString("ru-RU", { day: "numeric", month: "short" })} ~${hhmm}`;
}

function formatPast(iso: string): string {
  const d = new Date(iso);
  return d.toLocaleString("ru-RU", { day: "numeric", month: "short", hour: "2-digit", minute: "2-digit" });
}

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

function ThemeQueueCard({ theme }: { theme: ThemeQueue }) {
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
                {formatSlot(slot)}
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
                  {formatPast(r.published_at)}
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
  const { data, isLoading, error } = useQuery(queueQuery());

  return (
    <div className="flex flex-col gap-6">
      <div>
        <h1 className="text-xl font-semibold text-ink">Очередь публикаций</h1>
        <p className="mt-1 text-sm text-ink-muted">
          Что и примерно когда выйдет по каждой теме. Времена ориентировочные —
          система нарочно публикует с живым разбросом, а не по секундам.
        </p>
      </div>

      {isLoading && <LoadingState />}
      {error && <ErrorState message={error.message} />}
      {data && data.themes.length === 0 && (
        <Card>
          <EmptyState message="Активных тем нет — создайте тему, и здесь появится её расписание." />
        </Card>
      )}
      {data?.themes.map((theme) => (
        <ThemeQueueCard key={theme.theme_id} theme={theme} />
      ))}
    </div>
  );
}
