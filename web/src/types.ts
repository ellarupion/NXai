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

export interface PendingReviewPost {
  candidate_id: string;
  theme_id: string;
  source_channel_title: string;
  raw_text: string;
  rewritten_text: string;
  score: number | null;
  created_at: string;
  has_media: boolean;
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
