import { useFields } from "@/api/fields";
import { useMyProjectRole } from "@/api/project";
import ArticleModal from "@/components/Article/ArticleModal";
import { Loading } from "@/components/ui/loading";
import { AmcatArticle, AmcatField, AmcatProjectId, AmcatQuery, SortSpec } from "@/interfaces";
import { AmcatSessionUser } from "@/components/Contexts/AuthProvider";
import { useState } from "react";
import { ErrorMsg } from "../ui/error-message";
import ArticleSnippets from "./ArticleSnippets";

interface ArticlesProps {
  user: AmcatSessionUser;
  projectId: AmcatProjectId;
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
export default function Articles({ user, projectId, query, onClick, showOnClick = true }: ArticlesProps) {
  //TODO: add columns to meta OR retrieve fields (prefer the former) and pass the field types on to the table
  const { role } = useMyProjectRole(user, projectId);
  const [articleId, setArticleId] = useState<string | null>(null);
  const { data: fields, isLoading: loadingFields } = useFields(user, projectId);

  if (loadingFields) return <Loading msg="Loading fields" />;
  if (!fields) return <ErrorMsg type="Could not get project field data" />;

  const handleClick = (row: any) => {
    if (onClick != null) onClick(row);
    if (showOnClick) setArticleId(row._id);
  };

  return (
    <div className="w-full">
      <ArticleSnippets
        user={user}
        projectId={projectId}
        projectRole={role || "NONE"}
        query={query}
        fields={fields}
        onClick={handleClick}
      />

      {articleId ? (
        <ArticleModal
          key={articleId}
          user={user}
          projectId={projectId}
          id={articleId}
          query={query}
          changeArticle={setArticleId}
        />
      ) : null}
    </div>
  );
}
