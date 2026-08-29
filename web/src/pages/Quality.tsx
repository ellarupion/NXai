import { useEffect, useState } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useNavigate, useParams } from "react-router-dom";
import { api, ApiError } from "../api/client";
import { channelBotsQuery, qualityRunQuery, qualityRunsQuery, themesQuery } from "../api/queries";
import {
  Button,
  Card,
  CardSkeleton,
  EmptyState,
  ErrorState,
  Input,
  PageSkeleton,
  Select,
  TextAction,
  Textarea,
} from "../components/ui";
import { errorText } from "../lib/errors";
import { plural } from "../lib/plural";
import type { QualityPair, QualityRun, QualityVerdict } from "../types";

/* Замер качества рерайта.

   Про качество текстов не было ни одного числа: поменяли персону — стало лучше или
   хуже, судили по ощущению от последних просмотренных постов. Это ровно тот способ,
   которым люди подтверждают то, во что уже верят.

   Страница отвечает числом. На одинаковом наборе настоящих исходников готовятся два
   варианта каждого поста — текущей персоной и той, что проверяют, — судья сравнивает
   их вслепую и дважды, с перестановкой. На выходе «новый вариант выигрывает в 9 из
   12».

   Пары показываются целиком не для красоты: число без возможности посмотреть, за что
   именно присудили победу, — такое же «поверьте мне», от которого уходим. */

const SIZE_MIN = 5;
const SIZE_MAX = 30;

const STATUS_TITLES: Record<string, string> = {
  pending: "заказан, ждёт очереди",
  running: "идёт прямо сейчас",
  done: "готов",
  failed: "сорвался",
};

const VERDICT_TITLES: Record<QualityVerdict, string> = {
  baseline: "текущая",
  variant: "новая",
  tie: "ничья",
};

function verdictClass(verdict: QualityVerdict | null): string {
  if (verdict === "variant") return "bg-good-soft text-good";
  if (verdict === "baseline") return "bg-info-soft text-info";
  return "bg-surface-2 text-ink-muted";
}

function Bar({ run }: { run: QualityRun }) {
  const total = run.wins_baseline + run.wins_variant + run.ties;
  if (!total) return null;
  const parts: { key: string; n: number; cls: string; label: string }[] = [
    { key: "b", n: run.wins_baseline, cls: "bg-info", label: "текущая" },
    { key: "t", n: run.ties, cls: "bg-border", label: "ничья" },
    { key: "v", n: run.wins_variant, cls: "bg-good", label: "новая" },
  ];
  return (
    <div className="flex flex-col gap-1">
      {/* h-full на сегментах обязателен: без него они схлопываются в ноль внутри
          родителя с автоматической высотой — уже попадались на графике расходов. */}
      <div className="flex h-2.5 w-full overflow-hidden rounded-full bg-surface-2">
        {parts
          .filter((p) => p.n > 0)
          .map((p) => (
            <div
              key={p.key}
              className={`h-full ${p.cls}`}
              style={{ width: `${(p.n / total) * 100}%` }}
              title={`${p.label}: ${p.n}`}
            />
          ))}
      </div>
      <div className="flex flex-wrap gap-x-3 text-xs text-ink-faint">
        <span>текущая {run.wins_baseline}</span>
        <span>ничья {run.ties}</span>
        <span>новая {run.wins_variant}</span>
      </div>
    </div>
  );
}

