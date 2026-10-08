import { AggregationOptions, AmcatFilters, AmcatProjectId, AmcatQuery, AmcatQueryParams } from "@/interfaces";
import { amcatJobSchema } from "@/schemas";
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
  if (options.order) postOptions.order = options.order;

  return user.api.post(`index/${projectId}/aggregate`, {
    ...postAmcatQuery,
    ...postOptions,
  });
}

export function asPostAmcatQuery(query: AmcatQuery) {
  const postAmcatQuery: PostAmcatQuery = {};
  if (query.queries) {
    query.queries.forEach((q) => {
      // skip empty queries, e.g. from a blank line in the multiline query input
      if (!q.query?.trim()) return;
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

export interface FieldCopyOptions {
  rename?: string;
  exclude?: boolean;
  type?: string;
}

export async function postCopy(
  user: AmcatSessionUser,
  source: AmcatProjectId,
  destination: AmcatProjectId,
  query: AmcatQuery,
  field_options?: Record<string, FieldCopyOptions>,
) {
  const query_body = asPostAmcatQuery(query);
  const res = await user.api.post(`index/${source}/copy`, {
    destination: destination,
    ...query_body,
    ...(field_options && Object.keys(field_options).length > 0 ? { field_options } : {}),
  });
  // copying runs as a background job
  return amcatJobSchema.parse(res.data);
}
