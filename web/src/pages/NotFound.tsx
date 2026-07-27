import { Link } from "react-router-dom";
import { Card } from "../components/ui";

/* Раньше несуществующий адрес молча редиректил на дашборд: URL оставался
   неправильным, а оператор видел обычную главную и решал, что перешёл куда
   надо. Теперь ошибка называется вслух — UX-аудит, №14. */
export function NotFound() {
  return (
    <Card className="flex flex-col items-start gap-3">
      <h1 className="text-xl font-semibold text-ink">Страница не найдена</h1>
      <p className="text-sm text-ink-muted">
        Такого адреса в панели нет. Возможно, ссылка устарела — разделы переезжали:
        источники, боты, каналы и запас теперь живут внутри вкладки темы.
      </p>
      <div className="flex flex-wrap gap-2">
        <Link
          to="/"
          className="rounded-lg bg-accent px-3 py-1.5 text-xs font-semibold text-accent-ink hover:bg-accent-strong"
        >
          На дашборд
        </Link>
        <Link
          to="/themes"
          className="rounded-lg border border-border px-3 py-1.5 text-xs font-medium text-ink hover:bg-surface-2"
        >
          К темам
        </Link>
      </div>
    </Card>
  );
}
