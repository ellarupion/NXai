/* Человеческий текст ошибки для ErrorState (UX-аудит, №12).
 *
 * 5xx бэкенд отдаёт как "Internal Server Error" — показывать оператору
 * английскую техническую строку бессмысленно, он не может по ней ничего
 * сделать. Осмысленные 4xx бэкенд пишет по-русски сам (detail) — их оставляем
 * как есть, они полезнее любого общего текста. */
import { ApiError } from "../api/client";

export function errorText(error: unknown): string {
  if (error instanceof ApiError) {
    if (error.status >= 500) {
      return "Сервер не смог обработать запрос — это сбой на нашей стороне, а не ошибка ввода. Попробуйте ещё раз.";
    }
    if (error.status === 404) return "Данные не найдены — возможно, их успели удалить.";
    return error.message;
  }
  // fetch бросает TypeError, когда до сервера вообще не достучались
  if (error instanceof TypeError) {
    return "Нет связи с сервером. Проверьте интернет и попробуйте ещё раз.";
  }
  return error instanceof Error ? error.message : "Неизвестная ошибка.";
}
