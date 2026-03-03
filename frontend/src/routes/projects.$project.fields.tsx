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
    <div className="p-3">
      <FieldTable fields={fields || []} mutate={(action, fields) => mutate({ action, fields })} />
    </div>
  );
}
