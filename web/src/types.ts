// Ручной аналог interfaces/api/routers/*.py Pydantic-схем — кодогенератора пока
// нет (тот же компромисс, что в NX), держите в ручной синхронизации с бэкендом.

export interface Theme {
  id: string;
  name: string;
  default_style_prompt: string;
  is_active: boolean;
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
}

export interface TargetChannel {
  id: string;
  theme_id: string;
  tg_chat_id: number;
  title: string;
  signature: string;
  is_active: boolean;
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

export interface ChannelBot {
  id: string;
  theme_id: string | null;
  role: BotRole;
  persona_prompt: string;
  cadence: Cadence;
  is_active: boolean;
  token_set: boolean;
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
}
