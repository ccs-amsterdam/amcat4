import { amcatIndexSchema, amcatUserRoleSchema } from "@/schemas";
import { useQuery } from "@tanstack/react-query";
import { AmcatSessionUser } from "@/components/Contexts/AuthProvider";
import { z } from "zod";

interface Params {
  showAll?: boolean;
  showArchived?: boolean;
}

export function useAmcatProjects(user: AmcatSessionUser | undefined, params?: Params) {
  return useQuery({
    queryKey: ["projects", user, params],
    queryFn: async () => {
      const res = await getProjects(user, params);
      return z.array(amcatIndexSchema).parse(res);
    },
    enabled: user != null,
  });
}

export function useAmcatIndexRoles(user: AmcatSessionUser | undefined, params?: Params) {
  return useQuery({
    queryKey: ["projects", user, params, "minimal"],
    queryFn: async () => {
      const res = await getProjects(user, params, true);
      return z.record(z.string(), amcatUserRoleSchema).parse(res);
    },
    enabled: user != null,
  });
}

async function getProjects(user: AmcatSessionUser | undefined, p?: Params, minimal: boolean = false) {
  if (!user) return undefined;

  const params = {
    show_all: p?.showAll ? 1 : 0,
    minimal: minimal ? 1 : 0,
    show_archived: p?.showArchived ? 1 : 0,
  };
  const res = await user.api.get(`/index`, { params });
  return res.data;
}
