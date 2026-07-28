import { useEffect, useRef, useState } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { api, ApiError } from "../api/client";
import { pendingReviewCountsQuery, pendingReviewQuery, themesQuery } from "../api/queries";
import { Button, Card, EmptyState, ErrorState, Input, LoadingState, Select, TextAction, Textarea } from "../components/ui";
import { errorText } from "../lib/errors";
import { plural } from "../lib/plural";
import type { GeneratedPost, PendingReviewPost } from "../types";

function GenerateForm({ themeId }: { themeId: string }) {
  const queryClient = useQueryClient();
  // Строкой, а не числом: иначе Number() на каждый ввод залипляет ведущий ноль
  // и мешает очистить поле. В число приводим и ограничиваем 1–10 при отправке.
  const [count, setCount] = useState("3");
  const [error, setError] = useState<string | null>(null);
  const [lastGenerated, setLastGenerated] = useState<GeneratedPost[] | null>(null);

  const clampedCount = Math.min(10, Math.max(1, Number(count) || 1));

  const generate = useMutation({
    mutationFn: () =>
      api.post<GeneratedPost[]>("/candidates/generate", { theme_id: themeId, count: clampedCount }),
    onSuccess: (data) => {
      setError(null);
      setLastGenerated(data);
      queryClient.invalidateQueries({ queryKey: ["pending-review"] });
    },
    onError: (err) => {
      setLastGenerated(null);
      setError(err instanceof ApiError ? err.message : "Не удалось сгенерировать посты");
    },
  });

  return (
    <Card>
      <h2 className="mb-3 text-sm font-semibold text-ink">Сделать посты</h2>
      <p className="mb-3 text-sm text-ink-muted">
        Не хотите ждать, пока система сама отберёт лучшее — сделайте посты прямо
        сейчас: возьмём свежие посты источников темы, перепишем в стиле вашего
        бота и положим сюда на одобрение. Без вашего «Одобрить» в канал ничего
        не уйдёт.
      </p>
      <form
        className="flex flex-wrap gap-2"
        onSubmit={(e) => {
          e.preventDefault();
          setError(null);
          generate.mutate();
        }}
      >
        <Input
          type="number"
          min={1}
          max={10}
          value={count}
          onChange={(e) => setCount(e.target.value)}
          onBlur={() => setCount(String(clampedCount))}
          className="w-24"
        />
        <span title={!themeId ? "Сначала выберите тему в фильтре выше" : undefined}>
          <Button type="submit" disabled={generate.isPending || !themeId}>
            {generate.isPending ? "Генерирую…" : "Сделать посты"}
          </Button>
        </span>
        {!themeId && (
          <span className="self-center text-xs text-ink-muted">
            Выберите тему в фильтре выше — посты делаются для конкретной темы.
          </span>
        )}
      </form>
      {error && <p className="mt-2 text-sm text-bad">{error}</p>}
      {lastGenerated && (
        <p className="mt-2 text-sm text-good">
          Сгенерировано постов: {lastGenerated.length}. Смотрите список ниже.
        </p>
      )}
    </Card>
  );
}

const REJECTION_REASONS: Array<{ slug: string; label: string }> = [
  { slug: "too_long", label: "Слишком длинно" },
  { slug: "officialese", label: "Канцелярит" },
  { slug: "wrong_tone", label: "Не тот тон" },
  { slug: "watery", label: "Вода" },
  { slug: "lost_point", label: "Потерял суть" },
  { slug: "ad", label: "Реклама/мусор" },
];

function MediaPreview({ candidateId }: { candidateId: string }) {
  const [url, setUrl] = useState<string | null>(null);
  const [failed, setFailed] = useState(false);

  useEffect(() => {
    let objectUrl: string | null = null;
    let cancelled = false;
    api
      .getObjectUrl(`/candidates/${candidateId}/media`)
      .then((u) => {
        if (cancelled) {
          URL.revokeObjectURL(u);
          return;
        }
        objectUrl = u;
        setUrl(u);
      })
      .catch(() => setFailed(true));
    return () => {
      cancelled = true;
      if (objectUrl) URL.revokeObjectURL(objectUrl);
    };
  }, [candidateId]);

  if (failed) {
    return <p className="text-xs text-ink-muted">Фото недоступно (пост в источнике мог быть удалён).</p>;
  }
  if (!url) {
    return <p className="text-xs text-ink-muted">Загрузка фото…</p>;
  }
  return <img src={url} alt="Медиа поста" className="max-h-64 w-auto rounded-lg" />;
}

