import { useQuery } from "@tanstack/react-query";
import { Link } from "react-router-dom";
import {
  alertsQuery,
  dashboardStatsQuery,
  engagementQuery,
  onboardingQuery,
  themesQuery,
  trendsQuery,
} from "../api/queries";
import { Card, ErrorState, LoadingState, StatTile } from "../components/ui";
import { Sparkline } from "../components/Sparkline";
import { plural } from "../lib/plural";
import type { Alert, WorkerStatus } from "../types";

function EngagementCard() {
  const { data } = useQuery(engagementQuery());
  if (!data) return null;

  return (
    <Card>
      <h2 className="mb-3 text-sm font-semibold text-ink">Как заходят посты</h2>
      {!data.metrics_configured && (
        <p className="text-sm text-ink-muted">
          Сбор просмотров не настроен. Назначьте аккаунт-читалку каналу на странице{" "}
          <Link to="/target-channels" className="text-accent underline underline-offset-2">
            «Каналы»
          </Link>{" "}
          (аккаунт должен состоять в этом канале) — и здесь появятся просмотры и пересылки
          ваших постов.
        </p>
      )}
      {data.metrics_configured && data.publications.length === 0 && (
        <p className="text-sm text-ink-muted">
          Просмотры ещё не собраны — они появятся в течение получаса после первой публикации.
        </p>
      )}
      {data.publications.length > 0 && (
        <ul className="flex flex-col divide-y divide-border">
          {data.publications.map((p) => (
            <li key={p.publication_id} className="flex items-center justify-between gap-3 py-2">
              <span className="truncate text-sm text-ink">{p.channel_title}</span>
              <span className="font-mono text-xs tabular-nums text-ink-muted whitespace-nowrap">
                👁 {p.views ?? "—"} · 🔁 {p.forwards ?? "—"}
              </span>
            </li>
          ))}
        </ul>
      )}
    </Card>
  );
}

/* Пока система не настроена до конца, дашборд не разворачивает чеклист, а
   ведёт в визард /setup — там те же шаги, но с формами и проверками на месте. */
function OnboardingCard() {
  const { data } = useQuery(onboardingQuery());
  if (!data || data.all_done) return null;

  const doneCount = data.steps.filter((s) => s.done).length;

  return (
    <Card className="border-accent/40">
      <div className="flex flex-wrap items-center justify-between gap-3">
        <div>
          <h2 className="text-sm font-semibold text-ink">Система ещё не настроена до конца</h2>
          <p className="mt-1 text-xs text-ink-muted">
            Готово {doneCount} из {data.steps.length} шагов. Визард проведёт по
            оставшимся и проверит каждый.
          </p>
        </div>
        <Link
          to="/setup"
          className="shrink-0 rounded-lg bg-accent px-3 py-1.5 text-xs font-semibold text-accent-ink hover:bg-accent-strong"
        >
          Продолжить настройку (шаг {doneCount + 1} из {data.steps.length})
        </Link>
      </div>
    </Card>
  );
}

// Куда вести из алерта, чтобы проблему можно было чинить в один клик,
// а не искать нужную страницу по тексту. Ключи — Alert.category с бэка
// (interfaces/api/routers/alerts.py).
const ALERT_ACTIONS: Record<string, { href: string; label: string }> = {
  missing_bot: { href: "/bots", label: "Завести бота" },
  missing_target_channel: { href: "/target-channels", label: "Добавить канал" },
  theme_inactive: { href: "/review", label: "Проверить посты" },
  pool_stagnant: { href: "/pool-posts", label: "Пополнить запас" },
  source_no_output: { href: "/source-channels", label: "К источникам" },
  pending_review_stale: { href: "/review", label: "К проверке" },
};

function AlertLine({ alert }: { alert: Alert }) {
  const action = ALERT_ACTIONS[alert.category];
  return (
    <li
      className={`flex flex-wrap items-center justify-between gap-2 rounded-lg p-3 text-sm ${
        alert.severity === "warning" ? "bg-bad-soft text-bad" : "bg-surface-2 text-ink-muted"
      }`}
    >
      <span>{alert.message}</span>
      {action && (
        <Link
          to={action.href}
          className="shrink-0 rounded-lg border border-current px-2 py-1 text-xs font-medium hover:opacity-80"
        >
          {action.label}
        </Link>
      )}
    </li>
  );
}

/* «Сначала действия»: наверху только то, что требует внимания — критичные
   алерты, сгруппированные по темам; некритичное сворачивается. Заменяет
   прежнюю стену из всех алертов подряд. */
