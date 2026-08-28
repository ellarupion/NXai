import { NavLink, useLocation } from "react-router-dom";

// Нижняя панель телефона — приём перенесён из NX вместе с остальным оформлением.
//
// Чем это лучше прежнего меню-гамбургера: переход между разделами был в два тапа
// (открыть меню, выбрать пункт) и требовал дотянуться до правого верхнего угла — самой
// неудобной точки экрана для большого пальца. Здесь один тап, и всё под пальцем.
//
// «Жидкое стекло» — полупрозрачная подложка с размытием того, что под ней. Это одно из
// немногих мест, где тень уместна: панель действительно висит над содержимым, а не
// лежит в потоке.
//
// В панели пять разделов из семи — те, куда заходят каждый день. «Аккаунты» и
// «Настройки» открываются из шапки: их трогают при настройке, а не в работе, и место
// под пальцем они занимали бы зря.
//
// Только для телефона: на компьютере разделы стоят строкой в шапке, и дублировать одну
// и ту же навигацию дважды незачем.

function DashboardIcon() {
  return (
    <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.8" strokeLinecap="round" strokeLinejoin="round" className="h-6 w-6" aria-hidden>
      <rect x="3.5" y="3.5" width="7" height="7" rx="1.6" />
      <rect x="13.5" y="3.5" width="7" height="7" rx="1.6" />
      <rect x="3.5" y="13.5" width="7" height="7" rx="1.6" />
      <rect x="13.5" y="13.5" width="7" height="7" rx="1.6" />
    </svg>
  );
}

function ThemesIcon() {
  return (
    <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.8" strokeLinecap="round" strokeLinejoin="round" className="h-6 w-6" aria-hidden>
      <path d="M4 7.5h16M4 12h16M4 16.5h10" />
      <circle cx="19" cy="16.5" r="2" />
    </svg>
  );
}

function ReviewIcon() {
  return (
    <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.8" strokeLinecap="round" strokeLinejoin="round" className="h-6 w-6" aria-hidden>
      <rect x="4" y="3.5" width="16" height="17" rx="2.4" />
      <path d="M8.5 12.2l2.4 2.4 4.6-5" />
    </svg>
  );
}

function QueueIcon() {
  return (
    <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.8" strokeLinecap="round" strokeLinejoin="round" className="h-6 w-6" aria-hidden>
      <circle cx="12" cy="12" r="8.5" />
      <path d="M12 7.5V12l3 2" />
    </svg>
  );
}

function PublicationsIcon() {
  return (
    <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.8" strokeLinecap="round" strokeLinejoin="round" className="h-6 w-6" aria-hidden>
      <path d="M4.5 12.5l15-7-4 15.5-3.5-6z" />
      <path d="M12 15l7.5-9.5" />
    </svg>
  );
}

const TABS = [
  { to: "/", label: "Дашборд", icon: <DashboardIcon />, end: true },
  { to: "/themes", label: "Темы", icon: <ThemesIcon />, end: false },
  { to: "/review", label: "Проверка", icon: <ReviewIcon />, end: false },
  { to: "/queue", label: "Очередь", icon: <QueueIcon />, end: false },
  { to: "/publications", label: "Публикации", icon: <PublicationsIcon />, end: false },
];

export function MobileTabBar() {
  const location = useLocation();

  /** Нажатие на раздел, в котором уже находишься, возвращает страницу наверх. Так
   *  работают нижние панели в iOS и в Telegram, и это единственный быстрый способ
   *  вернуться к началу длинного экрана — «Проверка» и «Публикации» на телефоне
   *  прокручиваются на несколько экранов. Переход на другой раздел не трогаем: там
   *  прокрутка и так начинается сверху. */
  const backToTop = (isActive: boolean) => (event: React.MouseEvent) => {
    if (!isActive) return;
    event.preventDefault();
    window.scrollTo({ top: 0, behavior: "smooth" });
  };

  // NavLink сообщает «активен» только внутри className — обработчику нажатия это знание
  // нужно тоже, поэтому считаем так же, как он: точное совпадение для дашборда, начало
  // пути для остальных.
  const isActiveTab = (to: string, end: boolean) =>
    end ? location.pathname === to : location.pathname.startsWith(to);

  return (
    // Отступ снизу считаем по геометрии полоски жеста на iPhone. Безопасная зона там —
    // 34 точки: сама полоска высотой 5 точек стоит в 8 точках от края. Вычитаем эти 13
    // точек, и панель садится ровно в тех же 8 точках над полоской, в которых полоска
    // стоит над краем. Запас 8 точек — для Android и узких окон на компьютере, где
    // безопасной зоны нет вовсе и панель иначе прилипала бы к самому краю.
    <div className="fixed inset-x-0 bottom-0 z-40 flex items-stretch px-5 pb-[max(0.5rem,calc(env(safe-area-inset-bottom,0px)-0.8125rem))] md:hidden">
      <nav aria-label="Разделы" className="glass flex flex-1 items-center gap-1 rounded-full p-[5px]">
        {TABS.map((tab) => {
          const active = isActiveTab(tab.to, tab.end);
          return (
            <NavLink
              key={tab.to}
              to={tab.to}
              end={tab.end}
              onClick={backToTop(active)}
              title={tab.label}
              aria-label={tab.label}
              className={({ isActive }) =>
                [
                  "flex min-h-11 flex-1 items-center justify-center rounded-full transition-colors",
                  isActive ? "bg-accent-soft text-accent" : "text-ink-muted",
                ].join(" ")
              }
            >
              {tab.icon}
            </NavLink>
          );
        })}
      </nav>
    </div>
  );
}
