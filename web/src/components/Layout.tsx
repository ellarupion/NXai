import { Suspense, useEffect, useState } from "react";
import { Link, NavLink, Outlet, useLocation } from "react-router-dom";
import { useAuth } from "../auth/AuthContext";
import { LoadingState } from "./ui";

const NAV_ITEMS = [
  { to: "/", label: "Дашборд", end: true },
  { to: "/themes", label: "Темы" },
  { to: "/source-channels", label: "Источники" },
  { to: "/telethon-sessions", label: "Аккаунты" },
  { to: "/target-channels", label: "Каналы" },
  { to: "/bots", label: "Боты" },
  { to: "/review", label: "Проверка" },
  { to: "/pool-posts", label: "Запас" },
  { to: "/settings", label: "Настройки" },
];

function navLinkClass({ isActive }: { isActive: boolean }): string {
  return [
    "relative rounded-lg px-3 py-2 text-sm font-medium transition-colors",
    isActive
      ? "bg-surface-2 text-ink"
      : "text-ink-muted hover:bg-surface-2 hover:text-ink",
  ].join(" ");
}

/* Лаймовая «искра» — лого-знак NXai. Монограмма-разряд в квадрате-панели,
   читается как «сигнал/эфир», роднит с control-room-темой. */
function LogoMark({ className = "" }: { className?: string }) {
  return (
    <svg viewBox="0 0 32 32" fill="none" className={className} aria-hidden="true">
      <rect x="1.5" y="1.5" width="29" height="29" rx="8" stroke="var(--accent)" strokeWidth="2" />
      <path
        d="M9 22L15 10L17 17L23 10"
        stroke="var(--accent)"
        strokeWidth="2.4"
        strokeLinecap="round"
        strokeLinejoin="round"
      />
      <circle cx="23" cy="10" r="2.2" fill="var(--accent)" />
    </svg>
  );
}

function Wordmark() {
  return (
    <Link to="/" className="flex items-center gap-2.5 transition-opacity hover:opacity-80">
      <LogoMark className="h-8 w-8 shrink-0 glow-accent rounded-lg" />
      <span className="font-display text-lg font-extrabold tracking-tight text-ink">
        NX<span className="text-accent">ai</span>
      </span>
    </Link>
  );
}

function MenuIcon({ open }: { open: boolean }) {
  return (
    <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" className="h-5 w-5">
      {open ? <path d="M6 6l12 12M18 6L6 18" /> : <path d="M4 7h16M4 12h16M4 17h16" />}
    </svg>
  );
}

function NavList({ onNavigate }: { onNavigate?: () => void }) {
  return (
    <nav className="flex flex-col gap-1">
      {NAV_ITEMS.map((item) => (
        <NavLink key={item.to} to={item.to} end={item.end} className={navLinkClass} onClick={onNavigate}>
          {({ isActive }) => (
            <span className="flex items-center gap-2.5">
              <span
                className={[
                  "h-4 w-0.5 rounded-full transition-colors",
                  isActive ? "bg-accent" : "bg-transparent",
                ].join(" ")}
              />
              {item.label}
            </span>
          )}
        </NavLink>
      ))}
    </nav>
  );
}

export function Layout() {
  const { logout } = useAuth();
  const [menuOpen, setMenuOpen] = useState(false);
  const location = useLocation();

  useEffect(() => setMenuOpen(false), [location.pathname]);

  return (
    <div className="flex min-h-screen bg-bg">
      {/* Десктоп: фиксированный левый сайдбар — главная структурная разница с NX. */}
      <aside className="fixed inset-y-0 left-0 z-30 hidden w-60 flex-col border-r border-border bg-surface md:flex">
        <div className="flex h-16 items-center border-b border-border px-5">
          <Wordmark />
        </div>
        <div className="flex-1 overflow-y-auto px-3 py-4">
          <NavList />
        </div>
        <div className="border-t border-border px-3 py-3">
          <button
            onClick={logout}
            className="w-full rounded-lg px-3 py-2 text-left text-sm text-ink-muted transition-colors hover:bg-surface-2 hover:text-ink"
          >
            Выйти
          </button>
        </div>
      </aside>

      {/* Мобилка: верхняя полоска с бургером + выезжающее меню. */}
      <header className="fixed inset-x-0 top-0 z-30 flex h-14 items-center justify-between border-b border-border bg-surface px-4 md:hidden">
        <Wordmark />
        <button
          onClick={() => setMenuOpen((v) => !v)}
          title="Меню"
          aria-label="Меню"
          aria-expanded={menuOpen}
          className="grid h-9 w-9 place-items-center rounded-lg border border-border bg-surface text-ink-muted transition-colors hover:bg-surface-2 hover:text-ink"
        >
          <MenuIcon open={menuOpen} />
        </button>
      </header>

      {menuOpen && (
        <>
          <div
            className="fixed inset-0 z-30 bg-black/50 md:hidden"
            onClick={() => setMenuOpen(false)}
            aria-hidden="true"
          />
          <div className="fixed inset-y-0 left-0 z-40 flex w-64 flex-col border-r border-border bg-surface md:hidden">
            <div className="flex h-14 items-center border-b border-border px-4">
              <Wordmark />
            </div>
            <div className="flex-1 overflow-y-auto px-3 py-4">
              <NavList onNavigate={() => setMenuOpen(false)} />
            </div>
            <div className="border-t border-border px-3 py-3">
              <button
                onClick={logout}
                className="w-full rounded-lg px-3 py-2 text-left text-sm text-ink-muted transition-colors hover:bg-surface-2 hover:text-ink"
              >
                Выйти
              </button>
            </div>
          </div>
        </>
      )}

      {/* Контент со сдвигом под сайдбар (десктоп) / под верхнюю полоску (мобилка). */}
      <div className="flex min-w-0 flex-1 flex-col pt-14 md:pt-0 md:pl-60">
        <main className="mx-auto w-full max-w-6xl flex-1 px-4 py-6 md:px-8">
          <Suspense fallback={<LoadingState />}>
            <Outlet />
          </Suspense>
        </main>
      </div>
    </div>
  );
}
