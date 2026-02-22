import { useArticles } from "@/api/articles";
import { AmcatArticle, AmcatField, AmcatIndexId, AmcatQuery, AmcatSnippet, AmcatUserRole } from "@/interfaces";
import { AmcatSessionUser } from "@/components/Contexts/AuthProvider";
import { useCallback, useEffect, useMemo, useState } from "react";
import useListFields from "./useListFields";

interface params {
  user: AmcatSessionUser;
  indexId: AmcatIndexId;
  query: AmcatQuery;
  fields?: AmcatField[];
  indexRole?: AmcatUserRole;
  pageSize: number;
  highlight?: boolean;
  defaultSnippets?: AmcatSnippet;
  combineResults?: boolean;
  enabled?: boolean;
}

export default function usePaginatedArticles({
  user,
  indexId,
  query,
  fields,
  indexRole,
  pageSize,
  highlight,
  defaultSnippets,
  combineResults,
  enabled = true,
}: params) {
  const { listFields, layout } = useListFields(indexRole || "NONE", fields || [], defaultSnippets);
  const params = useMemo(
    () => ({ per_page: pageSize, highlight: !!highlight, fields: listFields }),
    [pageSize, listFields],
  );

  const [articles, setArticles] = useState<AmcatArticle[]>([]);
  const [pageIndex, setPageIndex] = useState(0);
  const [alignedPageIndex, setAlignedPageIndex] = useState(0);
  const { data, isLoading, isFetching, fetchNextPage } = useArticles(user, indexId, query, params, indexRole, enabled);

  useEffect(() => {
    if (!data?.pages || pageIndex > data.pages.length - 1) {
      return;
    }
    if (combineResults) {
      setArticles(data?.pages.map((page) => page.results).flat() || []);
    } else {
      setArticles(data?.pages[pageIndex]?.results || []);
    }
    setAlignedPageIndex(pageIndex);
  }, [combineResults, data, pageIndex]);

  const pageCount = data?.pages[0]?.meta?.page_count || 0;
  const totalCount = data?.pages[0]?.meta?.total_count || 0;
  const fetchedPages = data?.pages.length || 1;

  useEffect(() => {
    // makes sure pageIndex is within bounds
    setPageIndex((pageIndex) => Math.min(fetchedPages - 1, pageIndex));
  }, [fetchedPages]);

  const prevPage = useCallback(() => {
    setPageIndex((pageIndex) => Math.max(0, pageIndex - 1));
  }, [setPageIndex]);

  const nextPage = useCallback(() => {
    setPageIndex((pageIndex) => {
      const newPagenr = pageIndex + 1;
      if (newPagenr > fetchedPages - 1) fetchNextPage();
      return newPagenr;
    });
  }, [fetchNextPage, setPageIndex]);

  return {
    articles,
    listFields,
    layout,
    isLoading,
    isFetching,
    pageIndex: alignedPageIndex,
    pageCount,
    totalCount,
    prevPage,
    nextPage,
  };
}
