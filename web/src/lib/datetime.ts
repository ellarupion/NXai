/* Единый часовой пояс панели (UX-аудит, №11).
 *
 * Раньше времена расходились в трёх местах: «Очередь» рисовала их в поясе
 * БРАУЗЕРА (toLocaleTimeString без timeZone), тихие часы и дайджест считались
 * бэкендом в поясе ПРОЕКТА (panel_settings.timezone), а здоровье темы печатало
 * UTC. Оператор видел «выход завтра ~05:30» при тихих часах 23–08 и не мог
 * понять, сломано расписание или нет.
 *
 * Здесь все времена приводятся к поясу проекта — тому же, в котором система
 * реально принимает решения о публикации. */
import { useQuery } from "@tanstack/react-query";
import { generalSettingsQuery } from "../api/queries";

export const FALLBACK_TZ = "Europe/Moscow";

/** Пояс проекта из настроек. Пока настройки не загрузились — дефолт, тот же,
 *  что у бэкенда (core/services/scheduler_pool.py:DEFAULT_TIMEZONE). */
export function useProjectTz(): string {
  const { data } = useQuery(generalSettingsQuery());
  return data?.timezone || FALLBACK_TZ;
}

function fmt(iso: string, tz: string, options: Intl.DateTimeFormatOptions): string {
  try {
    return new Intl.DateTimeFormat("ru-RU", { ...options, timeZone: tz }).format(new Date(iso));
  } catch {
    // Неизвестное IANA-имя в настройках не должно ронять страницу — падаем на дефолт.
    return new Intl.DateTimeFormat("ru-RU", { ...options, timeZone: FALLBACK_TZ }).format(
      new Date(iso),
    );
  }
}

/** Какой это день в поясе проекта — нужно, чтобы «сегодня/завтра» считались
 *  по календарю оператора, а не по календарю браузера. */
function dayKey(iso: string, tz: string): string {
  return fmt(iso, tz, { year: "numeric", month: "2-digit", day: "2-digit" });
}

/** «сегодня ~18:37» / «завтра ~05:30» / «3 авг ~09:15» — для прогноза слотов. */
export function formatSlot(iso: string, tz: string): string {
  const now = new Date();
  const tomorrow = new Date(now.getTime() + 24 * 60 * 60 * 1000);
  const hhmm = fmt(iso, tz, { hour: "2-digit", minute: "2-digit" });
  const key = dayKey(iso, tz);

  if (key === dayKey(now.toISOString(), tz)) return `сегодня ~${hhmm}`;
  if (key === dayKey(tomorrow.toISOString(), tz)) return `завтра ~${hhmm}`;
  return `${fmt(iso, tz, { day: "numeric", month: "short" })} ~${hhmm}`;
}

/** «3 авг, 09:15» — для уже случившегося (публикации, метрики). */
export function formatMoment(iso: string, tz: string): string {
  return fmt(iso, tz, { day: "numeric", month: "short", hour: "2-digit", minute: "2-digit" });
}
