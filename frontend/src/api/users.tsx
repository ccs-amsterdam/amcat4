import { amcatUserDetailsSchema, amcatUserRoleSchema } from "@/schemas";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { AmcatSessionUser } from "@/components/Contexts/AuthProvider";

import { toast } from "sonner";
import { z } from "zod";

export function useUsers(user?: AmcatSessionUser) {
  return useQuery({
    queryKey: ["users", user],
    queryFn: () => getUsers(user),
    enabled: !!user,
  });
}

async function getUsers(user?: AmcatSessionUser) {
  if (!user) return undefined;
  const res = await user.api.get(`users`);
  const users = z.array(amcatUserDetailsSchema).parse(res.data);
  return users;
}

export function useMutateUser(user?: AmcatSessionUser) {
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
      return mutateUser(user, email, role, action);
    },
    onSuccess: (data, variables) => {
      queryClient.invalidateQueries({ queryKey: ["users", user] });
      queryClient.invalidateQueries({ queryKey: ["currentuserdetails", user] });

      if (variables.role === "NONE") {
        toast.success(`Deleted user ${variables.email}`);
      } else {
        toast.success(`User ${variables.email} has role ${variables.role}`);
      }
    },
  });
}

async function mutateUser(
  user: AmcatSessionUser,
  email: string | undefined,
  newRole: string,
  action: "create" | "delete" | "update",
) {
  const role = amcatUserRoleSchema.parse(newRole);
  if (action === "delete") {
    return await user.api.delete(`users/${email}`);
  } else if (action === "create") {
    return await user.api.post(`users`, { email, role });
  } else if (action === "update") {
    return await user.api.put(`users/${email}`, { role });
  }
}
