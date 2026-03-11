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
      refresh?: boolean;
    }) => {
      if (!user || !projectId) throw new Error("Not logged in");
      const url = params.refresh ? `/index/${projectId}/documents?refresh=true` : `/index/${projectId}/documents`;
      const { refresh: _refresh, ...body } = params;
      const res = await user.api.post(url, body);
      const raw = z.object({ successes: z.number(), failures: z.array(z.unknown()) }).parse(res.data);
      const failures = raw.failures.map((f): string => {
        if (typeof f === "string") return f;
        if (typeof f === "object" && f !== null) {
          const inner = Object.values(f as Record<string, any>)[0];
          return inner?.error?.reason ?? inner?.error?.type ?? JSON.stringify(f);
        }
        return String(f);
      });
      return { successes: raw.successes, failures };
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
