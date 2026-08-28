import { useState } from "react";
import { useQuery } from "@tanstack/react-query";
import { auditLogsQuery, themesQuery } from "../api/queries";
import { Button, Card, CardSkeleton, EmptyState, ErrorState, Select } from "../components/ui";
import { errorText } from "../lib/errors";
import type { AuditLogItem } from "../types";

/* Журнал действий.

   Записи копились с самого начала, но прочитать их было нечем: эндпоинта не
   существовало, и на вопрос «кто одобрил этот пост» или «когда меняли ключ»
   отвечали запросом в базу руками.

   Показываем строкой человеческого языка, а не полями таблицы: «дежурный
   одобрил пост» читается, `approve candidate 3f2b…` — нет. Идентификатор
   сущности остаётся рядом мелким, чтобы его можно было скопировать, когда
   разбираются в конкретном посте. */

/* Отглагольные существительные, а не «одобрил»: пол человека системе неизвестен,
   и любая глагольная форма половине операторов будет неверной. Заодно они ровно
   ложатся и на системные записи — «Система · перекрытие рекламы» читается, а
   «Система перекрыл рекламу» нет. Это выяснилось на живом журнале. */
const ACTION_TITLES: Record<string, string> = {
  login: "вход в панель",
  approve: "одобрение поста",
  reject: "отклонение поста",
  reject_all: "очистка очереди",
  restore: "возврат отклонённых",
  edit: "правка текста",
  unapprove: "снятие одобрения",
  generate: "заказ постов",
  settings_change: "смена настроек",
  bot_token_change: "смена токена бота",
  publish: "публикация",
  ad_detected: "найдена реклама",
  ad_covered: "перекрытие рекламы",
};

// Что делает только человек. Запись без автора здесь — не «система», а запись,
// сделанная до того, как журнал начал запоминать автора: подписать её «Системой»
// значило бы соврать про того, кто это сделал.
const HUMAN_ONLY = new Set([
  "login",
  "approve",
  "reject",
  "reject_all",
  "restore",
  "edit",
  "unapprove",
  "generate",
  "settings_change",
  "bot_token_change",
]);

// Порядок — по тому, как часто это ищут: сперва решения над очередью, потом
// доступы. Пустое значение = без фильтра.
const FILTERS: { value: string; label: string }[] = [
  { value: "", label: "Все действия" },
  { value: "approve", label: "Одобрения" },
  { value: "reject", label: "Отклонения" },
  { value: "edit", label: "Правки текста" },
  { value: "generate", label: "Заказы постов" },
  { value: "reject_all", label: "Очистка очереди" },
  { value: "restore", label: "Возвраты" },
  { value: "login", label: "Входы" },
  { value: "settings_change", label: "Настройки" },
  { value: "bot_token_change", label: "Токены ботов" },
];

function actorName(log: AuditLogItem): string {
  if (log.actor_admin_username) return log.actor_admin_username;
  if (log.actor_tg_user_id) return `Telegram ${log.actor_tg_user_id}`;
  // Оба поля пустые. Для действий планировщика это честная «Система», а для
  // действий, которые может сделать только человек, — старая запись без автора.
  return HUMAN_ONLY.has(log.action) ? "Автор не записан" : "Система";
}

/* Подробности разбираем ПО ДЕЙСТВИЮ, а не по наличию ключа в payload: ключи у
   разных действий совпадают (requested есть и у заказа постов, и у возврата), и
   разбор «по ключам» подписывал возврат четырёх постов как «заказано 4,
   приготовлено 0». Поймано на живом журнале. */
function detail(log: AuditLogItem): string | null {
  const p = (log.payload ?? {}) as Record<string, unknown>;
  const parts: string[] = [];
  const n = (k: string) => (typeof p[k] === "number" ? (p[k] as number) : null);
  const s = (k: string) => (typeof p[k] === "string" && p[k] ? (p[k] as string) : null);

  switch (log.action) {
    case "generate":
      parts.push(`заказано ${n("requested") ?? "?"}, приготовлено ${n("delivered") ?? 0}`);
      if (p.mode === "batch") parts.push("партия на день");
      break;
    case "reject_all":
      if (n("count") !== null) parts.push(`постов: ${n("count")}`);
      break;
    case "restore":
      if (n("restored") !== null) parts.push(`возвращено: ${n("restored")}`);
      break;
    case "edit":
      if (n("length") !== null) parts.push(`${n("length")} симв.`);
      break;
    case "reject":
      if (s("reason")) parts.push(`причина: ${s("reason")}`);
      break;
    case "settings_change":
      if (s("field")) parts.push(s("field")!);
      break;
  }
  if (p.via === "bot") parts.push("из бота");
  return parts.length ? parts.join(" · ") : null;
}