function NewRunForm({ themeId }: { themeId: string }) {
  const queryClient = useQueryClient();
  const bots = useQuery(channelBotsQuery());
  const [title, setTitle] = useState("");
  const [variant, setVariant] = useState("");
  const [size, setSize] = useState("12");
  const [error, setError] = useState<string | null>(null);

  const bot = (bots.data ?? []).find((b) => b.theme_id === themeId && b.role === "theme");

  const create = useMutation({
    mutationFn: () =>
      api.post("/quality-runs", {
        theme_id: themeId,
        title,
        variant_persona: variant,
        size: Math.min(SIZE_MAX, Math.max(SIZE_MIN, Number(size) || 12)),
      }),
    onSuccess: () => {
      setError(null);
      setVariant("");
      setTitle("");
      queryClient.invalidateQueries({ queryKey: ["quality-runs"] });
    },
    onError: (e) => setError(errorText(e as ApiError)),
  });

  return (
    <Card className="flex flex-col gap-4">
      <div className="flex flex-col gap-1">
        <h2 className="text-sm font-semibold text-ink">Проверить новую персону</h2>
        <p className="text-xs text-ink-muted">
          Система перепишет одни и те же посты дважды — как сейчас и по-новому, — а
          судья сравнит варианты вслепую, не зная, где чей, и дважды, меняя их местами.
          Замер идёт несколько минут: считает его планировщик, страница обновится сама.
        </p>
      </div>

      {bot ? (
        <details className="rounded-lg bg-surface-2 p-3">
          <summary className="cursor-pointer text-xs text-ink-muted">
            Персона, которая работает сейчас — с ней и будем сравнивать
          </summary>
          <p className="mt-2 whitespace-pre-wrap text-xs text-ink-muted">
            {bot.persona_prompt || "у бота задан только конструктор персоны"}
          </p>
        </details>
      ) : (
        <p className="text-sm text-bad">
          У темы нет бота — сравнивать не с чем: текущая персона живёт у него.
        </p>
      )}

      <label className="flex flex-col gap-1">
        <span className="text-xs text-ink-muted">Название замера — чтобы отличать в списке</span>
        <Input
          value={title}
          onChange={(e) => setTitle(e.target.value)}
          placeholder="Например: покороче и без эмодзи"
        />
      </label>

      <label className="flex flex-col gap-1">
        <span className="text-xs text-ink-muted">Новая персона целиком</span>
        <Textarea
          value={variant}
          onChange={(e) => setVariant(e.target.value)}
          rows={8}
          placeholder="Пиши коротко, дерзко, без канцелярита…"
        />
      </label>

      <label className="flex flex-col gap-1">
        <span className="text-xs text-ink-muted">
          Сколько постов сравнить ({SIZE_MIN}–{SIZE_MAX}). Меньше — быстрее и дешевле,
          больше — надёжнее вывод.
        </span>
        <Input
          type="number"
          min={SIZE_MIN}
          max={SIZE_MAX}
          value={size}
          onChange={(e) => setSize(e.target.value)}
          className="w-24"
        />
      </label>

      {error && <p className="text-sm text-bad">{error}</p>}

      <div>
        <Button
          onClick={() => create.mutate()}
          disabled={!bot || !variant.trim() || create.isPending}
        >
          {create.isPending ? "Заказываю…" : "Замерить"}
        </Button>
      </div>
    </Card>
  );
}

function PairCard({ pair, index }: { pair: QualityPair; index: number }) {
  const [open, setOpen] = useState(false);
  const disagreed =
    pair.verdict_direct && pair.verdict_swapped && pair.verdict_direct !== pair.verdict_swapped;

  return (
    <div className="flex flex-col gap-2 border-t border-border-soft py-3 first:border-t-0">
      <div className="flex flex-wrap items-center gap-2">
        <span className="text-xs text-ink-faint">Пост {index + 1}</span>
        <span
          className={`rounded-full px-2 py-0.5 text-xs font-medium ${verdictClass(pair.verdict)}`}
        >
          {pair.verdict ? VERDICT_TITLES[pair.verdict] : "не судили"}
        </span>
        {disagreed && (
          <span
            className="text-xs text-ink-faint"
            title="Судья выбрал разное до и после перестановки — значит, разница между текстами меньше, чем влияние их порядка."
          >
            судья поменял мнение от перестановки
          </span>
        )}
        <TextAction className="ml-auto" onClick={() => setOpen((v) => !v)}>
          {open ? "Свернуть" : "Показать тексты"}
        </TextAction>
      </div>
      {pair.reason && <p className="text-sm text-ink-muted">{pair.reason}</p>}
      {open && (
        <div className="flex flex-col gap-3">
          <div>
            <p className="mb-1 text-xs text-ink-faint">Исходник конкурента</p>
            <p className="whitespace-pre-wrap rounded-lg bg-surface-2 p-3 text-xs text-ink-muted">
              {pair.source_text}
            </p>
          </div>
          <div className="grid gap-3 md:grid-cols-2">
            <div>
              <p className="mb-1 text-xs text-info">Текущая персона</p>
              <p className="whitespace-pre-wrap rounded-lg bg-surface-2 p-3 text-sm text-ink">
                {pair.baseline_text || "—"}
              </p>
            </div>
            <div>
              <p className="mb-1 text-xs text-good">Новая персона</p>
              <p className="whitespace-pre-wrap rounded-lg bg-surface-2 p-3 text-sm text-ink">
                {pair.variant_text || "—"}
              </p>
            </div>
          </div>
        </div>
      )}
    </div>
  );
}