function AttentionSection({ pendingReviewCount }: { pendingReviewCount: number }) {
  const alerts = useQuery(alertsQuery());
  const themes = useQuery(themesQuery());
  const themeNameById = new Map(themes.data?.map((t) => [t.id, t.name]) ?? []);

  if (alerts.isLoading) return <LoadingState />;
  if (alerts.error) return <ErrorState message={alerts.error.message} />;
  const data = alerts.data ?? [];

  const critical = data.filter((a) => a.severity === "warning");
  const minor = data.filter((a) => a.severity !== "warning");

  // Группировка критичного по темам: одна тема с тремя проблемами — один блок,
  // а не три строки вперемешку с другими темами.
  const byTheme = new Map<string, Alert[]>();
  const noTheme: Alert[] = [];
  for (const a of critical) {
    if (a.theme_id) {
      const list = byTheme.get(a.theme_id) ?? [];
      list.push(a);
      byTheme.set(a.theme_id, list);
    } else {
      noTheme.push(a);
    }
  }

  const nothingToDo = pendingReviewCount === 0 && critical.length === 0;

  return (
    <Card className={critical.length > 0 || pendingReviewCount > 0 ? "border-accent/40" : undefined}>
      <h2 className="mb-3 text-sm font-semibold text-ink">Требует внимания</h2>

      {pendingReviewCount > 0 && (
        <div className="mb-3 flex flex-wrap items-center justify-between gap-2 rounded-lg bg-accent-soft p-3">
          <span className="text-sm text-ink">
            <span className="font-semibold">{pendingReviewCount}</span>{" "}
            {plural(pendingReviewCount, "пост ждёт", "поста ждут", "постов ждут")} вашего одобрения
          </span>
          <Link
            to="/review"
            className="shrink-0 rounded-lg bg-accent px-3 py-1.5 text-xs font-semibold text-accent-ink hover:bg-accent-strong"
          >
            К проверке
          </Link>
        </div>
      )}

      {nothingToDo && (
        <p className="text-sm text-good">Всё в порядке — вмешательство не требуется.</p>
      )}

      {(byTheme.size > 0 || noTheme.length > 0) && (
        <div className="flex flex-col gap-4">
          {[...byTheme.entries()].map(([themeId, list]) => (
            <div key={themeId}>
              <h3 className="mb-1.5 text-xs font-semibold uppercase tracking-wide text-ink-muted">
                {themeNameById.get(themeId) ?? "Тема"}
              </h3>
              <ul className="flex flex-col gap-2">
                {list.map((a, i) => (
                  <AlertLine key={i} alert={a} />
                ))}
              </ul>
            </div>
          ))}
          {noTheme.length > 0 && (
            <div>
              <h3 className="mb-1.5 text-xs font-semibold uppercase tracking-wide text-ink-muted">
                Система
              </h3>
              <ul className="flex flex-col gap-2">
                {noTheme.map((a, i) => (
                  <AlertLine key={i} alert={a} />
                ))}
              </ul>
            </div>
          )}
        </div>
      )}

      {minor.length > 0 && (
        <details className="mt-3">
          <summary className="cursor-pointer select-none text-xs text-ink-muted hover:text-ink">
            Ещё {minor.length}{" "}
            {plural(minor.length, "некритичное уведомление", "некритичных уведомления", "некритичных уведомлений")}
          </summary>
          <ul className="mt-2 flex flex-col gap-2">
            {minor.map((a, i) => (
              <AlertLine key={i} alert={a} />
            ))}
          </ul>
        </details>
      )}
    </Card>
  );
}

// Человеческие названия стадий конвейера вместо внутренних статусов.
const STATUS_LABELS: Record<string, string> = {
  new: "Только собраны",
  scoring: "Ждут оценку виральности",
  selected: "Отобраны как лучшие",
  rewritten: "Переписаны, ждут выхода",
  pending_review: "Ждут вашего одобрения",
  queued: "В очереди на публикацию",
  published: "Опубликованы",
  rejected: "Отклонены",
  duplicate: "Отсеяны как повторы",
};

const STATUS_ORDER = [
  "new",
  "scoring",
  "selected",
  "rewritten",
  "pending_review",
  "queued",
  "published",
  "rejected",
  "duplicate",
];

/* «Динамика за 14 дней»: два спарклайна (вышло / собрано). Числа продублированы
   текстом — график лишь показывает форму тренда. */
function TrendsCard({ themeId }: { themeId?: string }) {
  const { data } = useQuery(trendsQuery(themeId));
  if (!data) return null;
  const pubs = data.days.map((d) => d.publications);
  const cands = data.days.map((d) => d.candidates);
  const pubsTotal = pubs.reduce((a, b) => a + b, 0);
  const candsTotal = cands.reduce((a, b) => a + b, 0);
  if (pubsTotal === 0 && candsTotal === 0) return null;

  return (
    <Card>
      <h2 className="mb-3 text-sm font-semibold text-ink">Динамика за 14 дней</h2>
      <div className="grid grid-cols-1 gap-4 sm:grid-cols-2">
        <div className="flex items-center gap-3">
          <Sparkline values={pubs} />
          <div>
            <p className="font-mono text-lg tabular-nums text-ink">{pubsTotal}</p>
            <p className="text-xs text-ink-muted">
              публикаций · сегодня {pubs[pubs.length - 1]}
            </p>
          </div>
        </div>
        <div className="flex items-center gap-3">
          <Sparkline values={cands} />
          <div>
            <p className="font-mono text-lg tabular-nums text-ink">{candsTotal}</p>
            <p className="text-xs text-ink-muted">
              постов собрано · сегодня {cands[cands.length - 1]}
            </p>
          </div>
        </div>
      </div>
    </Card>
  );
}

