import { AmcatIndexId } from "@/interfaces";
import { amcatUserDetailsSchema, amcatUserRoleSchema } from "@/schemas";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { AmcatSessionUser } from "@/components/Contexts/AuthProvider";

import { toast } from "sonner";
import { z } from "zod";

export function useIndexUsers(user?: AmcatSessionUser, indexId?: AmcatIndexId) {
  return useQuery({
    queryKey: ["indexusers", user, indexId],
    queryFn: () => getIndexUsers(user, indexId),
    enabled: !!user && !!indexId,
  });
}

async function getIndexUsers(user?: AmcatSessionUser, indexId?: AmcatIndexId) {
  if (!user || !indexId) return undefined;
  const res = await user.api.get(`index/${indexId}/users`);
  const users = z.array(amcatUserDetailsSchema).parse(res.data);
  return users;
}

export function useMutateIndexUser(user?: AmcatSessionUser, indexId?: AmcatIndexId | undefined) {
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
      return mutateIndexUser(user, indexId || "", email, role, action);
    },
    onSuccess: (data, variables) => {
      queryClient.invalidateQueries({ queryKey: ["indices", user] });
      queryClient.invalidateQueries({ queryKey: ["index", user, indexId] });
      queryClient.invalidateQueries({ queryKey: ["indexusers", user, indexId] });
      if (variables.action === "delete") {
        toast.success(`Removed ${variables.email} from index users`);
      } else {
        toast.success(`Changed ${variables.email} role to ${variables.role}`);
      }
    },
  });
}

async function mutateIndexUser(
  user: AmcatSessionUser,
  indexId: AmcatIndexId,
  email: string | undefined,
  newRole: string,
  action: "create" | "delete" | "update",
) {
  const role = amcatUserRoleSchema.parse(newRole);
  if (action === "delete") {
    await user.api.delete(`/index/${indexId}/users/${email}`);
  } else if (action === "update") {
    await user.api.put(`/index/${indexId}/users/${email}`, { role });
  } else if (action === "create") {
    await user.api.post(`/index/${indexId}/users`, { email, role });
  }
}
