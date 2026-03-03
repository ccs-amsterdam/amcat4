import { highlightElasticTags } from "./highlightElasticTags";
import { AmcatArticle, AmcatField } from "@/interfaces";

/**
 * Format a meta field for presentation
 * @param {*} article
 * @param {*} field
 * @returns
 */
export const formatField = (article: AmcatArticle, field: AmcatField) => {
  const value = article[field.name];
  if (value == null) return null;

  switch (field.type) {
    case "date":
      // Only remove 'T' for now. But not sure why that's a great idea
      return value.replace("T", " ").substring(0, 19);

    case "keyword":
      // if value contains http or https, make it a link
      if (
        typeof value === "string" &&
        (value.startsWith("http://") || value.startsWith("https://") || value.startsWith("www."))
      )
        return <a href={value}>{value}</a>;
      if (Array.isArray(value)) return highlightableValue(value.join(", "));
      else return value ? <span>{highlightableValue(String(value))}</span> : null;
    case "tag":
      if (Array.isArray(value)) return highlightableValue(value.join(", "));
      else return value ? <span>{highlightableValue(String(value))}</span> : null;
    case "number":
      return <i>{value}</i>;
    case "text":
      return <span title={String(value)}>{highlightableValue(String(value))}</span>;
    default:
      if (typeof value === "string") return value;
      return JSON.stringify(value);
  }
};

function highlightableValue(value: string) {
  return value.includes("<em>") ? highlightElasticTags(value) : value;
}
