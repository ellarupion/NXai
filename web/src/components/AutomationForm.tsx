import { useState } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { api, ApiError } from "../api/client";
import { automationQuery } from "../api/queries";
import { Button, Card, CardSkeleton, ErrorState, Input, TextAction } from "../components/ui";
import { errorText } from "../lib/errors";
import type { AutomationSettings } from "../types";

/* Пороги и времена поведения.

   Всё это раньше было константами в коде: поменять значило собрать образ и
   перезапустить сервис. Числа отсюда однажды пришлось подбирать на горящем проде, и
   тогда на каждую попытку уходила пересборка.

   Границы показаны рядом с каждым полем не для красоты. Значение вне диапазона
   отвергает бэкенд, и человеку надо видеть, куда он может двигаться, ДО того как
   нажмёт «Сохранить». Плюс часть проверок парные — их бэкенд объясняет словами. */

type FieldSpec = {
  key: keyof AutomationSettings;
  label: string;
  hint: string;
  min: number;
  max: number;
  step: number;
  unit?: string;
};

type Section = { title: string; intro: string; fields: FieldSpec[] };

const SECTIONS: Section[] = [
  {
    title: "Отбор постов",
    intro:
      "Насколько пост должен выделяться на фоне своего канала, чтобы попасть в работу. " +
      "Самое влиятельное место: подняли порог — тема замолчала, опустили — в «Проверку» " +
      "полезло всё подряд.",
    fields: [
      {
        key: "selection_score_threshold",
        label: "Порог отбора",
        hint: "Во сколько раз пост должен обгонять медиану своего канала по пересылкам.",
        min: 0.1,
        max: 10,
        step: 0.1,
        unit: "× медианы",
      },
      {
        key: "min_samples_for_median",
        label: "Постов для медианы",
        hint:
          "Пока постов канала меньше, медиане верить нельзя и скор считается по сырым " +
          "пересылкам — у нового источника медианы просто нет.",
        min: 2,
        max: 50,
        step: 1,
      },
      {
        key: "selection_pool_factor",
        label: "Ширина пула отбора",
        hint:
          "Во сколько раз пул шире заказа. Из широкого пула раскладываем по подтемам: " +
          "«топ-N по виральности» на практике даёт N постов про один инфоповод.",
        min: 1,
        max: 10,
        step: 1,
        unit: "× заказа",
      },
    ],
  },
  {
    title: "Доверие источникам",
    intro:
      "Вес, на который домножается скор постов канала. Источник, чьи посты отклоняют, " +
      "опускается сам. Нижняя граница должна оставлять ему шанс выбраться: однажды она " +
      "была слишком низкой, и канал замолчал на недели.",
    fields: [
      {
        key: "min_trust_score",
        label: "Нижняя граница доверия",
        hint: "Ниже этого вес источника не опускается, как бы часто его ни отклоняли.",
        min: 0.1,
        max: 1,
        step: 0.05,
      },
      {
        key: "max_trust_score",
        label: "Верхняя граница доверия",
        hint: "Выше этого вес не поднимается, как бы хорош источник ни был.",
        min: 1,
        max: 5,
        step: 0.1,
      },
      {
        key: "trust_rejected_penalty",
        label: "Штраф за отклонение",
        hint: "На сколько падает вес, когда вы отклоняете пост руками.",
        min: 0,
        max: 0.5,
        step: 0.01,
      },
      {
        key: "trust_duplicate_penalty",
        label: "Штраф за повтор",
        hint: "Источник повторил чужую новость — сигнал мягче, чем отклонение.",
        min: 0,
        max: 0.5,
        step: 0.01,
      },
      {
        key: "trust_success_bonus",
        label: "Награда за удачный пост",
        hint: "На сколько растёт вес, когда пост источника дошёл до готового рерайта.",
        min: 0,
        max: 0.5,
        step: 0.01,
      },
    ],
  },
  {
    title: "Рерайт и расход",
    intro:
      "Сколько система переписывает и какой запас держит. Здесь же потолок скорости " +
      "трат: рерайт — единственная по-настоящему дорогая операция.",
    fields: [
      {
        key: "rewrite_batch_limit",
        label: "Постов за один заход",
        hint: "Планировщик работает раз в 5 минут, так что это ещё и потолок трат в час.",
        min: 1,
        max: 50,
        step: 1,
      },
      {
        key: "rewrite_stock_days",
        label: "Запас, дней",
        hint:
          "На сколько дней вперёд держим готовые посты. Больше — платим за то, что " +
          "протухнет неопубликованным.",
        min: 1,
        max: 7,
        step: 1,
      },
      {
        key: "min_rewrite_stock",
        label: "Минимальный запас",
        hint: "Сколько готовых постов держать даже у темы с редким расписанием.",
        min: 1,
        max: 50,
        step: 1,
      },
      {
        key: "max_daily_batch",
        label: "Партия на день, максимум",
        hint: "Ограничение про человека, а не про деньги: партию вы разбираете руками.",
        min: 1,
        max: 50,
        step: 1,
      },
      {
        key: "min_rewritable_length",
        label: "Минимальная длина исходника",
        hint:
          "Короче этого рерайтить нечего: модель начнёт додумывать, а на пустом посте " +
          "ответит репликой «дай текст», которая уйдёт вам как готовый пост.",
        min: 10,
        max: 500,
        step: 5,
        unit: "символов",
      },
    ],
  },
  {
    title: "Дубликаты и подтемы",
    intro: "Когда считать посты одинаковыми и как часто чередовать подтемы.",
    fields: [
      {
        key: "dedup_similarity_threshold",
        label: "Порог похожести",
        hint: "Выше этой близости посты считаются одним и тем же и второй отбрасывается.",
        min: 0.5,
        max: 1,
        step: 0.01,
      },
      {
        key: "rubric_recent_window",
        label: "Окно чередования подтем",
        hint: "Сколько последних публикаций смотрим, решая, не приелась ли подтема.",
        min: 1,
        max: 20,
        step: 1,
        unit: "постов",
      },
    ],
  },
  {
    title: "Перекрытие чужой рекламы",
    intro: "Через сколько ставить свой пост поверх чужой рекламы, замеченной в канале.",
    fields: [
      {
        key: "ad_cover_delay_minutes",
        label: "Задержка перекрытия",
        hint: "Отсчитывается от момента, когда реклама замечена.",
        min: 5,
        max: 480,
        step: 5,
        unit: "минут",
      },
    ],
  },
];

