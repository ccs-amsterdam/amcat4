import { createFileRoute } from "@tanstack/react-router";

export const Route = createFileRoute("/projects/$project/fields")({
  component: FieldsPage,
});

import { useAmcatConfig } from "@/api/config";
import { useFields, useMutateFields } from "@/api/fields";
import { useProject } from "@/api/project";
import FieldTable from "@/components/Fields/FieldTable";
import { ErrorMsg } from "@/components/ui/error-message";
import { Loading } from "@/components/ui/loading";
import { AmcatProject } from "@/interfaces";
import { useAmcatSession } from "@/components/Contexts/AuthProvider";
import { InfoBox } from "@/components/ui/info-box";
import { DynamicIcon } from "@/components/ui/dynamic-icon";
import { Key } from "lucide-react";

function FieldsPage() {
  const { project } = Route.useParams();
  const { user } = useAmcatSession();
  const projectId = decodeURI(project);
  const { data: projectData, isLoading: loadingProject } = useProject(user, projectId);

  if (loadingProject) return <Loading />;
  if (!projectData) return <ErrorMsg type="Not Allowed">Need to be logged in</ErrorMsg>;

  return (
    <div className="flex w-full  flex-col gap-10">
      <Fields project={projectData} />
    </div>
  );
}

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
  { elasticType: "text", types: [["text", "Longer free text (e.g. article body). Analysed word-by-word so individual words can be searched."]] },
  { elasticType: "date", types: [["date", "Date or date/time values."]] },
  { elasticType: "boolean", types: [["boolean", "True or false values."]] },
  { elasticType: "double", types: [["number", "Numeric values with decimals."]] },
  { elasticType: "long", types: [["integer", "Whole numbers without decimals."]] },
  { elasticType: "flattened", types: [["object", "Structured objects (JSON). Not analysed or parsed."]] },
  { elasticType: "dense_vector", types: [["vector", "Dense vectors for document embeddings / semantic search."]] },
  { elasticType: "geo_point", types: [["geo", "Geolocation (longitude and latitude)."]] },
];

function FieldsInfoBox() {
  return (
    <InfoBox title="Information on fields" storageKey="infobox:fields">
      <div className="flex flex-col gap-5 text-sm">
        <section>
          <h4 className="mb-2 font-semibold text-foreground">Field types</h4>
          <p className="mb-3">
            The table below lists the available field types, grouped by their Elasticsearch data type. You can change a
            field's type within the same group at any time, but Elasticsearch does not allow changes between different
            data types.
          </p>
          <div className="divide-y rounded border">
            {typeGroups.map(({ elasticType, types }) => (
              <>
                <div key={elasticType} className="flex items-center gap-2 bg-muted/50 px-3 py-1">
                  <span className="text-xs text-foreground/50">Elasticsearch type:</span>
                  <span className="font-mono text-xs font-medium">{elasticType}</span>
                </div>
                {types.map(([type, desc]) => (
                  <div key={type} className="flex items-start gap-3 px-3 py-2 pl-6">
                    <DynamicIcon type={type} className="mt-0.5 h-4 w-4 shrink-0 text-primary" />
                    <div>
                      <span className="font-mono font-medium">{type}</span>
                      <span className="ml-2 text-foreground/60">{desc}</span>
                    </div>
                  </div>
                ))}
              </>
            ))}
          </div>
        </section>

        <section>
          <h4 className="mb-2 flex items-center gap-2 font-semibold text-foreground">
            <Key className="h-4 w-4" /> Identifier fields
          </h4>
          <p>
            If a field is marked as an identifier, it is used to prevent duplicate documents — like a primary key in
            SQL. Use a naturally unique value (e.g. an article URL) if available. You can combine multiple identifier
            fields for a composite key (e.g. author + timestamp).
          </p>
          <p className="mt-2 text-primary">
            Identifier status cannot be changed after the field is created, and the values of identifier fields cannot
            be updated once a document has been indexed.
          </p>
        </section>
      </div>
    </InfoBox>
  );
}

function Fields({ project }: { project: AmcatProject }) {
  const { user } = useAmcatSession();
  const { data: fields, isLoading: loadingFields } = useFields(user, project.id);
  const { mutate } = useMutateFields(user, project.id);
  const { data: config } = useAmcatConfig();

  if (loadingFields) return <Loading />;

  const ownRole = config?.authorization === "no_auth" ? "ADMIN" : project?.user_role;
  if (!ownRole || !mutate) return <ErrorMsg type="Not Allowed">Need to be logged in</ErrorMsg>;
  if (ownRole !== "ADMIN" && ownRole !== "WRITER")
    return <ErrorMsg type="Not Allowed">Need to have the WRITER or ADMIN role to edit project fields</ErrorMsg>;

  return (
    <div className="flex flex-col gap-6 p-3">
      <FieldTable projectId={project.id} fields={fields || []} mutate={(action, fields) => mutate({ action, fields })} />
      <FieldsInfoBox />
    </div>
  );
}
