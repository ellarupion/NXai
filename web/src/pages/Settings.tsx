import { useEffect, useState } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { api, ApiError } from "../api/client";
import { generalSettingsQuery, settingsQuery } from "../api/queries";
import { Button, Card, ErrorState, Input, LoadingState } from "../components/ui";
import type { GeneralSettings, SecretSource, SettingsStatus } from "../types";

function GeneralSettingsCard() {
  const queryClient = useQueryClient();
  const { data, isLoading, error } = useQuery(generalSettingsQuery());
  const [tz, setTz] = useState("");
  const [cooldown, setCooldown] = useState("");
  const [saveError, setSaveError] = useState<string | null>(null);

  useEffect(() => {
    if (data) {
      setTz(data.timezone);
      setCooldown(String(data.pool_cooldown_days));
    }
  }, [data]);

  const update = useMutation({
    mutationFn: (payload: Partial<GeneralSettings>) =>
      api.put<GeneralSettings>("/settings/general", payload),
    onSuccess: () => {
      setSaveError(null);
      queryClient.invalidateQueries({ queryKey: ["settings-general"] });
    },
    onError: (err) => setSaveError(err instanceof ApiError ? err.message : "Не удалось сохранить"),
  });

  const dirty = data && (tz !== data.timezone || cooldown !== String(data.pool_cooldown_days));

  return (
    <Card className="flex flex-col gap-4">
      <h2 className="text-sm font-semibold text-ink">Общие настройки</h2>
      {isLoading && <LoadingState />}
      {error && <ErrorState message={error.message} />}
      {data && (
        <form
          className="flex flex-col gap-4"
          onSubmit={(e) => {
            e.preventDefault();
            if (!tz) return;
            setSaveError(null);
            update.mutate({ timezone: tz, pool_cooldown_days: Number(cooldown) });
          }}
        >
          <div className="flex flex-col gap-1">
            <span className="text-sm font-medium text-ink">Часовой пояс</span>
            <p className="text-xs text-ink-muted">
              В этом поясе считаются «тихие часы» публикации. IANA-имя: Europe/Moscow,
              Europe/Kyiv, Asia/Almaty. Меняется на лету.
            </p>
            <Input
              type="text"
              autoComplete="off"
              value={tz}
              onChange={(e) => setTz(e.target.value)}
              placeholder="Europe/Moscow"
            />
          </div>
          <div className="flex flex-col gap-1">
            <span className="text-sm font-medium text-ink">Повтор запасного поста, дней</span>
            <p className="text-xs text-ink-muted">
              Один и тот же пост из запаса не выйдет повторно чаще, чем раз в столько
              дней. 0 — без ограничения.
            </p>
            <Input
              type="number"
              min={0}
              value={cooldown}
              onChange={(e) => setCooldown(e.target.value)}
              placeholder="7"
            />
          </div>
          <Button type="submit" disabled={update.isPending || !tz || !dirty} className="self-start">
            Сохранить
          </Button>
        </form>
      )}
      {saveError && <p className="text-sm text-bad">{saveError}</p>}
    </Card>
  );
}

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
        className="flex flex-wrap gap-2"
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
        Ключи и доступы, общие для всей системы. Заданное здесь значение имеет приоритет
        над настройками сервера и подхватывается без его перезагрузки: LLM-ключи — в
        течение нескольких минут, Telegram-доступы — при следующем подключении аккаунта.
        Само значение обратно не показывается — только откуда оно берётся.
      </p>

      <GeneralSettingsCard />

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
