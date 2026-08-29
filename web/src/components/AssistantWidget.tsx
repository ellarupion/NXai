import { useEffect, useRef, useState } from "react";
import { useMutation } from "@tanstack/react-query";
import { api, ApiError } from "../api/client";
import { errorText } from "../lib/errors";

/* Помощник: свободный вопрос о своей же системе.

   Панель отвечает на вопросы, которые кто-то предвидел заранее. «Почему сегодня мало
   постов» — не из них: ответ складывается из порогов, состояния конвейера и того, что
   творится с источниками, то есть из трёх экранов и головы.

   Окно, а не отдельная страница: спрашивают обычно ПРО ТО, что сейчас на экране, и
   уходить ради вопроса со страницы неправильно.

   Переписка живёт в localStorage этого браузера. На сервере её нет вовсе — разговор
   длится минуты, и заводить ради него таблицу незачем. Отсюда же и «Очистить»:
   помощник видит всю переписку, и старый разговор про другую тему сбивает ответы. */

const STORAGE_KEY = "nxai_assistant_thread";

// Столько реплик держим в браузере. В модель уходит ещё меньше (хвост), но и здесь
// потолок нужен: localStorage не резиновый, а разговор недельной давности бесполезен.
const MAX_KEPT = 40

type Turn = {
  role: "user" | "assistant";
  content: string;
  used?: string[];
  error?: boolean;
};

type AskResponse = { answer: string; used: string[]; cost_usd: number };

const EXAMPLES = [
  "Почему сегодня мало постов?",
  "На что ушли деньги за неделю?",
  "Какой источник перестал давать выхлоп?",
  "Что вышло вчера и как зашло?",
];

function loadThread(): Turn[] {
  // В приватном окне и при запрещённых данных сайта обращение к localStorage бросает
  // исключение — не «возвращает пусто». Без try/catch падало бы всё окно помощника.
  try {
    const raw = localStorage.getItem(STORAGE_KEY);
    return raw ? (JSON.parse(raw) as Turn[]) : [];
  } catch {
    return [];
  }
}

function saveThread(turns: Turn[]) {
  try {
    localStorage.setItem(STORAGE_KEY, JSON.stringify(turns.slice(-MAX_KEPT)));
  } catch {
    /* не смогли сохранить — переписка просто не переживёт перезагрузку страницы */
  }
}

function ChatIcon() {
  return (
    <svg viewBox="0 0 24 24" fill="none" className="h-5 w-5" aria-hidden>
      <path
        d="M21 12a8 8 0 0 1-11.6 7.1L4 20l1-4.4A8 8 0 1 1 21 12Z"
        stroke="currentColor"
        strokeWidth="1.8"
        strokeLinejoin="round"
      />
    </svg>
  );
}

function CloseIcon() {
  return (
    <svg viewBox="0 0 24 24" fill="none" className="h-4 w-4" aria-hidden>
      <path d="m6 6 12 12M18 6 6 18" stroke="currentColor" strokeWidth="2" strokeLinecap="round" />
    </svg>
  );
}

