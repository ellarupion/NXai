import { useState } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { api, ApiError } from "../api/client";
import { themesQuery } from "../api/queries";
import { Button, Card, EmptyState, ErrorState, Input, LoadingState, StatusBadge, Textarea } from "../components/ui";
import type { Theme } from "../types";

function CreateThemeForm() {
  const queryClient = useQueryClient();
  const [name, setName] = useState("");
  const [stylePrompt, setStylePrompt] = useState("");
  const [error, setError] = useState<string | null>(null);

  const create = useMutation({
    mutationFn: () => api.post<Theme>("/themes", { name, default_style_prompt: stylePrompt }),
    onSuccess: () => {
      setName("");
      setStylePrompt("");
      queryClient.invalidateQueries({ queryKey: ["themes"] });
    },
    onError: (err) => setError(err instanceof ApiError ? err.message : "Не удалось создать тему"),
  });

  return (
    <Card>
      <h2 className="mb-3 text-sm font-semibold text-ink">Новая тема</h2>
      <form
        className="flex flex-col gap-2"
        onSubmit={(e) => {
          e.preventDefault();
          setError(null);
          create.mutate();
        }}
      >
        <Input
          value={name}
          onChange={(e) => setName(e.target.value)}
          placeholder="Название (например, men)"
          required
        />
        <Textarea
          value={stylePrompt}
          onChange={(e) => setStylePrompt(e.target.value)}
          placeholder="Стиль/персона по умолчанию для рерайта (необязательно)"
          rows={3}
        />
        <Button type="submit" disabled={create.isPending} className="self-start">
          Создать
        </Button>
        {error && <p className="text-sm text-bad">{error}</p>}
      </form>
    </Card>
  );
}

function ThemeRow({ theme }: { theme: Theme }) {
  const queryClient = useQueryClient();
  const [editing, setEditing] = useState(false);
  const [name, setName] = useState(theme.name);
  const [stylePrompt, setStylePrompt] = useState(theme.default_style_prompt);
  const [error, setError] = useState<string | null>(null);

  const invalidate = () => queryClient.invalidateQueries({ queryKey: ["themes"] });

  const update = useMutation({
    mutationFn: (payload: Partial<Theme>) => api.put<Theme>(`/themes/${theme.id}`, payload),
    onSuccess: () => {
      setError(null);
      setEditing(false);
      invalidate();
    },
    onError: (err) => setError(err instanceof ApiError ? err.message : "Не удалось сохранить"),
  });

  if (editing) {
    return (
      <li className="flex flex-col gap-2 py-3 first:pt-0 last:pb-0">
        <Input value={name} onChange={(e) => setName(e.target.value)} placeholder="Название" />
        <Textarea
          value={stylePrompt}
          onChange={(e) => setStylePrompt(e.target.value)}
          placeholder="Стиль/персона по умолчанию"
          rows={3}
        />
        <div className="flex gap-2">
          <Button
            onClick={() => update.mutate({ name, default_style_prompt: stylePrompt })}
            disabled={update.isPending || !name.trim()}
          >
            Сохранить
          </Button>
          <Button
            variant="secondary"
            onClick={() => {
              setName(theme.name);
              setStylePrompt(theme.default_style_prompt);
              setEditing(false);
              setError(null);
            }}
            disabled={update.isPending}
          >
            Отмена
          </Button>
        </div>
        {error && <p className="text-sm text-bad">{error}</p>}
      </li>
    );
  }

  return (
    <li className="flex flex-col gap-1 py-3 first:pt-0 last:pb-0">
      <div className="flex items-center justify-between gap-2">
        <span className="font-medium text-ink">{theme.name}</span>
        <div className="flex items-center gap-2">
          <StatusBadge active={theme.is_active} />
          <button
            type="button"
            onClick={() => setEditing(true)}
            className="text-xs text-ink-muted underline decoration-dotted hover:text-ink"
          >
            Изменить
          </button>
          <button
            type="button"
            onClick={() => update.mutate({ is_active: !theme.is_active })}
            disabled={update.isPending}
            className="text-xs text-ink-muted underline decoration-dotted hover:text-ink"
          >
            {theme.is_active ? "Выключить" : "Включить"}
          </button>
        </div>
      </div>
      {theme.default_style_prompt && (
        <p className="text-sm text-ink-muted">{theme.default_style_prompt}</p>
      )}
      {error && <p className="text-sm text-bad">{error}</p>}
    </li>
  );
}

export function Themes() {
  const { data, isLoading, error } = useQuery(themesQuery());

  return (
    <div className="flex flex-col gap-6">
      <h1 className="text-xl font-semibold text-ink">Темы</h1>

      <CreateThemeForm />

      <Card>
        <h2 className="mb-3 text-sm font-semibold text-ink">Все темы</h2>
        {isLoading && <LoadingState />}
        {error && <ErrorState message={error.message} />}
        {data && data.length === 0 && <EmptyState message="Тем пока нет — создайте первую выше." />}
        {data && data.length > 0 && (
          <ul className="flex flex-col divide-y divide-border">
            {data.map((theme) => (
              <ThemeRow key={theme.id} theme={theme} />
            ))}
          </ul>
        )}
      </Card>
    </div>
  );
}
