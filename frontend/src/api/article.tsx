import { addFilter } from "@/api/util";
import { AmcatProjectId, AmcatQuery, AmcatQueryParams } from "@/interfaces";
import { amcatQueryResultSchema } from "@/schemas";
import { useQuery } from "@tanstack/react-query";
import { AmcatSessionUser } from "@/components/Contexts/AuthProvider";
import { postQuery } from "./query";

export function useArticle(
  user: AmcatSessionUser,
  projectId: AmcatProjectId,
  articleId: string,
  query?: AmcatQuery,
  params?: AmcatQueryParams,
  projectRole?: string,
) {
  return useQuery({
    queryKey: ["article", user, projectId, articleId, query, params, projectRole],
    queryFn: () => getArticle(user, projectId, articleId, query, params),
    enabled: !!user && !!projectId && !!articleId,
  });
}

async function getArticle(
  user: AmcatSessionUser,
  projectId: AmcatProjectId,
  articleId: string,
  query?: AmcatQuery,
  params?: AmcatQueryParams,
) {
  let q = query || {};
  q = addFilter(q, { _id: { values: [articleId] } });
  const res = await postQuery(user, projectId, q, params);
  const queryResult = amcatQueryResultSchema.parse(res.data);
  return queryResult.results[0];
}
