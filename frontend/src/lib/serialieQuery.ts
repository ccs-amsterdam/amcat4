import { AmcatQuery } from "@/interfaces";
import lzstring from "lz-string";

export function serializeQuery(query: AmcatQuery, maxLength = 1000) {
  const hasQueries = query.queries && query.queries.length > 0;
  const hasFilters = query.filters && Object.keys(query.filters).length > 0;
  if (!hasQueries && !hasFilters) return null;

  const queryTuple = [query.queries, query.filters];
  const compressedQuery = lzstring.compressToEncodedURIComponent(JSON.stringify(queryTuple));
  if (compressedQuery.length < maxLength) {
    return compressedQuery;
  } else {
    return null;
  }
}

export function deserializeQuery(queryString: string | null): AmcatQuery {
  if (!queryString) return {};
  try {
    const queryTuple = JSON.parse(lzstring.decompressFromEncodedURIComponent(queryString));
    const [queries, filters] = queryTuple;
    return { queries, filters };
  } catch (e) {
    return {};
  }
}
