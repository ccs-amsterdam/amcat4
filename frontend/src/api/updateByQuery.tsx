import { AmcatProjectId, AmcatQuery } from "@/interfaces";
import { useMutation, useQueryClient } from "@tanstack/react-query";
import { AmcatSessionUser } from "@/components/Contexts/AuthProvider";
import { toast } from "sonner";
import { z } from "zod";
import { asPostAmcatQuery } from "./query";

interface UpdateByQueryParams {
  field: string;
  value: string | number | boolean | null;
  query: AmcatQuery;
}

export function useUpdateByQuery(user: AmcatSessionUser, projectId: AmcatProjectId) {
  const queryClient = useQueryClient();

  return useMutation({
    mutationFn: ({ field, value, query }: UpdateByQueryParams) => {
      const amcatQuery = asPostAmcatQuery(query);
      return user.api.post(`/index/${projectId}/update_by_query`, { ...amcatQuery, field, value });
    },
    onSuccess: (data: any, variables: any) => {
      queryClient.invalidateQueries({ queryKey: ["articles", user, projectId] });
      queryClient.invalidateQueries({ queryKey: ["aggregate", user, projectId] });
      queryClient.invalidateQueries({ queryKey: ["fieldValues", user, projectId] });
      const result = z.object({ updated: z.number(), total: z.number() }).parse(data.data);
      toast.success(`Updated field "${variables.field}" on ${result.updated} of ${result.total} documents`);
    },
  });
}

interface DeleteByQueryParams {
  query: AmcatQuery;
}

export function useDeleteByQuery(user: AmcatSessionUser, projectId: AmcatProjectId) {
  const queryClient = useQueryClient();

  return useMutation({
    mutationFn: ({ query }: DeleteByQueryParams) => {
      const amcatQuery = asPostAmcatQuery(query);
      return user.api.post(`/index/${projectId}/delete_by_query`, amcatQuery);
    },
    onSuccess: (data: any) => {
      queryClient.invalidateQueries({ queryKey: ["articles", user, projectId] });
      queryClient.invalidateQueries({ queryKey: ["aggregate", user, projectId] });
      queryClient.invalidateQueries({ queryKey: ["fieldValues", user, projectId] });
      queryClient.invalidateQueries({ queryKey: ["fieldStats", user, projectId] });
      const result = z.object({ updated: z.number(), total: z.number() }).parse(data.data);
      toast.success(`Deleted ${result.updated} documents`);
    },
  });
}
