import { AmcatProject, AmcatProjectId, AmcatUserRole, RecentProjects } from "@/interfaces";
import { amcatProjectSchema, amcatProjectUpdateSchema } from "@/schemas";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";

import { hasMinAmcatRole } from "@/lib/utils";
import { AmcatSessionUser } from "@/components/Contexts/AuthProvider";
import { z } from "zod";
import { useAmcatConfig } from "./config";
import useLocalStorage from "@/lib/useLocalStorage";

export function useProject(user?: AmcatSessionUser, projectId?: AmcatProjectId) {
  const [recentProjects, setRecentProjects] = useLocalStorage<RecentProjects>("recentProjects", {});

  function addToRecentProjects(project: AmcatProject) {
    setRecentProjects((prev) => {
      const key = user?.email || "guest";
      const currentList = prev[key] || [];
      const newList = [project, ...currentList.filter((ix) => ix.id !== project.id)];
      return { ...prev, [key]: newList.slice(0, 50) };
    });
  }

  return useQuery({
    queryKey: ["project", user, projectId],
    queryFn: async () => {
      const ix = await getProject(user, projectId);
      if (ix) addToRecentProjects(ix);
      return ix;
    },
    enabled: !!user && !!projectId,
  });
}

export function useMyProjectRole(
  user?: AmcatSessionUser,
  projectId?: AmcatProjectId,
): { role: AmcatUserRole | undefined; isLoading: boolean } {
  const { data: serverConfig } = useAmcatConfig();
  const { data: project, isLoading } = useProject(user, projectId);
  if (serverConfig?.authorization === "no_auth") return { role: "ADMIN", isLoading: false };
  return { role: project?.user_role, isLoading };
}

export function useHasProjectRole(user: AmcatSessionUser | undefined, projectId: AmcatProjectId, role: AmcatUserRole) {
  const { role: project_role } = useMyProjectRole(user, projectId);
  if (!project_role) return undefined;
  return hasMinAmcatRole(project_role, role);
}

async function getProject(user?: AmcatSessionUser, projectId?: string) {
  if (!user || !projectId) return undefined;
  const res = await user.api.get(`/index/${projectId}`);
  return amcatProjectSchema.parse(res.data);
}

export function useCreateProject(user: AmcatSessionUser | undefined) {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: (value: z.input<typeof amcatProjectSchema>) => {
      if (!user) throw new Error("Not logged in");
      return createProject(user, value);
    },
    onSuccess: (_, variables) => {
      queryClient.invalidateQueries({ queryKey: ["projects", user] });
      return variables.id;
    },
  });
}

async function createProject(user: AmcatSessionUser | undefined, value: z.input<typeof amcatProjectSchema>) {
  if (!user) throw new Error("Not logged in");
  if (value.guest_role === "NONE") value.guest_role = undefined;
  return await user.api.post(`/index`, value);
}

export function useMutateProject(user: AmcatSessionUser | undefined) {
  const queryClient = useQueryClient();

  return useMutation({
    mutationFn: (value: z.input<typeof amcatProjectUpdateSchema>) => mutateProject(user, value),
    onSuccess: (_, value) => {
      queryClient.invalidateQueries({ queryKey: ["project", user, value.id] });
      queryClient.invalidateQueries({ queryKey: ["projects", user] });
      return value.id;
    },
  });
}

async function mutateProject(user: AmcatSessionUser | undefined, value: z.input<typeof amcatProjectUpdateSchema>) {
  if (!user) throw new Error("Not logged in");
  return await user.api.put(`index/${value.id}`, value);
}

export function useArchiveProject(user: AmcatSessionUser | undefined) {
  const queryClient = useQueryClient();

  return useMutation({
    mutationFn: async (params: { projectId: string; archived: boolean }) => {
      if (!user) throw new Error("Not logged in");
      return await user.api.post(`index/${params.projectId}/archive`, { archived: params.archived });
    },
    onSuccess: (_, value) => {
      queryClient.invalidateQueries({ queryKey: ["project", user, value.projectId] });
      queryClient.invalidateQueries({ queryKey: ["projects", user] });
    },
  });
}

export function useUnregisteredIndices(user: AmcatSessionUser | undefined) {
  return useQuery({
    queryKey: ["unregistered_indices", user],
    queryFn: async () => {
      const res = await user!.api.get("/index/unregistered");
      return res.data as string[];
    },
    enabled: !!user,
  });
}

export function useRegisterProject(user: AmcatSessionUser | undefined) {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: (value: z.input<typeof amcatProjectSchema>) => {
      if (!user) throw new Error("Not logged in");
      const { id, ...body } = value;
      return user.api.post(`/index/${id}/register`, body);
    },
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["projects", user] });
    },
  });
}

export function useDeleteProject(user: AmcatSessionUser | undefined) {
  const queryClient = useQueryClient();

  return useMutation({
    mutationFn: (projectId: string) => deleteProject(user, projectId),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["projects", user] });
    },
  });
}

async function deleteProject(user: AmcatSessionUser | undefined, projectId: string) {
  if (!user) throw new Error("Not logged in");
  return await user.api.delete(`index/${projectId}`);
}
