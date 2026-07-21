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
