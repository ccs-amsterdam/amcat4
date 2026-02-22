import { AmcatIndexId, AmcatQuery } from "@/interfaces";
import { useMutation, useQueryClient } from "@tanstack/react-query";
import { AmcatSessionUser } from "@/components/Contexts/AuthProvider";
import { toast } from "sonner";
import { z } from "zod";
import { asPostAmcatQuery } from "./query";

interface MutateTagsParams {
  tag: string;
  action: "add" | "remove";
  field: string;
  query: AmcatQuery;
}

export function useMutateTags(user: AmcatSessionUser, indexId: AmcatIndexId) {
  const queryClient = useQueryClient();

  return useMutation({
    mutationFn: ({ tag, action, field = "tags", query }: MutateTagsParams) => {
      const amcatQuery = asPostAmcatQuery(query);
      return user.api.post(`/index/${indexId}/tags_update`, { ...amcatQuery, tag, action, field });
    },
    onSuccess: (data: any, variables: any) => {
      queryClient.invalidateQueries({ queryKey: ["fields", user, indexId] });
      queryClient.invalidateQueries({ queryKey: ["article", user, indexId] });
      queryClient.invalidateQueries({ queryKey: ["articles", user, indexId] });
      queryClient.invalidateQueries({ queryKey: ["fieldValues", user, indexId, variables.field] });
      queryClient.invalidateQueries({ queryKey: ["aggregate", user, indexId] });

      const result = z.object({ updated: z.number(), total: z.number() }).parse(data.data);
      if (variables.action === "add")
        toast.success(`Added tag "${variables.field}:${variables.tag}" to ${result.updated} documents`);
      if (variables.action === "remove")
        toast.success(`Removed tag "${variables.field}:${variables.tag}" from ${result.updated} documents`);
    },
  });
}
