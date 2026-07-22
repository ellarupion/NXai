import { useState } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { api, ApiError } from "../api/client";
import { poolPostsQuery, themesQuery } from "../api/queries";
import {
  Button,
  Card,
  EmptyState,
  ErrorState,
  LoadingState,
  Select,
  Textarea,
} from "../components/ui";
import type { PoolPost } from "../types";

function CreatePoolPostForm() {
  const queryClient = useQueryClient();
  const themes = useQuery(themesQuery());
  const [themeId, setThemeId] = useState("");
  const [text, setText] = useState("");
  const [error, setError] = useState<string | null>(null);

  const create = useMutation({
    mutationFn: () => api.post<PoolPost>("/pool-posts", { theme_id: themeId, text }),
    onSuccess: () => {
      setText("");
      setError(null);
      queryClient.invalidateQueries({ queryKey: ["pool-posts"] });
    },
    onError: (err) => setError(err instanceof ApiError ? err.message : "Не удалось добавить пост"),
  });

  return (
    <Card>
      <h2 className="mb-3 text-sm font-semibold text-ink">Добавить пост в запас</h2>
      <p className="mb-3 text-sm text-ink-muted">
        Запас — «вечные» посты темы, которые не устаревают. Они выручают в двух
        случаях: когда свежих переписанных постов не хватает, чтобы держать
        расписание, и когда в вашем канале появляется чужая реклама — антиреклама
        в течение часа перекрывает её постом из запаса. Держите в каждой теме
        3–5 таких постов.
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
        <Textarea
          value={text}
          onChange={(e) => setText(e.target.value)}
          placeholder="Текст поста"
          rows={4}
          required
        />
        <Button type="submit" disabled={create.isPending} className="self-start">
          Добавить
        </Button>
        {error && <p className="text-sm text-bad">{error}</p>}
      </form>
    </Card>
  );
}

function PoolPostRow({ post }: { post: PoolPost }) {
  const queryClient = useQueryClient();
  const [text, setText] = useState(post.text);
  const [error, setError] = useState<string | null>(null);

  const update = useMutation({
    mutationFn: (payload: Partial<Pick<PoolPost, "text">>) => api.put<PoolPost>(`/pool-posts/${post.id}`, payload),
    onSuccess: () => {
      setError(null);
      queryClient.invalidateQueries({ queryKey: ["pool-posts"] });
    },
    onError: (err) => setError(err instanceof ApiError ? err.message : "Не удалось обновить"),
  });

  const remove = useMutation({
    mutationFn: () => api.delete(`/pool-posts/${post.id}`),
    onSuccess: () => {
      setError(null);
      queryClient.invalidateQueries({ queryKey: ["pool-posts"] });
    },
    onError: (err) => setError(err instanceof ApiError ? err.message : "Не удалось удалить"),
  });

  const statusLabel = post.status === "ready" ? "Готов к выходу" : "Недавно выходил (отдыхает)";

  return (
    <li className="flex flex-col gap-2 py-3 first:pt-0 last:pb-0">
      <div className="flex items-center justify-between gap-2">
        <span
          className={`rounded-full px-2 py-0.5 text-xs font-medium whitespace-nowrap ${
            post.status === "ready" ? "bg-good-soft text-good" : "bg-surface-2 text-ink-muted"
          }`}
        >
          {statusLabel}
        </span>
        <span className="text-xs text-ink-muted">
          использован раз: {post.times_used} · источник:{" "}
          {post.source === "manual" ? "вручную" : post.source === "generated" ? "сгенерирован" : "переиспользован кандидат"}
        </span>
      </div>
      <form
        className="flex gap-2"
        onSubmit={(e) => {
          e.preventDefault();
          if (text === post.text) return;
          setError(null);
          update.mutate({ text });
        }}
      >
        <Textarea value={text} onChange={(e) => setText(e.target.value)} rows={3} className="flex-1" />
      </form>
      <div className="flex gap-2">
        {text !== post.text && (
          <Button variant="secondary" disabled={update.isPending} onClick={() => update.mutate({ text })}>
            Сохранить текст
          </Button>
        )}
        <Button
          variant="danger"
          disabled={remove.isPending}
          onClick={() => {
            if (window.confirm("Удалить пост из пула?")) remove.mutate();
          }}
        >
          Удалить
        </Button>
      </div>
      {error && <p className="text-xs text-bad">{error}</p>}
    </li>
  );
}

export function PoolPosts() {
  const { data, isLoading, error } = useQuery(poolPostsQuery());

  return (
    <div className="flex flex-col gap-6">
      <h1 className="text-xl font-semibold text-ink">Запас постов</h1>

      <CreatePoolPostForm />

      <Card>
        <h2 className="mb-3 text-sm font-semibold text-ink">Все посты запаса</h2>
        {isLoading && <LoadingState />}
        {error && <ErrorState message={error.message} />}
        {data && data.length === 0 && (
          <EmptyState message="Запас пуст. Добавьте 3–5 «вечных» постов на тему — без них антиреклама не сможет перекрывать чужие посты, а расписание может пустеть." />
        )}
        {data && data.length > 0 && (
          <ul className="flex flex-col divide-y divide-border">
            {data.map((post) => (
              <PoolPostRow key={post.id} post={post} />
            ))}
          </ul>
        )}
      </Card>
    </div>
  );
}
