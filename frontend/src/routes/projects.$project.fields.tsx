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
import { fieldTypeDescriptions } from "@/components/Fields/FieldsHelpDialog";

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

function FieldsInfoBox() {
  return (
    <InfoBox title="Information on fields" storageKey="infobox:fields">
      <div className="flex flex-col gap-5 text-sm">
        <section>
          <h4 className="mb-2 font-semibold text-foreground">Field types</h4>
          <p className="mb-3">
            The table below lists the available field types. You can change a field's type at any time: existing values
            are converted to the new type, which fails if any value cannot be converted.
          </p>
          <div className="divide-y rounded border">
            {fieldTypeDescriptions.map(([type, desc]) => (
              <div key={type} className="flex items-start gap-3 px-3 py-2">
                <DynamicIcon type={type} className="mt-0.5 h-4 w-4 shrink-0 text-primary" />
                <div>
                  <span className="font-mono font-medium">{type}</span>
                  <span className="ml-2 text-foreground/60">{desc}</span>
                </div>
              </div>
            ))}
          </div>
        </section>

        <section>
          <h4 className="mb-2 flex items-center gap-2 font-semibold text-foreground">
            <Key className="h-4 w-4" /> Unique fields
          </h4>
          <p>
            If one or more fields are marked as unique, documents with the same values for all unique fields are
            considered the same document — like a primary key in SQL. This prevents duplicate documents, and allows
            updating existing documents. Use a naturally unique value (e.g. an article URL) if available. You can
            combine multiple unique fields for a composite key (e.g. author + timestamp). Tag, vector and object fields
            cannot be unique.
          </p>
        </section>

        <section>
          <h4 className="mb-2 font-semibold text-foreground">Access</h4>
          <p>
            For users with the READER role, you can set whether a field is visible, and whether it can be used in
            queries and filters (by default, the same as visible). For users with the METAREADER role, a field can be
            invisible, visible as a snippet (text fields only), or fully visible, and you can again set whether it can
            be used in queries and filters. Metareaders can never see or query more than readers. Writers and admins
            can always see and query all fields.
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

  const canEdit = ownRole === "ADMIN" || ownRole === "WRITER";

  return (
    <div className="flex flex-col gap-6 p-3">
      <FieldTable
        projectId={project.id}
        fields={fields || []}
        mutate={canEdit ? (action, fields) => mutate({ action, fields }) : undefined}
      />
      <FieldsInfoBox />
    </div>
  );
}
