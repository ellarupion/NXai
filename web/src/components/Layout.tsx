import { Suspense, useEffect, useState } from "react";
import { Link, NavLink, Outlet, useLocation } from "react-router-dom";
import { useAuth } from "../auth/AuthContext";
import { LoadingState } from "./ui";

const NAV_ITEMS = [
  { to: "/", label: "Дашборд", end: true },
  { to: "/themes", label: "Темы" },
  { to: "/source-channels", label: "Источники" },
];

function navLinkClass({ isActive }: { isActive: boolean }): string {
  return [
    "rounded-lg px-3 py-2 text-sm font-medium whitespace-nowrap transition-colors",
    isActive ? "bg-ink text-bg" : "text-ink-muted hover:bg-surface-2 hover:text-ink",
  ].join(" ");
}

function MenuIcon({ open }: { open: boolean }) {
  return (
    <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" className="h-4 w-4">
      {open ? <path d="M6 6l12 12M18 6L6 18" /> : <path d="M4 7h16M4 12h16M4 17h16" />}
    </svg>
  );
}

export function Layout() {
  const { logout } = useAuth();
  const [menuOpen, setMenuOpen] = useState(false);
  const location = useLocation();

  useEffect(() => setMenuOpen(false), [location.pathname]);

  return (
    <div className="flex min-h-screen flex-col">
      <header className="relative border-b border-border bg-surface">
        <div className="mx-auto flex max-w-6xl items-center justify-between gap-4 px-4 py-4 md:py-3">
          <div className="flex min-w-0 items-center gap-6">
            <Link to="/" className="text-lg font-semibold tracking-tight text-ink transition-opacity hover:opacity-80">
              NXai
            </Link>
            <nav className="hidden gap-1 md:flex">
              {NAV_ITEMS.map((item) => (
                <NavLink key={item.to} to={item.to} end={item.end} className={navLinkClass}>
                  {item.label}
                </NavLink>
              ))}
            </nav>
          </div>
          <div className="flex items-center gap-2">
            <button
              onClick={logout}
              className="hidden rounded-lg px-3 py-2 text-sm text-ink-muted transition-colors hover:bg-surface-2 hover:text-ink md:inline-block"
            >
              Выйти
            </button>
            <button
              onClick={() => setMenuOpen((v) => !v)}
              title="Меню"
              aria-label="Меню"
              aria-expanded={menuOpen}
              className="grid h-9 w-9 place-items-center rounded-lg border border-border bg-surface text-ink-muted transition-colors hover:bg-surface-2 hover:text-ink md:hidden"
            >
              <MenuIcon open={menuOpen} />
            </button>
          </div>
        </div>

        {menuOpen && (
          <nav className="flex flex-col gap-1 border-t border-border px-4 py-3 md:hidden">
            {NAV_ITEMS.map((item) => (
              <NavLink key={item.to} to={item.to} end={item.end} className={navLinkClass}>
                {item.label}
              </NavLink>
            ))}
            <button
              onClick={logout}
              className="rounded-lg px-3 py-2 text-left text-sm text-ink-muted transition-colors hover:bg-surface-2 hover:text-ink"
            >
              Выйти
            </button>
          </nav>
        )}
      </header>
      <main className="mx-auto w-full max-w-6xl flex-1 px-4 py-6">
        <Suspense fallback={<LoadingState />}>
          <Outlet />
        </Suspense>
      </main>
    </div>
  );
}
