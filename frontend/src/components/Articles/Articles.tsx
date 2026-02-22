import { useFields } from "@/api/fields";
import { useMyIndexrole } from "@/api/index";
import ArticleModal from "@/components/Article/ArticleModal";
import { Loading } from "@/components/ui/loading";
import { AmcatArticle, AmcatField, AmcatIndexId, AmcatQuery, SortSpec } from "@/interfaces";
import { AmcatSessionUser } from "@/components/Contexts/AuthProvider";
import { useState } from "react";
import { ErrorMsg } from "../ui/error-message";
import ArticleSnippets from "./ArticleSnippets";

interface ArticlesProps {
  user: AmcatSessionUser;
  indexId: AmcatIndexId;
  /** Query/filter of which documents to show */
  query: AmcatQuery;
  /** an Array with objects indicating which columns to show and how */
  columns?: AmcatField[];
  /** if true, include all columns AFTER the columns specified in the columns argument */
  allColumns?: boolean;
  /** Number of articles per page */
  perPage?: number;
  /** How to sort results */
  sort?: SortSpec;
  /** Callback when clicking on an article.  */
  onClick?: (doc: AmcatArticle) => void;
  onSortChange?: (sort: SortSpec) => void;
  showOnClick?: boolean;
}

/**
 * Table overview of a subset of articles
 */
export default function Articles({ user, indexId, query, onClick, showOnClick = true }: ArticlesProps) {
  //TODO: add columns to meta OR retrieve fields (prefer the former) and pass the field types on to the table
  const { role } = useMyIndexrole(user, indexId);
  const [articleId, setArticleId] = useState<string | null>(null);
  const { data: fields, isLoading: loadingFields } = useFields(user, indexId);

  if (loadingFields) return <Loading msg="Loading fields" />;
  if (!fields) return <ErrorMsg type="Could not get index field data" />;

  const handleClick = (row: any) => {
    if (onClick != null) onClick(row);
    if (showOnClick) setArticleId(row._id);
  };

  return (
    <div className="w-full">
      <div className="grid grid-cols-[max,1fr] rounded ">
        <ArticleSnippets
          user={user}
          indexId={indexId}
          indexRole={role || "NONE"}
          query={query}
          fields={fields}
          onClick={handleClick}
        />
        <div> </div>
      </div>

      {articleId ? (
        <ArticleModal
          key={articleId}
          user={user}
          indexId={indexId}
          id={articleId}
          query={query}
          changeArticle={setArticleId}
        />
      ) : null}
    </div>
  );
}
