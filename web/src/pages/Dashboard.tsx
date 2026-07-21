import { useQuery } from "@tanstack/react-query";
import { Link } from "react-router-dom";
import { sourceChannelsQuery, themesQuery } from "../api/queries";
import { Card, ErrorState, LoadingState, StatTile } from "../components/ui";

export function Dashboard() {
  const themes = useQuery(themesQuery());
  const sourceChannels = useQuery(sourceChannelsQuery(false));

  if (themes.isLoading || sourceChannels.isLoading) return <LoadingState />;
  if (themes.error) return <ErrorState message={themes.error.message} />;
  if (sourceChannels.error) return <ErrorState message={sourceChannels.error.message} />;

  const activeThemes = themes.data?.filter((t) => t.is_active).length ?? 0;
  const totalChannels = sourceChannels.data?.length ?? 0;
  const unassigned = sourceChannels.data?.filter((c) => c.theme_id === null).length ?? 0;

  return (
    <div className="flex flex-col gap-6">
      <div>
        <h1 className="text-xl font-semibold text-ink">Дашборд</h1>
        <p className="mt-1 text-sm text-ink-muted">
          Phase 0/1 — панель показывает только то, что реально считает бэкенд:
          темы и источники. Пул кандидатов, боты и статистика появятся по мере
          наполнения (см. ROADMAP.md).
        </p>
      </div>

      <div className="grid grid-cols-2 gap-4 md:grid-cols-3">
        <StatTile label="Тем всего" value={themes.data?.length ?? 0} />
        <StatTile label="Активных тем" value={activeThemes} />
        <StatTile label="Источников всего" value={totalChannels} />
        <StatTile label="Без темы" value={unassigned} />
      </div>

      {unassigned > 0 && (
        <Card className="border-accent/40">
          <p className="text-sm text-ink">
            Есть <span className="font-semibold">{unassigned}</span> источник(ов) без
            темы —{" "}
            <Link to="/source-channels" className="text-accent underline underline-offset-2">
              распределите их
            </Link>{" "}
            по темам.
          </p>
        </Card>
      )}
    </div>
  );
}
