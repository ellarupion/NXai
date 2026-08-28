import { createContext, useCallback, useContext, useEffect, useMemo, useState, type ReactNode } from "react";

// Три режима темы, а не два. Прежде панель следовала за системой и всё: выбрать тему
// руками было нечем, и на светлом ноутбуке приходилось читать интерфейс, собранный под
// тёмный. Обратная крайность — запомнить выбор навсегда — тоже плохая: телефон сам
// переключается на тёмную по расписанию, и панель должна ехать за ним.
// Поэтому «как на устройстве» — это отдельное состояние, а не отсутствие выбора.
export type ThemeMode = "auto" | "light" | "dark";
type Theme = "light" | "dark";

const STORAGE_KEY = "nxai_theme";
const DARK_QUERY = "(prefers-color-scheme: dark)";

function systemTheme(): Theme {
  return window.matchMedia?.(DARK_QUERY).matches ? "dark" : "light";
}

function readStoredMode(): ThemeMode {
  // Отсутствие ключа = «как на устройстве». Своего значения для auto в хранилище нет
  // намеренно: тот же самый разбор делает скрипт в index.html до первой отрисовки, и
  // лишнее значение пришлось бы учить понимать в двух местах.
  try {
    const stored = localStorage.getItem(STORAGE_KEY);
    return stored === "light" || stored === "dark" ? stored : "auto";
  } catch {
    // Приватный режим и запрет на хранилище: тема просто следует за системой.
    return "auto";
  }
}

function applyMode(mode: ThemeMode) {
  // В режиме «как на устройстве» атрибут не ставим вообще: тему берёт на себя
  // @media (prefers-color-scheme) в index.css и меняет её вместе с системной без
  // участия JS. data-theme нужен только чтобы перебить этот медиа-запрос.
  try {
    if (mode === "auto") {
      document.documentElement.removeAttribute("data-theme");
      localStorage.removeItem(STORAGE_KEY);
    } else {
      document.documentElement.setAttribute("data-theme", mode);
      localStorage.setItem(STORAGE_KEY, mode);
    }
  } catch {
    // Не смогли записать — атрибут всё равно проставлен, тема в этой вкладке верная.
    if (mode !== "auto") document.documentElement.setAttribute("data-theme", mode);
  }
}

interface ThemeContextValue {
  /** Что выбрано кнопкой: «как на устройстве», светлая или тёмная. */
  mode: ThemeMode;
  /** Тема, которая реально видна сейчас — для значков и графиков. */
  theme: Theme;
  cycleTheme: () => void;
}

const ThemeContext = createContext<ThemeContextValue | null>(null);

export function ThemeProvider({ children }: { children: ReactNode }) {
  const [mode, setMode] = useState<ThemeMode>(readStoredMode);
  const [system, setSystem] = useState<Theme>(systemTheme);

  // Системная тема меняется и при открытой панели — телефон сам переключается на
  // тёмную по расписанию. Страница перекрашивается медиа-запросом сама, но состояние
  // React об этом не знает, и значок на кнопке остался бы от прошлой темы.
  useEffect(() => {
    const query = window.matchMedia?.(DARK_QUERY);
    if (!query) return;
    const onChange = (event: MediaQueryListEvent) => setSystem(event.matches ? "dark" : "light");
    query.addEventListener("change", onChange);
    return () => query.removeEventListener("change", onChange);
  }, []);

  useEffect(() => applyMode(mode), [mode]);

  const cycleTheme = useCallback(() => {
    setMode((prev) => (prev === "auto" ? "light" : prev === "light" ? "dark" : "auto"));
  }, []);

  const theme = mode === "auto" ? system : mode;
  const value = useMemo(() => ({ mode, theme, cycleTheme }), [mode, theme, cycleTheme]);

  return <ThemeContext.Provider value={value}>{children}</ThemeContext.Provider>;
}

// eslint-disable-next-line react-refresh/only-export-components
export function useTheme(): ThemeContextValue {
  const ctx = useContext(ThemeContext);
  if (!ctx) throw new Error("useTheme должен вызываться внутри ThemeProvider");
  return ctx;
}