function PendingReviewCard({
  post,
  themeName,
  onApproved,
}: {
  post: PendingReviewPost;
  themeName: string | null;
  onApproved: (post: PendingReviewPost) => void;
}) {
  const queryClient = useQueryClient();
  const [error, setError] = useState<string | null>(null);
  const [showRaw, setShowRaw] = useState(false);
  const [choosingReason, setChoosingReason] = useState(false);
  const [editing, setEditing] = useState(false);
  const [draft, setDraft] = useState(post.rewritten_text);

  const invalidate = () => {
    queryClient.invalidateQueries({ queryKey: ["pending-review"] });
    queryClient.invalidateQueries({ queryKey: ["pending-review-counts"] });
  };

  const approve = useMutation({
    mutationFn: () => api.post(`/candidates/${post.candidate_id}/approve`),
    onSuccess: () => {
      setError(null);
      onApproved(post);
      invalidate();
    },
    onError: (err) => {
      if (err instanceof ApiError && err.status === 409) {
        invalidate();
        return;
      }
      setError(err instanceof ApiError ? err.message : "Не удалось одобрить");
    },
  });

  const reject = useMutation({
    mutationFn: (reason: string | null) =>
      api.post(`/candidates/${post.candidate_id}/reject`, { reason }),
    onSuccess: () => {
      setError(null);
      invalidate();
    },
    onError: (err) => {
      if (err instanceof ApiError && err.status === 409) {
        invalidate();
        return;
      }
      setError(err instanceof ApiError ? err.message : "Не удалось отклонить");
    },
  });

  const saveEdit = useMutation({
    mutationFn: () => api.put(`/candidates/${post.candidate_id}/text`, { text: draft }),
    onSuccess: () => {
      setError(null);
      setEditing(false);
      invalidate();
    },
    onError: (err) => setError(err instanceof ApiError ? err.message : "Не удалось сохранить правку"),
  });

  const busy = approve.isPending || reject.isPending || saveEdit.isPending;

  return (
    <Card className="flex flex-col gap-3">
      <div className="flex items-center justify-between gap-2">
        <div className="flex flex-wrap items-center gap-2">
          {/* Тема — первым делом: одобрение публикует пост в канал именно этой
              темы, и раньше на карточке её не было вовсе (UX-аудит, №1). */}
          <span
            title="Тема, в чей канал уйдёт пост после одобрения"
            className={`rounded-full px-2 py-0.5 text-xs font-medium whitespace-nowrap ${
              themeName ? "bg-accent-soft text-ink" : "bg-bad-soft text-bad"
            }`}
          >
            {themeName ?? "без темы"}
          </span>
          <span className="text-sm font-medium text-ink">{post.source_channel_title}</span>
          {post.has_media && (
            <span className="rounded-full bg-surface-2 px-2 py-0.5 text-xs text-ink-muted">
              📷 с фото
            </span>
          )}
        </div>
        {post.score !== null && (
          <span
            title="Оценка виральности исходного поста: как быстро он набирал просмотры и пересылки у конкурента. Чем выше — тем «залётнее» тема."
            className="rounded-full bg-surface-2 px-2 py-0.5 text-xs text-ink-muted whitespace-nowrap"
          >
            виральность {post.score.toFixed(2)}
          </span>
        )}
      </div>

      {post.has_media && <MediaPreview candidateId={post.candidate_id} />}

      {editing ? (
        <>
          <Textarea
            value={draft}
            onChange={(e) => setDraft(e.target.value)}
            rows={8}
            className="text-sm"
          />
          <div className="flex gap-2">
            <Button onClick={() => saveEdit.mutate()} disabled={busy || !draft.trim()}>
              Сохранить
            </Button>
            <Button
              variant="secondary"
              onClick={() => {
                setDraft(post.rewritten_text);
                setEditing(false);
                setError(null);
              }}
              disabled={busy}
            >
              Отмена
            </Button>
          </div>
        </>
      ) : (
        <>
          <p className="whitespace-pre-wrap text-sm text-ink">{post.rewritten_text}</p>

          <div className="flex flex-wrap gap-x-4 gap-y-1">
            <TextAction onClick={() => setShowRaw((v) => !v)}>
              {showRaw ? "Скрыть оригинал" : "Показать оригинал"}
            </TextAction>
            <TextAction
              onClick={() => {
                setDraft(post.rewritten_text);
                setEditing(true);
              }}
            >
              Редактировать
            </TextAction>
          </div>
          {showRaw && (
            <p className="whitespace-pre-wrap rounded-lg bg-surface-2 p-3 text-xs text-ink-muted">
              {post.raw_text}
            </p>
          )}

          {choosingReason ? (
            <div className="flex flex-col gap-2">
              <p className="text-xs text-ink-muted">
                Что не так? Причины копятся у бота темы как подсказки для доводки стиля.
              </p>
              <div className="flex flex-wrap gap-2">
                {REJECTION_REASONS.map((r) => (
                  <button
                    key={r.slug}
                    type="button"
                    disabled={busy}
                    onClick={() => reject.mutate(r.slug)}
                    className="inline-flex min-h-11 items-center rounded-full bg-bad-soft px-3 py-1 text-xs font-medium text-bad hover:opacity-80 sm:min-h-0"
                  >
                    {r.label}
                  </button>
                ))}
                <button
                  type="button"
                  disabled={busy}
                  onClick={() => reject.mutate(null)}
                  className="inline-flex min-h-11 items-center rounded-full bg-surface-2 px-3 py-1 text-xs text-ink-muted hover:text-ink sm:min-h-0"
                >
                  Без причины
                </button>
                <button
                  type="button"
                  onClick={() => setChoosingReason(false)}
                  className="inline-flex min-h-11 items-center rounded-full px-3 py-1 text-xs text-ink-muted underline decoration-dotted hover:text-ink sm:min-h-0"
                >
                  Отмена
                </button>
              </div>
            </div>
          ) : (
            <div className="flex gap-2">
              <Button onClick={() => approve.mutate()} disabled={busy}>
                Одобрить
              </Button>
              <Button variant="danger" onClick={() => setChoosingReason(true)} disabled={busy}>
                Отклонить
              </Button>
            </div>
          )}
        </>
      )}
      {error && <p className="text-xs text-bad">{error}</p>}
    </Card>
  );
}

