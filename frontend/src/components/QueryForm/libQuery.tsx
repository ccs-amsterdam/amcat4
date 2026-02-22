import { AmcatQueryTerm } from "@/interfaces";

export function queriesToString(queries: AmcatQueryTerm[], multiline?: boolean): string {
  if (!queries) return "";
  const sep = multiline ? "\n" : ";";
  let str = queries
    .map((query) => {
      if (query.label) {
        if (!query.query) return query.label + "=";
        return `${query.label}=${query.query}`;
      }

      if (multiline) return query.query;
      return query.query;
    })
    .join(sep);

  if (!multiline) str = str.replaceAll(/;(?=\S)/g, `; `);
  return str;
}

export function queriesFromString(q: string): AmcatQueryTerm[] {
  if (!q?.trim()) return [];
  const queries = q.split(/;\s+;|[\n;]+/g);
  return queries.map((s, i) => queryfromString(s));
}

function queryfromString(q: string): AmcatQueryTerm {
  const labelRE = /(?<=\w\s*)=/;
  const m = q.match(labelRE);
  if (!m?.index) return { query: q };
  return {
    label: q.slice(0, m.index),
    query: q.slice(m.index + m.length),
  };
}
