import { AmcatIndex, AmcatIndexId, AmcatUserRole, RecentIndices } from "@/interfaces";
import { amcatIndexSchema, amcatIndexUpdateSchema } from "@/schemas";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";

import { hasMinAmcatRole } from "@/lib/utils";
import { AmcatSessionUser } from "@/components/Contexts/AuthProvider";
import { z } from "zod";
import { useAmcatConfig } from "./config";
import useLocalStorage from "@/lib/useLocalStorage";

export function useIndex(user?: AmcatSessionUser, indexId?: AmcatIndexId) {
  const [recentIndices, setRecentIndices] = useLocalStorage<RecentIndices>("recentIndices", {});

  function addToRecentIndices(index: AmcatIndex) {
    setRecentIndices((prev) => {
      const key = user?.email || "guest";
      const currentList = prev[key] || [];
      const newList = [index, ...currentList.filter((ix) => ix.id !== index.id)];
      return { ...prev, [key]: newList.slice(0, 50) };
    });
  }

  return useQuery({
    queryKey: ["index", user, indexId],
    queryFn: async () => {
      const ix = await getIndex(user, indexId);
      if (ix) addToRecentIndices(ix);
      return ix;
    },
    enabled: !!user && !!indexId,
  });
}

export function useMyIndexrole(user?: AmcatSessionUser, indexId?: AmcatIndexId) {
  const { data: serverConfig } = useAmcatConfig();
  const { data: index } = useIndex(user, indexId);
  if (serverConfig?.authorization === "no_auth") return "ADMIN";
  return index?.user_role;
}

export function useHasIndexRole(user: AmcatSessionUser | undefined, indexId: AmcatIndexId, role: AmcatUserRole) {
  const index_role = useMyIndexrole(user, indexId);
  if (!index_role) return undefined;
  return hasMinAmcatRole(index_role, role);
}

async function getIndex(user?: AmcatSessionUser, indexId?: string) {
  if (!user || !indexId) return undefined;
  const res = await user.api.get(`/index/${indexId}`);
  return amcatIndexSchema.parse(res.data);
}

export function useCreateIndex(user: AmcatSessionUser | undefined) {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: (value: z.input<typeof amcatIndexSchema>) => {
      if (!user) throw new Error("Not logged in");
      return createIndex(user, value);
    },
    onSuccess: (_, variables) => {
      queryClient.invalidateQueries({ queryKey: ["indices", user] });
      return variables.id;
    },
  });
}

async function createIndex(user: AmcatSessionUser | undefined, value: z.input<typeof amcatIndexSchema>) {
  if (!user) throw new Error("Not logged in");
  if (value.guest_role === "NONE") value.guest_role = undefined;
  return await user.api.post(`/index`, value);
}

export function useMutateIndex(user: AmcatSessionUser | undefined) {
  const queryClient = useQueryClient();

  return useMutation({
    mutationFn: (value: z.input<typeof amcatIndexUpdateSchema>) => mutateIndex(user, value),
    onSuccess: (_, value) => {
      queryClient.invalidateQueries({ queryKey: ["index", user, value.id] });
      queryClient.invalidateQueries({ queryKey: ["indices", user] });
      return value.id;
    },
  });
}

async function mutateIndex(user: AmcatSessionUser | undefined, value: z.input<typeof amcatIndexUpdateSchema>) {
  if (!user) throw new Error("Not logged in");
  return await user.api.put(`index/${value.id}`, value);
}

export function useArchiveIndex(user: AmcatSessionUser | undefined) {
  const queryClient = useQueryClient();

  return useMutation({
    mutationFn: async (params: { indexId: string; archived: boolean }) => {
      if (!user) throw new Error("Not logged in");
      return await user.api.post(`index/${params.indexId}/archive`, { archived: params.archived });
    },
    onSuccess: (_, value) => {
      queryClient.invalidateQueries({ queryKey: ["index", user, value.indexId] });
      queryClient.invalidateQueries({ queryKey: ["indices", user] });
    },
  });
}

export function useDeleteIndex(user: AmcatSessionUser | undefined) {
  const queryClient = useQueryClient();

  return useMutation({
    mutationFn: (indexId: string) => deleteIndex(user, indexId),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["indices", user] });
    },
  });
}

async function deleteIndex(user: AmcatSessionUser | undefined, indexId: string) {
  if (!user) throw new Error("Not logged in");
  return await user.api.delete(`index/${indexId}`);
}
