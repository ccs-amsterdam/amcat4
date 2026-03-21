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
  const queryClient = useQueryClient();
  return useQuery({
    queryKey: ["snapshots", repository],
    queryFn: async (ctx) => {
      if (!user) return [];
      const params = repository ? { repository } : {};
      const res = await user.api.get("snapshots", { params });
      const snapshots = z.array(snapshotInfoSchema).parse(res.data);
      // When a snapshot transitions from IN_PROGRESS to done, refresh policies
      // so that last_success / last_failure reflects the completed run.
      const prev = ctx.client.getQueryData<SnapshotInfo[]>(["snapshots", repository]);
      if (prev?.some((s) => s.state === "IN_PROGRESS") && snapshots.every((s) => s.state !== "IN_PROGRESS")) {
        queryClient.invalidateQueries({ queryKey: ["slm_policies"] });
      }
      return snapshots;
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

const slmPolicySchema = z.object({
  policy_id: z.string(),
  name: z.string(),
  repository: z.string(),
  schedule: z.string(),
  max_count: z.number(),
  next_execution: z.string().nullable().optional(),
  last_success: z.string().nullable().optional(),
  last_failure: z.string().nullable().optional(),
});

export type SLMPolicy = z.infer<typeof slmPolicySchema>;

export function useSLMPolicies(user?: AmcatSessionUser) {
  return useQuery({
    queryKey: ["slm_policies"],
    queryFn: async () => {
      if (!user) return [];
      const res = await user.api.get("snapshots/policies");
      return z.array(slmPolicySchema).parse(res.data);
    },
    enabled: !!user,
  });
}

interface MutateSLMPolicyParams {
  action: "create" | "delete" | "execute";
  policy_id: string;
  repository?: string;
  schedule?: string;
  max_count?: number;
}

export function useMutateSLMPolicy(user?: AmcatSessionUser) {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: async (params: MutateSLMPolicyParams) => {
      if (!user) throw new Error("Not logged in");
      if (params.action === "create") {
        await user.api.post("snapshots/policies", {
          policy_id: params.policy_id,
          repository: params.repository,
          schedule: params.schedule,
          max_count: params.max_count,
        });
      } else if (params.action === "delete") {
        await user.api.delete(`snapshots/policies/${params.policy_id}`);
      } else {
        await user.api.post(`snapshots/policies/${params.policy_id}/execute`);
      }
    },
    onSuccess: (_, params) => {
      queryClient.invalidateQueries({ queryKey: ["slm_policies"] });
      if (params.action === "execute") {
        queryClient.invalidateQueries({ queryKey: ["snapshots"] });
        // ES may not register the snapshot immediately; re-check after a short delay
        setTimeout(() => queryClient.invalidateQueries({ queryKey: ["snapshots"] }), 1000);
      }
    },
  });
}

export function useDeleteSnapshot(user?: AmcatSessionUser) {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: async (params: { repository: string; snapshot: string }) => {
      if (!user) throw new Error("Not logged in");
      await user.api.delete(`snapshots/${params.repository}/${params.snapshot}`);
    },
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["snapshots"] });
    },
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
