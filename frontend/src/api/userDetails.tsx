import { AmcatUserRole } from "@/interfaces";
import { amcatUserDetailsSchema, amcatUserRoleSchema } from "@/schemas";

import { hasMinAmcatRole } from "@/lib/utils";
import { useQuery } from "@tanstack/react-query";
import { AmcatSessionUser } from "@/components/Contexts/AuthProvider";
import { useSearchParams } from "next/navigation";
import { useAmcatConfig } from "./config";

export function useCurrentUserDetails(user?: AmcatSessionUser) {
  const params = useSearchParams();

  // This is a development feature to simulate different server roles without having to change them on the server
  const fakeServerRole = params?.get("fake_server_role") || undefined;

  return useQuery({
    queryKey: ["currentuserdetails", user],
    queryFn: async () => getCurrentUserDetails(user, fakeServerRole),
    enabled: user != null,
    retry: (_: any) => {
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

async function getCurrentUserDetails(user: AmcatSessionUser | undefined, fakeServerRole?: string) {
  if (!user?.email) return null;
  const res = await user.api.get(`/users/me`);
  const details = amcatUserDetailsSchema.parse(res.data);
  if (fakeServerRole) details.role = amcatUserRoleSchema.parse(fakeServerRole);
  return details;
}
