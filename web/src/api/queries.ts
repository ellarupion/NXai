import { api } from "./client";
import type { Me, SourceChannel, Theme } from "../types";

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
