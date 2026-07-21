import { useState } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { api, ApiError } from "../api/client";
import { pendingReviewQuery, themesQuery } from "../api/queries";
import {
  Button,
  Card,
  EmptyState,
  ErrorState,
  Input,
  LoadingState,
  Select,
  Textarea,
} from "../components/ui";
import type { GeneratedPost, PendingReviewPost } from "../types";

function GenerateForm() {
  const queryClient = useQueryClient();
  const themes = useQuery(themesQuery());
  const [themeId, setThemeId] = useState("");
  const [count, setCount] = useState(3);
  const [error, setError] = useState<string | null>(null);
  const [lastGenerated, setLastGenerated] = useState<GeneratedPost[] | null>(null);

  const generate = useMutation({
    mutationFn: () => api.post<GeneratedPost[]>("/candidates/generate", { theme_id: themeId, count }),
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
        Принудительный внеочередной прогон пайплайна на тему: докачивает историю
        источников, если свежих постов не хватает, минует обычное ожидание метрик,
        дедуп и рерайт — не ждёт штатных 30 мин/2 ч/6 ч. Результат уходит сюда же,
        в очередь на одобрение, а не сразу в автопаблиш.
      </p>
      <form
        className="flex flex-wrap gap-2"
        onSubmit={(e) => {
          e.preventDefault();
          setError(null);
          generate.mutate();
        }}
      >
        <Select value={themeId} onChange={(e) => setThemeId(e.target.value)} required className="flex-1">
          <option value="">— выберите тему —</option>
          {themes.data?.map((theme) => (
            <option key={theme.id} value={theme.id}>
              {theme.name}
            </option>
          ))}
        </Select>
        <Input
          type="number"
          min={1}
          max={10}
          value={count}
          onChange={(e) => setCount(Number(e.target.value))}
          className="w-24"
        />
        <span title={!themeId ? "Сначала выберите тему" : undefined}>
          <Button type="submit" disabled={generate.isPending || !themeId}>
            {generate.isPending ? "Генерирую…" : "Сделать посты"}
          </Button>
        </span>
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

function PendingReviewCard({ post }: { post: PendingReviewPost }) {
  const queryClient = useQueryClient();
  const [error, setError] = useState<string | null>(null);
  const [showRaw, setShowRaw] = useState(false);
  const [editing, setEditing] = useState(false);
  const [draft, setDraft] = useState(post.rewritten_text);

  const invalidate = () => queryClient.invalidateQueries({ queryKey: ["pending-review"] });

  const approve = useMutation({
    mutationFn: () => api.post(`/candidates/${post.candidate_id}/approve`),
    onSuccess: () => {
      setError(null);
      invalidate();
    },
    onError: (err) => setError(err instanceof ApiError ? err.message : "Не удалось одобрить"),
  });

  const reject = useMutation({
    mutationFn: () => api.post(`/candidates/${post.candidate_id}/reject`),
    onSuccess: () => {
      setError(null);
      invalidate();
    },
    onError: (err) => setError(err instanceof ApiError ? err.message : "Не удалось отклонить"),
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
        <span className="text-sm font-medium text-ink">{post.source_channel_title}</span>
        {post.score !== null && (
          <span className="rounded-full bg-surface-2 px-2 py-0.5 text-xs text-ink-muted whitespace-nowrap">
            score {post.score.toFixed(2)}
          </span>
        )}
      </div>

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

          <div className="flex gap-3">
            <button
              type="button"
              onClick={() => setShowRaw((v) => !v)}
              className="text-xs text-ink-muted underline decoration-dotted hover:text-ink"
            >
              {showRaw ? "Скрыть оригинал" : "Показать оригинал"}
            </button>
            <button
              type="button"
              onClick={() => {
                setDraft(post.rewritten_text);
                setEditing(true);
              }}
              className="text-xs text-ink-muted underline decoration-dotted hover:text-ink"
            >
              Редактировать
            </button>
          </div>
          {showRaw && (
            <p className="whitespace-pre-wrap rounded-lg bg-surface-2 p-3 text-xs text-ink-muted">
              {post.raw_text}
            </p>
          )}

          <div className="flex gap-2">
            <Button onClick={() => approve.mutate()} disabled={busy}>
              Одобрить
            </Button>
            <Button variant="danger" onClick={() => reject.mutate()} disabled={busy}>
              Отклонить
            </Button>
          </div>
        </>
      )}
      {error && <p className="text-xs text-bad">{error}</p>}
    </Card>
  );
}

export function Review() {
  const { data, isLoading, error } = useQuery(pendingReviewQuery());

  return (
    <div className="flex flex-col gap-6">
      <h1 className="text-xl font-semibold text-ink">Проверка постов</h1>

      <GenerateForm />

      <div className="flex flex-col gap-3">
        <h2 className="text-sm font-semibold text-ink">На одобрении</h2>
        {isLoading && <LoadingState />}
        {error && <ErrorState message={error.message} />}
        {data && data.length === 0 && (
          <Card>
            <EmptyState message="Нечего одобрять — сгенерируйте посты выше." />
          </Card>
        )}
        {data?.map((post) => (
          <PendingReviewCard key={post.candidate_id} post={post} />
        ))}
      </div>
    </div>
  );
}
