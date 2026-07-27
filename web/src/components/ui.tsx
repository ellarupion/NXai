import type { ReactNode } from "react";

export function Card({ children, className = "" }: { children: ReactNode; className?: string }) {
  return (
    <div className={`shadow-token rounded-xl border border-border bg-surface p-5 ${className}`}>
      {children}
    </div>
  );
}

export function StatTile({ label, value }: { label: string; value: ReactNode }) {
  return (
    <Card className="text-center">
      <div className="font-mono text-2xl font-medium tabular-nums whitespace-nowrap">{value}</div>
      <div className="mt-1 text-xs tracking-wide text-ink-muted uppercase">{label}</div>
    </Card>
  );
}

export function StatusBadge({ active }: { active: boolean }) {
  return (
    <span
      className={`rounded-full px-2 py-0.5 text-xs font-medium whitespace-nowrap ${
        active ? "bg-good-soft text-good" : "bg-surface-2 text-ink-muted"
      }`}
    >
      {active ? "Активна" : "Отключена"}
    </span>
  );
}

export function LoadingState({ label = "Загрузка…" }: { label?: string }) {
  return <p className="py-8 text-center text-sm text-ink-muted">{label}</p>;
}

export function ErrorState({ message, onRetry }: { message: string; onRetry?: () => void }) {
  return (
    <div className="flex flex-col items-start gap-2 rounded-lg bg-bad-soft p-3 text-sm text-bad">
      <p>{message}</p>
      {onRetry && (
        <button
          type="button"
          onClick={onRetry}
          className="min-h-[32px] underline underline-offset-2 hover:no-underline"
        >
          Повторить
        </button>
      )}
    </div>
  );
}

export function EmptyState({ message }: { message: string }) {
  return <p className="py-8 text-center text-sm text-ink-muted">{message}</p>;
}

export function Callout({ children, tone = "info" }: { children: ReactNode; tone?: "info" | "warning" }) {
  const styles = tone === "warning" ? "bg-bad-soft text-bad" : "bg-surface-2 text-ink-muted";
  return <div className={`rounded-lg p-3 text-sm ${styles}`}>{children}</div>;
}

export function Button({
  children,
  variant = "primary",
  className = "",
  ...props
}: React.ButtonHTMLAttributes<HTMLButtonElement> & { variant?: "primary" | "secondary" | "danger" }) {
  const variants = {
    primary: "bg-ink text-bg hover:bg-accent-strong hover:text-accent-ink",
    secondary: "bg-surface-2 text-ink-muted hover:bg-border hover:text-ink",
    danger: "bg-bad text-white hover:opacity-90",
  };
  return (
    <button
      className={`rounded-lg px-3 py-1.5 text-sm font-medium transition-colors disabled:cursor-not-allowed disabled:opacity-50 ${variants[variant]} ${className}`}
      {...props}
    >
      {children}
    </button>
  );
}

/* Тач-цели (UX-аудит, №16). Рекомендованный минимум для пальца — 44px, а у нас
   нативные чекбоксы рисовались 13×13, и текстовые действия-ссылки — высотой 16px.
   На мышке это норма, на телефоне — промах через раз. Ниже два примитива,
   которые растягивают ЗОНУ НАЖАТИЯ на мобильном, не раздувая вид на десктопе. */

/** Чекбокс с увеличенной зоной нажатия. Сам квадратик крупнее (18px), а строка
 *  целиком кликабельна и на мобильном имеет высоту от 44px. */
export function Checkbox({
  label,
  hint,
  className = "",
  ...props
}: React.InputHTMLAttributes<HTMLInputElement> & { label: ReactNode; hint?: ReactNode }) {
  return (
    <label
      className={`flex min-h-11 cursor-pointer items-start gap-3 py-1 sm:min-h-0 sm:py-0 ${className}`}
    >
      <input
        type="checkbox"
        {...props}
        className="mt-0.5 h-[18px] w-[18px] shrink-0 cursor-pointer accent-[var(--color-accent)]"
      />
      <span className="flex min-w-0 flex-col gap-0.5">
        <span className="text-sm font-medium text-ink">{label}</span>
        {hint && <span className="text-xs text-ink-muted">{hint}</span>}
      </span>
    </label>
  );
}

/** Текстовое действие-ссылка (пунктирное подчёркивание). На мобильном добирает
 *  высоту до 44px, на десктопе остаётся компактной строкой. */
export function TextAction({
  className = "",
  children,
  ...props
}: React.ButtonHTMLAttributes<HTMLButtonElement>) {
  return (
    <button
      type="button"
      {...props}
      className={`inline-flex min-h-11 items-center text-xs text-ink-muted underline decoration-dotted underline-offset-2 hover:text-ink disabled:cursor-not-allowed disabled:opacity-50 sm:min-h-0 ${className}`}
    >
      {children}
    </button>
  );
}

export function Input(props: React.InputHTMLAttributes<HTMLInputElement>) {
  return (
    <input
      {...props}
      className={`min-w-0 rounded-lg border border-border bg-surface px-3 py-1.5 text-sm text-ink outline-none focus:border-accent ${props.className ?? ""}`}
    />
  );
}

export function Select(props: React.SelectHTMLAttributes<HTMLSelectElement>) {
  return (
    <select
      {...props}
      className={`min-w-0 max-w-full rounded-lg border border-border bg-surface px-3 py-1.5 text-sm text-ink outline-none focus:border-accent ${props.className ?? ""}`}
    />
  );
}

export function Textarea(props: React.TextareaHTMLAttributes<HTMLTextAreaElement>) {
  return (
    <textarea
      {...props}
      className={`rounded-lg border border-border bg-surface px-3 py-1.5 text-sm text-ink outline-none focus:border-accent ${props.className ?? ""}`}
    />
  );
}