function RunDetail({ runId, onBack }: { runId: string; onBack: () => void }) {
  const queryClient = useQueryClient();
  const { data, isLoading, error, refetch } = useQuery(qualityRunQuery(runId));
  const remove = useMutation({
    mutationFn: () => api.delete(`/quality-runs/${runId}`),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["quality-runs"] });
      onBack();
    },
  });

  if (isLoading) return <PageSkeleton cards={2} />;
  if (error) return <ErrorState message={errorText(error)} onRetry={() => refetch()} />;
  if (!data) return null;

  return (
    <div className="flex flex-col gap-6">
      <div className="flex flex-wrap items-center gap-3">
        <TextAction onClick={onBack}>← Все замеры</TextAction>
        <h1 className="text-xl font-semibold text-ink">{data.title || "Замер без названия"}</h1>
      </div>

      <Card className="flex flex-col gap-4">
        <div className="flex flex-wrap items-baseline gap-x-3">
          <span className="text-sm text-ink-muted">{STATUS_TITLES[data.status] ?? data.status}</span>
          {data.theme_name && <span className="text-xs text-ink-faint">{data.theme_name}</span>}
          {data.status === "running" && (
            <span className="text-xs text-ink-faint">
              посчитано {data.judged} из {data.size}
            </span>
          )}
        </div>
        {data.status === "done" && (
          <>
            <p className="text-base text-ink">{data.summary}</p>
            <Bar run={data} />
          </>
        )}
        {data.status === "failed" && data.error && <p className="text-sm text-bad">{data.error}</p>}
        <div>
          <Button
            variant="danger"
            onClick={() => {
              if (window.confirm("Удалить замер вместе со всеми парами?")) remove.mutate();
            }}
            disabled={remove.isPending}
          >
            Удалить замер
          </Button>
        </div>
      </Card>

      <Card className="flex flex-col gap-1">
        <h2 className="text-sm font-semibold text-ink">Пары</h2>
        <p className="mb-2 text-xs text-ink-muted">
          Здесь видно, за что судья присудил победу. Число без возможности посмотреть
          тексты — такое же «поверьте мне», от которого уходим.
        </p>
        {data.pairs.length === 0 && <EmptyState message="Пар пока нет." />}
        {data.pairs.map((pair, i) => (
          <PairCard key={pair.id} pair={pair} index={i} />
        ))}
      </Card>
    </div>
  );
}

export function Quality() {
  const { runId } = useParams();
  const navigate = useNavigate();
  const themes = useQuery(themesQuery());
  const [themeId, setThemeId] = useState("");
  const runs = useQuery(qualityRunsQuery(themeId || undefined));

  // Первая тема по умолчанию: без выбранной темы форма заказа не работает, а
  // пустой список тем в селекте выглядит как поломка.
  useEffect(() => {
    if (!themeId && themes.data?.length) setThemeId(themes.data[0].id);
  }, [themeId, themes.data]);

  if (runId) return <RunDetail runId={runId} onBack={() => navigate("/quality")} />;

  return (
    <div className="flex flex-col gap-6">
      <div className="flex flex-col gap-1">
        <h1 className="text-xl font-semibold text-ink">Качество рерайта</h1>
        <p className="text-sm text-ink-muted">
          Стало лучше или хуже после правки персоны — вопрос, на который раньше не было
          ответа: судили по последним просмотренным постам. Здесь на него отвечает число.
        </p>
      </div>

      <div className="flex flex-wrap gap-2">
        <Select value={themeId} onChange={(e) => setThemeId(e.target.value)}>
          {(themes.data ?? []).map((t) => (
            <option key={t.id} value={t.id}>
              {t.name}
            </option>
          ))}
        </Select>
      </div>

      {themeId && <NewRunForm themeId={themeId} />}

      <Card className="flex flex-col gap-3">
        <h2 className="text-sm font-semibold text-ink">Прошлые замеры</h2>
        {runs.isLoading && <CardSkeleton rows={3} />}
        {runs.error && (
          <ErrorState message={errorText(runs.error)} onRetry={() => runs.refetch()} />
        )}
        {runs.data?.length === 0 && (
          <EmptyState message="Замеров пока не было. Закажите первый — он покажет, стоит ли менять персону." />
        )}
        {runs.data?.map((run) => (
          <button
            key={run.id}
            type="button"
            onClick={() => navigate(`/quality/${run.id}`)}
            className="flex flex-col gap-2 rounded-lg border border-border-soft p-3 text-left transition-colors hover:bg-surface-2"
          >
            <div className="flex flex-wrap items-baseline gap-x-2">
              <span className="text-sm font-medium text-ink">
                {run.title || "Замер без названия"}
              </span>
              <span className="text-xs text-ink-faint">
                {STATUS_TITLES[run.status] ?? run.status}
                {/* Замер идёт минутами: без продвижения строка «идёт прямо сейчас»
                    читается как зависание. Проверка на число — не перестраховка:
                    при обновлении панель может обогнать API, и без неё на экране
                    появлялось «посчитано undefined из 8» (видел на живой панели). */}
                {run.status === "running" &&
                  typeof run.judged === "number" &&
                  ` — посчитано ${run.judged} из ${run.size}`}
              </span>
              <span className="ml-auto text-xs text-ink-faint">
                {new Date(run.created_at).toLocaleDateString("ru-RU")} · {run.size}{" "}
                {plural(run.size, "пост", "поста", "постов")}
              </span>
            </div>
            {run.status === "done" && (
              <>
                <p className="text-sm text-ink-muted">{run.summary}</p>
                <Bar run={run} />
              </>
            )}
            {run.status === "failed" && run.error && (
              <p className="text-sm text-bad">{run.error}</p>
            )}
          </button>
        ))}
      </Card>
    </div>
  );
}
