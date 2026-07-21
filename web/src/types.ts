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
  is_active: boolean;
  trust_score: number;
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
}
