import { createFileRoute } from "@tanstack/react-router";

export const Route = createFileRoute("/projects/$project/fields")({
  component: FieldsPage,
});

import { useAmcatConfig } from "@/api/config";
import { useFields, useMutateFields } from "@/api/fields";
import { useIndex } from "@/api/index";
import FieldTable from "@/components/Fields/FieldTable";
import { ErrorMsg } from "@/components/ui/error-message";
import { Loading } from "@/components/ui/loading";
import { AmcatIndex } from "@/interfaces";
import { useAmcatSession } from "@/components/Contexts/AuthProvider";

function FieldsPage() {
  const { project } = Route.useParams();
  const { user } = useAmcatSession();
  const indexId = decodeURI(project);
  const { data: index, isLoading: loadingIndex } = useIndex(user, indexId);

  if (loadingIndex) return <Loading />;
  if (!index) return <ErrorMsg type="Not Allowed">Need to be logged in</ErrorMsg>;

  return (
    <div className="flex w-full  flex-col gap-10">
      <Fields index={index} />
    </div>
  );
}

function Fields({ index }: { index: AmcatIndex }) {
  const { user } = useAmcatSession();
  const { data: fields, isLoading: loadingFields } = useFields(user, index.id);
  const { mutate } = useMutateFields(user, index.id);
  const { data: config } = useAmcatConfig();

  if (loadingFields) return <Loading />;

  const ownRole = config?.authorization === "no_auth" ? "ADMIN" : index?.user_role;
  if (!ownRole || !mutate) return <ErrorMsg type="Not Allowed">Need to be logged in</ErrorMsg>;
  if (ownRole !== "ADMIN" && ownRole !== "WRITER")
    return <ErrorMsg type="Not Allowed">Need to have the WRITER or ADMIN role to edit index fields</ErrorMsg>;

  return (
    <div className="p-3">
      <FieldTable fields={fields || []} mutate={(action, fields) => mutate({ action, fields })} />
    </div>
  );
}
