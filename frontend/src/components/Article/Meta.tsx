import { AmcatArticle, AmcatField, AmcatProjectId } from "@/interfaces";
import { formatField } from "@/lib/formatField";
import { AmcatCopiedFrom } from "@/api/article";
import { Link } from "@tanstack/react-router";

interface MetaProps {
  article: AmcatArticle;
  fields: AmcatField[];
  projectId: AmcatProjectId;
  setArticle?: (id: string) => void;
  metareader?: boolean;
  /** If the document was copied from another project: the source project and document id */
  copiedFrom?: AmcatCopiedFrom | null;
}

export default function Meta({ article, fields, projectId, metareader, copiedFrom }: MetaProps) {
  const metaFields = fields.filter((f) => f.type !== "text" && f.client_settings.inDocument);
  if (metaFields.length === 0 && !article._id) return null;

  return (
    <div className=" prose-sm flex flex-col gap-4">
      {article._id && (
        <div className="flex flex-col">
          <span title="_id" className="line-clamp-1 overflow-hidden text-ellipsis font-semibold text-primary/80">
            ID
          </span>
          <a
            href={`/projects/${encodeURIComponent(projectId)}/articles/${article._id}`}
            onClick={(e) => e.preventDefault()}
            className="line-clamp-3 overflow-hidden text-ellipsis text-[0.8rem] leading-5 hover:underline"
          >
            {article._id}
          </a>
          <div className="mt-2 border-b border-foreground/10" />
        </div>
      )}
      {copiedFrom && (
        <div className="flex flex-col">
          <span className="line-clamp-1 overflow-hidden text-ellipsis font-semibold text-primary/80">COPIED FROM</span>
          <Link
            to="/projects/$project/articles/$articleId"
            params={{ project: copiedFrom.project, articleId: copiedFrom.doc_id }}
            className="line-clamp-3 overflow-hidden text-ellipsis text-[0.8rem] leading-5 hover:underline"
          >
            {copiedFrom.project} / {copiedFrom.doc_id}
          </Link>
          <div className="mt-2 border-b border-foreground/10" />
        </div>
      )}
      {fields.map((field) => {
        if (["text", "image", "video", "preprocess"].includes(field.type)) return null;

        const noAccessMessage =
          metareader && field.metareader.access !== "read" ? (
            <span className="text-secondary">Not visible for METAREADER</span>
          ) : null;

        if (!article[field.name] && !noAccessMessage) return null;

        let value = article[field.name];
        if (Array.isArray(value)) value = value.join(", ");
        value = String(value);

        return (
          <div key={field.name} className="flex flex-col">
            {/*<Badge
              tooltip={
                <div className="grid grid-cols-[auto,1fr] items-center gap-x-3">
                  <b>FIELD</b>
                  <span>{field.name}</span>
                  <b>TYPE</b>
                  <span className="">{field.type}</span>

                  <b>VALUE</b>
                  <span className="">{noAccessMessage || formatField(article, field)}</span>
                </div>
              }
            >
              {field.name}
            </Badge>*/}
            <span
              title={field.name}
              className="line-clamp-1 overflow-hidden text-ellipsis font-semibold text-primary/80"
            >
              {field.name.replaceAll("_", " ").toUpperCase()}
            </span>

            <span
              className="line-clamp-3 overflow-hidden text-ellipsis text-[0.8rem] leading-5"
              title={noAccessMessage ? null : value}
            >
              {noAccessMessage || formatField(article, field) || <span className="text-primary">NA</span>}
            </span>
            <div className="mt-2 border-b border-foreground/10" />
          </div>
        );
      })}
    </div>
  );
}
