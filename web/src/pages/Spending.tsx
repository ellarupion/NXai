import { useState } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { api, ApiError } from "../api/client";
import { automationQuery, llmUsageQuery } from "../api/queries";
import { Button, Card, EmptyState, ErrorState, Input, PageSkeleton } from "../components/ui";
import { errorText } from "../lib/errors";
import { plural } from "../lib/plural";
import type { AutomationSettings, LlmUsage } from "../types";

/* Страница расходов на ИИ.
   Отвечает на два разных вопроса, и оба нужны. «Сколько всего» — чтобы понимать
   порядок трат. «На что именно» — чтобы понимать, какая кнопка дорогая: без разбивки
   по разделам работы видно одно число, и решить, что урезать, по нему нельзя. */

function usd(value: number): string {
  // Меньше цента показываем с четырьмя знаками: классификация подтемы стоит доли
  // цента, и «$0.00» на такой строке выглядел бы как «бесплатно».
  return value >= 0.01 ? `$${value.toFixed(2)}` : `$${value.toFixed(4)}`;
}

function BudgetCard({ usage }: { usage: LlmUsage }) {
  const queryClient = useQueryClient();
  const automation = useQuery(automationQuery());
  const [limit, setLimit] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);

  const save = useMutation({
    mutationFn: (value: number) =>
      api.put<AutomationSettings>("/settings/automation", { daily_budget_usd: value }),
    onSuccess: () => {
      setError(null);
      setLimit(null);
      queryClient.invalidateQueries({ queryKey: ["automation"] });
      queryClient.invalidateQueries({ queryKey: ["llm-usage"] });
    },
    onError: (err) => setError(err instanceof ApiError ? err.message : "Не удалось сохранить"),
  });

  const stored = automation.data?.daily_budget_usd ?? 0;
  const value = limit ?? String(stored);
  const dirty = Number(value) !== stored;
  const { budget } = usage;

  // Классы перечислены целиком, а не собираются как `text-${tone}`: Tailwind ищет
  // имена классов в исходнике и вычисленное в рантайме имя не соберёт — цвет просто
  // не применился бы, причём молча.
  const tone = budget.exceeded
    ? { text: "text-bad", bar: "bg-bad" }
    : budget.near_limit
      ? { text: "text-warn", bar: "bg-warn" }
      : { text: "text-good", bar: "bg-good" };

  return (
    <Card className="flex flex-col gap-4">
      <div className="flex flex-wrap items-baseline justify-between gap-2">
        <h2 className="text-sm font-semibold text-ink">Сегодня</h2>
        <span className={`font-mono text-2xl tabular-nums ${tone.text}`}>
          {usd(budget.spent_today_usd)}
        </span>
      </div>

      {budget.enabled ? (
        <div className="flex flex-col gap-1.5">
          <div className="h-2 w-full overflow-hidden rounded-full bg-surface-2">
            <div
              className={`h-full rounded-full ${tone.bar} transition-[width]`}
              style={{ width: `${Math.min(100, budget.percent)}%` }}
            />
          </div>
          <p className="text-xs text-ink-muted">
            {budget.percent}% дневного лимита {usd(budget.limit_usd)}
            {budget.exceeded && " — дорогие операции остановлены до полуночи"}
            {!budget.exceeded &&
              budget.near_limit &&
              ` — близко к потолку (предупреждаем с ${budget.warn_percent}%)`}
          </p>
        </div>
      ) : (
        <p className="text-xs text-ink-muted">
          Дневной потолок выключен: система потратит столько, сколько потребуется.
          Поставьте сумму, если хотите, чтобы дорогие операции останавливались, когда
          она исчерпана.
        </p>
      )}

      <form
        className="flex flex-wrap items-end gap-2"
        onSubmit={(e) => {
          e.preventDefault();
          save.mutate(Number(value) || 0);
        }}
      >
        <label className="flex flex-col gap-1">
          <span className="text-xs text-ink-muted">Дневной потолок, $ (0 — выключен)</span>
          {/* Шаг в центах, а не в полдолларах: браузер сам блокирует отправку формы,
              когда значение не кратно шагу, причём молча. С шагом 0.5 сумма вроде
              $3.75 просто не сохранялась бы, и понять почему было бы нечем. */}
          <Input
            type="number"
            min={0}
            max={1000}
            step="0.01"
            value={value}
            onChange={(e) => setLimit(e.target.value)}
            className="w-40"
          />
        </label>
        {dirty && (
          <Button type="submit" disabled={save.isPending}>
            {save.isPending ? "Сохраняю…" : "Сохранить"}
          </Button>
        )}
      </form>
      {error && <p className="text-sm text-bad">{error}</p>}
      <p className="text-xs text-ink-muted">
        Потолок останавливает только то, что можно повторить завтра: партию постов,
        подбор подтем, поиск источников, пробу персоны и фоновый рерайт. Приём постов из
        источников и публикация уже готового к модели не обращаются и продолжат
        работать.
      </p>
    </Card>
  );
}

