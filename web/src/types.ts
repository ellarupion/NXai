// Ручной аналог interfaces/api/routers/*.py Pydantic-схем — кодогенератора пока
// нет (тот же компромисс, что в NX), держите в ручной синхронизации с бэкендом.

export interface Theme {
  id: string;
  name: string;
  default_style_prompt: string;
  is_active: boolean;
  digest_enabled: boolean;
  digest_hour: number;
  premoderation: boolean;
  rubrics: string[];
  manual_mode: boolean;
}

export type ThemeHealthStatus = "ok" | "warn" | "crit";

export interface ThemeHealthStage {
  key: string;
  label: string;
  status: ThemeHealthStatus;
  value: string;
  hint: string | null;
}

export interface ThemeHealth {
  stages: ThemeHealthStage[];
}

export interface SourceChannel {
  id: string;
  tg_username: string | null;
  tg_chat_id: number | null;
  title: string;
  theme_id: string | null;
  ingest_session_id: string | null;
  is_active: boolean;
  trust_score: number;
  last_scanned_at: string | null;
  candidate_count: number;
}

export interface CrosspostPlatform {
  enabled?: boolean;
  access_token?: string;
  owner_id?: string;
  chat_id?: string;
}

export interface CrosspostConfig {
  vk?: CrosspostPlatform;
  max?: CrosspostPlatform;
}

export interface TargetChannel {
  id: string;
  theme_id: string;
  tg_chat_id: number;
  title: string;
  signature: string;
  is_active: boolean;
  metrics_session_id: string | null;
  crosspost: CrosspostConfig;
}

export interface PublicationEngagement {
  publication_id: string;
  published_at: string;
  channel_title: string;
  preview: string;
  views: number | null;
  forwards: number | null;
}

export interface Engagement {
  metrics_configured: boolean;
  publications: PublicationEngagement[];
}

export interface AdminAccount {
  id: string;
  username: string;
  is_superadmin: boolean;
  created_at: string;
}

export interface Me {
  username: string;
  is_superadmin: boolean;
}

export interface Cadence {
  posts_per_day_target: number;
  min_interval_minutes: number;
  max_interval_minutes: number;
  jitter_minutes: number;
  quiet_hours_start: number;
  quiet_hours_end: number;
}

export type BotRole = "theme" | "admin";

export interface PersonaConfig {
  tone?: "brash" | "expert" | "friendly" | "news" | "custom";
  tone_custom?: string;
  length?: "shorter" | "same" | "longer";
  emoji?: "none" | "few" | "many";
  address?: "ty" | "vy" | "neutral";
  boldness?: number;
  stop_words?: string[];
  hashtags?: string;
  examples_good?: string[];
  examples_bad?: string[];
}

export interface ChannelBot {
  id: string;
  theme_id: string | null;
  role: BotRole;
  persona_prompt: string;
  persona_config: PersonaConfig;
  cadence: Cadence;
  is_active: boolean;
  token_set: boolean;
  editor_chat_id: number | null;
  use_media: boolean;
  autopublish_enabled: boolean;
  notify_chat_set: boolean;
}

// Источник ключа: задан из панели (DB-оверрайд), из .env, или нигде не задан —
// см. interfaces/api/routers/settings.py:_status.
export type SecretSource = "panel" | "env" | "unset";

export interface SecretStatus {
  source: SecretSource;
}

export interface SettingsStatus {
  anthropic_api_key: SecretStatus;
  voyage_api_key: SecretStatus;
  telegram_api_id: SecretStatus;
  telegram_api_hash: SecretStatus;
}

export interface GeneralSettings {
  timezone: string;
  pool_cooldown_days: number;
}

export interface TelethonSession {
  id: string;
  label: string;
  is_active: boolean;
}

export interface TelethonLoginStartResult {
  attempt_id: string;
}

// "password_required" — на аккаунте включена 2FA, нужен ещё один запрос
// (submit password) с тем же attempt_id прежде чем telethon_session появится.
export interface TelethonLoginStepResult {
  status: "done" | "password_required";
  telethon_session: TelethonSession | null;
}

export interface GeneratedPost {
  candidate_id: string;
  source_channel_title: string;
  rewritten_text: string;
  score: number | null;
}

/* Ответ «Посты на сегодня». ordered — сколько заказано (дневное расписание
   темы), delivered — сколько удалось приготовить: их может быть меньше, если
   в источниках не набралось подходящих постов. */
export interface DailyBatch {
  ordered: number;
  delivered: number;
  posts: GeneratedPost[];
}

