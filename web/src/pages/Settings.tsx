import { useState } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { api, ApiError } from "../api/client";
import { settingsQuery } from "../api/queries";
import { Button, Card, ErrorState, Input, LoadingState } from "../components/ui";
import type { SecretSource, SettingsStatus } from "../types";

const SOURCE_LABEL: Record<SecretSource, string> = {
  panel: "Задан из панели",
  env: "Задан из .env сервера",
  unset: "Не задан",
};

function SourceBadge({ source }: { source: SecretSource }) {
  const styles: Record<SecretSource, string> = {
    panel: "bg-good-soft text-good",
    env: "bg-surface-2 text-ink-muted",
    unset: "bg-bad-soft text-bad",
  };
  return (
    <span className={`rounded-full px-2 py-0.5 text-xs font-medium whitespace-nowrap ${styles[source]}`}>
      {SOURCE_LABEL[source]}
    </span>
  );
}

function SecretField({
  label,
  field,
  status,
}: {
  label: string;
  field: "anthropic_api_key" | "voyage_api_key";
  status: SecretSource;
}) {
  const queryClient = useQueryClient();
  const [value, setValue] = useState("");
  const [error, setError] = useState<string | null>(null);

  const update = useMutation({
    mutationFn: (payload: string) => api.put<SettingsStatus>("/settings", { [field]: payload }),
    onSuccess: () => {
      setError(null);
      setValue("");
      queryClient.invalidateQueries({ queryKey: ["settings"] });
    },
    onError: (err) => setError(err instanceof ApiError ? err.message : "Не удалось сохранить"),
  });

  return (
    <div className="flex flex-col gap-2">
      <div className="flex items-center justify-between gap-2">
        <span className="text-sm font-medium text-ink">{label}</span>
        <SourceBadge source={status} />
      </div>
      <form
        className="flex gap-2"
        onSubmit={(e) => {
          e.preventDefault();
          if (!value) return;
          setError(null);
          update.mutate(value);
        }}
      >
        <Input
          type="password"
          autoComplete="off"
          value={value}
          onChange={(e) => setValue(e.target.value)}
          placeholder="Новое значение ключа"
          className="flex-1"
        />
        <Button type="submit" disabled={update.isPending || !value}>
          Сохранить
        </Button>
        {status === "panel" && (
          <Button
            type="button"
            variant="secondary"
            disabled={update.isPending}
            onClick={() => {
              setError(null);
              update.mutate("");
            }}
          >
            Сбросить
          </Button>
        )}
      </form>
      {error && <p className="text-sm text-bad">{error}</p>}
    </div>
  );
}

export function Settings() {
  const { data, isLoading, error } = useQuery(settingsQuery());

  return (
    <div className="flex flex-col gap-6">
      <h1 className="text-xl font-semibold text-ink">Настройки</h1>
      <p className="text-sm text-ink-muted">
        Ключи для LLM-рерайта и эмбеддингов дедупа. Значение из панели переопределяет
        .env сервера без перезапуска — вступает в силу со следующего тика планировщика
        (до 5 минут). Сохранённое значение не показывается повторно — только источник.
      </p>

      <Card className="flex flex-col gap-6">
        {isLoading && <LoadingState />}
        {error && <ErrorState message={error.message} />}
        {data && (
          <>
            <SecretField label="Anthropic API Key" field="anthropic_api_key" status={data.anthropic_api_key.source} />
            <SecretField label="Voyage API Key" field="voyage_api_key" status={data.voyage_api_key.source} />
          </>
        )}
      </Card>
    </div>
  );
}
