import { useState } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { Link } from "react-router-dom";
import { api, ApiError } from "../api/client";
import { publicationsQuery, sourceChannelsQuery, themesQuery } from "../api/queries";
import {
  Button,
  Card,
  EmptyState,
  ErrorState,
  LoadingState,
  Select,
  TextAction,
} from "../components/ui";
import { PostPassportCard } from "../components/PostPassportCard";
import { formatMoment, useProjectTz } from "../lib/datetime";
import { errorText } from "../lib/errors";
import { plural } from "../lib/plural";
import type { PublicationItem } from "../types";

/* «Публикации» — то, чего в панели не было вовсе (UX-аудит, №3 и структурный
   вывод). Конвейер обрывался на выходе поста: единственным следом были пять
   строк превью в свёрнутом блоке на «Очереди», без ссылки на источник и без
   единого действия. Поэтому не работали три сценария сразу: «откуда пришёл
   плохой пост», «этот источник поставляет мусор» и «что зашло за месяц».

   Здесь публикация показана целиком — вышедший текст, оригинал, из которого
   его сделали, источник, персона на момент генерации и метрики отдачи — и от
   неё же можно действовать: убрать источник из ротации или взять текст в
   образцы стиля. */

const PAGE_SIZE = 20;

function tgLink(chatId: number, messageId: number): string {
  // Приватный супергрупп/канал: -100XXXXXXXXXX -> t.me/c/XXXXXXXXXX/<msg>.
  // Ссылка открывается у того, кто состоит в канале, — то есть у оператора.
  const raw = String(chatId).replace(/^-100/, "").replace(/^-/, "");
  return `https://t.me/c/${raw}/${messageId}`;
}

function Metric({ views, forwards }: { views: number | null; forwards: number | null }) {
  if (views === null && forwards === null) {
    return (
      <span
        title="Просмотры собираются только если целевому каналу назначен аккаунт-читалка (вкладка темы → «Каналы»)."
        className="text-xs text-ink-muted whitespace-nowrap"
      >
        метрики не собираются
      </span>
    );
  }
  return (
    <span className="font-mono text-xs tabular-nums text-ink-muted whitespace-nowrap">
      👁 {views ?? "—"} · 🔁 {forwards ?? "—"}
    </span>
  );
}

