import { useState } from "react";
import { useMutation } from "@tanstack/react-query";
import { api, ApiError } from "../api/client";
import { Button, Input, Select, Textarea } from "./ui";
import type { PersonaConfig } from "../types";

/* Конструктор персоны бота (UX-этап 4): структурные настройки стиля вместо
   одного textarea. Значения компилируются в промпт на бэке
   (core/services/persona.py) — здесь только форма. Встроены два помощника:
   «Научиться у конкурента» (StyleExtractor предзаполняет поля) и
   «Проверить персону» (dry-run рерайт реального поста до сохранения). */

export interface PersonaValue {
  config: PersonaConfig;
  custom: string;
}

const BOLDNESS_LABELS: Record<number, string> = {
  1: "1 — очень близко к оригиналу",
  2: "2 — сдержанно",
  3: "3 — сохраняю суть, подача своя",
  4: "4 — смело, только идея и факты",
  5: "5 — полное переосмысление",
};

function splitExamples(text: string): string[] {
  return text
    .split(/\n\s*\n/)
    .map((e) => e.trim())
    .filter(Boolean);
}

function joinExamples(list: string[] | undefined): string {
  return (list ?? []).join("\n\n");
}

export function PersonaEditor({
  value,
  onChange,
  botId,
}: {
  value: PersonaValue;
  onChange: (value: PersonaValue) => void;
  /** Задан — доступна песочница «Проверить персону» (нужен существующий бот). */
  botId?: string;
}) {
  const { config, custom } = value;
  const set = (patch: Partial<PersonaConfig>) => onChange({ config: { ...config, ...patch }, custom });

  const [refs, setRefs] = useState("");
  const [extractError, setExtractError] = useState<string | null>(null);
  const extract = useMutation({
    mutationFn: () =>
      api.post<{ suggested_persona: string; suggested_config: PersonaConfig & { custom?: string } }>(
        "/channel-bots/extract-style",
        { reference_posts: splitExamples(refs) },
      ),
    onSuccess: (data) => {
      setExtractError(null);
      const { custom: suggestedCustom, ...suggested } = data.suggested_config;
      onChange({
        config: { ...config, ...suggested },
        custom: suggestedCustom || custom,
      });
    },
    onError: (err) =>
      setExtractError(err instanceof ApiError ? err.message : "Не удалось выучить стиль"),
  });

  const [previewText, setPreviewText] = useState("");
  const [preview, setPreview] = useState<{ original: string; rewritten: string } | null>(null);
  const [previewError, setPreviewError] = useState<string | null>(null);
  const runPreview = useMutation({
    mutationFn: () =>
      api.post<{ original: string; rewritten: string }>(`/channel-bots/${botId}/preview-rewrite`, {
        persona_config: config,
        persona_prompt: custom,
        text: previewText.trim() || null,
      }),
    onSuccess: (data) => {
      setPreviewError(null);
      setPreview(data);
    },
    onError: (err) => {
      setPreview(null);
      setPreviewError(err instanceof ApiError ? err.message : "Не удалось выполнить рерайт");
    },
  });

  return (
    <div className="flex flex-col gap-4">
      <div className="grid grid-cols-1 gap-3 sm:grid-cols-2">
        <label className="flex flex-col gap-1 text-xs text-ink-muted">
          Тон
          <Select
            value={config.tone ?? ""}
            onChange={(e) => set({ tone: (e.target.value || undefined) as PersonaConfig["tone"] })}
          >
            <option value="">— не задан —</option>
            <option value="brash">Дерзкий блогер</option>
            <option value="expert">Спокойный эксперт</option>
            <option value="friendly">Дружеский</option>
            <option value="news">Новостной</option>
            <option value="custom">Свой (описать словами)</option>
          </Select>
        </label>
        <label className="flex flex-col gap-1 text-xs text-ink-muted">
          Длина постов
          <Select
            value={config.length ?? ""}
            onChange={(e) => set({ length: (e.target.value || undefined) as PersonaConfig["length"] })}
          >
            <option value="">— как получится —</option>
            <option value="shorter">Короче исходника</option>
            <option value="same">Как исходник</option>
            <option value="longer">Развёрнутее</option>
          </Select>
        </label>
        <label className="flex flex-col gap-1 text-xs text-ink-muted">
          Эмодзи
          <Select
            value={config.emoji ?? ""}
            onChange={(e) => set({ emoji: (e.target.value || undefined) as PersonaConfig["emoji"] })}
          >
            <option value="">— как получится —</option>
            <option value="none">Совсем без эмодзи</option>
            <option value="few">Немного (1–2 на пост)</option>
            <option value="many">Много</option>
          </Select>
        </label>
        <label className="flex flex-col gap-1 text-xs text-ink-muted">
          Обращение к читателю
          <Select
            value={config.address ?? ""}
            onChange={(e) => set({ address: (e.target.value || undefined) as PersonaConfig["address"] })}
          >
            <option value="">— как получится —</option>
            <option value="ty">На «ты»</option>
            <option value="vy">На «вы»</option>
            <option value="neutral">Безлично</option>
          </Select>
        </label>
      </div>

      {config.tone === "custom" && (
        <label className="flex flex-col gap-1 text-xs text-ink-muted">
          Свой тон — опишите словами
          <Textarea
            value={config.tone_custom ?? ""}
            onChange={(e) => set({ tone_custom: e.target.value })}
            placeholder="Например: пишет как старший брат — жёстко, но по делу и без хамства"
            rows={2}
          />
        </label>
      )}

      <label className="flex flex-col gap-1 text-xs text-ink-muted">
        Насколько смело переписывать: {BOLDNESS_LABELS[config.boldness ?? 3]}
        <input
          type="range"
          min={1}
          max={5}
          step={1}
          value={config.boldness ?? 3}
          onChange={(e) => set({ boldness: Number(e.target.value) })}
          className="accent-[var(--accent)]"
        />
      </label>

      <div className="grid grid-cols-1 gap-3 sm:grid-cols-2">
        <label className="flex flex-col gap-1 text-xs text-ink-muted">
          Стоп-слова и запретные темы (через запятую)
          <Input
            value={(config.stop_words ?? []).join(", ")}
            onChange={(e) =>
              set({
                stop_words: e.target.value
                  .split(",")
                  .map((w) => w.trim())
                  .filter(Boolean),
              })
            }
            placeholder="крипта, политика, «друзья мои»"
          />
        </label>
        <label className="flex flex-col gap-1 text-xs text-ink-muted">
          Хэштеги в конце поста
          <Input
            value={config.hashtags ?? ""}
            onChange={(e) => set({ hashtags: e.target.value })}
            placeholder="#мужскойклуб (пусто — без хэштегов)"
          />
        </label>
      </div>

      <label className="flex flex-col gap-1 text-xs text-ink-muted">
        Примеры «пиши так» (до 5, разделяйте пустой строкой)
        <Textarea
          value={joinExamples(config.examples_good)}
          onChange={(e) => set({ examples_good: splitExamples(e.target.value) })}
          placeholder={"Пример хорошего поста…\n\nЕщё один…"}
          rows={4}
        />
      </label>
      <label className="flex flex-col gap-1 text-xs text-ink-muted">
        Примеры «так НЕ пиши» (до 3, разделяйте пустой строкой)
        <Textarea
          value={joinExamples(config.examples_bad)}
          onChange={(e) => set({ examples_bad: splitExamples(e.target.value) })}
          placeholder="Пример поста с неправильным тоном…"
          rows={3}
        />
      </label>

      <label className="flex flex-col gap-1 text-xs text-ink-muted">
        Особые указания (свободным текстом)
        <Textarea
          value={custom}
          onChange={(e) => onChange({ config, custom: e.target.value })}
          placeholder="Всё, что не влезло в поля выше"
          rows={3}
        />
      </label>

      <details className="rounded-lg bg-surface-2 p-3">
        <summary className="cursor-pointer select-none text-xs font-medium text-ink">
          Научиться у конкурента — вставьте 3–10 его постов, ИИ заполнит поля выше
        </summary>
        <div className="mt-2 flex flex-col gap-2">
          <Textarea
            value={refs}
            onChange={(e) => setRefs(e.target.value)}
            placeholder={"Пост 1…\n\nПост 2…\n\nПост 3…"}
            rows={5}
          />
          <Button
            type="button"
            variant="secondary"
            className="self-start"
            disabled={extract.isPending || !refs.trim()}
            onClick={() => extract.mutate()}
          >
            {extract.isPending ? "Анализирую…" : "Заполнить поля по примерам"}
          </Button>
          {extractError && <p className="text-xs text-bad">{extractError}</p>}
        </div>
      </details>

      {botId && (
        <details className="rounded-lg bg-surface-2 p-3">
          <summary className="cursor-pointer select-none text-xs font-medium text-ink">
            Проверить персону — прогнать реальный пост через рерайт до сохранения
          </summary>
          <div className="mt-2 flex flex-col gap-2">
            <Textarea
              value={previewText}
              onChange={(e) => setPreviewText(e.target.value)}
              placeholder="Свой текст для проверки (пусто — возьмём последний собранный пост темы)"
              rows={2}
            />
            <Button
              type="button"
              variant="secondary"
              className="self-start"
              disabled={runPreview.isPending}
              onClick={() => runPreview.mutate()}
            >
              {runPreview.isPending ? "Переписываю…" : "Проверить персону"}
            </Button>
            {previewError && <p className="text-xs text-bad">{previewError}</p>}
            {preview && (
              <div className="grid grid-cols-1 gap-2 md:grid-cols-2">
                <div>
                  <p className="mb-1 text-xs font-medium text-ink-muted">Оригинал</p>
                  <p className="whitespace-pre-wrap rounded-lg bg-surface p-2 text-xs text-ink-muted">
                    {preview.original}
                  </p>
                </div>
                <div>
                  <p className="mb-1 text-xs font-medium text-ink-muted">С этой персоной</p>
                  <p className="whitespace-pre-wrap rounded-lg bg-surface p-2 text-xs text-ink">
                    {preview.rewritten}
                  </p>
                </div>
              </div>
            )}
          </div>
        </details>
      )}
    </div>
  );
}
