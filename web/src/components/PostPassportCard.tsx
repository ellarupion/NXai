import { useQuery } from "@tanstack/react-query";
import { postPassportQuery } from "../api/queries";
import { CardSkeleton, ErrorState } from "../components/ui";
import { errorText } from "../lib/errors";
import type { PostPassportFacts } from "../types";

/* «Почему вышел именно такой пост».

   Система принимает на каждый пост несколько решений — взять этот, а не
   соседний; каким порогом; какой персоной переписать; к какой подтеме отнести —
   и до паспорта ни одно из них не сохранялось. Оператор видел карточку с
   текстом и числом виральности, а на вопрос «почему выбрали это» ответить было
   нечем, кроме как читать код и логи.

   Показываем словами, а не полями. «Обогнал свой канал в 2,4 раза при пороге
   1,8» — это ответ; `score=2.41 threshold=1.8` — нет.

   Строки, для которых фактов нет, не рисуем вовсе: у поста, прошедшего конвейер
   до появления очередного факта, его в паспорте не будет, и пустая строка
   «Персона: —» выглядела бы сбоем, хотя это просто старая запись. */

function num(n: number | null | undefined, digits = 2): string {
  return typeof n === "number" ? n.toLocaleString("ru-RU", { maximumFractionDigits: digits }) : "—";
}

function Row({ label, children }: { label: string; children: React.ReactNode }) {
  return (
    <div className="flex flex-col gap-0.5 sm:flex-row sm:gap-3">
      <span className="shrink-0 text-xs text-ink-faint sm:w-32 sm:pt-px">{label}</span>
      <span className="text-sm text-ink">{children}</span>
    </div>
  );
}

function selectionLine(f: PostPassportFacts): React.ReactNode {
  if (f.origin === "manual") {
    return (
      <>
        Заказан вручную кнопкой «Сделать посты» — порог отбора к нему не применялся,
        взят как один из самых заметных в пуле{f.score != null ? ` (${num(f.score)}× медианы)` : ""}.
      </>
    );
  }
  if (f.origin === "batch") {
    return (
      <>
        Из партии «Посты на сегодня» — порог не применялся, пул раскладывали по подтемам
        {f.score != null ? `, заметность ${num(f.score)}× медианы` : ""}.
      </>
    );
  }
  if (f.score != null && f.threshold != null) {
    return (
      <>
        Обогнал свой канал в <b>{num(f.score)}×</b> при пороге {num(f.threshold)}×.
      </>
    );
  }
  return f.score != null ? <>Заметность {num(f.score)}× медианы своего канала.</> : null;
}

export function PostPassportCard({ candidateId }: { candidateId: string }) {
  const { data, isLoading, error, refetch } = useQuery(postPassportQuery(candidateId));

  if (isLoading) return <CardSkeleton rows={4} />;
  if (error) return <ErrorState message={errorText(error)} onRetry={() => refetch()} />;
  if (!data) return null;

  const f = data.facts;
  const empty = Object.keys(f).length === 0;
  const sel = selectionLine(f);

  return (
    <div className="flex flex-col gap-3 rounded-lg border border-border-soft bg-surface-2 p-3">
      {empty && (
        <p className="text-sm text-ink-muted">
          Этот пост прошёл конвейер до того, как система начала записывать, из чего
          складывается решение. У новых постов здесь будет разбор.
        </p>
      )}

      {sel && <Row label="Почему выбран">{sel}</Row>}

      {(f.forwards != null || f.median_forwards != null) && (
        <Row label="Пересылки">
          {num(f.forwards, 0)} у поста при медиане канала {num(f.median_forwards)}
          {f.trust_score != null && <> · доверие источнику {num(f.trust_score)}</>}
        </Row>
      )}

      {data.source_channel_title && <Row label="Источник">{data.source_channel_title}</Row>}

      {f.rubric && (
        <Row label="Подтема">
          {f.rubric}
          <span className="text-ink-faint">
            {f.rubric_decided_by === "raw"
              ? " — определена по исходнику, до рерайта"
              : f.rubric_decided_by === "rewritten"
                ? " — определена по готовому тексту"
                : ""}
          </span>
        </Row>
      )}

      {f.persona && (
        <Row label="Чем писали">
          <span className="text-ink-muted">{f.persona}</span>
        </Row>
      )}

      {(f.source_length != null || f.result_length != null) && (
        <Row label="Длина">
          было {num(f.source_length, 0)} симв., стало {num(f.result_length, 0)}
          {f.variant_no != null && f.variant_no > 1 && <> · вариант №{f.variant_no}</>}
        </Row>
      )}

      {f.edited_via && (
        <Row label="Правка редактора">
          {f.edit_length_before != null && f.edit_length_after != null
            ? `${num(f.edit_length_before, 0)} → ${num(f.edit_length_after, 0)} симв.`
            : "текст правили"}
          {f.edited_via === "bot" ? " · из бота" : " · из панели"}
        </Row>
      )}

      {f.published_to?.length ? (
        <Row label="Куда вышел">
          {f.published_to.join(", ")}
          {f.published_with_photo && " · с фото"}
        </Row>
      ) : null}

      {data.cost_usd > 0 && (
        <Row label="Стоил">
          ${data.cost_usd.toFixed(4)}
          {/* Разбивку показываем, только когда разделов больше одного: иначе
              строка повторяет саму себя — «$0.0121 (Рерайт постов: $0.0121)». */}
          {data.cost_by_kind.length > 1 && (
            <span className="text-ink-faint">
              {" "}
              ({data.cost_by_kind.map((k) => `${k.title}: $${k.cost_usd.toFixed(4)}`).join(", ")})
            </span>
          )}
        </Row>
      )}
    </div>
  );
}
