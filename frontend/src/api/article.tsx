import { addFilter } from "@/api/util";
import { AmcatProjectId, AmcatQuery, AmcatQueryParams } from "@/interfaces";
import { amcatQueryResultSchema } from "@/schemas";
import { useQuery } from "@tanstack/react-query";
import { z } from "zod";
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

const copiedFromSchema = z.object({ project: z.string(), doc_id: z.string() });
export type AmcatCopiedFrom = z.infer<typeof copiedFromSchema>;

/**
 * Get the provenance of a document that was copied from another project (or null).
 * This is only available from the single document endpoint (requires READER role)
 */
export function useCopiedFrom(user: AmcatSessionUser, projectId: AmcatProjectId, articleId: string, enabled = true) {
  return useQuery({
    queryKey: ["article_copied_from", user, projectId, articleId],
    queryFn: async () => {
      const res = await user.api.get(`index/${projectId}/documents/${encodeURIComponent(articleId)}`);
      return copiedFromSchema.nullish().parse(res.data?._copied_from) ?? null;
    },
    enabled: enabled && !!user && !!projectId && !!articleId,
  });
}
