import { AmcatUserRole } from "@/interfaces";
import { amcatUserDetailsSchema } from "@/schemas";

import { AmcatSessionUser } from "@/components/Contexts/AuthProvider";
import { hasMinAmcatRole } from "@/lib/utils";
import { useQuery } from "@tanstack/react-query";
import { useAmcatConfig } from "./config";

export function useCurrentUserDetails(user?: AmcatSessionUser) {
  return useQuery({
    queryKey: ["currentuserdetails", user],
    queryFn: async () => getCurrentUserDetails(user),
    enabled: user != null,
    retry: () => {
      // Don't retry. It's either forbidden or user not known
      return false;
    },
  });
}

export function useMyGlobalRole(user?: AmcatSessionUser | undefined) {
  const { data: userInfo } = useCurrentUserDetails(user);
  return userInfo?.role;
}

export function useHasGlobalRole(user: AmcatSessionUser | undefined, role: AmcatUserRole) {
  const { data: serverConfig } = useAmcatConfig();
  const actual_role = useMyGlobalRole(user);
  if (!user) return undefined;
  if (serverConfig?.authorization === "no_auth") return true;
  if (actual_role == null) return undefined;
  return hasMinAmcatRole(actual_role, role);
}

async function getCurrentUserDetails(user: AmcatSessionUser | undefined) {
  if (!user?.email) return null;
  const res = await user.api.get(`/users/me`);
  const details = amcatUserDetailsSchema.parse(res.data);
  return details;
}