function PublicationCard({ pub, tz }: { pub: PublicationItem; tz: string }) {
  const queryClient = useQueryClient();
  const [showOrigin, setShowOrigin] = useState(false);
  const [showPersona, setShowPersona] = useState(false);
  const [showPassport, setShowPassport] = useState(false);
  const [note, setNote] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);

  const learn = useMutation({
    mutationFn: () => api.post<{ detail: string }>(`/publications/${pub.id}/learn`),
    onSuccess: (r) => {
      setError(null);
      setNote(r.detail);
      queryClient.invalidateQueries({ queryKey: ["channel-bots"] });
    },
    onError: (err) => setError(err instanceof ApiError ? err.message : "Не удалось сохранить"),
  });

  const retireSource = useMutation({
    mutationFn: () =>
      api.put(`/source-channels/${pub.source_channel_id}/active`, { is_active: false }),
    onSuccess: () => {
      setError(null);
      setNote("Источник выключен — новые посты из него браться не будут.");
      queryClient.invalidateQueries({ queryKey: ["publications"] });
      queryClient.invalidateQueries({ queryKey: ["source-channels"] });
    },
    onError: (err) => setError(err instanceof ApiError ? err.message : "Не удалось выключить"),
  });

  const busy = learn.isPending || retireSource.isPending;

  return (
    <Card className="flex flex-col gap-3">
      <div className="flex flex-wrap items-center justify-between gap-2">
        <div className="flex flex-wrap items-center gap-2">
          <Link
            to={`/themes/${pub.theme_id}`}
            className="inline-flex min-h-11 items-center rounded-full bg-accent-soft px-2.5 py-0.5 text-xs font-medium text-ink hover:opacity-80 sm:min-h-0"
          >
            {pub.theme_name}
          </Link>
          <span className="text-xs text-ink-muted">{pub.channel_title}</span>
          {pub.rubric && (
            <span
              title="Подтема поста. По ним планировщик чередует выдачу — здесь видно, ровно ли она ложится."
              className="rounded-full bg-surface-2 px-2 py-0.5 text-xs text-ink-muted"
            >
              {pub.rubric}
            </span>
          )}
          {pub.kind === "pool" && (
            <span
              title="Пост из собственного запаса темы, а не рерайт чужого."
              className="rounded-full bg-surface-2 px-2 py-0.5 text-xs text-ink-muted"
            >
              из запаса
            </span>
          )}
          {pub.is_ad_cover && (
            <span
              title="Этим постом система перекрыла чужую рекламу в канале."
              className="rounded-full bg-surface-2 px-2 py-0.5 text-xs text-ink-muted"
            >
              перекрытие рекламы
            </span>
          )}
        </div>
        <Metric views={pub.views} forwards={pub.forwards} />
      </div>

      <p className="whitespace-pre-wrap text-sm text-ink">{pub.text || "— текст не сохранился —"}</p>

      <div className="flex flex-wrap items-center gap-x-3 gap-y-1 text-xs text-ink-muted">
        <span>{formatMoment(pub.published_at, tz)}</span>
        <span>·</span>
        <a
          href={tgLink(pub.channel_tg_chat_id, pub.tg_message_id)}
          target="_blank"
          rel="noreferrer"
          className="inline-flex min-h-11 items-center underline decoration-dotted underline-offset-2 hover:text-ink sm:min-h-0"
        >
          Открыть в Telegram
        </a>
        {pub.source_channel_title && (
          <>
            <span>·</span>
            <span>
              из{" "}
              <span className="text-ink">{pub.source_channel_title}</span>
              {pub.source_channel_username && ` (@${pub.source_channel_username})`}
              {pub.score !== null && ` · виральность ${pub.score.toFixed(2)}`}
              {pub.source_channel_active === false && " · источник выключен"}
            </span>
          </>
        )}
      </div>

      <div className="flex flex-wrap gap-x-4 gap-y-1">
        {pub.raw_text && (
          <TextAction onClick={() => setShowOrigin((v) => !v)}>
            {showOrigin ? "Скрыть оригинал" : "Показать оригинал"}
          </TextAction>
        )}
        {pub.persona_prompt_used && (
          <TextAction onClick={() => setShowPersona((v) => !v)}>
            {showPersona ? "Скрыть персону" : "Чем переписан"}
          </TextAction>
        )}
        {/* У постов из собственного запаса кандидата нет — разбирать нечего. */}
        {pub.candidate_id && (
          <TextAction onClick={() => setShowPassport((v) => !v)}>
            {showPassport ? "Скрыть разбор" : "Почему такой пост"}
          </TextAction>
        )}
        <TextAction
          disabled={busy}
          onClick={() => learn.mutate()}
          title="Текст станет образцом «пиши так» для бота темы — следующие рерайты будут на него равняться."
        >
          Этот пост — в персону
        </TextAction>
        {pub.source_channel_id && pub.source_channel_active !== false && (
          <TextAction
            className="text-bad hover:opacity-80"
            disabled={busy}
            onClick={() => {
              if (
                window.confirm(
                  `Выключить источник «${pub.source_channel_title}»? Новые посты из него браться не будут, уже собранные останутся. Включить обратно можно во вкладке темы.`,
                )
              ) {
                retireSource.mutate();
              }
            }}
          >
            Убрать источник из ротации
          </TextAction>
        )}
      </div>

      {showOrigin && pub.raw_text && (
        <div>
          <p className="mb-1 text-xs text-ink-muted">Исходный пост конкурента:</p>
          <p className="whitespace-pre-wrap rounded-lg bg-surface-2 p-3 text-xs text-ink-muted">
            {pub.raw_text}
          </p>
        </div>
      )}
      {showPersona && pub.persona_prompt_used && (
        <div>
          <p className="mb-1 text-xs text-ink-muted">
            Персона на момент генерации (сейчас она могла измениться):
          </p>
          <p className="whitespace-pre-wrap rounded-lg bg-surface-2 p-3 text-xs text-ink-muted">
            {pub.persona_prompt_used}
          </p>
        </div>
      )}

      {showPassport && pub.candidate_id && <PostPassportCard candidateId={pub.candidate_id} />}

      {note && <p className="text-xs text-good">{note}</p>}
      {error && <p className="text-xs text-bad">{error}</p>}
    </Card>
  );
}

