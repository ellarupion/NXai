import { useQuery } from "@tanstack/react-query";
import { Link } from "react-router-dom";
import { alertsQuery, dashboardStatsQuery, engagementQuery, onboardingQuery } from "../api/queries";
import { Card, ErrorState, LoadingState, StatTile } from "../components/ui";
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
          Сбор метрик публикаций не настроен. Назначьте аккаунт-читалку каналу на странице{" "}
          <Link to="/target-channels" className="text-accent underline underline-offset-2">
            «Каналы»
          </Link>{" "}
          (аккаунт должен состоять в этом канале) — и здесь появятся просмотры и пересылки
          ваших постов.
        </p>
      )}
      {data.metrics_configured && data.publications.length === 0 && (
        <p className="text-sm text-ink-muted">
          Метрики ещё не собраны — они появятся в течение получаса после первой публикации.
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

function OnboardingCard() {
  const { data } = useQuery(onboardingQuery());
  if (!data || data.all_done) return null;

  return (
    <Card className="border-accent/40">
      <h2 className="mb-1 text-sm font-semibold text-ink">С чего начать</h2>
      <p className="mb-3 text-xs text-ink-muted">
        Чтобы система заработала, пройдите эти шаги по порядку.
      </p>
      <ol className="flex flex-col gap-2">
        {data.steps.map((step, i) => (
          <li key={step.key} className="flex items-center gap-3">
            <span
              className={`flex h-5 w-5 shrink-0 items-center justify-center rounded-full text-xs font-medium ${
                step.done ? "bg-good-soft text-good" : "bg-surface-2 text-ink-muted"
              }`}
            >
              {step.done ? "✓" : i + 1}
            </span>
            {step.done ? (
              <span className="text-sm text-ink-muted line-through">{step.label}</span>
            ) : (
              <Link to={step.href} className="text-sm text-accent underline underline-offset-2">
                {step.label}
              </Link>
            )}
          </li>
        ))}
      </ol>
    </Card>
  );
}

function WorkersCard({ workers }: { workers: WorkerStatus[] }) {
  return (
    <Card>
      <h2 className="mb-3 text-sm font-semibold text-ink">Фоновые процессы</h2>
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
    </Card>
  );
}

const STATUS_LABELS: Record<string, string> = {
  new: "Новые",
  scoring: "Дозревают",
  selected: "Отобраны",
  rewritten: "Готовы к паблишу",
  pending_review: "На одобрении",
  queued: "В очереди",
  published: "Опубликованы",
  rejected: "Отклонены",
  duplicate: "Дубли",
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

function AlertsSection() {
  const { data, isLoading, error } = useQuery(alertsQuery());

  return (
    <Card>
      <h2 className="mb-3 text-sm font-semibold text-ink">Алерты</h2>
      {isLoading && <LoadingState />}
      {error && <ErrorState message={error.message} />}
      {data && data.length === 0 && (
        <p className="text-sm text-good">Проблем не обнаружено — всё настроено и работает.</p>
      )}
      {data && data.length > 0 && (
        <ul className="flex flex-col gap-2">
          {data.map((alert: Alert, i: number) => (
            <li
              key={i}
              className={`rounded-lg p-3 text-sm ${
                alert.severity === "warning" ? "bg-bad-soft text-bad" : "bg-surface-2 text-ink-muted"
              }`}
            >
              {alert.message}
            </li>
          ))}
        </ul>
      )}
    </Card>
  );
}

export function Dashboard() {
  const { data, isLoading, error } = useQuery(dashboardStatsQuery());

  if (isLoading) return <LoadingState />;
  if (error) return <ErrorState message={error.message} />;
  if (!data) return null;

  return (
    <div className="flex flex-col gap-6">
      <div>
        <h1 className="text-xl font-semibold text-ink">Дашборд</h1>
        <p className="mt-1 text-sm text-ink-muted">
          Живая статистика работы системы: сколько тем и источников заведено, что на
          разных стадиях обработки, сколько опубликовано.
        </p>
      </div>

      <OnboardingCard />

      <AlertsSection />

      <div className="grid grid-cols-2 gap-4 md:grid-cols-4">
        <StatTile label="Тем всего" value={data.themes_total} />
        <StatTile label="Активных тем" value={data.themes_active} />
        <StatTile label="Источников всего" value={data.source_channels_total} />
        <StatTile label="Источников без темы" value={data.source_channels_unassigned} />
        <StatTile label="Публикаций всего" value={data.publications_total} />
        <StatTile label="Публикаций сегодня" value={data.publications_today} />
        <StatTile label="Пул: всего" value={data.pool_posts_total} />
        <StatTile label="Пул: готово" value={data.pool_posts_ready} />
      </div>

      {data.pending_review_count > 0 && (
        <Card className="border-accent/40">
          <p className="text-sm text-ink">
            <span className="font-semibold">{data.pending_review_count}</span>{" "}
            {plural(data.pending_review_count, "пост ждёт", "поста ждут", "постов ждут")} одобрения —{" "}
            <Link to="/review" className="text-accent underline underline-offset-2">
              перейти к проверке
            </Link>
            .
          </p>
        </Card>
      )}

      {data.source_channels_unassigned > 0 && (
        <Card className="border-accent/40">
          <p className="text-sm text-ink">
            Есть <span className="font-semibold">{data.source_channels_unassigned}</span>{" "}
            {plural(data.source_channels_unassigned, "источник", "источника", "источников")} без
            темы —{" "}
            <Link to="/source-channels" className="text-accent underline underline-offset-2">
              распределите их
            </Link>{" "}
            по темам.
          </p>
        </Card>
      )}

      <Card>
        <h2 className="mb-3 text-sm font-semibold text-ink">Кандидаты по стадиям пайплайна</h2>
        <div className="grid grid-cols-2 gap-4 sm:grid-cols-3 md:grid-cols-4">
          {STATUS_ORDER.map((status) => (
            <StatTile
              key={status}
              label={STATUS_LABELS[status] ?? status}
              value={data.candidates_by_status[status] ?? 0}
            />
          ))}
        </div>
      </Card>

      <Card>
        <h2 className="mb-3 text-sm font-semibold text-ink">Топ-5 источников по числу кандидатов</h2>
        {data.top_sources.length === 0 && (
          <p className="text-sm text-ink-muted">Пока нет ни одного кандидата ни от одного источника.</p>
        )}
        {data.top_sources.length > 0 && (
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
        )}
      </Card>

      <EngagementCard />

      <WorkersCard workers={data.workers} />
    </div>
  );
}
