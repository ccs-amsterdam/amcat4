import { AmcatProjectId } from "@/interfaces";
import { amcatUserDetailsSchema, amcatUserRoleSchema } from "@/schemas";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { AmcatSessionUser } from "@/components/Contexts/AuthProvider";

import { toast } from "sonner";
import { z } from "zod";

export function useProjectUsers(user?: AmcatSessionUser, projectId?: AmcatProjectId) {
  return useQuery({
    queryKey: ["projectusers", user, projectId],
    queryFn: () => getProjectUsers(user, projectId),
    enabled: !!user && !!projectId,
  });
}

async function getProjectUsers(user?: AmcatSessionUser, projectId?: AmcatProjectId) {
  if (!user || !projectId) return undefined;
  const res = await user.api.get(`index/${projectId}/users`);
  const users = z.array(amcatUserDetailsSchema).parse(res.data);
  return users;
}

export function useMutateProjectUser(user?: AmcatSessionUser, projectId?: AmcatProjectId | undefined) {
  const queryClient = useQueryClient();

  return useMutation({
    mutationFn: ({
      email,
      role,
      action,
    }: {
      email: string | undefined;
      role: string;
      action: "create" | "delete" | "update";
    }) => {
      if (!user) throw new Error("Not logged in");
      return mutateProjectUser(user, projectId || "", email, role, action);
    },
    onSuccess: (data, variables) => {
      queryClient.invalidateQueries({ queryKey: ["projects", user] });
      queryClient.invalidateQueries({ queryKey: ["project", user, projectId] });
      queryClient.invalidateQueries({ queryKey: ["projectusers", user, projectId] });
      if (variables.action === "delete") {
        toast.success(`Removed ${variables.email} from project users`);
      } else {
        toast.success(`Changed ${variables.email} role to ${variables.role}`);
      }
    },
  });
}

async function mutateProjectUser(
  user: AmcatSessionUser,
  projectId: AmcatProjectId,
  email: string | undefined,
  newRole: string,
  action: "create" | "delete" | "update",
) {
  const role = amcatUserRoleSchema.parse(newRole);
  if (action === "delete") {
    await user.api.delete(`/index/${projectId}/users/${email}`);
  } else if (action === "update") {
    await user.api.put(`/index/${projectId}/users/${email}`, { role });
  } else if (action === "create") {
    await user.api.post(`/index/${projectId}/users`, { email, role });
  }
}
