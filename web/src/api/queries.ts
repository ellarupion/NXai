import { api } from "./client";
import type {
  Alert,
  ChannelBot,
  DashboardStats,
  Me,
  PendingReviewPost,
  PoolPost,
  SettingsStatus,
  SourceChannel,
  TargetChannel,
  TelethonSession,
  Theme,
} from "../types";

export const meQuery = () => ({
  queryKey: ["me"],
  queryFn: () => api.get<Me>("/auth/me"),
});

export const themesQuery = () => ({
  queryKey: ["themes"],
  queryFn: () => api.get<Theme[]>("/themes"),
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
