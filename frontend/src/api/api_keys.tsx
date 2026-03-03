import { AmcatApiKey } from "@/interfaces";
import { amcatApiKeySchema } from "@/schemas";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import axios from "axios";
import { AmcatSessionUser, useAmcatSession } from "@/components/Contexts/AuthProvider";
import { z } from "zod";

export function useApiKeys(user?: AmcatSessionUser) {
  return useQuery({
    queryKey: ["api_keys"],
    queryFn: async () => {
      if (!user) return [];
      const res = await user.api.get(`api_keys`);
      return z.array(amcatApiKeySchema).parse(res.data);
    },
    enabled: !!user,
  });
}

interface MutateApiKeysParams {
  update: AmcatApiKey;
  action: "update" | "delete" | "create";
  regenerate?: boolean;
}

export function useMutateApiKeys(user?: AmcatSessionUser) {
  const queryClient = useQueryClient();

  return useMutation({
    mutationFn: async (params: MutateApiKeysParams) => {
      if (!user) throw new Error("Not logged in");
      let api_key: string | null = null;

      if (params.action === "delete") {
        await user.api.delete(`api_keys/${params.update.id}`);
      } else if (params.action === "update") {
        const update: any = { ...params.update };
        if (params.regenerate) update.regenerate_key = true;
        const res = await user.api.put(`api_keys/${params.update.id}`, update);
        api_key = res.data.api_key || null;
      } else if (params.action === "create") {
        const res = await user.api.post(`api_keys`, params.update);
        api_key = res.data.api_key || null;
      }
      return api_key;
    },
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["api_keys"] });
    },
  });
}