/* Плашка отмены: одобрение — самое дешёвое действие в очереди (одна клавиша,
   без подтверждения) и при этом до сих пор было необратимым. Подтверждение
   убило бы скорость разбора, поэтому вместо него окно на несколько секунд
   (UX-аудит, №2). */
const UNDO_SECONDS = 8;

function UndoBar({
  post,
  onDone,
}: {
  post: PendingReviewPost;
  onDone: () => void;
}) {
  const queryClient = useQueryClient();
  const [left, setLeft] = useState(UNDO_SECONDS);
  const [error, setError] = useState<string | null>(null);

  const undo = useMutation({
    mutationFn: () => api.post(`/candidates/${post.candidate_id}/unapprove`),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["pending-review"] });
      onDone();
    },
    onError: (err) =>
      setError(err instanceof ApiError ? err.message : "Не удалось отменить одобрение"),
  });

  useEffect(() => {
    if (error) return; // с ошибкой на экране не прячем плашку по таймеру
    if (left <= 0) {
      onDone();
      return;
    }
    const t = setTimeout(() => setLeft((v) => v - 1), 1000);
    return () => clearTimeout(t);
  }, [left, error, onDone]);

  return (
    <div className="flex flex-wrap items-center justify-between gap-2 rounded-lg bg-good-soft p-3 text-sm text-good">
      <span className="min-w-0 truncate">
        {error ? error : `Одобрено: ${post.rewritten_text.slice(0, 60)}…`}
      </span>
      {error ? (
        <button
          type="button"
          onClick={onDone}
          className="shrink-0 min-h-[32px] underline underline-offset-2"
        >
          Понятно
        </button>
      ) : (
        <button
          type="button"
          onClick={() => undo.mutate()}
          disabled={undo.isPending}
          className="shrink-0 min-h-[32px] rounded-lg border border-current px-2 py-1 text-xs font-medium hover:opacity-80"
        >
          Отменить ({left})
        </button>
      )}
    </div>
  );
}

/* Вкладки тем со счётчиками — вместо выпадающего фильтра. Очередь копится
   общим пулом, и при нескольких темах непонятно, где именно затор: список
   один, а счётчик один на всех. Вкладки показывают распределение сразу и
   переключают разбор на конкретную тему одним нажатием — тот же приём, что на
   рабочем столе темы. */
