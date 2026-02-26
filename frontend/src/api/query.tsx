import { AggregationOptions, AmcatFilters, AmcatProjectId, AmcatQuery, AmcatQueryParams } from "@/interfaces";
import { AmcatSessionUser } from "@/components/Contexts/AuthProvider";

interface PostAmcatQuery {
  filters?: AmcatFilters;
  queries?: Record<string, string>;
}

export function postQuery(
  user: AmcatSessionUser,
  projectId: AmcatProjectId,
  query?: AmcatQuery,
  params?: AmcatQueryParams,
) {
  const postAmcatQuery = query ? asPostAmcatQuery(query) : undefined;
  return user.api.post(`index/${projectId}/query`, {
    ...postAmcatQuery,
    ...params,
  });
}

export function postAggregateQuery(
  user: AmcatSessionUser,
  projectId: AmcatProjectId,
  options: AggregationOptions,
  query?: AmcatQuery,
) {
  const postAmcatQuery = query ? asPostAmcatQuery(query) : undefined;

  const postOptions: any = { axes: options.axes };
  if (options.metrics)
    postOptions.aggregations = options.metrics.map((m) => {
      return { field: m.field, function: m.function, name: m.name || m.field };
    });
  if (options.after) postOptions.after = options.after;

  return user.api.post(`index/${projectId}/aggregate`, {
    ...postAmcatQuery,
    ...postOptions,
  });
}

export function asPostAmcatQuery(query: AmcatQuery) {
  const postAmcatQuery: PostAmcatQuery = {};
  if (query.queries) {
    query.queries.forEach((q) => {
      if (!postAmcatQuery.queries) postAmcatQuery.queries = {};
      postAmcatQuery.queries[q.label || q.query] = q.query;
    });
  }
  if (query.filters) {
    postAmcatQuery.filters = { ...query.filters };
    Object.keys(postAmcatQuery.filters).forEach((key) => {
      delete postAmcatQuery.filters?.[key].justAdded;
    });
  }

  return postAmcatQuery;
}

export function postReindex(
  user: AmcatSessionUser,
  source: AmcatProjectId,
  destination: AmcatProjectId,
  query: AmcatQuery,
) {
  const query_body = asPostAmcatQuery(query);
  return user.api.post(`index/${source}/reindex`, {
    destination: destination,
    ...query_body,
  });
}
