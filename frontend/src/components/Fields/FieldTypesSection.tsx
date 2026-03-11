export function FieldTypesSection() {
  return (
    <section>
      <h4 className="mb-1.5 font-semibold text-foreground">Field types</h4>
      <div className="rounded-md bg-primary/10 p-3">
        <div className="grid grid-cols-[10rem_1fr] gap-3">
          <b className="text-primary">keyword</b>
          Short labels or categories (e.g. country, language). Searched as exact values.
          <b className="text-primary">tag</b>
          Like keyword, but a document can have multiple tags.
          <b className="text-primary">text</b>
          Longer free text (e.g. article body). Analysed word-by-word for full-text search.
          <b className="text-primary">date</b>
          Date or date/time values.
          <b className="text-primary">integer</b>
          Whole numbers without decimals.
          <b className="text-primary">number</b>
          Numeric values with decimals.
          <b className="text-primary">boolean</b>
          True or false values.
          <b className="text-primary">url / image / video / audio</b>
          Links to web pages or media files. Displayed as a clickable link or inline media.
          <b className="text-primary">object</b>
          Structured JSON objects. Not analysed or parsed by Elasticsearch.
        </div>
      </div>
    </section>
  );
}