function ThemeTabs({
  themes,
  counts,
  activeId,
  onSelect,
}: {
  themes: Array<{ id: string; name: string }>;
  counts: Map<string | null, number>;
  activeId: string;
  onSelect: (id: string) => void;
}) {
  const total = [...counts.values()].reduce((a, b) => a + b, 0);
  const orphan = counts.get(null) ?? 0;
  // Темы без единого поста в очереди не показываем: вкладка, по которой всегда
  // пусто, — это шум, а не навигация. Исключение — выбранная тема: если её
  // только что разобрали до нуля, вкладка не должна исчезать из-под курсора,
  // иначе непонятно, где ты находишься и почему список пуст.
  const withPosts = themes.filter((t) => (counts.get(t.id) ?? 0) > 0 || t.id === activeId);

  const chip = (active: boolean) =>
    `inline-flex min-h-11 shrink-0 items-center gap-1.5 rounded-full px-3 py-1.5 text-xs font-medium transition-colors sm:min-h-0 ${
      active ? "bg-accent text-accent-ink" : "bg-surface-2 text-ink-muted hover:text-ink"
    }`;

  return (
    <div className="-mx-1 flex flex-nowrap gap-2 overflow-x-auto px-1 pb-1">
      <button type="button" className={chip(activeId === "")} onClick={() => onSelect("")}>
        Все темы
        <span className="font-mono tabular-nums opacity-70">{total}</span>
      </button>
      {withPosts.map((t) => (
        <button
          key={t.id}
          type="button"
          className={chip(activeId === t.id)}
          onClick={() => onSelect(t.id)}
        >
          <span className="max-w-[14rem] truncate">{t.name}</span>
          <span className="font-mono tabular-nums opacity-70">{counts.get(t.id) ?? 0}</span>
        </button>
      ))}
      {orphan > 0 && (
        <span
          title="Посты источников, у которых удалили тему. Отклоните их — публиковать такие некуда."
          className="inline-flex min-h-11 shrink-0 items-center gap-1.5 rounded-full bg-bad-soft px-3 py-1.5 text-xs font-medium text-bad sm:min-h-0"
        >
          без темы
          <span className="font-mono tabular-nums opacity-70">{orphan}</span>
        </span>
      )}
    </div>
  );
}

/* Плашка отмены массового отклонения. «Отклонить все» стирает очередь одним
   нажатием — без отмены это была бы самая дорогая ошибка в панели. */
function BulkUndoBar({
  count,
  ids,
  onDone,
}: {
  count: number;
  ids: string[];
  onDone: () => void;
}) {
  const queryClient = useQueryClient();
  const [error, setError] = useState<string | null>(null);

  const undo = useMutation({
    mutationFn: () => api.post<{ restored: number }>("/candidates/restore", { candidate_ids: ids }),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["pending-review"] });
      queryClient.invalidateQueries({ queryKey: ["pending-review-counts"] });
      onDone();
    },
    onError: (err) =>
      setError(err instanceof ApiError ? err.message : "Не удалось вернуть посты"),
  });

  return (
    <div className="flex flex-wrap items-center justify-between gap-2 rounded-lg bg-surface-2 p-3 text-sm text-ink">
      <span>
        {error ??
          `Отклонено ${count} ${plural(count, "пост", "поста", "постов")}. Рейтинг источников не изменён.`}
      </span>
      <div className="flex gap-2">
        <Button variant="secondary" onClick={() => undo.mutate()} disabled={undo.isPending}>
          Вернуть в проверку
        </Button>
        <Button variant="secondary" onClick={onDone}>
          Готово
        </Button>
      </div>
    </div>
  );
}

