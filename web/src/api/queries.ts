import { api } from "./client";
import type {
  Alert,
  AuditLogsPage,
  AutomationSettings,
  ChannelBot,
  DashboardStats,
  Engagement,
  LlmUsage,
  GeneralSettings,
  Me,
  Onboarding,
  PendingReviewPost,
  PoolPost,
  PostPassport,
  PublicationsPage,
  QualityRun,
  QualityRunDetail,
  SettingsStatus,
  SourceChannel,
  TargetChannel,
  TelethonSession,
  Theme,
  ThemeHealth,
  ThemePendingCount,
  Trends,
} from "../types";

export const meQuery = () => ({
  queryKey: ["me"],
  queryFn: () => api.get<Me>("/auth/me"),
});

export const themesQuery = () => ({
  queryKey: ["themes"],
  queryFn: () => api.get<Theme[]>("/themes"),
});

export const trendsQuery = (themeId?: string) => ({
  queryKey: ["trends", themeId ?? "all"],
  queryFn: () => api.get<Trends>(`/dashboard/trends${themeId ? `?theme_id=${themeId}` : ""}`),
});

export const themeQuery = (themeId: string) => ({
  queryKey: ["themes", themeId],
  queryFn: () => api.get<Theme>(`/themes/${themeId}`),
});

export const themeHealthQuery = (themeId: string) => ({
  queryKey: ["theme-health", themeId],
  queryFn: () => api.get<ThemeHealth>(`/themes/${themeId}/health`),
});

export const sourceChannelsQuery = (unassignedOnly: boolean) => ({
  queryKey: ["source-channels", { unassignedOnly }],
  queryFn: () =>
    api.get<SourceChannel[]>(`/source-channels${unassignedOnly ? "?unassigned_only=true" : ""}`),
});

export const channelBotsQuery = () => ({
  queryKey: ["channel-bots"],
  queryFn: () => api.get<ChannelBot[]>("/channel-bots"),
});

export const settingsQuery = () => ({
  queryKey: ["settings"],
  queryFn: () => api.get<SettingsStatus>("/settings"),
});

export const generalSettingsQuery = () => ({
  queryKey: ["settings-general"],
  queryFn: () => api.get<GeneralSettings>("/settings/general"),
});

export const telethonSessionsQuery = () => ({
  queryKey: ["telethon-sessions"],
  queryFn: () => api.get<TelethonSession[]>("/telethon-sessions"),
});

export const targetChannelsQuery = () => ({
  queryKey: ["target-channels"],
  queryFn: () => api.get<TargetChannel[]>("/target-channels"),
});

export const pendingReviewQuery = (themeId?: string) => ({
  queryKey: ["pending-review", { themeId }],
  queryFn: () =>
    api.get<PendingReviewPost[]>(`/candidates/pending-review${themeId ? `?theme_id=${themeId}` : ""}`),
});

export const poolPostsQuery = (themeId?: string) => ({
  queryKey: ["pool-posts", { themeId }],
  queryFn: () => api.get<PoolPost[]>(`/pool-posts${themeId ? `?theme_id=${themeId}` : ""}`),
});

export const dashboardStatsQuery = () => ({
  queryKey: ["dashboard-stats"],
  queryFn: () => api.get<DashboardStats>("/dashboard/stats"),
});

export const alertsQuery = () => ({
  queryKey: ["alerts"],
  queryFn: () => api.get<Alert[]>("/alerts"),
});

export const onboardingQuery = () => ({
  queryKey: ["onboarding"],
  queryFn: () => api.get<Onboarding>("/dashboard/onboarding"),
});

export const engagementQuery = () => ({
  queryKey: ["engagement"],
  queryFn: () => api.get<Engagement>("/dashboard/engagement"),
});

export const publicationsQuery = (params: {
  themeId?: string;
  sourceChannelId?: string;
  days?: number;
  limit?: number;
  offset?: number;
}) => {
  const q = new URLSearchParams();
  if (params.themeId) q.set("theme_id", params.themeId);
  if (params.sourceChannelId) q.set("source_channel_id", params.sourceChannelId);
  if (params.days) q.set("days", String(params.days));
  q.set("limit", String(params.limit ?? 20));
  q.set("offset", String(params.offset ?? 0));
  return {
    queryKey: ["publications", params],
    queryFn: () => api.get<PublicationsPage>(`/publications?${q.toString()}`),
  };
};

export const pendingReviewCountsQuery = () => ({
  queryKey: ["pending-review-counts"],
  queryFn: () => api.get<ThemePendingCount[]>("/candidates/pending-review/counts"),
});

export const llmUsageQuery = (days: number) => ({
  queryKey: ["llm-usage", days],
  queryFn: () => api.get<LlmUsage>(`/llm-usage?days=${days}`),
});

export const automationQuery = () => ({
  queryKey: ["automation"],
  queryFn: () => api.get<AutomationSettings>("/settings/automation"),
});

export const auditLogsQuery = (params: {
  action?: string;
  themeId?: string;
  actor?: string;
  limit?: number;
}) => {
  const q = new URLSearchParams();
  if (params.action) q.set("action", params.action);
  if (params.themeId) q.set("theme_id", params.themeId);
  if (params.actor) q.set("actor", params.actor);
  q.set("limit", String(params.limit ?? 50));
  return {
    queryKey: ["audit-logs", params],
    queryFn: () => api.get<AuditLogsPage>(`/audit-logs?${q.toString()}`),
  };
};

export const qualityRunsQuery = (themeId?: string) => ({
  queryKey: ["quality-runs", themeId ?? "all"],
  queryFn: () => api.get<QualityRun[]>(`/quality-runs${themeId ? `?theme_id=${themeId}` : ""}`),
  // Замер считает планировщик минутами — без опроса страница показывала бы
  // «заказан» до тех пор, пока её не перезагрузят руками.
  refetchInterval: 10_000,
});

export const qualityRunQuery = (runId: string) => ({
  queryKey: ["quality-run", runId],
  queryFn: () => api.get<QualityRunDetail>(`/quality-runs/${runId}`),
  refetchInterval: 10_000,
});

export const postPassportQuery = (candidateId: string) => ({
  queryKey: ["post-passport", candidateId],
  queryFn: () => api.get<PostPassport>(`/candidates/${candidateId}/passport`),
});
