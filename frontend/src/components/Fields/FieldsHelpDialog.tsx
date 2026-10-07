import { Dialog, DialogContent, DialogHeader, DialogTitle, DialogTrigger } from "@/components/ui/dialog";
import { HelpCircle, Key } from "lucide-react";
import { DynamicIcon } from "../ui/dynamic-icon";

export const fieldTypeDescriptions: [string, string][] = [
  ["keyword", "Short labels or categories (e.g. country, language). Searched as exact values."],
  ["tag", "Like keyword, but a document can have multiple tags."],
  ["text", "Longer free text (e.g. article body). Analysed word-by-word so individual words can be searched."],
  ["url", "Links to web pages or external resources. Displayed as a clickable link."],
  ["image", "Links to image files stored in AmCAT."],
  ["video", "Links to video files stored in AmCAT."],
  ["audio", "Links to audio files stored in AmCAT."],
  ["date", "Date or date/time values."],
  ["boolean", "True or false values."],
  ["number", "Numeric values with decimals."],
  ["integer", "Whole numbers without decimals."],
  ["object", "Structured objects (JSON). Not analysed or parsed."],
  ["vector", "Dense vectors for document embeddings / semantic search."],
  ["geo_point", "Geolocation (longitude and latitude)."],
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
            The table below lists the available field types. You can change a field's type at any time: existing values
            are converted to the new type, which fails if any value cannot be converted.
          </p>
          <div className="divide-y rounded border text-sm">
            {fieldTypeDescriptions.map(([type, desc]) => (
              <div key={type} className="flex items-start gap-3 px-3 py-2">
                <DynamicIcon type={type} className="mt-0.5 h-4 w-4 shrink-0 text-primary" />
                <div>
                  <span className="font-mono font-medium">{type}</span>
                  <span className="ml-2 text-muted-foreground">{desc}</span>
                </div>
              </div>
            ))}
          </div>
        </section>

        <section className="mt-4">
          <h3 className="mb-2 flex items-center gap-2 font-semibold">
            <Key className="h-4 w-4" /> Unique fields
          </h3>
          <p className="text-sm text-muted-foreground">
            If one or more fields are marked as unique, documents with the same values for all unique fields are
            considered the same document — like a primary key in SQL. This prevents duplicate documents, and allows
            updating existing documents. Use a naturally unique value (e.g. an article URL) if available. You can
            combine multiple unique fields for a composite key (e.g. author + timestamp). Tag, vector and object fields
            cannot be unique.
          </p>
        </section>
      </DialogContent>
    </Dialog>
  );
}
