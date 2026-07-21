import { api } from "./client";
import type { ChannelBot, Me, SettingsStatus, SourceChannel, TelethonSession, Theme } from "../types";

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