// Идентификатор показываем только когда он UUID: его копируют, чтобы найти
// конкретный пост. У настроек там имя раздела, и обрезка до восьми знаков давала
// в журнале загадочное «automati».
const UUID_RE = /^[0-9a-f]{8}-[0-9a-f]{4}-/i;

function when(iso: string): string {
  const d = new Date(iso);
  return d.toLocaleString("ru-RU", {
    day: "2-digit",
    month: "2-digit",
    hour: "2-digit",
    minute: "2-digit",
  });
}

export function AuditLogCard() {
  const [action, setAction] = useState("");
  const [themeId, setThemeId] = useState("");
  const [limit, setLimit] = useState(50);
  const themes = useQuery(themesQuery());
  const { data, isLoading, error, refetch } = useQuery(
    auditLogsQuery({ action: action || undefined, themeId: themeId || undefined, limit })
  );

  return (
    <Card className="flex flex-col gap-4">
      <div className="flex flex-col gap-1">
        <h2 className="text-sm font-semibold text-ink">Журнал действий</h2>
        <p className="text-xs text-ink-muted">
          Кто что сделал и когда: решения над очередью, входы в панель, смена ключей.
          Записи не редактируются и не удаляются.
        </p>
      </div>

      <div className="flex flex-wrap gap-2">
        <Select value={action} onChange={(e) => setAction(e.target.value)}>
          {FILTERS.map((f) => (
            <option key={f.value} value={f.value}>
              {f.label}
            </option>
          ))}
        </Select>
        <Select value={themeId} onChange={(e) => setThemeId(e.target.value)}>
          <option value="">Все темы</option>
          {(themes.data ?? []).map((t) => (
            <option key={t.id} value={t.id}>
              {t.name}
            </option>
          ))}
        </Select>
      </div>

      {isLoading && <CardSkeleton rows={4} />}
      {error && <ErrorState message={errorText(error)} onRetry={() => refetch()} />}
      {data && data.items.length === 0 && (
        <EmptyState message="Записей пока нет — под выбранный фильтр ничего не попало." />
      )}

      {data && data.items.length > 0 && (
        <ul className="flex flex-col divide-y divide-border-soft">
          {data.items.map((log) => {
            // Собираем одной строкой и склеиваем точками, а не рисуем «· что-то»
            // каждым куском: иначе у записи без подробностей строка начиналась с
            // висящей точки. Видно на снимке живого журнала.
            const meta = [
              detail(log),
              log.actor_ip,
              UUID_RE.test(log.entity_id) ? log.entity_id.slice(0, 8) : null,
            ].filter(Boolean);
            return (
              <li key={log.id} className="flex flex-col gap-0.5 py-2">
                {/* Время отдельной несжимаемой колонкой, а не в общем потоке:
                    в одном ряду с темой оно на телефоне съезжало на свою строку,
                    и список шёл лесенкой. */}
                <div className="flex items-baseline justify-between gap-2">
                  <span className="flex flex-wrap items-baseline gap-x-2 text-sm text-ink">
                    <span>
                      <span className="font-medium">{actorName(log)}</span>
                      {" · "}
                      {ACTION_TITLES[log.action] ?? log.action}
                    </span>
                    {log.theme_name && (
                      <span className="text-xs text-ink-muted">{log.theme_name}</span>
                    )}
                  </span>
                  <span className="shrink-0 text-xs tabular-nums text-ink-faint">
                    {when(log.created_at)}
                  </span>
                </div>
                {meta.length > 0 && (
                  <p className="text-xs text-ink-faint">{meta.join(" · ")}</p>
                )}
              </li>
            );
          })}
        </ul>
      )}

      {data?.has_more && (
        <div>
          <Button variant="secondary" onClick={() => setLimit((n) => Math.min(n + 50, 200))}>
            Показать ещё
          </Button>
        </div>
      )}
    </Card>
  );
}
