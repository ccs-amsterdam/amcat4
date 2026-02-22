import { AmcatArticle, AmcatField, AmcatIndexId, AmcatQuery, AmcatUserRole } from "@/interfaces";
import { AlertTriangle, Link as LinkIcon, SkipBack, SkipForward } from "lucide-react";
import { AmcatSessionUser } from "@/components/Contexts/AuthProvider";
import { Link } from "@tanstack/react-router";
import { highlightElasticTags, removeElasticTags } from "../../lib/highlightElasticTags";
import { Badge } from "../ui/badge";
import { Button } from "../ui/button";
import usePaginatedArticles from "./usePaginatedArticles";
import { DynamicIcon } from "../ui/dynamic-icon";
import { ReactNode } from "react";

interface Props {
  user: AmcatSessionUser;
  indexId: AmcatIndexId;
  indexRole: AmcatUserRole;
  query: AmcatQuery;
  fields: AmcatField[];
  onClick?: (doc: AmcatArticle) => void;
}

const defaultSnippets = {
  nomatch_chars: 200,
  max_matches: 5,
  match_chars: 50,
};

export default function ArticleSnippets({ user, indexId, indexRole, query, fields, onClick }: Props) {
  const { articles, layout, listFields, isFetching, pageIndex, pageCount, totalCount, prevPage, nextPage } =
    usePaginatedArticles({ user, indexId, query, fields, indexRole, highlight: true, defaultSnippets, pageSize: 6 });

  // if (isLoading) return <Loading msg="Loading articles" />;
  return (
    <div>
      <div className="mb-1 flex items-center justify-between">
        <div>
          <h3 className="text-xl font-semibold text-foreground">{totalCount} articles</h3>
        </div>
        <div className={`flex select-none items-center justify-end ${pageCount > 1 ? "" : "hidden"}`}>
          <Button variant="ghost" className="hover:bg-transparent" onClick={() => prevPage()} disabled={pageIndex <= 0}>
            <SkipBack />
          </Button>
          <div className="grid grid-cols-[1fr,auto,1fr] gap-2">
            <div className="text-center">{pageIndex + 1}</div>
            <div>of</div>
            <div>{pageCount}</div>
          </div>
          <Button
            variant="ghost"
            className="hover:bg-transparent"
            onClick={nextPage}
            disabled={pageIndex > pageCount - 2 || isFetching}
          >
            <SkipForward />
          </Button>
        </div>
      </div>
      <div className="relative rounded ">
        <div className={`relative grid max-h-full grid-cols-1 gap-2  pr-3 ${isFetching ? "opacity-80" : ""}`}>
          {articles.map((row, i: number) => (
            <button
              key={row._id + i}
              onClick={() => onClick && onClick(row)}
              className={`prose prose-sm max-w-full animate-fade-in rounded-t border-b border-primary text-left shadow-foreground/50
                        transition-all dark:prose-invert hover:translate-x-1    ${onClick ? "cursor-pointer" : ""}`}
            >
              <article className={`my-1 min-h-[5rem] py-1  `}>
                <div className="flex  justify-between">
                  <h4 className="mt-2">
                    {layout.title.map((title, i) => {
                      return (
                        <span key={title} title={removeElasticTags(String(row[title] || ""))}>
                          {i > 0 ? <span className="mx-1 text-primary"> | </span> : ""}
                          {highlightElasticTags(String(row[title] || "NA"))}
                        </span>
                      );
                    })}
                  </h4>
                  {row.url ? (
                    <Link
                      to={row.url}
                      tabIndex={i}
                      rel="noopener noreferrer"
                      target="_blank"
                      onClick={(e) => {
                        e.stopPropagation();
                      }}
                    >
                      <LinkIcon className=" h-7 w-7 rounded-full bg-primary/20 p-1 hover:bg-primary hover:text-primary-foreground" />
                    </Link>
                  ) : null}
                </div>

                <div className="line-clamp-2 overflow-hidden text-ellipsis">{snippetText(row, layout.text)}</div>
                <div className="flex flex-wrap gap-1 pt-2">
                  {listFields
                    .filter(
                      (field) => layout.meta.includes(field.name) && !layout.text.includes(field.name),
                      // && !layout.title.includes(field.name),
                    )
                    .map((field) => {
                      let value = row[field.name];
                      if (Array.isArray(value)) value = value.join(", ");

                      value = String(value);
                      let variant: "secondary" | "default" | "destructive" = value.includes("<em>")
                        ? "secondary"
                        : "default";
                      let showValue: ReactNode = removeElasticTags(value);

                      const type = fields.find((f) => f.name === field.name)?.type;
                      if (type === "image") showValue = DynamicIcon({ type: "image", className: "h-4 w-4" });
                      if (type === "preprocess") {
                        if (row[field.name]?.status === "error") {
                          variant = "destructive";
                          showValue = <AlertTriangle className="h-4 w-4" />;
                        } else if (row[field.name]?.status === "done") {
                          return null;
                        } else {
                          variant = "secondary";
                          showValue = <DynamicIcon type="preprocess" className="h-4 w-4" />;
                        }
                      }
                      return (
                        !!row[field.name] && (
                          <Badge
                            key={field.name}
                            className="max-w-[15rem]"
                            tooltip={
                              <div className="grid grid-cols-[auto,1fr] items-center gap-x-3">
                                <b>FIELD</b>
                                <span>{field.name}</span>
                                <b>TYPE</b>
                                <span className="">{type}</span>
                              </div>
                            }
                            variant={variant}
                          >
                            {showValue}
                          </Badge>
                        )
                      );
                    })}
                </div>
              </article>
            </button>
          ))}
        </div>
        <div className={`h-full ${isFetching ? "block" : "hidden"}`}></div>
      </div>
    </div>
  );
}

function snippetText(row: AmcatArticle, fields: string[]) {
  const text = fields
    .map((f) => row[f])
    .filter((t) => !!t)
    .join(" | ");
  if (text && text.includes("<em>")) return highlightElasticTags(text);
  return text;
}
