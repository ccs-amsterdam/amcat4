import { AmcatArticle, AmcatField } from "@/interfaces";
import { formatField } from "@/lib/formatField";
import { Badge } from "../ui/badge";

interface MetaProps {
  article: AmcatArticle;
  fields: AmcatField[];
  setArticle?: (id: string) => void;
  metareader?: boolean;
}

export default function Meta({ article, fields, setArticle, metareader }: MetaProps) {
  const metaFields = fields.filter((f) => f.type !== "text" && f.client_settings.inDocument);
  if (metaFields.length === 0) return null;

  return (
    <div className=" prose-sm flex flex-col gap-4">
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
                  <span className="">
                    {field.type === field.elastic_type ? field.type : `${field.type} (${field.elastic_type})`}
                  </span>

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
