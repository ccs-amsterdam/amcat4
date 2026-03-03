import { Dialog, DialogContent, DialogHeader, DialogTitle, DialogTrigger } from "@/components/ui/dialog";
import { HelpCircle, Key } from "lucide-react";
import { DynamicIcon } from "../ui/dynamic-icon";

const typeGroups: { elasticType: string; types: [string, string][] }[] = [
  {
    elasticType: "keyword",
    types: [
      ["keyword", "Short labels or categories (e.g. country, language). Searched as exact values."],
      ["tag", "Like keyword, but a document can have multiple tags."],
      ["url", "Links to web pages or external resources. Displayed as a clickable link."],
      ["image", "Links to image files stored in AmCAT."],
      ["video", "Links to video files stored in AmCAT."],
      ["audio", "Links to audio files stored in AmCAT."],
    ],
  },
  {
    elasticType: "text",
    types: [["text", "Longer free text (e.g. article body). Analysed word-by-word so individual words can be searched."]],
  },
  { elasticType: "date", types: [["date", "Date or date/time values."]] },
  { elasticType: "boolean", types: [["boolean", "True or false values."]] },
  { elasticType: "double", types: [["number", "Numeric values with decimals."]] },
  { elasticType: "long", types: [["integer", "Whole numbers without decimals."]] },
  { elasticType: "flattened", types: [["object", "Structured objects (JSON). Not analysed or parsed."]] },
  { elasticType: "dense_vector", types: [["vector", "Dense vectors for document embeddings / semantic search."]] },
  { elasticType: "geo_point", types: [["geo", "Geolocation (longitude and latitude)."]] },
];

export default function FieldsHelpDialog({ children }: { children?: React.ReactNode }) {
  return (
    <Dialog>
      <DialogTrigger asChild>
        {children ?? <HelpCircle className="cursor-pointer text-primary" />}
      </DialogTrigger>
      <DialogContent className="max-h-[80vh] max-w-2xl overflow-y-auto">
        <DialogHeader>
          <DialogTitle>Field reference</DialogTitle>
        </DialogHeader>

        <section>
          <h3 className="mb-2 font-semibold">Field types</h3>
          <p className="mb-3 text-sm text-muted-foreground">
            The table below lists the available field types, grouped by their Elasticsearch data type. You can change a
            field's type within the same group at any time, but Elasticsearch does not allow changes between different
            data types.
          </p>
          <div className="divide-y rounded border text-sm">
            {typeGroups.map(({ elasticType, types }) => (
              <>
                <div key={elasticType} className="flex items-center gap-2 bg-muted/50 px-3 py-1">
                  <span className="text-xs text-muted-foreground">Elasticsearch type:</span>
                  <span className="font-mono text-xs font-medium">{elasticType}</span>
                </div>
                {types.map(([type, desc]) => (
                  <div key={type} className="flex items-start gap-3 px-3 py-2 pl-6">
                    <DynamicIcon type={type} className="mt-0.5 h-4 w-4 shrink-0 text-primary" />
                    <div>
                      <span className="font-mono font-medium">{type}</span>
                      <span className="ml-2 text-muted-foreground">{desc}</span>
                    </div>
                  </div>
                ))}
              </>
            ))}
          </div>
        </section>

        <section className="mt-4">
          <h3 className="mb-2 flex items-center gap-2 font-semibold">
            <Key className="h-4 w-4" /> Identifiers
          </h3>
          <p className="text-sm text-muted-foreground">
            If a field is marked as an identifier, it is used to prevent duplicate documents — like a primary key in
            SQL. Use a naturally unique value (e.g. an article URL) if available. You can combine multiple identifier
            fields for a composite key (e.g. author + timestamp).
          </p>
          <p className="mt-2 text-sm text-primary">
            Identifier status cannot be changed after the field is created, and the values of identifier fields cannot
            be updated once a document has been indexed.
          </p>
        </section>
      </DialogContent>
    </Dialog>
  );
}
