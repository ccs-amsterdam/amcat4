import { AggregationOptions, AmcatProjectId, AmcatQuery } from "@/interfaces";
import { postAggregateQuery } from "./query";

import { amcatAggregateDataSchema } from "@/schemas";
import { useQuery } from "@tanstack/react-query";
import { AmcatSessionUser } from "@/components/Contexts/AuthProvider";

export function useCount(user: AmcatSessionUser, projectId: AmcatProjectId, query: AmcatQuery) {
  const result = useAggregate(user, projectId, query, { axes: [], display: "list" });
  const count = result.data == null ? null : result.data.data[0].n;

  return { count, ...result };
}

export function useAggregate(
  user: AmcatSessionUser,
  projectId: AmcatProjectId,
  query: AmcatQuery,
  options: AggregationOptions,
) {
  return useQuery({
    queryKey: ["aggregate", user, projectId, query, options],
    queryFn: () => postAggregate(user, projectId, query, options),
    enabled: !!user && !!projectId && !!query && !!options?.axes,
  });
}

async function postAggregate(
  user: AmcatSessionUser,
  projectId: AmcatProjectId,
  query: AmcatQuery,
  options: AggregationOptions,
) {
  const res = await postAggregateQuery(user, projectId, options, query);
  return amcatAggregateDataSchema.parse(res.data);
}