export interface PendingReviewPost {
  candidate_id: string;
  // null — тему удалили, а кандидат остался (см. PendingReviewOut на бэке)
  theme_id: string | null;
  source_channel_title: string;
  raw_text: string;
  rewritten_text: string;
  score: number | null;
  created_at: string;
  has_media: boolean;
  // Подтема. null — рубрики у темы не заданы либо классификатор промолчал.
  rubric: string | null;
}

export type PoolPostStatus = "ready" | "used";
export type PoolPostSource = "manual" | "generated" | "recycled";

export interface PoolPost {
  id: string;
  theme_id: string;
  text: string;
  source: PoolPostSource;
  status: PoolPostStatus;
  times_used: number;
}

export interface TopSource {
  title: string;
  candidate_count: number;
}

export interface WorkerStatus {
  worker_name: string;
  label: string;
  is_alive: boolean;
  last_beat_at: string | null;
  detail: string | null;
}

export interface DashboardStats {
  themes_total: number;
  themes_active: number;
  source_channels_total: number;
  source_channels_unassigned: number;
  candidates_by_status: Record<string, number>;
  pending_review_count: number;
  publications_total: number;
  publications_today: number;
  pool_posts_total: number;
  pool_posts_ready: number;
  top_sources: TopSource[];
  workers: WorkerStatus[];
}

export interface OnboardingStep {
  key: string;
  label: string;
  done: boolean;
  href: string;
}

export interface Onboarding {
  all_done: boolean;
  steps: OnboardingStep[];
}

export interface TrendDay {
  date: string;
  publications: number;
  candidates: number;
}

export interface Trends {
  days: TrendDay[];
}

export type AlertSeverity = "warning" | "info";

export interface Alert {
  severity: AlertSeverity;
  category: string;
  message: string;
  theme_id: string | null;
  source_channel_id: string | null;
}

/* Лента вышедшего (страница «Публикации»). Собирает публикацию обратно в
   цепочку: что вышло -> из какого кандидата -> из какого источника -> какой
   персоной переписано -> как зашло. */
export interface PublicationItem {
  id: string;
  published_at: string;
  theme_id: string;
  theme_name: string;
  channel_title: string;
  channel_tg_chat_id: number;
  tg_message_id: number;
  kind: "candidate" | "pool";
  is_ad_cover: boolean;
  text: string;
  source_channel_id: string | null;
  source_channel_title: string | null;
  source_channel_username: string | null;
  source_channel_active: boolean | null;
  raw_text: string | null;
  score: number | null;
  persona_prompt_used: string | null;
  rubric: string | null;
  views: number | null;
  forwards: number | null;
}

export interface PublicationsPage {
  items: PublicationItem[];
  has_more: boolean;
}

/* Счётчики для вкладок «Проверки»: сколько постов ждёт одобрения в каждой
   теме. theme_id=null — посты источников, у которых тему удалили. */
export interface ThemePendingCount {
  theme_id: string | null;
  count: number;
}

/* Поиск источников под тему: LLM подбирает запросы, Telegram отдаёт
   кандидатов (core/services/source_discovery.py). */
export interface ChannelCandidate {
  username: string;
  title: string;
  participants: number | null;
  posts_per_day: number;
  days_since_last_post: number;
  found_via: string;
  already_added: boolean;
}

/* Расходы на ИИ. cost в долларах: счёт от провайдера приходит в них, а придуманный
   курс рубля врал бы. */
export interface LlmUsageKind {
  kind: string;
  title: string;
  cost_usd: number;
  calls: number;
  input_tokens: number;
  output_tokens: number;
  cache_read_tokens: number;
}

export interface LlmUsageBudget {
  limit_usd: number;
  spent_today_usd: number;
  percent: number;
  enabled: boolean;
  exceeded: boolean;
  near_limit: boolean;
  warn_percent: number;
}

export interface LlmUsage {
  days: number;
  total_usd: number;
  budget: LlmUsageBudget;
  by_kind: LlmUsageKind[];
  by_day: { day: string; cost_usd: number }[];
  by_model: [string, number][];
  by_theme: { theme_id: string | null; theme_name: string; cost_usd: number }[];
}

/* Пороги и времена поведения. Схема на бэке — core/services/automation.py. */
export interface AutomationSettings {
  daily_budget_usd: number;
  budget_warn_percent: number;
  selection_score_threshold: number;
  min_samples_for_median: number;
  selection_pool_factor: number;
  min_trust_score: number;
  max_trust_score: number;
  trust_duplicate_penalty: number;
  trust_rejected_penalty: number;
  trust_success_bonus: number;
  dedup_similarity_threshold: number;
  rewrite_batch_limit: number;
  rewrite_stock_days: number;
  min_rewrite_stock: number;
  max_daily_batch: number;
  min_rewritable_length: number;
  rubric_recent_window: number;
  ad_cover_delay_minutes: number;
}
