import { Suspense, useEffect, useRef, useState } from "react";
import { Link, NavLink, Outlet, useLocation } from "react-router-dom";
import { useAuth } from "../auth/AuthContext";
import { MobileTabBar } from "./MobileTabBar";
import { ThemeToggle } from "./ThemeToggle";
import { PageSkeleton } from "./ui";

// Каркас панели после переноса оформления NX. Главная перемена — навигация: раньше на
// компьютере был левый сайдбар, а на телефоне бургер с выезжающим меню. Теперь строка
// разделов в шапке (компьютер) и «стеклянная» панель снизу (телефон): переход в раздел
// стал одним нажатием вместо двух, и не надо тянуться в верхний угол экрана.
//
// Источники, боты, каналы и запас живут внутри вкладок темы (см. Themes.tsx) — этот
// приём NXai сохранён: правка одной темы не должна требовать обхода четырёх страниц.

const NAV_ITEMS = [
  { to: "/", label: "Дашборд", end: true },
  { to: "/themes", label: "Темы" },
  { to: "/review", label: "Проверка" },
  { to: "/queue", label: "Очередь" },
  { to: "/publications", label: "Публикации" },
  { to: "/spending", label: "Расходы" },
  { to: "/telethon-sessions", label: "Аккаунты" },
  { to: "/settings", label: "Настройки" },
];

// На телефоне в нижнюю панель влезает пять разделов; остальные открываются из шапки:
// их смотрят при настройке и разборе, а не в ежедневной работе.
const EXTRA_ITEMS = NAV_ITEMS.filter(
  (item) =>
    item.to === "/spending" || item.to === "/telethon-sessions" || item.to === "/settings",
);

function navLinkClass({ isActive }: { isActive: boolean }): string {
  return [
    "rounded-lg px-2.5 py-1.5 text-sm font-medium whitespace-nowrap transition-colors",
    isActive ? "bg-accent-soft text-accent" : "text-ink-muted hover:bg-surface-2 hover:text-ink",
  ].join(" ");
}

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
    <Link to="/" className="flex shrink-0 items-center gap-2.5 transition-opacity hover:opacity-80">
      <LogoMark className="h-8 w-8 shrink-0" />
      <span className="font-display text-lg text-ink">
        NX<span className="text-accent">ai</span>
      </span>
    </Link>
  );
}

function MoreIcon() {
  return (
    <svg viewBox="0 0 24 24" fill="currentColor" className="h-[18px] w-[18px]" aria-hidden>
      <circle cx="5" cy="12" r="1.8" />
      <circle cx="12" cy="12" r="1.8" />
      <circle cx="19" cy="12" r="1.8" />
    </svg>
  );
}

/** Разделы, не попавшие в нижнюю панель, плюс выход. Только на телефоне. */
function MoreMenu() {
  const { logout } = useAuth();
  const [open, setOpen] = useState(false);
  const location = useLocation();
  const boxRef = useRef<HTMLDivElement>(null);

  useEffect(() => setOpen(false), [location.pathname]);

  // Нажатие мимо меню закрывает его: иначе на телефоне оно висит поверх страницы, и
  // убрать его можно только выбрав пункт.
  useEffect(() => {
    if (!open) return;
    const onDown = (event: MouseEvent) => {
      if (boxRef.current && !boxRef.current.contains(event.target as Node)) setOpen(false);
    };
    document.addEventListener("mousedown", onDown);
    return () => document.removeEventListener("mousedown", onDown);
  }, [open]);

  return (
    <div ref={boxRef} className="relative md:hidden">
      <button
        type="button"
        onClick={() => setOpen((v) => !v)}
        title="Ещё"
        aria-label="Ещё"
        aria-expanded={open}
        className="grid h-9 w-9 place-items-center rounded-lg border border-border text-ink-muted transition-colors hover:bg-surface-2 hover:text-ink"
      >
        <MoreIcon />
      </button>
      {open && (
        <div className="absolute right-0 top-11 z-50 flex w-48 flex-col overflow-hidden rounded-xl border border-border bg-surface shadow-token">
          {EXTRA_ITEMS.map((item) => (
            <NavLink
              key={item.to}
              to={item.to}
              className="flex min-h-11 items-center px-4 text-sm text-ink transition-colors hover:bg-surface-2"
            >
              {item.label}
            </NavLink>
          ))}
          <button
            onClick={logout}
            className="flex min-h-11 items-center border-t border-border-soft px-4 text-left text-sm text-ink-muted transition-colors hover:bg-surface-2 hover:text-ink"
          >
            Выйти
          </button>
        </div>
      )}
    </div>
  );
}

export function Layout() {
  const { logout } = useAuth();

  return (
    <div className="flex min-h-screen flex-col bg-bg">
      {/* safe-area-top — панель, открытая с домашнего экрана iOS, рисуется во весь
          экран, и без отступа шапка уезжает под «чёлку». */}
      <header className="safe-area-top sticky top-0 z-30 border-b border-border bg-surface">
        <div className="mx-auto flex h-14 w-full max-w-6xl items-center gap-3 px-4 md:px-8">
          <Wordmark />

          {/* Разделы строкой — только на компьютере: на телефоне их место внизу. */}
          <nav className="hidden min-w-0 flex-1 items-center gap-0.5 overflow-x-auto md:flex">
            {NAV_ITEMS.map((item) => (
              <NavLink key={item.to} to={item.to} end={item.end} className={navLinkClass}>
                {item.label}
              </NavLink>
            ))}
          </nav>

          <div className="ml-auto flex items-center gap-2 md:ml-0">
            <ThemeToggle />
            <MoreMenu />
            <button
              onClick={logout}
              className="hidden rounded-lg px-3 py-2 text-sm text-ink-muted transition-colors hover:bg-surface-2 hover:text-ink md:block"
            >
              Выйти
            </button>
          </div>
        </div>
      </header>

      {/* Нижний отступ на телефоне — под «стеклянную» панель, иначе последняя карточка
          страницы прячется под ней. */}
      <main className="mx-auto w-full max-w-6xl flex-1 px-4 pb-28 pt-6 md:px-8 md:pb-10">
        <Suspense fallback={<PageSkeleton />}>
          <Outlet />
        </Suspense>
      </main>

      <MobileTabBar />
    </div>
  );
}