export function AutomationForm() {
  const queryClient = useQueryClient();
  const { data, isLoading, error, refetch } = useQuery(automationQuery());
  const [draft, setDraft] = useState<Partial<Record<string, string>>>({});
  const [saveError, setSaveError] = useState<string | null>(null);
  const [saved, setSaved] = useState(false);

  const save = useMutation({
    mutationFn: (patch: Record<string, number>) =>
      api.put<AutomationSettings>("/settings/automation", patch),
    onSuccess: () => {
      setSaveError(null);
      setDraft({});
      setSaved(true);
      queryClient.invalidateQueries({ queryKey: ["automation"] });
      queryClient.invalidateQueries({ queryKey: ["llm-usage"] });
    },
    onError: (err) => {
      setSaved(false);
      setSaveError(err instanceof ApiError ? err.message : "Не удалось сохранить настройки");
    },
  });

  if (isLoading) return <CardSkeleton rows={6} />;
  if (error) return <ErrorState message={errorText(error)} onRetry={() => refetch()} />;
  if (!data) return null;

  const valueOf = (key: string) => draft[key] ?? String(data[key as keyof AutomationSettings]);
  const changed = Object.keys(draft).filter(
    (k) => Number(draft[k]) !== Number(data[k as keyof AutomationSettings]),
  );

  return (
    <div className="flex flex-col gap-4">
      {SECTIONS.map((section) => (
        <Card key={section.title} className="flex flex-col gap-3">
          <div>
            <h2 className="text-sm font-semibold text-ink">{section.title}</h2>
            <p className="mt-1 text-xs text-ink-muted">{section.intro}</p>
          </div>
          <div className="flex flex-col gap-3">
            {section.fields.map((f) => (
              <div key={f.key} className="flex flex-col gap-1 border-t border-border-soft pt-3">
                <div className="flex flex-wrap items-center gap-x-3 gap-y-1">
                  <label className="flex-1 text-sm text-ink" htmlFor={f.key}>
                    {f.label}
                  </label>
                  <Input
                    id={f.key}
                    type="number"
                    min={f.min}
                    max={f.max}
                    step={f.step}
                    value={valueOf(f.key)}
                    onChange={(e) => {
                      setSaved(false);
                      setDraft((prev) => ({ ...prev, [f.key]: e.target.value }));
                    }}
                    className="w-28 text-right"
                  />
                  <span className="w-24 text-xs text-ink-muted">{f.unit ?? ""}</span>
                </div>
                <p className="text-xs text-ink-muted">
                  {f.hint}{" "}
                  <span className="whitespace-nowrap text-ink-faint">
                    Допустимо {f.min}–{f.max}.
                  </span>
                </p>
              </div>
            ))}
          </div>
        </Card>
      ))}

      {/* Кнопка появляется только когда есть что сохранять: постоянная кнопка на
          странице настроек провоцирует нажимать её «на всякий случай». */}
      {changed.length > 0 && (
        <Card className="flex flex-wrap items-center gap-3">
          <Button
            onClick={() =>
              save.mutate(Object.fromEntries(changed.map((k) => [k, Number(draft[k])])))
            }
            disabled={save.isPending}
          >
            {save.isPending ? "Сохраняю…" : `Сохранить (${changed.length})`}
          </Button>
          <TextAction onClick={() => setDraft({})}>Отменить правки</TextAction>
          <span className="text-xs text-ink-muted">
            Новые значения подхватываются без перезапуска — планировщик перечитывает их
            на каждом заходе.
          </span>
        </Card>
      )}

      {saveError && <ErrorState message={saveError} />}
      {saved && <p className="text-sm text-good">Настройки сохранены.</p>}
    </div>
  );
}