export { TrendsCard };

function WorkersList({ workers }: { workers: WorkerStatus[] }) {
  return (
    <ul className="flex flex-col divide-y divide-border">
      {workers.map((w) => (
        <li key={w.worker_name} className="flex items-center justify-between py-2">
          <span className="text-sm text-ink">{w.label}</span>
          <span
            className={`rounded-full px-2 py-0.5 text-xs font-medium whitespace-nowrap ${
              w.is_alive ? "bg-good-soft text-good" : "bg-bad-soft text-bad"
            }`}
          >
            {w.is_alive ? "работает" : w.last_beat_at ? "не отвечает" : "не запущен"}
          </span>
        </li>
      ))}
    </ul>
  );
}

export function Dashboard() {
  const { data, isLoading, error } = useQuery(dashboardStatsQuery());

  if (isLoading) return <LoadingState />;
  if (error) return <ErrorState message={error.message} />;
  if (!data) return null;

  // Нулевые стадии конвейера не показываем — сетка из девяти нулей ни о чём
  // не говорит; когда данных нет вообще, вместо неё одна строка-подсказка.
  const activeStages = STATUS_ORDER.filter((s) => (data.candidates_by_status[s] ?? 0) > 0);

  return (
    <div className="flex flex-col gap-6">
      <div>
        <h1 className="text-xl font-semibold text-ink">Дашборд</h1>
        <p className="mt-1 text-sm text-ink-muted">
          Что требует вашего участия — сверху; сводка и служебное — ниже.
        </p>
      </div>

      <OnboardingCard />

      <AttentionSection pendingReviewCount={data.pending_review_count} />

      <div className="grid grid-cols-2 gap-4 md:grid-cols-4">
        <StatTile label="Вышло сегодня" value={data.publications_today} />
        <StatTile label="Вышло за всё время" value={data.publications_total} />
        <StatTile label="Активных тем" value={data.themes_active} />
        <StatTile label="Источников" value={data.source_channels_total} />
      </div>

      {data.source_channels_unassigned > 0 && (
        <Card className="border-accent/40">
          <p className="text-sm text-ink">
            Есть <span className="font-semibold">{data.source_channels_unassigned}</span>{" "}
            {plural(data.source_channels_unassigned, "источник", "источника", "источников")} без
            темы — их посты никуда не идут.{" "}
            <Link to="/source-channels" className="text-accent underline underline-offset-2">
              Распределите их
            </Link>{" "}
            по темам.
          </p>
        </Card>
      )}

      <TrendsCard />

      <Card>
        <h2 className="mb-3 text-sm font-semibold text-ink">Посты в работе</h2>
        {activeStages.length === 0 && (
          <p className="text-sm text-ink-muted">
            Пока пусто — как только читалки соберут первые посты из источников, здесь
            появится их путь от сбора до публикации.
          </p>
        )}
        {activeStages.length > 0 && (
          <div className="grid grid-cols-2 gap-4 sm:grid-cols-3 md:grid-cols-4">
            {activeStages.map((status) => (
              <StatTile
                key={status}
                label={STATUS_LABELS[status] ?? status}
                value={data.candidates_by_status[status] ?? 0}
              />
            ))}
          </div>
        )}
      </Card>

      {data.top_sources.length > 0 && (
        <Card>
          <h2 className="mb-3 text-sm font-semibold text-ink">Самые плодовитые источники</h2>
          <ul className="flex flex-col divide-y divide-border">
            {data.top_sources.map((source) => (
              <li key={source.title} className="flex items-center justify-between py-2">
                <span className="truncate text-sm text-ink">{source.title}</span>
                <span className="font-mono text-sm tabular-nums text-ink-muted">
                  {source.candidate_count}
                </span>
              </li>
            ))}
          </ul>
        </Card>
      )}

      <EngagementCard />

      <details>
        <summary className="cursor-pointer select-none text-xs text-ink-muted hover:text-ink">
          Служебное: фоновые процессы и запас постов
        </summary>
        <Card className="mt-2">
          <WorkersList workers={data.workers} />
          <p className="mt-3 text-xs text-ink-muted">
            Запас постов: {data.pool_posts_ready} из {data.pool_posts_total} готово к выходу —{" "}
            <Link to="/pool-posts" className="text-accent underline underline-offset-2">
              управлять запасом
            </Link>
            .
          </p>
        </Card>
      </details>
    </div>
  );
}
