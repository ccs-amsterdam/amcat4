import { addFilter } from "@/api/util";
import { AmcatIndexId, AmcatQuery, AmcatQueryParams } from "@/interfaces";
import { amcatQueryResultSchema } from "@/schemas";
import { useQuery } from "@tanstack/react-query";
import { AmcatSessionUser } from "@/components/Contexts/AuthProvider";
import { postQuery } from "./query";

export function useArticle(
  user: AmcatSessionUser,
  indexId: AmcatIndexId,
  articleId: string,
  query?: AmcatQuery,
  params?: AmcatQueryParams,
  indexRole?: string,
) {
  return useQuery({
    queryKey: ["article", user, indexId, articleId, query, params, indexRole],
    queryFn: () => getArticle(user, indexId, articleId, query, params),
    enabled: !!user && !!indexId && !!articleId,
  });
}

async function getArticle(
  user: AmcatSessionUser,
  indexId: AmcatIndexId,
  articleId: string,
  query?: AmcatQuery,
  params?: AmcatQueryParams,
) {
  let q = query || {};
  q = addFilter(q, { _id: { values: [articleId] } });
  const res = await postQuery(user, indexId, q, params);
  const queryResult = amcatQueryResultSchema.parse(res.data);
  return queryResult.results[0];
}
