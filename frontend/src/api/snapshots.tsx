import { AmcatSessionUser } from "@/components/Contexts/AuthProvider";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { z } from "zod";

const snapshotRepositorySchema = z.object({
  name: z.string(),
  type: z.string(),
  settings: z.record(z.unknown()),
});

const snapshotInfoSchema = z.object({
  snapshot: z.string(),
  repository: z.string(),
  uuid: z.string(),
  state: z.string(),
  indices: z.array(z.string()),
  start_time: z.string(),
  end_time: z.string().nullable(),
  size_in_bytes: z.number().nullable().optional(),
});

export type SnapshotRepository = z.infer<typeof snapshotRepositorySchema>;
export type SnapshotInfo = z.infer<typeof snapshotInfoSchema>;

export function useSnapshotRepositories(user?: AmcatSessionUser) {
  return useQuery({
    queryKey: ["snapshot_repositories"],
    queryFn: async () => {
      if (!user) return [];
      const res = await user.api.get("snapshots/repositories");
      return z.array(snapshotRepositorySchema).parse(res.data);
    },
    enabled: !!user,
  });
}

interface MutateRepositoryParams {
  action: "create" | "delete";
  name: string;
  type?: string;
  settings?: Record<string, unknown>;
}

export function useMutateRepositories(user?: AmcatSessionUser) {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: async (params: MutateRepositoryParams) => {
      if (!user) throw new Error("Not logged in");
      if (params.action === "create") {
        await user.api.post("snapshots/repositories", {
          name: params.name,
          type: params.type,
          settings: params.settings,
        });
      } else {
        await user.api.delete(`snapshots/repositories/${params.name}`);
      }
    },
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["snapshot_repositories"] });
    },
  });
}

export function useSnapshots(user?: AmcatSessionUser, repository?: string) {
  return useQuery({
    queryKey: ["snapshots", repository],
    queryFn: async () => {
      if (!user) return [];
      const params = repository ? { repository } : {};
      const res = await user.api.get("snapshots", { params });
      return z.array(snapshotInfoSchema).parse(res.data);
    },
    enabled: !!user,
    refetchInterval: (query) => {
      const data = query.state.data as SnapshotInfo[] | undefined;
      return data?.some((s) => s.state === "IN_PROGRESS") ? 3000 : false;
    },
  });
}

export function useSnapshotPathRepo(user?: AmcatSessionUser) {
  return useQuery({
    queryKey: ["snapshot_path_repo"],
    queryFn: async () => {
      if (!user) return [];
      const res = await user.api.get("snapshots/path-repo");
      return z.array(z.string()).parse(res.data);
    },
    enabled: !!user,
  });
}

export function useCreateSnapshot(user?: AmcatSessionUser) {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: async (params: { repository: string; snapshot: string }) => {
      if (!user) throw new Error("Not logged in");
      const res = await user.api.post("snapshots", params);
      return snapshotInfoSchema.parse(res.data);
    },
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["snapshots"] });
    },
  });
}
