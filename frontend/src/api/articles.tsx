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
    queryClient.setQueryData(["articles", user, projectId, query, params, projectRole], (oldData: any) => {
      if (oldData == null) return undefined;
      return {
        pageParams: [undefined],
        pages: [oldData.pages[0]],
      };
    });
  }, [queryClient, user, projectId, query, params, projectRole]);

  return useInfiniteQuery({
    queryKey: ["articles", user, projectId, query, params, projectRole],
    // pages are fetched sequentially, using the cursor (meta.next) of the previous page
    queryFn: ({ pageParam }) =>
      getArticles(user, projectId, query, { ...(params || {}), ...(pageParam ? { after: pageParam } : {}) }),
    enabled: enabled && !!user && !!projectId && !!query,
    initialPageParam: undefined as string | undefined,
    staleTime: Infinity,
    refetchOnWindowFocus: false,
    getNextPageParam: (lastPage) => lastPage?.meta?.next ?? undefined,
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
      return z.object({ created: z.number(), updated: z.number() }).parse(res.data);
    },
    onSuccess: (data, variables) => {
      // removeQueries for data queries: avoids a race where setQueryData in useArticles clears the
      // isInvalidated flag before the refetch triggers, causing stale data to persist indefinitely.
      queryClient.removeQueries({ queryKey: ["article"] });
      queryClient.removeQueries({ queryKey: ["articles"] });
      queryClient.removeQueries({ queryKey: ["aggregate"] });
      queryClient.invalidateQueries({ queryKey: ["fields"] });
      queryClient.invalidateQueries({ queryKey: ["fieldValues"] });
    },
  });
}
