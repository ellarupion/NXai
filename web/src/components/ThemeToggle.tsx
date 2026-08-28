import { useTheme, type ThemeMode } from "../theme/ThemeContext";

// Кнопка перебирает три состояния по кругу: как на устройстве → светлая → тёмная.
// Отдельного выпадающего списка нет намеренно: состояний три, и перебор одним нажатием
// быстрее, чем открыть меню и выбрать. Что выбрано сейчас — видно по значку, а словами
// написано в подсказке.

const TITLES: Record<ThemeMode, string> = {
  auto: "Тема: как на устройстве. Нажмите — светлая",
  light: "Тема: светлая. Нажмите — тёмная",
  dark: "Тема: тёмная. Нажмите — как на устройстве",
};

function SunIcon() {
  return (
    <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.8" strokeLinecap="round" className="h-[18px] w-[18px]" aria-hidden>
      <circle cx="12" cy="12" r="4" />
      <path d="M12 2.5v2M12 19.5v2M4.2 4.2l1.4 1.4M18.4 18.4l1.4 1.4M2.5 12h2M19.5 12h2M4.2 19.8l1.4-1.4M18.4 5.6l1.4-1.4" />
    </svg>
  );
}

function MoonIcon() {
  return (
    <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.8" strokeLinecap="round" strokeLinejoin="round" className="h-[18px] w-[18px]" aria-hidden>
      <path d="M20 13.5A8.5 8.5 0 0 1 10.5 4a7.5 7.5 0 1 0 9.5 9.5z" />
    </svg>
  );
}

/** «Как на устройстве» — половина солнца, половина луны: значок сам говорит, что
 *  режим не выбран, а следует за системой. */
function AutoIcon() {
  return (
    <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.8" strokeLinecap="round" strokeLinejoin="round" className="h-[18px] w-[18px]" aria-hidden>
      <circle cx="12" cy="12" r="8.5" />
      <path d="M12 3.5v17a8.5 8.5 0 0 0 0-17z" fill="currentColor" stroke="none" />
    </svg>
  );
}

export function ThemeToggle({ className = "" }: { className?: string }) {
  const { mode, cycleTheme } = useTheme();
  const icon = mode === "auto" ? <AutoIcon /> : mode === "light" ? <SunIcon /> : <MoonIcon />;

  return (
    <button
      type="button"
      onClick={cycleTheme}
      title={TITLES[mode]}
      aria-label={TITLES[mode]}
      className={`grid h-9 w-9 shrink-0 place-items-center rounded-lg border border-border text-ink-muted transition-colors hover:bg-surface-2 hover:text-ink ${className}`}
    >
      {icon}
    </button>
  );
}
