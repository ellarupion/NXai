import { api } from "./client";
import type {
  ChannelBot,
  Me,
  PendingReviewPost,
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