export function Review() {
  const queryClient = useQueryClient();
  const themes = useQuery(themesQuery());
  /* Один селектор темы на всю страницу. Раньше он стоял внутри «Сделать посты»
     и НЕ фильтровал список под собой — оператор естественно читал его как
     фильтр и разбирал вперемешку посты всех тем (UX-аудит, №1). */
  const [themeId, setThemeId] = useState("");
  /* По умолчанию — сначала самые виральные: бэкенд отдаёт по created_at desc,
     и «разобрать топ-5 и хватит» было невозможно — приходилось просматривать
     все, чтобы не пропустить залётный пост (UX-аудит, №7). */
  const [sortBy, setSortBy] = useState<"score" | "new">("score");
  /* На телефоне очередь из 20 карточек — это лента почти в 6000px, пролистать
     её до нужного поста невозможно (UX-аудит, №17). Показываем по одному: сразу
     после решения карточка уходит из списка, и следующий пост встаёт на её
     место — разбор превращается в стопку, а не в скроллинг. На десктопе, где
     список обозрим, по умолчанию остаётся лента. */
  const [oneByOne, setOneByOne] = useState(
    () => typeof window !== "undefined" && window.matchMedia("(max-width: 640px)").matches,
  );
  const { data, isLoading, error, refetch } = useQuery(pendingReviewQuery(themeId || undefined));
  const [hotkeyError, setHotkeyError] = useState<string | null>(null);
  const [approved, setApproved] = useState<PendingReviewPost | null>(null);
  const [bulk, setBulk] = useState<{ count: number; ids: string[] } | null>(null);
  const [bulkError, setBulkError] = useState<string | null>(null);
  const counts = useQuery(pendingReviewCountsQuery());

  const themeNameById = new Map(themes.data?.map((t) => [t.id, t.name]) ?? []);
  const countByTheme = new Map<string | null, number>(
    counts.data?.map((c) => [c.theme_id, c.count]) ?? [],
  );

  const rejectAll = useMutation({
    mutationFn: () =>
      api.post<{ count: number; candidate_ids: string[] }>("/candidates/reject-all", {
        theme_id: themeId || null,
      }),
    onSuccess: (r) => {
      setBulkError(null);
      setBulk({ count: r.count, ids: r.candidate_ids });
      queryClient.invalidateQueries({ queryKey: ["pending-review"] });
      queryClient.invalidateQueries({ queryKey: ["pending-review-counts"] });
    },
    onError: (err) =>
      setBulkError(err instanceof ApiError ? err.message : "Не удалось отклонить"),
  });

  // Из счётчиков, а не из длины списка: кнопка должна называть то число,
  // которое реально уйдёт в отклонение, даже если список ещё грузится.
  const visibleCount = themeId
    ? (countByTheme.get(themeId) ?? 0)
    : [...countByTheme.values()].reduce((a, b) => a + b, 0);

  const visible = [...(data ?? [])].sort((a, b) =>
    sortBy === "score"
      ? (b.score ?? -1) - (a.score ?? -1)
      : new Date(b.created_at).getTime() - new Date(a.created_at).getTime(),
  );

  // В ref, а не в замыкании: слушатель клавиатуры вешается один раз, а верхний
  // пост меняется после каждого одобрения — ref всегда указывает на актуальный.
  // Важно, что это верхний ВИДИМЫЙ пост (после фильтра и сортировки), иначе
  // хоткей обрабатывал бы не то, что оператор видит первым.
  const topPostRef = useRef<PendingReviewPost | null>(null);
  topPostRef.current = visible[0] ?? null;
  const busyRef = useRef(false);

  useEffect(() => {
    const onKey = (e: KeyboardEvent) => {
      // Не перехватываем печать в полях форм.
      const tag = (e.target as HTMLElement | null)?.tagName;
      if (tag === "INPUT" || tag === "TEXTAREA" || tag === "SELECT") return;
      if (e.metaKey || e.ctrlKey || e.altKey) return;
      const key = e.key.toLowerCase();
      const approveKey = key === "a" || key === "ф";
      const rejectKey = key === "d" || key === "в";
      if (!approveKey && !rejectKey) return;
      const post = topPostRef.current;
      if (!post || busyRef.current) return;
      busyRef.current = true;
      api
        .post(`/candidates/${post.candidate_id}/${approveKey ? "approve" : "reject"}`)
        .then(() => {
          setHotkeyError(null);
          // Окно отмены работает и для хоткея — именно им промахнуться проще
          // всего, ради него оно и делалось.
          if (approveKey) setApproved(post);
        })
        .catch((err) => {
          // 409 — пост уже обработан (вторая вкладка, двойное нажатие,
          // массовое отклонение рядом). Это рассинхрон списка, а не сбой:
          // краснеть незачем, invalidate ниже всё поправит.
          if (err instanceof ApiError && err.status === 409) {
            setHotkeyError(null);
            return;
          }
          setHotkeyError(err instanceof ApiError ? err.message : "Не удалось обработать пост");
        })
        .finally(() => {
          busyRef.current = false;
          queryClient.invalidateQueries({ queryKey: ["pending-review"] });
          queryClient.invalidateQueries({ queryKey: ["pending-review-counts"] });
        });
    };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [queryClient]);

  return (
    <div className="flex flex-col gap-6">
      <h1 className="text-xl font-semibold text-ink">Проверка постов</h1>

      <ThemeTabs
        themes={themes.data ?? []}
        counts={countByTheme}
        activeId={themeId}
        onSelect={setThemeId}
      />

      <Card className="flex flex-col gap-2">
        <div className="flex flex-col gap-2 sm:flex-row sm:items-end">
          <label className="flex flex-col gap-1 text-xs text-ink-muted sm:w-64">
            Порядок
            <Select
              value={sortBy}
              onChange={(e) => setSortBy(e.target.value as "score" | "new")}
            >
              <option value="score">Сначала самые виральные</option>
              <option value="new">Сначала новые</option>
            </Select>
          </label>
          <div className="flex flex-1 justify-end">
            <Button
              variant="danger"
              disabled={rejectAll.isPending || visibleCount === 0}
              onClick={() => {
                const where = themeId
                  ? `в теме «${themeNameById.get(themeId) ?? "выбранной"}»`
                  : "ВО ВСЕХ ТЕМАХ";
                if (
                  window.confirm(
                    `Отклонить все ${visibleCount} ${plural(visibleCount, "пост", "поста", "постов")} ${where}?\n\n` +
                      "Очередь очистится целиком. Рейтинг источников не изменится, и бот ничему не научится — " +
                      "для обучения отклоняйте по одному с причиной.\n\nСразу после можно будет вернуть всё обратно.",
                  )
                ) {
                  rejectAll.mutate();
                }
              }}
            >
              {rejectAll.isPending
                ? "Отклоняю…"
                : `Отклонить все${themeId ? " в теме" : ""} (${visibleCount})`}
            </Button>
          </div>
        </div>
        <p className="text-xs text-ink-muted">
          Вкладка темы действует и на список ниже, и на кнопку «Сделать посты», и на массовое
          отклонение.
        </p>
        {bulkError && <p className="text-sm text-bad">{bulkError}</p>}
      </Card>

      {bulk && (
        <BulkUndoBar count={bulk.count} ids={bulk.ids} onDone={() => setBulk(null)} />
      )}

      <GenerateForm themeId={themeId} />

      <div className="flex flex-col gap-3">
        <div className="flex flex-wrap items-center justify-between gap-2">
          <h2 className="text-sm font-semibold text-ink">
            На одобрении{visible.length > 0 && ` (${visible.length})`}
          </h2>
          <div className="flex flex-wrap items-center gap-x-4 gap-y-1">
            {visible.length > 1 && (
              <TextAction onClick={() => setOneByOne((v) => !v)}>
                {oneByOne ? "Показать списком" : "Разбирать по одному"}
              </TextAction>
            )}
            {visible.length > 0 && (
              <span className="hidden text-xs text-ink-muted sm:inline">
                Клавиши: <kbd className="rounded border border-border px-1">A</kbd> — одобрить,{" "}
                <kbd className="rounded border border-border px-1">D</kbd> — отклонить верхний пост
              </span>
            )}
          </div>
        </div>

        {approved && <UndoBar post={approved} onDone={() => setApproved(null)} />}

        {hotkeyError && <p className="text-xs text-bad">{hotkeyError}</p>}
        {isLoading && <LoadingState />}
        {error && <ErrorState message={errorText(error)} onRetry={() => refetch()} />}
        {data && visible.length === 0 && (
          <Card>
            <EmptyState
              message={
                themeId
                  ? "В этой теме нечего одобрять — выберите другую тему или сделайте посты выше."
                  : "Нечего одобрять — сгенерируйте посты выше."
              }
            />
          </Card>
        )}
        {(oneByOne ? visible.slice(0, 1) : visible).map((post) => (
          <PendingReviewCard
            key={post.candidate_id}
            post={post}
            themeName={post.theme_id ? (themeNameById.get(post.theme_id) ?? null) : null}
            onApproved={setApproved}
          />
        ))}

        {oneByOne && visible.length > 1 && (
          <p className="text-center text-xs text-ink-muted">
            Дальше в очереди ещё {visible.length - 1}{" "}
            {plural(visible.length - 1, "пост", "поста", "постов")}. Решите по этому — следующий
            встанет на его место.
          </p>
        )}
      </div>
    </div>
  );
}
