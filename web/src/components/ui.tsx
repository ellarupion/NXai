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

export function ErrorState({ message }: { message: string }) {
  return <p className="rounded-lg bg-bad-soft p-3 text-sm text-bad">{message}</p>;
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

export function Input(props: React.InputHTMLAttributes<HTMLInputElement>) {
  return (
    <input
      {...props}
      className={`rounded-lg border border-border bg-surface px-3 py-1.5 text-sm text-ink outline-none focus:border-accent ${props.className ?? ""}`}
    />
  );
}

export function Select(props: React.SelectHTMLAttributes<HTMLSelectElement>) {
  return (
    <select
      {...props}
      className={`rounded-lg border border-border bg-surface px-3 py-1.5 text-sm text-ink outline-none focus:border-accent ${props.className ?? ""}`}
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