export function Publications() {
  const tz = useProjectTz();
  const themes = useQuery(themesQuery());
  const sources = useQuery(sourceChannelsQuery(false));
  const [themeId, setThemeId] = useState("");
  const [sourceId, setSourceId] = useState("");
  const [days, setDays] = useState("");
  const [pages, setPages] = useState(1);

  const filters = {
    themeId: themeId || undefined,
    sourceChannelId: sourceId || undefined,
    days: days ? Number(days) : undefined,
    limit: PAGE_SIZE * pages,
    offset: 0,
  };
  const { data, isLoading, error, refetch } = useQuery(publicationsQuery(filters));

  const resetPages = () => setPages(1);

  return (
    <div className="flex flex-col gap-6">
      <div>
        <h1 className="text-xl font-semibold text-ink">Публикации</h1>
        <p className="mt-1 text-sm text-ink-muted">
          Что уже вышло в каналы — с оригиналом, источником и отдачей. Отсюда же можно убрать
          источник из ротации или взять удачный пост в образцы стиля.
        </p>
      </div>

      <Card className="flex flex-col gap-2">
        <div className="flex flex-col gap-2 sm:flex-row">
          <label className="flex flex-1 flex-col gap-1 text-xs text-ink-muted">
            Тема
            <Select
              value={themeId}
              onChange={(e) => {
                setThemeId(e.target.value);
                resetPages();
              }}
            >
              <option value="">Все темы</option>
              {themes.data?.map((t) => (
                <option key={t.id} value={t.id}>
                  {t.name}
                </option>
              ))}
            </Select>
          </label>
          <label className="flex flex-1 flex-col gap-1 text-xs text-ink-muted">
            Источник
            <Select
              value={sourceId}
              onChange={(e) => {
                setSourceId(e.target.value);
                resetPages();
              }}
            >
              <option value="">Любой источник</option>
              {sources.data?.map((s) => (
                <option key={s.id} value={s.id}>
                  {s.title}
                </option>
              ))}
            </Select>
          </label>
          <label className="flex flex-col gap-1 text-xs text-ink-muted sm:w-44">
            Период
            <Select
              value={days}
              onChange={(e) => {
                setDays(e.target.value);
                resetPages();
              }}
            >
              <option value="">За всё время</option>
              <option value="1">За сутки</option>
              <option value="7">За неделю</option>
              <option value="30">За месяц</option>
            </Select>
          </label>
        </div>
        <p className="text-xs text-ink-muted">
          Фильтр по источнику отвечает на вопрос «что этот канал нам дал» — видно и сколько
          постов, и как они зашли.
        </p>
      </Card>

      {isLoading && <LoadingState />}
      {error && <ErrorState message={errorText(error)} onRetry={() => refetch()} />}
      {data && data.items.length === 0 && (
        <Card>
          <EmptyState
            message={
              themeId || sourceId || days
                ? "По этим фильтрам публикаций нет — попробуйте расширить период."
                : "Публикаций ещё не было. Как только бот выпустит первый пост, он появится здесь."
            }
          />
        </Card>
      )}

      {data?.items.map((pub) => (
        <PublicationCard key={pub.id} pub={pub} tz={tz} />
      ))}

      {data?.has_more && (
        <Button variant="secondary" onClick={() => setPages((p) => p + 1)} className="self-center">
          Показать ещё {PAGE_SIZE} {plural(PAGE_SIZE, "публикацию", "публикации", "публикаций")}
        </Button>
      )}
    </div>
  );
}