function KindsCard({ usage }: { usage: LlmUsage }) {
  if (usage.by_kind.length === 0) {
    return (
      <Card>
        <h2 className="mb-2 text-sm font-semibold text-ink">На что уходит</h2>
        <EmptyState message="За выбранный период система к модели не обращалась." />
      </Card>
    );
  }
  const max = Math.max(...usage.by_kind.map((k) => k.cost_usd));
  return (
    <Card className="flex flex-col gap-3">
      <h2 className="text-sm font-semibold text-ink">На что уходит</h2>
      <div className="flex flex-col gap-2.5">
        {usage.by_kind.map((k) => (
          <div key={k.kind} className="flex flex-col gap-1">
            <div className="flex flex-wrap items-baseline justify-between gap-x-3">
              <span className="text-sm text-ink">{k.title}</span>
              <span className="font-mono text-sm tabular-nums text-ink">{usd(k.cost_usd)}</span>
            </div>
            <div className="h-1.5 w-full overflow-hidden rounded-full bg-surface-2">
              <div
                className="h-full rounded-full bg-accent"
                style={{ width: `${max > 0 ? (k.cost_usd / max) * 100 : 0}%` }}
              />
            </div>
            <span className="text-xs text-ink-muted">
              {k.calls} {plural(k.calls, "вызов", "вызова", "вызовов")}
              {k.cache_read_tokens > 0 &&
                ` · ${Math.round((k.cache_read_tokens / Math.max(1, k.cache_read_tokens + k.input_tokens)) * 100)}% входа прочитано из кэша`}
            </span>
          </div>
        ))}
      </div>
      <p className="text-xs text-ink-muted">
        Кэш — это повторно отправленный кусок запроса (персона темы). Он стоит десятую
        часть обычного входа, поэтому доля кэша прямо говорит, насколько дёшево обходятся
        повторные вызовы.
      </p>
    </Card>
  );
}

function ThemesCard({ usage }: { usage: LlmUsage }) {
  if (usage.by_theme.length === 0) return null;
  return (
    <Card className="flex flex-col gap-2">
      <h2 className="text-sm font-semibold text-ink">По темам</h2>
      <ul className="flex flex-col divide-y divide-border-soft">
        {usage.by_theme.map((t) => (
          <li
            key={t.theme_id ?? t.theme_name}
            className="flex items-baseline justify-between gap-3 py-1.5"
          >
            <span className="text-sm text-ink">{t.theme_name}</span>
            <span className="font-mono text-sm tabular-nums text-ink-muted">{usd(t.cost_usd)}</span>
          </li>
        ))}
      </ul>
    </Card>
  );
}

function DaysCard({ usage }: { usage: LlmUsage }) {
  if (usage.by_day.length === 0) return null;
  if (usage.by_day.length === 1) {
    const only = usage.by_day[0];
    return (
      <Card className="flex flex-wrap items-baseline justify-between gap-2">
        <h2 className="text-sm font-semibold text-ink">По дням</h2>
        <span className="text-sm text-ink-muted">
          Пока один день с расходом — {only.day}, {usd(only.cost_usd)}. График появится,
          когда наберётся хотя бы два.
        </span>
      </Card>
    );
  }
  const max = Math.max(...usage.by_day.map((d) => d.cost_usd));
  return (
    <Card className="flex flex-col gap-3">
      <h2 className="text-sm font-semibold text-ink">По дням</h2>
      {/* Столбики, а не таблица: всплеск расхода должен быть виден глазом — именно так
          выглядел бы день, когда планировщик ушёл в непрерывный рерайт. */}
      <div className="flex h-24 items-end gap-1 overflow-x-auto">
        {usage.by_day.map((d) => (
          <div
            key={d.day}
            title={`${d.day}: ${usd(d.cost_usd)}`}
            className="flex h-full min-w-[6px] flex-1 flex-col justify-end"
          >
            <div
              className="rounded-t bg-accent"
              style={{ height: `${max > 0 ? Math.max(2, (d.cost_usd / max) * 100) : 2}%` }}
            />
          </div>
        ))}
      </div>
      <div className="flex justify-between text-xs text-ink-muted">
        <span>{usage.by_day[0]?.day}</span>
        <span>{usage.by_day[usage.by_day.length - 1]?.day}</span>
      </div>
    </Card>
  );
}

export function Spending() {
  const [days, setDays] = useState(30);
  const { data, isLoading, error, refetch } = useQuery(llmUsageQuery(days));

  if (isLoading) return <PageSkeleton />;
  if (error) return <ErrorState message={errorText(error)} onRetry={() => refetch()} />;
  if (!data) return null;

  return (
    <div className="flex flex-col gap-4">
      <div className="flex flex-wrap items-end justify-between gap-3">
        <div>
          <h1 className="font-display text-xl text-ink">Расходы на ИИ</h1>
          <p className="text-sm text-ink-muted">
            За {data.days} дней потрачено {usd(data.total_usd)}.
          </p>
        </div>
        <div className="flex gap-1">
          {[7, 30, 60].map((d) => (
            <button
              key={d}
              type="button"
              onClick={() => setDays(d)}
              className={`min-h-11 rounded-lg px-3 text-sm transition-colors sm:min-h-0 sm:py-1.5 ${
                days === d ? "bg-accent-soft text-accent" : "text-ink-muted hover:bg-surface-2"
              }`}
            >
              {d} дней
            </button>
          ))}
        </div>
      </div>

      <BudgetCard usage={data} />
      <KindsCard usage={data} />
      <ThemesCard usage={data} />
      <DaysCard usage={data} />
    </div>
  );
}
