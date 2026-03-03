import { AggregationOptions, AmcatProjectId, AmcatQuery } from "@/interfaces";
import { postAggregateQuery } from "./query";

import { amcatAggregateDataSchema } from "@/schemas";
import { useInfiniteQuery } from "@tanstack/react-query";
import { AmcatSessionUser } from "@/components/Contexts/AuthProvider";

export function useCount(user: AmcatSessionUser, projectId: AmcatProjectId, query: AmcatQuery) {
  const result = useAggregate(user, projectId, query, { axes: [], display: "list" });
  const count = result.data == null ? null : result.data.pages[0].data[0].n;

  return { count, ...result };
}

export function useAggregate(
  user: AmcatSessionUser,
  projectId: AmcatProjectId,
  query: AmcatQuery,
  options: AggregationOptions,
) {
  return useInfiniteQuery({
    queryKey: ["aggregate", user, projectId, query, options],
    queryFn: ({ pageParam }) => postAggregate(user, projectId, query, options, pageParam),
    initialPageParam: {},
    getNextPageParam: (lastPage) => {
      return lastPage?.meta?.after;
    },

    enabled: !!user && !!projectId && !!query && !!options?.axes,
  });
}

async function postAggregate(
  user: AmcatSessionUser,
  projectId: AmcatProjectId,
  query: AmcatQuery,
  options: AggregationOptions,
  pageParam: Record<string, any>,
) {
  const res = await postAggregateQuery(user, projectId, { ...options, after: pageParam }, query);
  return amcatAggregateDataSchema.parse(res.data);
}
