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

type SecretFieldName = "anthropic_api_key" | "voyage_api_key" | "telegram_api_id" | "telegram_api_hash";

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
  numeric = false,
  mask = true,
  emptyValue = "",
}: {
  label: string;
  field: SecretFieldName;
  status: SecretSource;
  numeric?: boolean;
  mask?: boolean;
  emptyValue?: string | number;
}) {
  const queryClient = useQueryClient();
  const [value, setValue] = useState("");
  const [error, setError] = useState<string | null>(null);

  const update = useMutation({
    mutationFn: (payload: string | number) =>
      api.put<SettingsStatus>("/settings", { [field]: payload }),
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
          update.mutate(numeric ? Number(value) : value);
        }}
      >
        <Input
          type={numeric ? "number" : mask ? "password" : "text"}
          autoComplete="off"
          value={value}
          onChange={(e) => setValue(e.target.value)}
          placeholder="Новое значение"
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
              update.mutate(emptyValue);
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
        Ключи и креды, общие для всего процесса. Значение из панели переопределяет
        .env сервера без перезапуска — LLM-ключи вступают в силу со следующего тика
        планировщика (до 5 минут), Telegram-креды — со следующего запроса веб-логина
        Telethon-сессии (аккаунты-читалки, живущие ingest-воркеры перечитывают их
        только при рестарте). Сохранённое значение не показывается повторно — только
        источник.
      </p>

      <Card className="flex flex-col gap-6">
        <h2 className="text-sm font-semibold text-ink">LLM-ключи</h2>
        {isLoading && <LoadingState />}
        {error && <ErrorState message={error.message} />}
        {data && (
          <>
            <SecretField label="Anthropic API Key" field="anthropic_api_key" status={data.anthropic_api_key.source} />
            <SecretField label="Voyage API Key" field="voyage_api_key" status={data.voyage_api_key.source} />
          </>
        )}
      </Card>

      <Card className="flex flex-col gap-6">
        <h2 className="text-sm font-semibold text-ink">Telegram (my.telegram.org)</h2>
        <p className="-mt-4 text-xs text-ink-muted">
          Нужны для веб-логина аккаунтов-читалок (вкладка «Аккаунты») — api_id/api_hash
          одного приложения, общие для всего пула Telethon-сессий.
        </p>
        {data && (
          <>
            <SecretField
              label="Telegram API ID"
              field="telegram_api_id"
              status={data.telegram_api_id.source}
              numeric
              mask={false}
              emptyValue={0}
            />
            <SecretField label="Telegram API Hash" field="telegram_api_hash" status={data.telegram_api_hash.source} />
          </>
        )}
      </Card>
    </div>
  );
}