export function AssistantWidget() {
  const [open, setOpen] = useState(false);
  const [turns, setTurns] = useState<Turn[]>(loadThread);
  const [draft, setDraft] = useState("");
  const bottomRef = useRef<HTMLDivElement>(null);
  const inputRef = useRef<HTMLTextAreaElement>(null);

  useEffect(() => saveThread(turns), [turns]);
  useEffect(() => {
    if (open) bottomRef.current?.scrollIntoView({ block: "end" });
  }, [open, turns]);

  const ask = useMutation({
    mutationFn: (question: string) =>
      api.post<AskResponse>("/assistant/ask", {
        question,
        // Отправляем только текст реплик: строка «Смотрел» — это для человека, модели
        // она ничего не добавляет, а токены стоит.
        history: turns.map((t) => ({ role: t.role, content: t.content })),
      }),
    onSuccess: (data) =>
      setTurns((prev) => [...prev, { role: "assistant", content: data.answer, used: data.used }]),
    onError: (error) =>
      setTurns((prev) => [
        ...prev,
        {
          role: "assistant",
          // Исчерпанный потолок расходов — не поломка, а состояние, которое владелец
          // сам себе задал, и в тексте уже написано, где его поднять. Красным его
          // рисовать незачем: красное в панели значит «что-то сломалось».
          content:
            error instanceof ApiError && error.status === 402
              ? errorText(error)
              : `Не получилось спросить: ${errorText(error)}`,
          error: !(error instanceof ApiError && error.status === 402),
        },
      ]),
  });

  function send(question: string) {
    const text = question.trim();
    if (!text || ask.isPending) return;
    setTurns((prev) => [...prev, { role: "user", content: text }]);
    setDraft("");
    ask.mutate(text);
  }

  if (!open) {
    return (
      <button
        type="button"
        onClick={() => setOpen(true)}
        title="Спросить помощника"
        aria-label="Спросить помощника"
        /* Над нижней панелью на телефоне — иначе кнопка легла бы поверх разделов.
           Формула та же, что у самой панели: env() у обычного экрана равен нулю. */
        className="fixed right-4 bottom-[max(6.5rem,calc(env(safe-area-inset-bottom,0px)+6rem))] z-40 grid h-12 w-12 place-items-center rounded-full bg-ink text-bg shadow-token transition-colors hover:bg-accent-strong hover:text-accent-ink md:bottom-6"
      >
        <ChatIcon />
      </button>
    );
  }

  return (
    <div className="fixed inset-x-0 bottom-0 z-40 flex justify-end px-0 md:px-6 md:pb-6">
      <div className="flex h-[80vh] w-full flex-col overflow-hidden rounded-t-2xl border border-border bg-surface shadow-token md:h-[32rem] md:w-96 md:rounded-2xl">
        <div className="flex items-center gap-2 border-b border-border-soft px-4 py-3">
          {/* Заголовок и приписка в столбик: в одну строку они на ширине окна
              налезали друг на друга (видно на снимке живой панели). */}
          <div className="flex min-w-0 flex-col">
            <span className="text-sm font-semibold text-ink">Помощник</span>
            <span className="text-xs text-ink-faint">только смотрит, ничего не меняет</span>
          </div>
          <div className="ml-auto flex shrink-0 items-center gap-1">
            {turns.length > 0 && (
              <button
                type="button"
                onClick={() => setTurns([])}
                className="rounded-lg px-2 py-1 text-xs text-ink-muted transition-colors hover:bg-surface-2 hover:text-ink"
              >
                Очистить
              </button>
            )}
            <button
              type="button"
              onClick={() => setOpen(false)}
              aria-label="Закрыть"
              className="grid h-8 w-8 place-items-center rounded-lg text-ink-muted transition-colors hover:bg-surface-2 hover:text-ink"
            >
              <CloseIcon />
            </button>
          </div>
        </div>

        <div className="flex-1 overflow-y-auto px-4 py-3">
          {turns.length === 0 && (
            <div className="flex flex-col gap-3">
              <p className="text-sm text-ink-muted">
                Спросите про своё хозяйство — помощник сам сходит за данными: темы,
                очередь, публикации, источники, расходы, журнал действий.
              </p>
              <div className="flex flex-col items-start gap-1.5">
                {EXAMPLES.map((example) => (
                  <button
                    key={example}
                    type="button"
                    onClick={() => send(example)}
                    className="rounded-full bg-surface-2 px-3 py-1.5 text-left text-xs text-ink-muted transition-colors hover:text-ink"
                  >
                    {example}
                  </button>
                ))}
              </div>
            </div>
          )}

          <div className="flex flex-col gap-3">
            {turns.map((turn, i) => (
              <div
                key={i}
                className={turn.role === "user" ? "flex justify-end" : "flex justify-start"}
              >
                <div
                  className={[
                    "max-w-[85%] rounded-2xl px-3 py-2 text-sm whitespace-pre-wrap",
                    turn.role === "user"
                      ? "bg-accent-soft text-ink"
                      : turn.error
                        ? "bg-bad-soft text-bad"
                        : "bg-surface-2 text-ink",
                  ].join(" ")}
                >
                  {turn.content}
                  {/* «Смотрел» — чтобы ответ можно было отличить от придуманного. */}
                  {turn.used && turn.used.length > 0 && (
                    <p className="mt-1.5 border-t border-border-soft pt-1.5 text-xs text-ink-faint">
                      Смотрел: {turn.used.join("; ")}
                    </p>
                  )}
                </div>
              </div>
            ))}
            {ask.isPending && (
              <div className="flex justify-start">
                <div className="rounded-2xl bg-surface-2 px-3 py-2 text-sm text-ink-muted">
                  Смотрю данные…
                </div>
              </div>
            )}
          </div>
          <div ref={bottomRef} />
        </div>

        <form
          onSubmit={(e) => {
            e.preventDefault();
            send(draft);
          }}
          /* Отступ под полоску iPhone: без него поле ввода упирается в самый низ
             экрана и наполовину перекрывается системным жестом. */
          className="flex items-end gap-2 border-t border-border-soft px-3 py-2 pb-[max(0.5rem,env(safe-area-inset-bottom,0px))]"
        >
          <textarea
            ref={inputRef}
            value={draft}
            onChange={(e) => setDraft(e.target.value)}
            onKeyDown={(e) => {
              // Enter отправляет, Shift+Enter переносит строку: вопрос почти всегда
              // однострочный, и тянуться к кнопке на каждый — лишнее движение.
              if (e.key === "Enter" && !e.shiftKey) {
                e.preventDefault();
                send(draft);
              }
            }}
            rows={1}
            placeholder="Спросить про систему…"
            className="max-h-24 min-h-9 flex-1 resize-none rounded-lg border border-border bg-surface px-3 py-1.5 text-sm text-ink outline-none focus:border-accent"
          />
          <button
            type="submit"
            disabled={!draft.trim() || ask.isPending}
            className="h-9 shrink-0 rounded-lg bg-ink px-3 text-sm font-medium text-bg transition-colors hover:bg-accent-strong hover:text-accent-ink disabled:cursor-not-allowed disabled:opacity-50"
          >
            Спросить
          </button>
        </form>
      </div>
    </div>
  );
}
