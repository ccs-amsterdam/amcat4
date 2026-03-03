import {
  AmcatProjectId,
  AmcatQuery,
  AmcatQueryParams,
  AmcatQueryResult,
  UpdateAmcatField,
  UploadOperation,
} from "@/interfaces";
import { amcatQueryResultSchema } from "@/schemas";
import { useInfiniteQuery, useMutation, useQueryClient } from "@tanstack/react-query";
import { AmcatSessionUser } from "@/components/Contexts/AuthProvider";
import { useEffect } from "react";
import { z } from "zod";
import { postQuery } from "./query";

export function useArticles(
  user: AmcatSessionUser,
  projectId: AmcatProjectId,
  query: AmcatQuery,
  params?: AmcatQueryParams,
  projectRole?: string,
  enabled: boolean = true,
) {
  const queryClient = useQueryClient();

  useEffect(() => {
    // whenever the query changes (or component mounts) reset the page.
    // this is necessary because react query otherwise refetches ALL pages at once,
    // both slowing down the UI and making needless API requests
    return () =>
      queryClient.setQueryData(["articles", user, projectId, query, params, projectRole], (oldData: any) => {
        if (!oldData) return oldData;
        return {
          pageParams: [0],
          pages: [oldData.pages[0]],
        };
      });
  }, [queryClient, user, projectId, query, params, projectRole]);

  return useInfiniteQuery({
    queryKey: ["articles", user, projectId, query, params, projectRole],
    queryFn: ({ pageParam }) => getArticles(user, projectId, query, { page: pageParam, ...(params || {}) }),
    enabled: enabled && !!user && !!projectId && !!query,
    initialPageParam: 0,
    staleTime: Infinity,
    refetchOnWindowFocus: false,
    getNextPageParam: (lastPage) => {
      if (lastPage?.meta?.page == undefined || lastPage?.meta?.page_count == undefined) return undefined;
      if (lastPage.meta.page >= lastPage.meta.page_count) return undefined;
      return lastPage.meta.page + 1;
    },
  });
}

async function getArticles(
  user: AmcatSessionUser,
  projectId: AmcatProjectId,
  query: AmcatQuery,
  params: AmcatQueryParams,
) {
  // TODO, make sure query doesn't run needlessly
  // also check that it doesn't run if field is added but empty
  const res = await postQuery(user, projectId, query, params);
  const queryResult: AmcatQueryResult = amcatQueryResultSchema.parse(res.data);
  return queryResult;
}

export function useMutateArticles(user?: AmcatSessionUser, projectId?: AmcatProjectId | undefined) {
  const queryClient = useQueryClient();

  return useMutation({
    mutationFn: async (params: {
      documents: Record<string, any>;
      fields?: Record<string, UpdateAmcatField>;
      operation: UploadOperation;
    }) => {
      if (!user || !projectId) throw new Error("Not logged in");
      const res = await user.api.post(`/index/${projectId}/documents`, params);
      return z
        .object({
          successes: z.number(),
          failures: z.array(z.string()),
        })
        .parse(res.data);
    },
    onSuccess: (data, variables) => {
      queryClient.invalidateQueries({ queryKey: ["article", user, projectId] });
      queryClient.invalidateQueries({ queryKey: ["articles", user, projectId] });
      queryClient.invalidateQueries({ queryKey: ["fields", user, projectId] });
      queryClient.invalidateQueries({ queryKey: ["fieldValues", user, projectId] });
      queryClient.invalidateQueries({ queryKey: ["aggregate", user, projectId] });
    },
  });
}
